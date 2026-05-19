# FortiGate Policy Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Implementation status:** executed on `agent/fortigate-policy-orchestration-design`
on 2026-05-15. The shipped slice covers allowed FortiGate port-scan detection,
FortiGate CMDB policy helpers, governed policy review/apply persistence and
BFF endpoints, SOAR `fortigate.temporary_block`, the Lab Policy Wizard and the
ticket drawer review/apply flow. The task-level checkboxes below are retained
as the original execution checklist; product status now lives in
`docs/product/feature-map.md` and `docs/product/roadmap.md`.

**Goal:** Ship the first governed FortiGate firewall-policy orchestration slice: a lab allow+log wizard that creates real logged policies for detection demos, allowed-port-scan detection in `siem_kowalski`, and a ticket-linked SOAR approval path that turns an incident into a reviewed temporary FortiGate block.

**Architecture:** Keep `apps/api` as the only component that talks to FortiGate. Add a FortiGate policy orchestrator behind audited BFF endpoints, store policy change requests in Postgres, expose the workflow through the Vue cockpit, and let `siem_kowalski` detect real scan behavior from forwarded FortiGate traffic logs. SOAR remains the approval/workflow layer, but the final FortiGate write is executed by explicit cockpit action through `apps/api`.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Alembic, Pytest, httpx, Vue 3, Pinia, vue-i18n, Vitest, FortiOS CMDB API.

---

## Scope Boundaries

Implement this vertical slice only:

- Lab policy wizard for `allow + log` FortiGate policies.
- Temporary block policy review/apply flow linked to SIEM tickets and SOAR runs.
- Source-only, source-to-destination and source-to-destination-service block scopes.
- Allowed-port-scan detection from accepted FortiGate traffic logs.
- Removal of the visible `traffic-policy-draft` UX path.

Do not implement:

- Autonomous AI apply/approval.
- Customer-owned policy reordering.
- Permanent destructive response automation.
- FortiWeb/WAF integration.
- New external queue/search infrastructure.

## Implementation Notes

- Keep lab IPs, provider hostnames and API keys out of source and docs.
- Example IPs in test snippets use documentation-only ranges and must not be
  copied into live lab configuration.
- Every mutating endpoint must require CSRF/session auth and write an audit event.
- Every proposed FortiGate write must include preflight, review hash and redacted before/after summary.
- FortiGate writes are limited to owned objects/policies with `PG_` prefixes.
- Existing customer policies are read for placement decisions but are not modified silently.

---

## Task 1: Add SIEM Detection For Allowed Port Scans

- [ ] Add a failing test in `apps/siem_kowalski/tests/test_events_incidents.py` that proves accepted FortiGate traffic creates a `network.scan` incident without denied traffic.

Use the existing module-level `client` and `admin/reset` pattern:

```python
def test_allowed_fortigate_traffic_burst_creates_port_scan_incident() -> None:
    client.post("/admin/reset")

    for port in range(2200, 2221):
        payload = _event_payload(
            eventType="network.event",
            source="fortigate",
            severity="info",
            title=f"Allowed TCP connection to {port}",
            description="FortiGate accepted lab scan traffic",
            attributes={
                "integrationId": "integration-lab",
                "sourceIp": "192.0.2.50",
                "destinationIp": "198.51.100.10",
                "destinationPort": port,
                "service": f"tcp/{port}",
                "action": "accept",
                "policyId": "PG_LAB_ALLOW_SCAN",
                "subtype": "forward",
                "logid": f"000000{port}",
            },
        )
        response = client.post("/events", json=payload)
        assert response.status_code == 201

    incidents = client.get("/incidents").json()
    matching = [
        incident
        for incident in incidents
        if incident["ruleId"] == "network_scan"
        and incident["attributes"].get("sourceIp") == "192.0.2.50"
        and incident["attributes"].get("destinationIp") == "198.51.100.10"
    ]

    assert len(matching) == 1
    incident = matching[0]
    assert incident["severity"] == "high"
    assert incident["eventType"] == "network.scan"
    assert incident["attributes"]["uniqueDestinationPortCount"] == 21
    assert incident["attributes"]["scanWindowSeconds"] == 60
    assert 2200 in incident["attributes"]["destinationPorts"]
    assert 2220 in incident["attributes"]["destinationPorts"]
```

- [ ] Update `apps/siem_kowalski/app/store.py` to support bounded event reads for correlation.

Add a helper that reuses the in-memory/SQL store abstraction already used by `list_events`:

```python
def list_recent_events(
    *,
    event_type: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    events = list_events(limit=limit, event_type=event_type)
    return sorted(
        events,
        key=lambda event: event.get("occurredAt") or event.get("createdAt") or "",
        reverse=True,
    )
```

If `list_events` already returns newest-first in the active store implementation, keep the explicit sort to make the detector deterministic in tests.

- [ ] Update `apps/siem_kowalski/app/main.py` to enrich allowed scan traffic before normal detection.

Add the constants near the detection helpers:

```python
ALLOWED_SCAN_WINDOW_SECONDS = 60
ALLOWED_SCAN_MIN_UNIQUE_PORTS = 20
ALLOWED_SCAN_EVENT_LIMIT = 250
```

Add the helper call inside `_ingest_event()` immediately after `_enrich_failed_login_burst(stored_event)`:

```python
    _enrich_failed_login_burst(stored_event)
    _enrich_allowed_port_scan(stored_event)
```

Implement the helper:

```python
def _enrich_allowed_port_scan(event: dict[str, Any]) -> None:
    if event.get("eventType") != "network.event":
        return

    attributes = event.get("attributes") or {}
    if str(attributes.get("action", "")).lower() not in {"accept", "allowed", "allow"}:
        return

    integration_id = attributes.get("integrationId")
    source_ip = attributes.get("sourceIp")
    destination_ip = attributes.get("destinationIp")
    destination_port = _coerce_int(attributes.get("destinationPort"))
    if not integration_id or not source_ip or not destination_ip or destination_port is None:
        return

    occurred_at = _parse_datetime(event.get("occurredAt"))
    if occurred_at is None:
        occurred_at = datetime.now(timezone.utc)
    window_start = occurred_at - timedelta(seconds=ALLOWED_SCAN_WINDOW_SECONDS)

    ports: set[int] = {destination_port}
    related_event_ids: list[str] = [event["id"]]
    for candidate in store.list_recent_events(
        event_type="network.event",
        limit=ALLOWED_SCAN_EVENT_LIMIT,
    ):
        if candidate["id"] == event["id"]:
            continue
        candidate_attributes = candidate.get("attributes") or {}
        if candidate_attributes.get("integrationId") != integration_id:
            continue
        if candidate_attributes.get("sourceIp") != source_ip:
            continue
        if candidate_attributes.get("destinationIp") != destination_ip:
            continue
        if str(candidate_attributes.get("action", "")).lower() not in {"accept", "allowed", "allow"}:
            continue

        candidate_time = _parse_datetime(candidate.get("occurredAt"))
        if candidate_time is None or candidate_time < window_start or candidate_time > occurred_at:
            continue

        port = _coerce_int(candidate_attributes.get("destinationPort"))
        if port is not None:
            ports.add(port)
            related_event_ids.append(candidate["id"])

    if len(ports) < ALLOWED_SCAN_MIN_UNIQUE_PORTS:
        return

    event["eventType"] = "network.scan"
    event["severity"] = "high"
    event["title"] = "Possible port scan"
    event["description"] = (
        f"{source_ip} reached {len(ports)} destination ports on {destination_ip} "
        f"within {ALLOWED_SCAN_WINDOW_SECONDS}s through FortiGate allowed traffic."
    )
    event["attributes"] = {
        **attributes,
        "attackType": "allowed_port_scan",
        "destinationPorts": sorted(ports),
        "uniqueDestinationPortCount": len(ports),
        "scanWindowSeconds": ALLOWED_SCAN_WINDOW_SECONDS,
        "relatedEventIds": related_event_ids,
    }
```

