# FortiWeb WAF Marketplace Landing Lab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a real FortiWeb WAF integration, delivered as a marketplace add-on, that protects an external landing page, forwards WAF telemetry into FortiDashboard, creates SIEM incidents in realtime, and lets FortiDashboard drive approved response actions.

**Architecture:** The landing page lives outside this repository and is placed behind a FortiWeb trial VM/appliance in reverse-proxy mode. FortiWeb sends attack/traffic/event telemetry to FortiDashboard through a push/syslog ingestion path. FortiDashboard normalizes FortiWeb events into SIEM events, streams incidents to the cockpit through SSE, and presents SOAR/FortiGate/FortiWeb response actions behind explicit approval.

**Tech Stack:** FortiWeb trial, external landing app, FastAPI, Pydantic, SQLAlchemy, Vue 3, Pinia, `siem_kowalski`, `soar_skipper`, add-on registry packages from `ping-wins/fortidashboard-addons`, Docker Compose, Pytest, Vitest.

---

## References

- FortiWeb logging docs: https://docs.fortinet.com/document/fortiweb/7.4.7/administration-guide/303842/logging
- FortiWeb attack log reference: https://docs.fortinet.com/document/fortiweb/7.0.3/log-message-reference/445549/attack
- FortiWeb log access docs: https://docs.fortinet.com/document/fortiweb/7.4.8/administration-guide/929320/checking-attack-traffic-event-logs
- Current add-on contract: `docs/marketplace/README.md`
- Current realtime contract: `docs/architecture/realtime-telemetry-flow.md`

## Scope

In scope:

- FortiWeb trial integration appears in the FortiDashboard marketplace as `fortiweb-waf`.
- Marketplace install downloads the add-on from the registry repo.
- FortiWeb telemetry creates SIEM events and incidents.
- Incidents appear in tickets, recent incident widgets, and incident toasts through existing SSE behavior.
- A runbook explains how the external landing page must be placed behind FortiWeb.
- SOAR presents response actions that are initiated and audited from FortiDashboard.

Out of scope for this repo:

- Building the landing page source code.
- Hosting/domain/TLS automation for the landing page.
- Running uncontrolled public DoS traffic.
- Hidden FortiWeb/FortiGate changes outside FortiDashboard.

Safety boundary:

- The demo attack must target only lab-owned infrastructure.
- DoS validation must be rate-limited and time-boxed.
- Live blocking/policy writes require explicit approval in FortiDashboard and an ADR before implementation.
- Until that ADR lands, FortiGate/FortiWeb response steps remain recommendation-only or dry-run.

## File Structure

External registry repo `ping-wins/fortidashboard-addons`:

- Create: `catalog.json`
  - Add `fortiweb-waf` entry and version metadata.
- Create: `fortiweb-waf/0.1.0/addon.json`
  - Marketplace manifest for FortiWeb.
- Create: `fortiweb-waf/0.1.0/connector/__init__.py`
  - Duck-typed add-on connector.
- Create: `fortiweb-waf/0.1.0/fixtures/attack-log.json`
  - Sanitized FortiWeb attack sample.
- Create: `fortiweb-waf/0.1.0/README.md`
  - Package-specific setup notes.

This repo:

- Modify: `apps/api/app/routers/soc_ingest.py`
  - Add FortiWeb push ingest endpoint and normalizer.
- Modify: `apps/api/tests/test_soc_ingest.py`
  - Add FortiWeb ingest tests.
- Modify: `apps/siem_kowalski/app/main.py`
  - Add FortiWeb WAF detections.
- Modify: `apps/siem_kowalski/tests/test_events_incidents.py`
  - Add incident tests for WAF attack/DoS events.
- Modify: `apps/web/src/services/marketplaceClient.ts`
  - Add install API call and installed metadata types.
- Modify: `apps/web/src/stores/useMarketplaceStore.ts`
  - Add install action and refresh behavior.
- Modify: `apps/web/src/components/marketplace/MarketplacePanel.vue`
  - Show installed badge and call real install endpoint.
- Modify: `apps/web/tests/unit/*marketplace*`
  - Add or extend marketplace tests.
- Create: `docs/operations/fortiweb-landing-waf-lab.md`
  - Operator runbook for the FortiWeb + external landing topology.
- Create: `docs/architecture/decisions/ADR-2026-05-15-fortiweb-response-boundary.md`
  - Required before any live FortiWeb/FortiGate write action.
- Modify: `docs/product/feature-map.md`
  - Add FortiWeb integration row.
- Modify: `docs/product/roadmap.md`
  - Add FortiWeb landing lab under Now/Next depending on delivery date.
- Modify: `docs/product/release-notes.md`
  - Add user-visible marketplace/WAF/SIEM behavior.

---

### Task 1: Define The External Landing Contract

**Files:**
- Create: `docs/operations/fortiweb-landing-waf-lab.md`

- [ ] **Step 1: Write the runbook skeleton**

Create `docs/operations/fortiweb-landing-waf-lab.md`:

```markdown
# FortiWeb Landing WAF Lab

This runbook describes the lab topology used to demonstrate FortiDashboard with
FortiWeb protecting an external landing page.

## Topology

```txt
Internet or lab attacker
  -> FortiWeb trial virtual server
  -> external landing page origin

FortiWeb
  -> FortiDashboard API /api/soc/ingest/fortiweb
  -> siem_kowalski
  -> FortiDashboard cockpit through SSE
```

## Landing Page Requirements

- The landing source code lives outside this repository.
- The landing origin must be reachable from FortiWeb.
- Public traffic must reach the landing through FortiWeb, not directly.
- The origin should expose:
  - `GET /`
  - `GET /demo/search?q=...`
  - `POST /api/contact`
- The origin must not contain real customer data or real credentials.

## Demo Attack Inputs

Use only against lab-owned infrastructure:

```bash
curl -k "https://<FORTIWEB_PUBLIC_HOST>/demo/search?q=%27%20OR%201%3D1--"
curl -k "https://<FORTIWEB_PUBLIC_HOST>/.env"
hey -z 20s -q 5 -c 20 "https://<FORTIWEB_PUBLIC_HOST>/"
```

The `hey` command is intentionally rate-limited. Do not run open-ended DoS
traffic against public infrastructure.

## Expected Result

- FortiWeb records Attack or Traffic logs.
- FortiDashboard receives FortiWeb telemetry.
- `siem_kowalski` creates a WAF incident.
- The dashboard shows an incident toast, recent incident, and ticket without a
  browser refresh.
- SOAR proposes an approved response action from inside FortiDashboard.
```

- [ ] **Step 2: Run Markdown grep check**

Run:

```bash
rg -n "FORTIWEB_PUBLIC_HOST|/api/soc/ingest/fortiweb|Do not run open-ended" docs/operations/fortiweb-landing-waf-lab.md
```

Expected: all three strings are found.

- [ ] **Step 3: Commit**

```bash
git add docs/operations/fortiweb-landing-waf-lab.md
git commit -m "docs(ops): add FortiWeb landing WAF lab runbook"
```

---

### Task 2: Add The FortiWeb Marketplace Package In The Registry Repo

**Files in `ping-wins/fortidashboard-addons`:**
- Create: `fortiweb-waf/0.1.0/addon.json`
- Create: `fortiweb-waf/0.1.0/connector/__init__.py`
- Create: `fortiweb-waf/0.1.0/fixtures/attack-log.json`
- Modify: `catalog.json`

- [ ] **Step 1: Create the manifest**

Create `fortiweb-waf/0.1.0/addon.json`:

```json
{
  "id": "fortiweb-waf",
  "version": "0.1.0",
  "name": "FortiWeb WAF",
  "vendor": "Fortinet",
  "category": "waf",
  "description": "Ingest FortiWeb Attack, Traffic, and Event telemetry from a protected web application and generate SIEM incidents.",
  "icon": "fortinet",
  "minDashboardVersion": "0.1.0",
  "provider": {
    "type": "fortiweb",
    "auth": {
      "kind": "apiKey",
      "fields": [
        {
          "id": "host",
          "label": "FortiWeb URL",
          "type": "url",
          "required": true,
          "placeholder": "https://fortiweb.example.local"
        },
        {
          "id": "apiKey",
          "label": "API Key",
          "type": "secret",
          "required": false
        },
        {
          "id": "ingestMode",
          "label": "Ingestion Mode",
          "type": "text",
          "required": true,
          "default": "push"
        },
        {
          "id": "verifyTls",
          "label": "Verify TLS",
          "type": "boolean",
          "default": false
        }
      ]
    }
  },
  "compatibility": {
    "testedVersions": ["7.4.x", "7.6.x", "8.0.x"],
    "notes": "MVP telemetry path uses FortiWeb Attack, Traffic, and Event logs forwarded to FortiDashboard. REST health can be enabled when the FortiWeb trial exposes an API token."
  },
  "routes": [
    {
      "id": "push-ingest",
      "method": "POST",
      "path": "/api/soc/ingest/fortiweb",
      "summary": "FortiDashboard endpoint that receives FortiWeb WAF log payloads."
    }
  ],
  "widgets": [
    "soc-recent-incidents",
    "soc-open-tickets",
    "soc-incidents-by-severity"
  ],
  "siemEventTypes": [
    "waf.attack",
    "waf.dos",
    "waf.blocked_request",
    "http.attack"
  ],
  "entrypoint": "connector",
  "requirements": []
}
```

- [ ] **Step 2: Create the minimal connector**

Create `fortiweb-waf/0.1.0/connector/__init__.py`:

```python
from datetime import datetime
from typing import Any


class FortiWebConnector:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def health_check(self) -> dict[str, Any]:
        host = str(self.config.get("host") or "").rstrip("/")
        ingest_mode = str(self.config.get("ingestMode") or "push")
        if not host:
            return {
                "ok": False,
                "status": "missing_host",
                "device": {},
                "message": "FortiWeb host is required",
            }
        return {
            "ok": True,
            "status": "ready",
            "device": {
                "vendor": "Fortinet",
                "product": "FortiWeb",
                "host": host,
                "ingestMode": ingest_mode,
            },
            "message": "FortiWeb add-on is ready for push telemetry",
        }

    def get_widget_data(self, req: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "ready",
            "data": {
                "message": "FortiWeb WAF events are surfaced through SIEM widgets",
                "widgetId": req.get("widget_id"),
            },
            "meta": {"source": "fortiweb", "mode": "push"},
        }

    def ingest_events(self, since: datetime | None) -> list[dict[str, Any]]:
        return []

    def close(self) -> None:
        return None


def get_connector(config: dict[str, Any]) -> FortiWebConnector:
    return FortiWebConnector(config)
```

- [ ] **Step 3: Add a sanitized fixture**

Create `fortiweb-waf/0.1.0/fixtures/attack-log.json`:

```json
{
  "type": "attack",
  "subtype": "signature",
  "src": "203.0.113.50",
  "dst": "198.51.100.10",
  "host": "landing.example.test",
  "method": "GET",
  "url": "/demo/search?q=' OR 1=1--",
  "action": "block",
  "severity": "high",
  "msg": "SQL Injection Detected",
  "policy": "landing-waf-policy",
  "eventtime": "2026-05-15T12:00:00Z"
}
```

- [ ] **Step 4: Add the catalog entry**

Modify `catalog.json`:

```json
{
  "id": "fortiweb-waf",
  "name": "FortiWeb WAF",
  "vendor": "Fortinet",
  "category": "waf",
  "icon": "fortinet",
  "description": "Ingest FortiWeb WAF telemetry and turn web attacks into SIEM incidents.",
  "latestVersion": "0.1.0",
  "versions": ["0.1.0"],
  "tagTemplate": "fortiweb-waf-v{version}"
}
```

- [ ] **Step 5: Test package import locally**

Run from the registry repo:

```bash
python - <<'PY'
import importlib.util
from pathlib import Path

path = Path("fortiweb-waf/0.1.0/connector/__init__.py")
spec = importlib.util.spec_from_file_location("fortiweb_test", path)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)
connector = mod.get_connector({"host": "https://fortiweb.example.test"})
print(connector.health_check())
PY
```

Expected: printed dict has `"ok": True`.

- [ ] **Step 6: Tag the package**

```bash
git add catalog.json fortiweb-waf/0.1.0
git commit -m "feat(fortiweb): add WAF marketplace package"
git tag fortiweb-waf-v0.1.0
git push origin main fortiweb-waf-v0.1.0
```

---

### Task 3: Implement FortiWeb Push Ingestion In The API

**Files:**
- Modify: `apps/api/app/routers/soc_ingest.py`
- Modify: `apps/api/tests/test_soc_ingest.py`

- [ ] **Step 1: Write failing tests**

Append to `apps/api/tests/test_soc_ingest.py`:

```python
def test_fortiweb_attack_log_emits_waf_attack():
    fake_siem = FakeSiemClient()
    app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem
    client = TestClient(app)

    response = client.post(
        "/api/soc/ingest/fortiweb",
        headers={
            "Authorization": "Bearer test-secret-token",
            "X-FortiDashboard-Integration-Id": "int_fweb_landing",
        },
        json={
            "type": "attack",
            "subtype": "signature",
            "src": "203.0.113.50",
            "dst": "198.51.100.10",
            "host": "landing.example.test",
            "method": "GET",
            "url": "/demo/search?q=' OR 1=1--",
            "action": "block",
            "severity": "high",
            "msg": "SQL Injection Detected",
            "policy": "landing-waf-policy",
            "eventtime": "2026-05-15T12:00:00Z",
        },
    )

    assert response.status_code == 200
    assert response.json()["emitted"] == 1
    forwarded = fake_siem.calls[0]["json"]
    assert forwarded["eventType"] == "waf.attack"
    assert forwarded["severity"] == "high"
    assert forwarded["entities"]["sourceIp"] == "203.0.113.50"
    assert forwarded["entities"]["destinationIp"] == "198.51.100.10"
    assert forwarded["entities"]["httpHost"] == "landing.example.test"
    assert forwarded["entities"]["integrationId"] == "int_fweb_landing"
    assert forwarded["attributes"]["action"] == "block"
    assert forwarded["attributes"]["policy"] == "landing-waf-policy"


def test_fortiweb_dos_log_emits_waf_dos():
    fake_siem = FakeSiemClient()
    app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem
    client = TestClient(app)

    response = client.post(
        "/api/soc/ingest/fortiweb",
        headers={"Authorization": "Bearer test-secret-token"},
        json={
            "type": "attack",
            "subtype": "dos",
            "src": "203.0.113.60",
            "host": "landing.example.test",
            "action": "block",
            "severity": "critical",
            "msg": "HTTP Flood detected",
            "count": 250,
        },
    )

    assert response.status_code == 200
    forwarded = fake_siem.calls[0]["json"]
    assert forwarded["eventType"] == "waf.dos"
    assert forwarded["severity"] == "critical"
    assert forwarded["attributes"]["count"] == 250
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd apps/api && uv run pytest -q tests/test_soc_ingest.py::test_fortiweb_attack_log_emits_waf_attack tests/test_soc_ingest.py::test_fortiweb_dos_log_emits_waf_dos
```