Add helpers if they do not already exist:

```python
def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
```

- [ ] Extend `_incident_attributes()` in `apps/siem_kowalski/app/main.py` so the incident preserves these keys:

```python
for key in (
    "demoRunId",
    "attackType",
    "count",
    "users",
    "attempts",
    "message",
    "action",
    "subtype",
    "integrationId",
    "sourceIp",
    "destinationIp",
    "destinationPort",
    "destinationPorts",
    "uniqueDestinationPortCount",
    "scanWindowSeconds",
    "policyId",
    "service",
    "relatedEventIds",
):
    if key in attributes:
        incident_attributes[key] = attributes[key]
```

- [ ] Run and commit:

```bash
cd apps/siem_kowalski && uv run pytest -q tests/test_events_incidents.py
git add apps/siem_kowalski/app/main.py apps/siem_kowalski/app/store.py apps/siem_kowalski/tests/test_events_incidents.py
git commit -m "feat(siem): detect allowed FortiGate port scans"
```

---

## Task 2: Add FortiGate Policy CMDB Client Helpers

- [ ] Add failing tests in `apps/api/tests/test_fortigate_client.py` for address object creation and firewall policy creation.

Use `httpx.MockTransport` and assert exact FortiOS endpoints:

```python
@pytest.mark.asyncio
async def test_fortigate_client_creates_owned_address_object() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST" and request.url.path == "/api/v2/cmdb/firewall/address":
            body = json.loads(request.content.decode())
            assert body == {
                "name": "PG_ADDR_192_0_2_50",
                "subnet": "192.0.2.50 255.255.255.255",
                "comment": "Penguard owned temporary block object",
            }
            return httpx.Response(200, json={"status": "success", "mkey": "PG_ADDR_192_0_2_50"})
        return httpx.Response(404, json={"status": "error"})

    client = FortiGateApiClient(
        base_url="https://fortigate.local",
        api_key="secret",
        transport=httpx.MockTransport(handler),
    )

    result = await client.create_address_object(
        name="PG_ADDR_192_0_2_50",
        subnet="192.0.2.50 255.255.255.255",
        comment="Penguard owned temporary block object",
    )

    assert result["status"] == "success"
    assert requests[0].headers["Authorization"] == "Bearer secret"
```

```python
@pytest.mark.asyncio
async def test_fortigate_client_creates_firewall_policy() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/v2/cmdb/firewall/policy":
            body = json.loads(request.content.decode())
            assert body["name"] == "PG_TMP_BLOCK_192_0_2_50"
            assert body["action"] == "deny"
            assert body["logtraffic"] == "all"
            assert body["srcaddr"] == [{"name": "PG_ADDR_192_0_2_50"}]
            return httpx.Response(200, json={"status": "success", "mkey": 42})
        return httpx.Response(404, json={"status": "error"})

    client = FortiGateApiClient(
        base_url="https://fortigate.local",
        api_key="secret",
        transport=httpx.MockTransport(handler),
    )

    result = await client.create_firewall_policy(
        {
            "name": "PG_TMP_BLOCK_192_0_2_50",
            "action": "deny",
            "logtraffic": "all",
            "srcaddr": [{"name": "PG_ADDR_192_0_2_50"}],
            "dstaddr": [{"name": "all"}],
            "service": [{"name": "ALL"}],
            "schedule": "always",
            "srcintf": [{"name": "port2"}],
            "dstintf": [{"name": "port3"}],
            "status": "enable",
            "comments": "Penguard owned temporary block",
        }
    )

    assert result["mkey"] == 42
```

- [ ] Update `apps/api/app/integrations/fortigate/client.py`.

Add these methods to `FortiGateApiClient`:

```python
    async def get_address_objects(self) -> list[dict[str, Any]]:
        return await self._get("/api/v2/cmdb/firewall/address")

    async def create_address_object(
        self,
        *,
        name: str,
        subnet: str,
        comment: str,
    ) -> dict[str, Any]:
        return await self._post(
            "/api/v2/cmdb/firewall/address",
            {
                "name": name,
                "subnet": subnet,
                "comment": comment,
            },
        )

    async def create_firewall_policy(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return await self._post("/api/v2/cmdb/firewall/policy", dict(payload))
```

Add `_post` next to `_put`:

```python
    async def _post(self, path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            verify=self.verify_tls,
            timeout=self.timeout_seconds,
            transport=self.transport,
        ) as client:
            response = await client.post(path, headers=self._headers(), json=dict(payload))
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict):
            return data
        return {"result": data}
```

- [ ] Extend the `FortiGateClient` protocol in `apps/api/app/integrations/fortigate/service.py` with the same methods.

```python
    async def get_address_objects(self) -> list[dict[str, Any]]: ...

    async def create_address_object(
        self,
        *,
        name: str,
        subnet: str,
        comment: str,
    ) -> dict[str, Any]: ...

    async def create_firewall_policy(self, payload: Mapping[str, Any]) -> dict[str, Any]: ...
```

- [ ] Add mock implementations to `MockFortiGateIntegrationService` so API tests can exercise policy orchestration without live FortiGate.

```python
    async def get_address_objects(self) -> list[dict[str, Any]]:
        return []

    async def create_address_object(
        self,
        *,
        name: str,
        subnet: str,
        comment: str,
    ) -> dict[str, Any]:
        return {"status": "success", "mkey": name, "subnet": subnet, "comment": comment}

    async def create_firewall_policy(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return {"status": "success", "mkey": payload.get("name"), "payload": dict(payload)}
```

- [ ] Rename or replace the old read-only-write-boundary test in `apps/api/tests/test_fortigate_client.py`.

Use the new expectation: first-cut telemetry still uses read-only GETs, while policy orchestration writes are isolated to explicit policy methods.

- [ ] Run and commit:

```bash
cd apps/api && uv run pytest -q tests/test_fortigate_client.py
git add apps/api/app/integrations/fortigate/client.py apps/api/app/integrations/fortigate/service.py apps/api/tests/test_fortigate_client.py
git commit -m "feat(fortigate): add policy cmdb client helpers"
```

---

## Task 3: Create Policy Models And Orchestrator

- [ ] Add `apps/api/app/integrations/fortigate/policy_models.py`.

Define strict request/response contracts:

```python
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class FortiGatePolicyIntent(StrEnum):
    LAB_ALLOW_LOG = "lab_allow_log"
    TEMPORARY_BLOCK = "temporary_block"


class FortiGatePolicyScope(StrEnum):
    SOURCE_ONLY = "source_only"
    SOURCE_DESTINATION = "source_destination"
    SOURCE_DESTINATION_SERVICE = "source_destination_service"


class FortiGatePolicyAction(StrEnum):
    ACCEPT = "accept"
    DENY = "deny"


class FortiGatePolicyPreflightRequest(BaseModel):
    intent: FortiGatePolicyIntent
    scope: FortiGatePolicyScope
    source_interface: str = Field(min_length=1, max_length=64)
    destination_interface: str = Field(min_length=1, max_length=64)
    source_ip: str = Field(min_length=3, max_length=64)
    destination_ip: str | None = Field(default=None, min_length=3, max_length=64)
    service: str | None = Field(default=None, min_length=1, max_length=64)
    duration_minutes: int | None = Field(default=None, ge=5, le=1440)
    incident_id: str | None = None
    playbook_run_id: str | None = None

    @field_validator("destination_ip")
    @classmethod
    def destination_required_for_destination_scope(cls, value: str | None, info: Any) -> str | None:
        scope = info.data.get("scope")
        if scope in {
            FortiGatePolicyScope.SOURCE_DESTINATION,
            FortiGatePolicyScope.SOURCE_DESTINATION_SERVICE,
        } and not value:
            raise ValueError("destination_ip is required for this scope")
        return value

    @field_validator("service")
    @classmethod
    def service_required_for_service_scope(cls, value: str | None, info: Any) -> str | None:
        if info.data.get("scope") == FortiGatePolicyScope.SOURCE_DESTINATION_SERVICE and not value:
            raise ValueError("service is required for source_destination_service scope")
        return value
```

```python
class FortiGatePolicyObjectChange(BaseModel):
    operation: Literal["create", "reuse"]
    object_type: Literal["firewall.address", "firewall.policy"]
    name: str
    payload: dict[str, Any]


class FortiGatePolicyPreflightResponse(BaseModel):
    intent: FortiGatePolicyIntent
    scope: FortiGatePolicyScope
    integration_id: str
    existing_policy_count: int
    owned_policy_count: int
    proposed_policy_name: str
    placement: str
    warnings: list[str]
    changes: list[FortiGatePolicyObjectChange]
    review_hash: str
```

```python
class FortiGatePolicyReviewRequest(FortiGatePolicyPreflightRequest):
    pass


class FortiGatePolicyReviewResponse(FortiGatePolicyPreflightResponse):
    request_id: str
    status: Literal["pending_review"]
    expires_at: datetime | None = None


class FortiGatePolicyApplyRequest(BaseModel):
    request_id: str
    review_hash: str


class FortiGatePolicyApplyResponse(BaseModel):
    request_id: str
    status: Literal["applied"]
    applied_changes: list[dict[str, Any]]
```

- [ ] Add `apps/api/app/integrations/fortigate/policy_orchestrator.py`.

Implement pure planning helpers and keep FortiGate writes in one method:

```python
from __future__ import annotations

import hashlib
import ipaddress
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from .policy_models import (
    FortiGatePolicyAction,
    FortiGatePolicyIntent,
    FortiGatePolicyObjectChange,
    FortiGatePolicyPreflightRequest,
    FortiGatePolicyPreflightResponse,
    FortiGatePolicyScope,
)


PG_LAB_PREFIX = "PG_LAB_ALLOW"
PG_TMP_BLOCK_PREFIX = "PG_TMP_BLOCK"
PG_ADDR_PREFIX = "PG_ADDR"


def normalize_address_name(ip_value: str) -> str:
    address = ipaddress.ip_address(ip_value)
    return f"{PG_ADDR_PREFIX}_{str(address).replace('.', '_').replace(':', '_')}"


def host_subnet(ip_value: str) -> str:
    address = ipaddress.ip_address(ip_value)
    if address.version == 4:
        return f"{address} 255.255.255.255"
    return f"{address}/128"
```

Add the orchestrator class:

```python
class FortiGatePolicyOrchestrator:
    def __init__(self, client: Any, *, integration_id: str) -> None:
        self.client = client
        self.integration_id = integration_id

    async def preflight(self, request: FortiGatePolicyPreflightRequest) -> FortiGatePolicyPreflightResponse:
        policies = await self.client.get_policies()
        address_objects = await self.client.get_address_objects()
        changes = self._build_changes(request, policies, address_objects)
        policy_name = self._policy_name(request)
        warnings = self._warnings(request, policies)
        payload = {
            "intent": request.intent.value,
            "scope": request.scope.value,
            "integrationId": self.integration_id,
            "changes": [change.model_dump(mode="json") for change in changes],
            "placement": self._placement(request, policies),
            "warnings": warnings,
        }
        return FortiGatePolicyPreflightResponse(
            intent=request.intent,
            scope=request.scope,
            integration_id=self.integration_id,
            existing_policy_count=len(policies),
            owned_policy_count=sum(1 for policy in policies if str(policy.get("name", "")).startswith("PG_")),
            proposed_policy_name=policy_name,
            placement=self._placement(request, policies),
            warnings=warnings,
            changes=changes,
            review_hash=hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        )

    async def apply_changes(self, changes: list[FortiGatePolicyObjectChange]) -> list[dict[str, Any]]:
        applied: list[dict[str, Any]] = []
        for change in changes:
            if change.operation == "reuse":
                applied.append({"operation": "reuse", "objectType": change.object_type, "name": change.name})
                continue
            if change.object_type == "firewall.address":
                result = await self.client.create_address_object(
                    name=change.payload["name"],
                    subnet=change.payload["subnet"],
                    comment=change.payload["comment"],
                )
            elif change.object_type == "firewall.policy":
                result = await self.client.create_firewall_policy(change.payload)
            else:
                raise ValueError(f"Unsupported FortiGate object type: {change.object_type}")
            applied.append(
                {
                    "operation": change.operation,
                    "objectType": change.object_type,
                    "name": change.name,
                    "result": result,
                }
            )
        return applied
```

Implement `_build_changes`, `_policy_name`, `_placement` and `_warnings` with deterministic behavior:

```python
    def _build_changes(
        self,
        request: FortiGatePolicyPreflightRequest,
        policies: list[dict[str, Any]],
        address_objects: list[dict[str, Any]],
    ) -> list[FortiGatePolicyObjectChange]:
        existing_addresses = {str(item.get("name")) for item in address_objects}
        source_name = normalize_address_name(request.source_ip)
        changes: list[FortiGatePolicyObjectChange] = []
        if source_name in existing_addresses:
            changes.append(self._reuse_address(source_name, request.source_ip))
        else:
            changes.append(self._create_address(source_name, request.source_ip))

        destination_name: str | None = None
        if request.destination_ip:
            destination_name = normalize_address_name(request.destination_ip)
            if destination_name in existing_addresses:
                changes.append(self._reuse_address(destination_name, request.destination_ip))
            else:
                changes.append(self._create_address(destination_name, request.destination_ip))

        changes.append(
            FortiGatePolicyObjectChange(
                operation="create",
                object_type="firewall.policy",
                name=self._policy_name(request),
                payload=self._policy_payload(request, source_name, destination_name),
            )
        )
        return changes
```

Policy payload rules:

```python
    def _policy_payload(
        self,
        request: FortiGatePolicyPreflightRequest,
        source_name: str,
        destination_name: str | None,
    ) -> dict[str, Any]:
        action = (
            FortiGatePolicyAction.ACCEPT
            if request.intent == FortiGatePolicyIntent.LAB_ALLOW_LOG
            else FortiGatePolicyAction.DENY
        )
        service_name = request.service or "ALL"
        return {
            "name": self._policy_name(request),
            "srcintf": [{"name": request.source_interface}],
            "dstintf": [{"name": request.destination_interface}],
            "srcaddr": [{"name": source_name}],
            "dstaddr": [{"name": destination_name or "all"}],
            "action": action.value,
            "schedule": "always",
            "service": [{"name": service_name}],
            "logtraffic": "all",
            "status": "enable",
            "comments": self._comment(request),
        }
```

Temporary block expiration is stored in the request table, not pushed into FortiGate until an explicit cleanup feature exists.