Expected: FAIL because `/api/soc/ingest/fortiweb` does not exist yet.

- [ ] **Step 3: Add FortiWeb normalizer helpers**

In `apps/api/app/routers/soc_ingest.py`, add:

```python
def _fortiweb_field(raw: dict[str, Any], *names: str) -> str:
    for name in names:
        value = _coerce_str(raw.get(name))
        if value:
            return value
    return ""


def _classify_fortiweb_event(raw: dict[str, Any]) -> str:
    kind = _fortiweb_field(raw, "type", "log_type").lower()
    subtype = _fortiweb_field(raw, "subtype", "sub_type", "main_type").lower()
    message = _fortiweb_field(raw, "msg", "message", "attack", "signature").lower()
    action = _fortiweb_field(raw, "action").lower()

    if "dos" in subtype or "flood" in message or "rate" in message:
        return "waf.dos"
    if kind == "attack" or subtype or "attack" in message:
        return "waf.attack"
    if action in {"block", "blocked", "deny", "dropped"}:
        return "waf.blocked_request"
    return "http.attack"


def _normalize_fortiweb_event(
    raw: dict[str, Any],
    *,
    integration_id: str,
) -> dict[str, Any]:
    occurred_at = _parse_fortigate_timestamp(
        raw.get("eventtime") or raw.get("time") or raw.get("date")
    )
    source_ip = _fortiweb_field(raw, "src", "srcip", "source", "client_ip")
    destination_ip = _fortiweb_field(raw, "dst", "dstip", "destination", "server_ip")
    host = _fortiweb_field(raw, "host", "http_host", "hostname")
    method = _fortiweb_field(raw, "method", "http_method").upper()
    url = _fortiweb_field(raw, "url", "uri", "path", "request")
    action = _fortiweb_field(raw, "action")
    policy = _fortiweb_field(raw, "policy", "policy_name", "server_policy")
    message = _fortiweb_field(raw, "msg", "message", "attack", "signature")
    severity = _map_severity(raw)

    count_raw = raw.get("count") or raw.get("matches") or raw.get("total")
    try:
        count = int(count_raw)
    except (TypeError, ValueError):
        count = 1

    return {
        "eventType": _classify_fortiweb_event(raw),
        "source": "fortiweb",
        "severity": severity,
        "message": message or "FortiWeb WAF event",
        "occurredAt": occurred_at,
        "entities": {
            "sourceIp": source_ip,
            "destinationIp": destination_ip,
            "httpHost": host,
            "integrationId": integration_id,
        },
        "attributes": {
            "action": action,
            "policy": policy,
            "method": method,
            "url": url,
            "count": count,
            "rawType": _fortiweb_field(raw, "type", "log_type"),
            "rawSubtype": _fortiweb_field(raw, "subtype", "sub_type"),
            "ingestionMode": "push",
        },
    }
```

- [ ] **Step 4: Add endpoint**

In `apps/api/app/routers/soc_ingest.py`, add:

```python
@router.post("/api/soc/ingest/fortiweb")
def ingest_fortiweb_event(
    request: Request,
    payload: Annotated[Any, Body()],
    authorization: Annotated[str | None, Header()] = None,
    integration_id: Annotated[
        str | None,
        Header(alias="X-FortiDashboard-Integration-Id"),
    ] = None,
    siem_client: SocClient = Depends(get_siem_client),
    audit_store: AuditStore = Depends(get_auth_audit_store),
) -> dict[str, Any]:
    _verify_token(authorization)
    raw_items = payload if isinstance(payload, list) else [payload]
    emitted = 0
    integration = integration_id or "fortiweb"

    for item in raw_items:
        if not isinstance(item, dict):
            continue
        event = _normalize_fortiweb_event(item, integration_id=integration)
        siem_client.request("POST", "/events/ingest", json=event)
        emitted += 1

    audit_store.record(
        user_id="system",
        action="soc.fortiweb_events.ingested",
        outcome="success",
        metadata={
            "sourceIp": _client_ip(request),
            "integrationId": integration,
            "received": len(raw_items),
            "emitted": emitted,
        },
    )
    return {"received": len(raw_items), "emitted": emitted}
```