- [ ] Add unit tests for naming, review hash stability and payload generation in `apps/api/tests/test_fortigate_policy_orchestrator.py`.

Required assertions:

- `lab_allow_log` policy names start with `PG_LAB_ALLOW_`.
- `temporary_block` policy names start with `PG_TMP_BLOCK_`.
- IPv4 source `192.0.2.50` maps to address object `PG_ADDR_192_0_2_50`.
- `source_only` block uses destination address `all` and service `ALL`.
- `source_destination_service` block uses both destination object and configured service.
- Same preflight input produces the same `review_hash`.

- [ ] Run and commit:

```bash
cd apps/api && uv run pytest -q tests/test_fortigate_policy_orchestrator.py tests/test_fortigate_client.py
git add apps/api/app/integrations/fortigate/policy_models.py apps/api/app/integrations/fortigate/policy_orchestrator.py apps/api/tests/test_fortigate_policy_orchestrator.py
git commit -m "feat(fortigate): plan governed policy changes"
```

---

## Task 4: Persist Policy Change Requests

- [ ] Add `FortiGatePolicyChangeRequestModel` to `apps/api/app/db/models.py`.

```python
class FortiGatePolicyChangeRequestModel(Base):
    __tablename__ = "fortigate_policy_change_requests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    integration_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    incident_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    playbook_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_review")
    intent_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    preflight_summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    proposed_changes_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    review_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    applied_result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
```

Ensure `Any`, `JSON`, `DateTime` and `func` imports already exist or add them once.

- [ ] Add migration `apps/api/migrations/versions/20260515_0012_fortigate_policy_change_requests.py`.

Because the current migration directory has two active 0011 revisions, use a merge-style `down_revision`:

```python
"""create fortigate policy change requests

Revision ID: 20260515_0012
Revises: 20260514_0011, 20260515_0011
Create Date: 2026-05-15
"""

from alembic import op
import sqlalchemy as sa


revision = "20260515_0012"
down_revision = ("20260514_0011", "20260515_0011")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fortigate_policy_change_requests",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("owner_user_id", sa.String(length=255), nullable=False),
        sa.Column("integration_id", sa.String(length=64), nullable=False),
        sa.Column("incident_id", sa.String(length=64), nullable=True),
        sa.Column("playbook_run_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending_review"),
        sa.Column("intent_json", sa.JSON(), nullable=False),
        sa.Column("preflight_summary_json", sa.JSON(), nullable=False),
        sa.Column("proposed_changes_json", sa.JSON(), nullable=False),
        sa.Column("review_hash", sa.String(length=128), nullable=False),
        sa.Column("applied_result_json", sa.JSON(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_fortigate_policy_change_requests_owner_user_id",
        "fortigate_policy_change_requests",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_fortigate_policy_change_requests_integration_id",
        "fortigate_policy_change_requests",
        ["integration_id"],
    )
    op.create_index(
        "ix_fortigate_policy_change_requests_incident_id",
        "fortigate_policy_change_requests",
        ["incident_id"],
    )
    op.create_index(
        "ix_fortigate_policy_change_requests_playbook_run_id",
        "fortigate_policy_change_requests",
        ["playbook_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_fortigate_policy_change_requests_playbook_run_id", table_name="fortigate_policy_change_requests")
    op.drop_index("ix_fortigate_policy_change_requests_incident_id", table_name="fortigate_policy_change_requests")
    op.drop_index("ix_fortigate_policy_change_requests_integration_id", table_name="fortigate_policy_change_requests")
    op.drop_index("ix_fortigate_policy_change_requests_owner_user_id", table_name="fortigate_policy_change_requests")
    op.drop_table("fortigate_policy_change_requests")
```

- [ ] Add a small repository helper module `apps/api/app/integrations/fortigate/policy_requests.py`.

Functions:

```python
def create_policy_request(
    db: Session,
    *,
    owner_user_id: str,
    integration_id: str,
    request: FortiGatePolicyReviewRequest,
    preflight: FortiGatePolicyReviewResponse | FortiGatePolicyPreflightResponse,
    expires_at: datetime | None,
) -> FortiGatePolicyChangeRequestModel:
    record = FortiGatePolicyChangeRequestModel(
        id=f"fgpcr_{secrets.token_urlsafe(18)}",
        owner_user_id=owner_user_id,
        integration_id=integration_id,
        incident_id=request.incident_id,
        playbook_run_id=request.playbook_run_id,
        status="pending_review",
        intent_json=request.model_dump(mode="json"),
        preflight_summary_json=preflight.model_dump(mode="json", exclude={"changes"}),
        proposed_changes_json=[change.model_dump(mode="json") for change in preflight.changes],
        review_hash=preflight.review_hash,
        expires_at=expires_at,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
```

```python
def get_policy_request_for_user(
    db: Session,
    *,
    owner_user_id: str,
    request_id: str,
) -> FortiGatePolicyChangeRequestModel:
    record = db.get(FortiGatePolicyChangeRequestModel, request_id)
    if record is None or record.owner_user_id != owner_user_id:
        raise HTTPException(status_code=404, detail="Policy request not found")
    return record
```

```python
def mark_policy_request_applied(
    db: Session,
    *,
    record: FortiGatePolicyChangeRequestModel,
    result: dict[str, Any],
) -> FortiGatePolicyChangeRequestModel:
    record.status = "applied"
    record.applied_result_json = result
    db.commit()
    db.refresh(record)
    return record
```

- [ ] Add tests in `apps/api/tests/test_fortigate_policy_requests.py` that insert, fetch and mark applied using the test DB session fixture already used by integration tests.

- [ ] Run and commit:

```bash
cd apps/api && uv run pytest -q tests/test_fortigate_policy_requests.py
cd apps/api && uv run alembic upgrade head
git add apps/api/app/db/models.py apps/api/app/integrations/fortigate/policy_requests.py apps/api/migrations/versions/20260515_0012_fortigate_policy_change_requests.py apps/api/tests/test_fortigate_policy_requests.py
git commit -m "feat(fortigate): persist policy change reviews"
```

---

## Task 5: Add BFF Endpoints For FortiGate Policy Review And Apply

- [ ] Replace the old test for `traffic-policy-draft` in `apps/api/tests/test_fortigate_integrations.py`.

Add tests for:

- `POST /api/integrations/fortigate/{integrationId}/policy/preflight` returns changes and does not call write methods.
- `POST /api/integrations/fortigate/{integrationId}/policy/review` persists a pending review.
- `POST /api/integrations/fortigate/{integrationId}/policy/apply` rejects mismatched `review_hash`.
- `POST /api/integrations/fortigate/{integrationId}/policy/apply` creates address objects/policy and writes audit events.

Use a fake FortiGate client with counters:

```python
class PolicyFakeFortiGateClient:
    def __init__(self) -> None:
        self.created_addresses: list[dict[str, Any]] = []
        self.created_policies: list[dict[str, Any]] = []

    async def get_policies(self) -> list[dict[str, Any]]:
        return [{"name": "PG_LAB_ALLOW_SCAN", "policyid": 10}]

    async def get_address_objects(self) -> list[dict[str, Any]]:
        return []

    async def create_address_object(self, *, name: str, subnet: str, comment: str) -> dict[str, Any]:
        self.created_addresses.append({"name": name, "subnet": subnet, "comment": comment})
        return {"status": "success", "mkey": name}

    async def create_firewall_policy(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        self.created_policies.append(dict(payload))
        return {"status": "success", "mkey": payload["name"]}
```