- [ ] **Step 5: Run FortiWeb ingest tests**

Run:

```bash
cd apps/api && uv run pytest -q tests/test_soc_ingest.py
```

Expected: all tests in `test_soc_ingest.py` pass.

- [ ] **Step 6: Run API lint**

```bash
cd apps/api && uv run ruff check .
```

Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/routers/soc_ingest.py apps/api/tests/test_soc_ingest.py
git commit -m "feat(api): ingest FortiWeb WAF events"
```

---

### Task 4: Add FortiWeb SIEM Detections

**Files:**
- Modify: `apps/siem_kowalski/app/main.py`
- Modify: `apps/siem_kowalski/tests/test_events_incidents.py`

- [ ] **Step 1: Write failing SIEM tests**

Append to `apps/siem_kowalski/tests/test_events_incidents.py`:

```python
def test_waf_attack_creates_incident(client):
    response = client.post(
        "/events/ingest",
        json={
            "eventType": "waf.attack",
            "source": "fortiweb",
            "severity": "high",
            "message": "SQL Injection Detected",
            "occurredAt": "2026-05-15T12:00:00Z",
            "entities": {
                "sourceIp": "203.0.113.50",
                "destinationIp": "198.51.100.10",
                "httpHost": "landing.example.test",
                "integrationId": "int_fweb_landing",
            },
            "attributes": {
                "action": "block",
                "policy": "landing-waf-policy",
                "method": "GET",
                "url": "/demo/search?q=' OR 1=1--",
                "count": 1,
            },
        },
    )

    assert response.status_code == 200
    incident = response.json()["incident"]
    assert incident["title"] == "FortiWeb WAF attack blocked"
    assert incident["severity"] == "high"
    assert incident["triageLevel"] == "T1"
    assert incident["entities"]["sourceIp"] == "203.0.113.50"
    assert incident["entities"]["httpHost"] == "landing.example.test"
    assert incident["attributes"]["policy"] == "landing-waf-policy"


def test_waf_dos_creates_critical_incident(client):
    response = client.post(
        "/events/ingest",
        json={
            "eventType": "waf.dos",
            "source": "fortiweb",
            "severity": "critical",
            "message": "HTTP Flood detected",
            "occurredAt": "2026-05-15T12:00:00Z",
            "entities": {
                "sourceIp": "203.0.113.60",
                "httpHost": "landing.example.test",
            },
            "attributes": {
                "action": "block",
                "count": 250,
            },
        },
    )

    assert response.status_code == 200
    incident = response.json()["incident"]
    assert incident["title"] == "FortiWeb DoS activity detected"
    assert incident["severity"] == "critical"
    assert incident["triageLevel"] == "T1"
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd apps/siem_kowalski && uv run pytest -q tests/test_events_incidents.py::test_waf_attack_creates_incident tests/test_events_incidents.py::test_waf_dos_creates_critical_incident
```

Expected: FAIL because FortiWeb detection rules do not exist yet.

- [ ] **Step 3: Add detection rules**

In `apps/siem_kowalski/app/main.py`, add these entries to `DETECTION_RULES` after the FortiGate resource pressure rule:

```python
DetectionRule(
    id="fortiweb_waf_attack",
    title="FortiWeb WAF attack blocked",
    severity="high",
    summary="FortiWeb blocked a web attack against a protected application.",
    eventTypes=["waf.attack", "http.attack"],
    conditions=[RuleCondition(path="attributes.action", operator="exists")],
),
DetectionRule(
    id="fortiweb_dos_activity",
    title="FortiWeb DoS activity detected",
    severity="critical",
    summary="FortiWeb reported DoS activity against a protected application.",
    eventTypes=["waf.dos"],
),
DetectionRule(
    id="fortiweb_blocked_request",
    title="FortiWeb blocked suspicious request",
    severity="medium",
    summary="FortiWeb blocked a suspicious request against a protected application.",
    eventTypes=["waf.blocked_request"],
),
```

- [ ] **Step 4: Preserve WAF attributes on incidents**

In `_incident_attributes()` in `apps/siem_kowalski/app/main.py`, extend the copied attribute tuple:

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
        "policy",
        "method",
        "url",
        "rawType",
        "rawSubtype",
        "ingestionMode",
    ):
        value = event.attributes.get(key)
        if value is not None and value != "":
            attributes[key] = value
```

- [ ] **Step 5: Run SIEM tests**

```bash
cd apps/siem_kowalski && uv run pytest -q tests/test_events_incidents.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add apps/siem_kowalski/app/main.py apps/siem_kowalski/tests/test_events_incidents.py
git commit -m "feat(siem): detect FortiWeb WAF incidents"
```

---

### Task 5: Finish Marketplace Install UX

**Files:**
- Modify: `apps/web/src/services/marketplaceClient.ts`
- Modify: `apps/web/src/stores/useMarketplaceStore.ts`
- Modify: `apps/web/src/components/marketplace/MarketplacePanel.vue`
- Modify: `apps/web/src/components/settings/SettingsModal.vue`
- Test: add or update `apps/web/tests/unit/marketplacePanel.test.ts`

- [ ] **Step 1: Add install client**

Modify `apps/web/src/services/marketplaceClient.ts`:

```ts
export type AddonManifest = {
  id: string
  version: string
  name: string
  vendor: string
  category: string
  description: string
  icon?: string
  minDashboardVersion?: string
  provider: { type: string, auth: AddonAuth }
  routes: AddonRoute[]
  widgets: string[]
  siemEventTypes: string[]
  installed?: boolean
  installedVersion?: string | null
}

export async function installMarketplaceAddon(addonId: string, version: string): Promise<void> {
  const response = await fetch(`/api/marketplace/addons/${encodeURIComponent(addonId)}/install`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ version }),
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail ?? 'Failed to install add-on')
  }
}
```

- [ ] **Step 2: Add store action**

Modify `apps/web/src/stores/useMarketplaceStore.ts`:

```ts
import {
  installMarketplaceAddon,
  listMarketplaceAddons,
  type AddonManifest,
} from '../services/marketplaceClient'

const installingId = ref<string | null>(null)

async function install(addon: AddonManifest): Promise<void> {
  installingId.value = addon.id
  error.value = null
  try {
    await installMarketplaceAddon(addon.id, addon.version)
    await refresh()
  } catch (err: any) {
    error.value = err?.message ?? 'Failed to install marketplace add-on'
    throw err
  } finally {
    installingId.value = null
  }
}

return { addons, isLoading, error, hasLoadedOnce, byCategory, installingId, refresh, install }
```

- [ ] **Step 3: Wire component install**

Modify `apps/web/src/components/marketplace/MarketplacePanel.vue`:

```ts
async function installAddon(addon: AddonManifest) {
  await store.install(addon)
  emit('install', addon)
}
```

Add badge/disabled state in the install button:

```vue
<span
  v-if="addon.installed"
  class="rounded border border-emerald-400/30 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] uppercase text-emerald-200"
>
  {{ t('marketplace.installed') }}
</span>

<button
  type="button"
  class="flex items-center gap-1 rounded border border-theme-primary/40 bg-theme-primary/10 px-2 py-1 text-xs font-medium text-theme-primary hover:bg-theme-primary/20 disabled:opacity-50"
  :disabled="addon.installed || store.installingId === addon.id"
  @click="installAddon(addon)"
>
  <Plug :size="12" />
  {{ addon.installed ? t('marketplace.installed') : t('marketplace.install') }}
</button>
```

- [ ] **Step 4: Add translations**

Add to both `apps/web/src/i18n/messages/en-US.ts` and `apps/web/src/i18n/messages/pt-BR.ts`:

```ts
installed: 'Installed',
```

Portuguese:

```ts
installed: 'Instalado',
```

- [ ] **Step 5: Add web test**

Create or update `apps/web/tests/unit/marketplacePanel.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import MarketplacePanel from '../../src/components/marketplace/MarketplacePanel.vue'
import { useMarketplaceStore } from '../../src/stores/useMarketplaceStore'

describe('MarketplacePanel', () => {
  it('disables install for installed add-ons', async () => {
    const wrapper = mount(MarketplacePanel, {
      global: {
        plugins: [
          createTestingPinia({
            createSpy: vi.fn,
            stubActions: false,
          }),
        ],
        stubs: { Teleport: true },
      },
    })
    const store = useMarketplaceStore()
    store.addons = [
      {
        id: 'fortiweb-waf',
        version: '0.1.0',
        name: 'FortiWeb WAF',
        vendor: 'Fortinet',
        category: 'waf',
        description: 'WAF telemetry',
        provider: { type: 'fortiweb', auth: { kind: 'apiKey', fields: [] } },
        routes: [],
        widgets: [],
        siemEventTypes: ['waf.attack'],
        installed: true,
        installedVersion: '0.1.0',
      },
    ]
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('FortiWeb WAF')
    const button = wrapper.find('button[disabled]')
    expect(button.exists()).toBe(true)
  })
})
```

- [ ] **Step 6: Run web tests**

```bash
cd apps/web && pnpm test -- tests/unit/marketplacePanel.test.ts
```

Expected: test passes.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/services/marketplaceClient.ts apps/web/src/stores/useMarketplaceStore.ts apps/web/src/components/marketplace/MarketplacePanel.vue apps/web/src/components/settings/SettingsModal.vue apps/web/src/i18n/messages/en-US.ts apps/web/src/i18n/messages/pt-BR.ts apps/web/tests/unit/marketplacePanel.test.ts
git commit -m "feat(web): install marketplace add-ons from UI"
```

---

### Task 6: Add Response Boundary ADR

**Files:**
- Create: `docs/architecture/decisions/ADR-2026-05-15-fortiweb-response-boundary.md`

- [ ] **Step 1: Create ADR**

Create `docs/architecture/decisions/ADR-2026-05-15-fortiweb-response-boundary.md`:

```markdown
# ADR 2026-05-15: FortiWeb And FortiGate Response Boundary