- [ ] Update `apps/api/app/routers/integrations.py`.

Remove the visible `traffic-policy-draft` route, or keep it as a deprecated `410 Gone` compatibility route:

```python
@router.post("/integrations/fortigate/{integration_id}/traffic-policy-draft", status_code=status.HTTP_410_GONE)
async def draft_fortigate_traffic_policy_deprecated(...) -> dict[str, str]:
    return {
        "detail": "Traffic policy drafts were replaced by governed FortiGate policy review endpoints.",
    }
```

Add imports:

```python
from app.integrations.fortigate.policy_models import (
    FortiGatePolicyApplyRequest,
    FortiGatePolicyApplyResponse,
    FortiGatePolicyPreflightRequest,
    FortiGatePolicyPreflightResponse,
    FortiGatePolicyReviewRequest,
    FortiGatePolicyReviewResponse,
)
from app.integrations.fortigate.policy_orchestrator import FortiGatePolicyOrchestrator
from app.integrations.fortigate.policy_requests import (
    create_policy_request,
    get_policy_request_for_user,
    mark_policy_request_applied,
)
```

Add an internal client loader:

```python
async def _get_policy_orchestrator(
    *,
    integration_id: str,
    current_user: ApiUser,
    service: FortiGateIntegrationService,
) -> FortiGatePolicyOrchestrator:
    integration = await service.get_integration_for_user(
        user_id=current_user.id,
        integration_id=integration_id,
    )
    if integration is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    client = await service.build_client_for_integration(integration)
    return FortiGatePolicyOrchestrator(client, integration_id=integration_id)
```

If `build_client_for_integration` is not available, add it to `FortiGateIntegrationService` using the existing decrypted credential path used by widget fetches.

Add endpoints:

```python
@router.post(
    "/integrations/fortigate/{integration_id}/policy/preflight",
    response_model=FortiGatePolicyPreflightResponse,
)
async def preflight_fortigate_policy(
    integration_id: str,
    payload: FortiGatePolicyPreflightRequest,
    current_user: ApiUser = Depends(get_current_api_user),
    service: FortiGateIntegrationService = Depends(get_fortigate_integration_service),
) -> FortiGatePolicyPreflightResponse:
    orchestrator = await _get_policy_orchestrator(
        integration_id=integration_id,
        current_user=current_user,
        service=service,
    )
    preflight = await orchestrator.preflight(payload)
    await audit_event(
        actor_user_id=current_user.id,
        action="fortigate.policy.preflight",
        resource_type="fortigate.integration",
        resource_id=integration_id,
        metadata={"intent": payload.intent.value, "scope": payload.scope.value},
    )
    return preflight
```

```python
@router.post(
    "/integrations/fortigate/{integration_id}/policy/review",
    response_model=FortiGatePolicyReviewResponse,
)
async def review_fortigate_policy(
    integration_id: str,
    payload: FortiGatePolicyReviewRequest,
    db: Session = Depends(get_db),
    current_user: ApiUser = Depends(get_current_api_user),
    service: FortiGateIntegrationService = Depends(get_fortigate_integration_service),
) -> FortiGatePolicyReviewResponse:
    orchestrator = await _get_policy_orchestrator(
        integration_id=integration_id,
        current_user=current_user,
        service=service,
    )
    preflight = await orchestrator.preflight(payload)
    expires_at = None
    if payload.duration_minutes:
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=payload.duration_minutes)
    record = create_policy_request(
        db,
        owner_user_id=current_user.id,
        integration_id=integration_id,
        request=payload,
        preflight=preflight,
        expires_at=expires_at,
    )
    await audit_event(
        actor_user_id=current_user.id,
        action="fortigate.policy.review_created",
        resource_type="fortigate.policy_change_request",
        resource_id=record.id,
        metadata={"integrationId": integration_id, "reviewHash": preflight.review_hash},
    )
    return FortiGatePolicyReviewResponse(
        **preflight.model_dump(mode="json"),
        request_id=record.id,
        status="pending_review",
        expires_at=expires_at,
    )
```

```python
@router.post(
    "/integrations/fortigate/{integration_id}/policy/apply",
    response_model=FortiGatePolicyApplyResponse,
)
async def apply_fortigate_policy(
    integration_id: str,
    payload: FortiGatePolicyApplyRequest,
    db: Session = Depends(get_db),
    current_user: ApiUser = Depends(get_current_api_user),
    service: FortiGateIntegrationService = Depends(get_fortigate_integration_service),
) -> FortiGatePolicyApplyResponse:
    record = get_policy_request_for_user(
        db,
        owner_user_id=current_user.id,
        request_id=payload.request_id,
    )
    if record.integration_id != integration_id:
        raise HTTPException(status_code=404, detail="Policy request not found")
    if record.status != "pending_review":
        raise HTTPException(status_code=409, detail="Policy request is not pending review")
    if record.review_hash != payload.review_hash:
        raise HTTPException(status_code=409, detail="Policy review hash mismatch")

    orchestrator = await _get_policy_orchestrator(
        integration_id=integration_id,
        current_user=current_user,
        service=service,
    )
    changes = [
        FortiGatePolicyObjectChange.model_validate(change)
        for change in record.proposed_changes_json
    ]
    applied_changes = await orchestrator.apply_changes(changes)
    mark_policy_request_applied(
        db,
        record=record,
        result={"appliedChanges": applied_changes},
    )
    await audit_event(
        actor_user_id=current_user.id,
        action="fortigate.policy.applied",
        resource_type="fortigate.policy_change_request",
        resource_id=record.id,
        metadata={"integrationId": integration_id, "changeCount": len(applied_changes)},
    )
    return FortiGatePolicyApplyResponse(
        request_id=record.id,
        status="applied",
        applied_changes=applied_changes,
    )
```

- [ ] Ensure the route uses the repository's actual audit helper signature. If `audit_event` is sync or DB-backed in this router, adapt the call shape without changing event names.

- [ ] Run and commit:

```bash
cd apps/api && uv run pytest -q tests/test_fortigate_integrations.py
git add apps/api/app/routers/integrations.py apps/api/tests/test_fortigate_integrations.py
git commit -m "feat(api): expose FortiGate policy review endpoints"
```

---

## Task 6: Add SOAR Temporary Block Node And API Link

- [ ] Update `packages/soc-catalog/playbook-node-types.json`.

Add the new node:

```json
{
  "id": "fortigate.temporary_block",
  "label": "FortiGate temporary block",
  "category": "response",
  "executionMode": "approval_required",
  "liveAvailable": true,
  "boundary": "fortigate_policy_orchestration",
  "sensitive": true,
  "configSchema": {
    "type": "object",
    "required": ["scope", "durationMinutes", "sourceField"],
    "properties": {
      "scope": {
        "type": "string",
        "enum": ["source_only", "source_destination", "source_destination_service"]
      },
      "durationMinutes": {
        "type": "integer",
        "minimum": 5,
        "maximum": 1440
      },
      "sourceField": { "type": "string" },
      "destinationField": { "type": "string" },
      "serviceField": { "type": "string" }
    }
  }
}
```

- [ ] Update `apps/soar_skipper/app/main.py`.

Replace or supplement `fortigate.recommend_block` with:

```python
{
    "type": "fortigate.temporary_block",
    "label": "FortiGate temporary block",
    "category": "response",
    "executionMode": "approval_required",
    "liveAvailable": True,
    "boundary": "fortigate_policy_orchestration",
    "sensitive": True,
    "configSchema": {
        "type": "object",
        "required": ["scope", "durationMinutes", "sourceField"],
        "properties": {
            "scope": {
                "type": "string",
                "enum": ["source_only", "source_destination", "source_destination_service"],
            },
            "durationMinutes": {"type": "integer", "minimum": 5, "maximum": 1440},
            "sourceField": {"type": "string"},
            "destinationField": {"type": "string"},
            "serviceField": {"type": "string"},
        },
    },
}
```

Keep `fortigate.recommend_block` only if existing fixtures require backward compatibility. Mark it `deprecated: true` and keep `liveAvailable: false`.

- [ ] Add/adjust tests in `apps/soar_skipper/tests/` to assert the node catalog exposes `fortigate.temporary_block` with `executionMode == "approval_required"` and `liveAvailable is True`.

- [ ] Update `apps/api/app/routers/soc.py`.

Change `_map_ai_step_to_soar_node` so firewall block intents map to the new node:

```python
if normalized in {
    "firewall.block_ip",
    "fortigate.block_ip",
    "fortigate.temporary_block",
    "fortigate.recommend_block",
}:
    return {
        "type": "fortigate.temporary_block",
        "label": step.get("label") or "Prepare FortiGate temporary block",
        "config": {
            "scope": step.get("scope") or "source_only",
            "durationMinutes": int(step.get("durationMinutes") or 30),
            "sourceField": step.get("sourceField") or "attributes.sourceIp",
            "destinationField": step.get("destinationField") or "attributes.destinationIp",
            "serviceField": step.get("serviceField") or "attributes.service",
        },
        "requiresApproval": True,
    }
```

- [ ] Add tests in `apps/api/tests/test_soc_gateway.py` or the existing SOC router test file for AI containment mapping.

Expected result:

- Drafted playbook contains `fortigate.temporary_block`.
- Applying containment creates a SOAR run in `waiting_approval`.
- Approving the run does not directly write FortiGate; it returns enough metadata for the ticket UI to create a policy review.

- [ ] Run and commit:

```bash
cd apps/soar_skipper && uv run pytest -q
cd apps/api && uv run pytest -q tests/test_soc_gateway.py
git add packages/soc-catalog/playbook-node-types.json apps/soar_skipper/app/main.py apps/soar_skipper/tests apps/api/app/routers/soc.py apps/api/tests/test_soc_gateway.py
git commit -m "feat(soar): add FortiGate temporary block node"
```

---

## Task 7: Add Ticket-To-Policy Review Gateway Endpoints

- [ ] Add tests in the SOC router test file for:

- `POST /api/soc/playbook-runs/{runId}/policy-review` creates a FortiGate policy change request from a waiting approved SOAR run.
- `POST /api/soc/playbook-runs/{runId}/policy-apply` applies the saved request and patches the linked SIEM ticket to `contained`.
- Missing FortiGate integration returns `409` with an actionable error.
- Non-`fortigate.temporary_block` runs return `409`.

Use existing fake SIEM/SOAR clients from SOC gateway tests and a fake integrations service.

- [ ] Add request/response models in `apps/api/app/routers/soc.py` or a router-local schema module.

```python
class PlaybookRunPolicyReviewRequest(BaseModel):
    integrationId: str
    scope: Literal["source_only", "source_destination", "source_destination_service"]
    sourceIp: str
    destinationIp: str | None = None
    service: str | None = None
    sourceInterface: str
    destinationInterface: str
    durationMinutes: int = Field(default=30, ge=5, le=1440)


class PlaybookRunPolicyApplyRequest(BaseModel):
    integrationId: str
    requestId: str
    reviewHash: str
```

- [ ] Add `POST /api/soc/playbook-runs/{run_id}/policy-review`.

Behavior:

1. Load SOAR run by `run_id`.
2. Confirm run belongs to current user context according to existing SOC gateway rules.
3. Confirm the run has a `fortigate.temporary_block` waiting or approved step.
4. Convert request to `FortiGatePolicyReviewRequest(intent="temporary_block")`.
5. Call the same FortiGate orchestrator/persistence path as the integrations router.
6. Audit `soc.playbook.policy_review_created`.
7. Return the policy review response plus `runId` and `incidentId`.

- [ ] Add `POST /api/soc/playbook-runs/{run_id}/policy-apply`.

Behavior:

1. Apply the saved policy request through the same FortiGate apply path.
2. Patch the linked SIEM ticket to `contained`.
3. Audit `soc.playbook.policy_applied`.
4. Return apply result and ticket patch result.

- [ ] Avoid duplicating apply logic between routers.

Extract shared functions into `apps/api/app/integrations/fortigate/policy_workflow.py`:

```python
async def create_policy_review_for_user(...) -> FortiGatePolicyReviewResponse:
    ...


async def apply_policy_review_for_user(...) -> FortiGatePolicyApplyResponse:
    ...
```

Then have both `apps/api/app/routers/integrations.py` and `apps/api/app/routers/soc.py` call these helpers.

- [ ] Run and commit:

```bash
cd apps/api && uv run pytest -q tests/test_soc_gateway.py tests/test_fortigate_integrations.py
git add apps/api/app/routers/soc.py apps/api/app/routers/integrations.py apps/api/app/integrations/fortigate/policy_workflow.py apps/api/tests/test_soc_gateway.py apps/api/tests/test_fortigate_integrations.py
git commit -m "feat(api): link SOAR approvals to FortiGate policy reviews"
```

---

## Task 8: Replace Traffic Policy Draft UI With Lab Policy Wizard

- [ ] Update `apps/web/src/stores/useIntegrationsStore.ts`.

Remove `draftFortigateTrafficPolicy()` and add:

```ts
async function preflightFortigatePolicy(
  integrationId: string,
  payload: FortiGatePolicyPreflightPayload,
): Promise<FortiGatePolicyPreflightResponse> {
  return apiClient.post(`/api/integrations/fortigate/${integrationId}/policy/preflight`, payload)
}

async function createFortigatePolicyReview(
  integrationId: string,
  payload: FortiGatePolicyReviewPayload,
): Promise<FortiGatePolicyReviewResponse> {
  return apiClient.post(`/api/integrations/fortigate/${integrationId}/policy/review`, payload)
}

async function applyFortigatePolicy(
  integrationId: string,
  payload: FortiGatePolicyApplyPayload,
): Promise<FortiGatePolicyApplyResponse> {
  return apiClient.post(`/api/integrations/fortigate/${integrationId}/policy/apply`, payload)
}
```

Define TypeScript types in this store or a colocated `apps/web/src/types/fortigatePolicy.ts`:

```ts
export type FortiGatePolicyIntent = 'lab_allow_log' | 'temporary_block'
export type FortiGatePolicyScope = 'source_only' | 'source_destination' | 'source_destination_service'

export interface FortiGatePolicyPreflightPayload {
  intent: FortiGatePolicyIntent
  scope: FortiGatePolicyScope
  source_interface: string
  destination_interface: string
  source_ip: string
  destination_ip?: string
  service?: string
  duration_minutes?: number
  incident_id?: string
  playbook_run_id?: string
}

export interface FortiGatePolicyChange {
  operation: 'create' | 'reuse'
  object_type: 'firewall.address' | 'firewall.policy'
  name: string
  payload: Record<string, unknown>
}

export interface FortiGatePolicyPreflightResponse {
  intent: FortiGatePolicyIntent
  scope: FortiGatePolicyScope
  integration_id: string
  existing_policy_count: number
  owned_policy_count: number
  proposed_policy_name: string
  placement: string
  warnings: string[]
  changes: FortiGatePolicyChange[]
  review_hash: string
}

export interface FortiGatePolicyReviewResponse extends FortiGatePolicyPreflightResponse {
  request_id: string
  status: 'pending_review'
  expires_at?: string | null
}

export interface FortiGatePolicyApplyResponse {
  request_id: string
  status: 'applied'
  applied_changes: Array<Record<string, unknown>>
}
```