## Status

Proposed

## Context

FortiDashboard will ingest FortiWeb WAF telemetry from a FortiWeb trial protecting
the external landing page. SIEM incidents may require response suggestions such
as blocking an abusive source IP, increasing WAF enforcement, or asking
FortiGate to block traffic upstream.

## Decision

All response actions must be initiated from FortiDashboard, require an
authenticated admin session, require explicit approval, and write audit events
before and after the action.

For the first FortiWeb WAF MVP, live response actions are not auto-applied.
`soar_skipper` may create recommendation-only or dry-run actions:

- Recommend FortiWeb block rule.
- Recommend FortiGate upstream block.
- Draft CLI/API payload for operator review.

Live FortiWeb/FortiGate writes require a follow-up ADR that names exact API
paths, preflight reads, rollback behavior, audit fields, and permission checks.

## Consequences

- The demo can show FortiWeb blocking attacks and FortiDashboard generating
  incidents in realtime.
- FortiDashboard remains the only place where response actions are requested.
- The project does not silently modify customer WAF/firewall policy.
```

- [ ] **Step 2: Commit ADR**

```bash
git add docs/architecture/decisions/ADR-2026-05-15-fortiweb-response-boundary.md
git commit -m "docs(architecture): define FortiWeb response boundary"
```

---

### Task 7: Add SOAR Recommendation For FortiWeb Incidents

**Files:**
- Modify: `apps/soar_skipper/app/main.py`
- Modify: `apps/soar_skipper/tests/test_playbooks.py`

- [ ] **Step 1: Write failing test**

Add to `apps/soar_skipper/tests/test_playbooks.py`:

```python
def test_fortiweb_recommend_block_node_is_dry_run_only(client):
    response = client.get("/playbook-node-types")
    assert response.status_code == 200
    nodes = {node["id"]: node for node in response.json()["items"]}
    node = nodes["fortiweb.recommend_block"]
    assert node["executionMode"] == "dry_run"
    assert node["liveAvailable"] is False
    assert node["boundary"] == "recommendation_only"
    assert node["sensitive"] is True
```

- [ ] **Step 2: Run test to verify failure**

```bash
cd apps/soar_skipper && uv run pytest -q tests/test_playbooks.py::test_fortiweb_recommend_block_node_is_dry_run_only
```

Expected: FAIL because the node does not exist.

- [ ] **Step 3: Add node type**

In `apps/soar_skipper/app/main.py`, add to the node type list:

```python
{
    "id": "fortiweb.recommend_block",
    "label": "Recommend FortiWeb Block",
    "description": "Drafts a FortiWeb source-IP block recommendation for an approved operator.",
    "category": "action",
    "sensitive": True,
    "executionMode": "dry_run",
    "liveAvailable": False,
    "boundary": "recommendation_only",
    "configSchema": {
        "type": "object",
        "properties": {
            "sourceIp": {"type": "string"},
            "durationMinutes": {"type": "integer", "minimum": 1, "default": 60}
        },
        "required": ["sourceIp"]
    }
}
```

- [ ] **Step 4: Run SOAR tests**

```bash
cd apps/soar_skipper && uv run pytest -q
```

Expected: all SOAR tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/soar_skipper/app/main.py apps/soar_skipper/tests/test_playbooks.py
git commit -m "feat(soar): add FortiWeb response recommendation"
```

---

### Task 8: Update Product Docs

**Files:**
- Modify: `docs/product/feature-map.md`
- Modify: `docs/product/roadmap.md`
- Modify: `docs/product/release-notes.md`
- Modify: `docs/product/timeline.md`

- [ ] **Step 1: Add feature-map row**

Add row to `docs/product/feature-map.md`:

```markdown
| Integrations | FortiWeb WAF marketplace add-on and push telemetry | `apps/api` + `apps/web` + external add-on registry | planned | yes | FortiWeb trial and external landing lab | `docs/operations/fortiweb-landing-waf-lab.md`, `ping-wins/fortidashboard-addons/fortiweb-waf` | `cd apps/api && uv run pytest -q tests/test_soc_ingest.py && cd ../siem_kowalski && uv run pytest -q tests/test_events_incidents.py` |
```

- [ ] **Step 2: Add roadmap item**

Under `## Now: Real Telemetry Stabilization`, add:

```markdown
- [ ] FortiWeb trial protects the external landing page and forwards WAF
  telemetry into SIEM incidents through FortiDashboard.
```

- [ ] **Step 3: Add release note**

Under `## Unreleased > Added`, add:

```markdown
- Planned FortiWeb WAF marketplace add-on for the external landing-page demo,
  with WAF telemetry normalized into SIEM incidents.
```

- [ ] **Step 4: Add timeline entry**

Add to `docs/product/timeline.md`:

```markdown
| 2026-05-15 | Planned FortiWeb WAF marketplace integration for the landing-page demo. | Gives Fortinet evaluators a concrete WAF story while preserving honest integration boundaries. | [FortiWeb WAF plan](../superpowers/plans/2026-05-15-fortiweb-waf-marketplace-landing-lab.md), [FortiWeb lab runbook](../operations/fortiweb-landing-waf-lab.md) |
```

- [ ] **Step 5: Commit**

```bash
git add docs/product/feature-map.md docs/product/roadmap.md docs/product/release-notes.md docs/product/timeline.md
git commit -m "docs(product): plan FortiWeb WAF marketplace integration"
```

---

### Task 9: End-To-End Lab Validation

**Files:**
- No source changes expected.
- Update `docs/operations/fortiweb-landing-waf-lab.md` only if commands drift during validation.

- [ ] **Step 1: Start FortiDashboard**

```bash
docker compose up -d --build api web siem-kowalski soar-skipper redis db keycloak
docker compose ps
```

Expected: API, web, SIEM, SOAR, Redis, DB and Keycloak are healthy or running.

- [ ] **Step 2: Configure FortiWeb trial**

Use FortiWeb UI/CLI to configure:

```txt
virtual server: <FORTIWEB_PUBLIC_HOST>:443
server pool: external landing origin
server policy: landing-waf-policy
protection profile: SQLi/path traversal/DoS enabled
logging: Attack, Traffic, Event enabled
forwarding: POST/syslog to FortiDashboard API
```

Expected: browser can reach the landing page through FortiWeb.

- [ ] **Step 3: Install FortiWeb add-on**

In FortiDashboard:

```txt
Settings -> Marketplace -> FortiWeb WAF -> Install
```

Expected: add-on shows `Installed`.

- [ ] **Step 4: Generate safe WAF attack**

```bash
curl -k "https://<FORTIWEB_PUBLIC_HOST>/demo/search?q=%27%20OR%201%3D1--"
curl -k "https://<FORTIWEB_PUBLIC_HOST>/.env"
```

Expected: FortiWeb logs Attack events.

- [ ] **Step 5: Generate controlled DoS signal**

```bash
hey -z 20s -q 5 -c 20 "https://<FORTIWEB_PUBLIC_HOST>/"
```

Expected: FortiWeb logs DoS/rate activity or aggregated attack activity. Stop immediately if FortiWeb or origin health degrades unexpectedly.

- [ ] **Step 6: Verify backend ingestion**

```bash
docker compose logs --tail=150 api
docker compose logs --tail=150 siem-kowalski
```

Expected:

```txt
api: soc.fortiweb_events.ingested
siem-kowalski: siem_event_ingested
```

- [ ] **Step 7: Verify cockpit**

In browser:

```txt
SOC Tickets -> new FortiWeb incident exists
Recent Incidents widget -> WAF incident appears without refresh
Incident toast -> appears through SSE
SOAR Playbooks -> FortiWeb recommendation action exists and is dry-run
Audit drawer -> FortiWeb ingestion summary appears
```

- [ ] **Step 8: Run final test suite**

```bash
git diff --check
docker compose config --quiet
cd apps/api && uv run ruff check . && uv run pytest -q
cd ../siem_kowalski && uv run ruff check . && uv run pytest -q
cd ../soar_skipper && uv run pytest -q
cd ../web && pnpm test && pnpm build
```

Expected: all checks pass. Vite chunk-size warnings are acceptable unless build exits non-zero.

---

## Execution Order

Recommended order:

1. Task 1: runbook first so the lab contract is explicit.
2. Task 2: add-on package in registry.
3. Task 3: API FortiWeb ingest.
4. Task 4: SIEM detections.
5. Task 5: marketplace install UX.
6. Task 6: response boundary ADR.
7. Task 7: SOAR recommendation node.
8. Task 8: product docs.
9. Task 9: end-to-end lab validation.

Do not implement live FortiGate/FortiWeb writes until the ADR from Task 6 is
approved and amended with exact API paths, preflight checks, rollback behavior,
RBAC, and audit payloads.

## Self-Review

- Spec coverage: Covers external landing boundary, registry add-on, API ingest,
  SIEM incidents, marketplace UX, SOAR response, product docs, and E2E lab
  validation.
- Placeholder scan: No unfinished markers or unspecified implementation steps
  remain.
- Type consistency: Event names are consistently `waf.attack`, `waf.dos`,
  `waf.blocked_request`, and `http.attack`; marketplace add-on id is consistently
  `fortiweb-waf`.