- [ ] Add `apps/web/src/components/integrations/LabPolicyWizard.vue`.

Use existing form/control styling from the integrations drawer. Required UI states:

- Select connected FortiGate integration.
- Inputs for source interface, destination interface, source IP, destination IP and service.
- Preflight button.
- Review summary showing policy name, placement, object changes and warnings.
- Apply button disabled until review is created and review hash is present.
- Success state showing applied object names.
- Error state using existing notification pattern.

Script skeleton:

```vue
<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ShieldCheck, ClipboardCheck, Play } from 'lucide-vue-next'
import { useIntegrationsStore } from '@/stores/useIntegrationsStore'
import type {
  FortiGatePolicyPreflightResponse,
  FortiGatePolicyReviewResponse,
} from '@/types/fortigatePolicy'

const props = defineProps<{
  integrationId: string
}>()

const { t } = useI18n()
const integrationsStore = useIntegrationsStore()

const sourceInterface = ref('port2')
const destinationInterface = ref('port3')
const sourceIp = ref('')
const destinationIp = ref('')
const service = ref('ALL')
const preflight = ref<FortiGatePolicyPreflightResponse | null>(null)
const review = ref<FortiGatePolicyReviewResponse | null>(null)
const isLoading = ref(false)
const errorMessage = ref<string | null>(null)

const payload = computed(() => ({
  intent: 'lab_allow_log' as const,
  scope: 'source_destination_service' as const,
  source_interface: sourceInterface.value,
  destination_interface: destinationInterface.value,
  source_ip: sourceIp.value,
  destination_ip: destinationIp.value,
  service: service.value || 'ALL',
}))

async function runPreflight() {
  isLoading.value = true
  errorMessage.value = null
  try {
    preflight.value = await integrationsStore.preflightFortigatePolicy(props.integrationId, payload.value)
    review.value = null
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : t('integrations.fortigatePolicy.errors.preflight')
  } finally {
    isLoading.value = false
  }
}

async function createReview() {
  isLoading.value = true
  errorMessage.value = null
  try {
    review.value = await integrationsStore.createFortigatePolicyReview(props.integrationId, payload.value)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : t('integrations.fortigatePolicy.errors.review')
  } finally {
    isLoading.value = false
  }
}

async function applyReview() {
  if (!review.value) return
  isLoading.value = true
  errorMessage.value = null
  try {
    await integrationsStore.applyFortigatePolicy(props.integrationId, {
      request_id: review.value.request_id,
      review_hash: review.value.review_hash,
    })
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : t('integrations.fortigatePolicy.errors.apply')
  } finally {
    isLoading.value = false
  }
}
</script>
```

- [ ] Update `apps/web/src/components/layout/Sidebar.vue`.

Remove:

- `handleDraftFortigateTrafficPolicy`
- `Traffic policy helper`
- `Draft CLI`
- `Recommendation only`
- hardcoded `port2`/`port3` draft call from the old sidebar action.

Render `LabPolicyWizard` inside the FortiGate integration detail section when an integration is connected.

- [ ] Add i18n keys to `apps/web/src/i18n/messages/pt-BR.ts` and `apps/web/src/i18n/messages/en-US.ts`.

Required namespace:

```ts
fortigatePolicy: {
  title: 'Lab policy wizard',
  subtitle: 'Create an allow + log policy for controlled scan detection.',
  sourceInterface: 'Source interface',
  destinationInterface: 'Destination interface',
  sourceIp: 'Source IP',
  destinationIp: 'Destination IP',
  service: 'Service',
  preflight: 'Preflight',
  createReview: 'Create review',
  apply: 'Apply FortiGate policy',
  proposedPolicy: 'Proposed policy',
  placement: 'Placement',
  objectChanges: 'Object changes',
  warnings: 'Warnings',
  applied: 'Policy applied',
  errors: {
    preflight: 'Unable to run policy preflight.',
    review: 'Unable to create policy review.',
    apply: 'Unable to apply policy.',
  },
}
```

Translate naturally in `pt-BR`.

- [ ] Update frontend tests:

- `apps/web/tests/unit/integrationsStore.test.ts`: assert the three new store actions call the new endpoints.
- `apps/web/tests/unit/sidebarIntegrations.test.ts`: assert old draft action text is absent and lab wizard text is present.
- Add `apps/web/tests/unit/labPolicyWizard.test.ts` for preflight/review/apply state transitions.

- [ ] Run and commit:

```bash
cd apps/web && pnpm test -- integrationsStore sidebarIntegrations labPolicyWizard
git add apps/web/src/stores/useIntegrationsStore.ts apps/web/src/types/fortigatePolicy.ts apps/web/src/components/integrations/LabPolicyWizard.vue apps/web/src/components/layout/Sidebar.vue apps/web/src/i18n/messages/pt-BR.ts apps/web/src/i18n/messages/en-US.ts apps/web/tests/unit/integrationsStore.test.ts apps/web/tests/unit/sidebarIntegrations.test.ts apps/web/tests/unit/labPolicyWizard.test.ts
git commit -m "feat(web): add FortiGate lab policy wizard"
```

---

## Task 9: Add Ticket Drawer Policy Review And Apply Flow

- [ ] Update `apps/web/src/services/ticketsClient.ts`.

Add:

```ts
export interface PlaybookRunPolicyReviewPayload {
  integrationId: string
  scope: 'source_only' | 'source_destination' | 'source_destination_service'
  sourceIp: string
  destinationIp?: string
  service?: string
  sourceInterface: string
  destinationInterface: string
  durationMinutes: number
}

export interface PlaybookRunPolicyApplyPayload {
  integrationId: string
  requestId: string
  reviewHash: string
}

export async function createPlaybookRunPolicyReview(
  runId: string,
  payload: PlaybookRunPolicyReviewPayload,
) {
  return apiClient.post(`/api/soc/playbook-runs/${runId}/policy-review`, payload)
}

export async function applyPlaybookRunPolicy(runId: string, payload: PlaybookRunPolicyApplyPayload) {
  return apiClient.post(`/api/soc/playbook-runs/${runId}/policy-apply`, payload)
}
```

- [ ] Update the ticket store or `apps/web/src/components/tickets/TicketsPanel.vue`, following the current approval code around `approvePlaybookRun`.

After a playbook run is approved and contains a `fortigate.temporary_block` step:

1. Show a `Policy Change Review` section.
2. Pre-fill values from incident attributes:
   - `sourceIp` from `attributes.sourceIp`
   - `destinationIp` from `attributes.destinationIp`
   - `service` from `attributes.service`
3. Let analyst choose scope, source interface, destination interface and duration.
4. Call `createPlaybookRunPolicyReview`.
5. Show FortiGate object changes and warnings.
6. Final button text must be `Apply FortiGate Policy`.
7. Call `applyPlaybookRunPolicy`.
8. Refresh the ticket through the existing ticket realtime/SSE store.

Guard function:

```ts
function runHasFortiGatePolicyStep(run: PlaybookRun | null): boolean {
  return Boolean(
    run?.steps?.some((step) => step.type === 'fortigate.temporary_block'),
  )
}
```

- [ ] Add i18n keys under the ticket namespace in both locale files.

Required keys:

```ts
policyReview: {
  title: 'Policy change review',
  scope: 'Scope',
  sourceOnly: 'Source only',
  sourceDestination: 'Source to destination',
  sourceDestinationService: 'Source to destination and service',
  duration: 'Duration',
  create: 'Create policy review',
  apply: 'Apply FortiGate Policy',
  applied: 'Temporary block applied',
}
```

- [ ] Add/update tests:

- `apps/web/tests/unit/ticketsPanel.test.ts`: approve playbook, render policy review section, create review, apply policy.
- `apps/web/tests/unit/ticketsRealtimeStore.test.ts`: assert ticket refresh/realtime update is consumed after policy apply if this store owns the refresh.

- [ ] Run and commit:

```bash
cd apps/web && pnpm test -- ticketsPanel ticketsRealtimeStore
git add apps/web/src/services/ticketsClient.ts apps/web/src/components/tickets/TicketsPanel.vue apps/web/src/i18n/messages/pt-BR.ts apps/web/src/i18n/messages/en-US.ts apps/web/tests/unit/ticketsPanel.test.ts apps/web/tests/unit/ticketsRealtimeStore.test.ts
git commit -m "feat(web): link tickets to FortiGate policy reviews"
```

---

## Task 10: Update Documentation And Remove Old Draft References

- [ ] Update `AGENTS.md` so the FortiGate write boundary matches the implemented product contract.

Required wording:

- FortiGate policy writes are allowed only through governed policy review/apply endpoints.
- Lab allow+log policies are allowed for controlled scan detection.
- Temporary block policies are allowed only after ticket/SOAR approval and explicit analyst apply.
- AI may suggest or prepare, but cannot approve or apply.

- [ ] Update `docs/product/feature-map.md`.

Add or update rows:

- FortiGate syslog/log forwarding: `beta`.
- SIEM realtime FortiGate incidenting over SSE: `beta`.
- FortiGate lab policy wizard: `beta`.
- FortiGate ticket-linked temporary block: `beta`.

Each row must link to:

- `docs/superpowers/specs/2026-05-15-fortigate-policy-orchestration-design.md`
- `docs/superpowers/plans/2026-05-15-fortigate-policy-orchestration.md`
- the operations runbook below.

- [ ] Update or create `docs/operations/fortigate-policy-orchestration.md`.

Runbook sections:

1. Prerequisites: connected FortiGate integration, syslog/log-forwarding healthy, traffic path through FortiGate, FortiGate API user with explicit policy privileges.
2. Lab allow+log wizard: fields to enter, what gets created, where logs appear.
3. Nmap validation: attacker scans victim through FortiGate; expected SIEM `Possible port scan` incident.
4. Ticket/SOAR response: draft containment, approve playbook, review policy change, apply FortiGate policy.
5. Rollback: disable/remove only `PG_` owned policies/objects from FortiGate GUI/CLI.
6. Troubleshooting: no logs, no incident, wrong interface, customer policy shadowing, review hash mismatch.

Do not include real lab IPs or secrets.

- [ ] Update `docs/architecture/decisions/ADR-2026-05-15-fortigate-policy-orchestration.md`.

Add an "Implemented endpoints" section with:

```txt
POST /api/integrations/fortigate/{integrationId}/policy/preflight
POST /api/integrations/fortigate/{integrationId}/policy/review
POST /api/integrations/fortigate/{integrationId}/policy/apply
POST /api/soc/playbook-runs/{runId}/policy-review
POST /api/soc/playbook-runs/{runId}/policy-apply
```

- [ ] Search and remove stale visible draft language.

```bash
rg -n "traffic-policy-draft|Traffic policy helper|Draft CLI|recommendation_only|recommend_block|draft policy|CLI snippet" AGENTS.md docs apps packages
```

Keep only historical references that explicitly say deprecated or archived.

- [ ] Run and commit:

```bash
git diff --check
git add AGENTS.md docs/product/feature-map.md docs/operations/fortigate-policy-orchestration.md docs/architecture/decisions/ADR-2026-05-15-fortigate-policy-orchestration.md
git commit -m "docs: document FortiGate policy orchestration"
```

---

## Task 11: Full Verification And Final Merge Prep

- [ ] Run API verification:

```bash
cd apps/api && uv run ruff check .
cd apps/api && uv run pytest -q
cd apps/api && uv run alembic upgrade head
```

- [ ] Run SIEM verification:

```bash
cd apps/siem_kowalski && uv run ruff check .
cd apps/siem_kowalski && uv run pytest -q
```

- [ ] Run SOAR verification:

```bash
cd apps/soar_skipper && uv run ruff check .
cd apps/soar_skipper && uv run pytest -q
```

- [ ] Run web verification:

```bash
cd apps/web && pnpm test
cd apps/web && pnpm build
```

- [ ] Run repository checks:

```bash
git diff --check
docker compose config --quiet
```

- [ ] Optional live lab smoke, only with operator-provided environment variables:

```bash
PENGUARD_FGT_INTEGRATION_ID=<integration-id> \
PENGUARD_LAB_SOURCE_INTERFACE=<source-interface> \
PENGUARD_LAB_DESTINATION_INTERFACE=<destination-interface> \
PENGUARD_LAB_ATTACKER_IP=<attacker-ip> \
PENGUARD_LAB_VICTIM_IP=<victim-ip> \
scripts/smoke/fortigate-policy-orchestration.sh
```

The smoke script must read values from environment variables and must not commit lab IPs.

- [ ] Final status:

```bash
git status --short --branch
git log --oneline --decorate -8
```

Expected branch shape:

```txt
feat(siem): detect allowed FortiGate port scans
feat(fortigate): add policy cmdb client helpers
feat(fortigate): plan governed policy changes
feat(fortigate): persist policy change reviews
feat(api): expose FortiGate policy review endpoints
feat(soar): add FortiGate temporary block node
feat(api): link SOAR approvals to FortiGate policy reviews
feat(web): add FortiGate lab policy wizard
feat(web): link tickets to FortiGate policy reviews
docs: document FortiGate policy orchestration
```

---

## Manual Acceptance Criteria

- Connecting FortiGate and enabling syslog/log forwarding stays unchanged.
- Lab policy wizard creates a real FortiGate `PG_LAB_ALLOW_*` policy with `logtraffic all`.
- Running an authorized nmap scan from attacker to victim through FortiGate creates a `Possible port scan` SIEM incident without browser refresh.
- The incident appears in the ticket console through existing SSE updates.
- Ticket containment can create a SOAR run with `fortigate.temporary_block`.
- Approving the run does not write FortiGate immediately.
- The ticket drawer shows `Policy Change Review` and the final `Apply FortiGate Policy` button.
- Applying creates only `PG_` owned objects/policies and writes audit events.
- Mismatched review hash blocks apply.
- Old `Traffic policy helper` / `Draft CLI` UX is gone.

## Self-Review Checklist For The Implementer

- [ ] No API key, hostname, lab IP, password or token was committed.
- [ ] All new UI strings are present in `pt-BR` and `en-US`.
- [ ] FortiGate writes are isolated to explicit policy apply paths.
- [ ] AI paths produce suggestions only and cannot call apply endpoints.
- [ ] Audit events exist for preflight, review creation and apply.
- [ ] SIEM detection uses bounded in-process correlation and does not require polling.
- [ ] Tests prove allowed traffic scan detection, policy review hash protection and ticket-linked apply.
- [ ] Documentation links the spec, plan, ADR and operations runbook.
