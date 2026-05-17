# SOC Policy Manager Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first workspace-based administrative policy manager for FortiGate now, with the common provider contract required to attach FortiWeb policy management when the FortiWeb connector branch lands.

**Architecture:** Add a provider-agnostic policy service under `apps/api/app/policies/`, expose `/api/policies/*` through the BFF, then add a Vue widget that consumes that contract through a Pinia store. FortiGate is implemented in this plan because its code is present in this worktree; FortiWeb is integrated through the same contract after the parallel FortiWeb connector files are merged.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy-ready service seams, existing FortiGate integration client/service, Vue 3, Pinia, Vite/Vitest, Tailwind, Lucide Vue, vue-i18n.

---

## File Structure

- Create `docs/architecture/decisions/ADR-2026-05-17-admin-policy-manager.md`: expands the accepted write boundary so admins can manage all policies.
- Modify `apps/api/app/auth/permissions.py`: add `policies.manage`.
- Modify `apps/web/src/i18n/messages/en-US.ts` and `apps/web/src/i18n/messages/pt-BR.ts`: add permission labels and policy widget strings.
- Create `apps/api/app/policies/models.py`: shared Pydantic models and enums.
- Create `apps/api/app/policies/adapters.py`: provider adapter protocols.
- Create `apps/api/app/policies/service.py`: provider registry, inventory fan-out, review and apply dispatch.
- Create `apps/api/app/policies/fortigate_adapter.py`: maps FortiGate policies to normalized rows and applies FortiGate actions.
- Create `apps/api/app/routers/policies.py`: BFF endpoints.
- Modify `apps/api/app/main.py`: include the new router.
- Modify `apps/api/app/integrations/fortigate/client.py` and `service.py`: add update/delete firewall policy helpers.
- Create `apps/api/tests/test_policies.py`: policy manager API/service tests.
- Create `apps/web/src/services/policiesClient.ts`: frontend API client.
- Create `apps/web/src/stores/usePoliciesStore.ts`: Pinia state/actions.
- Create `apps/web/src/components/widgets/policies/WidgetSocPolicyManager.vue`: widget UI.
- Modify `apps/web/src/components/canvas/DashboardCanvas.vue`: register the widget renderer.
- Modify `packages/contracts/fixtures/widget_catalog_soc.json`: add widget preset.
- Modify `apps/web/src/components/integrations/LabPolicyWizard.vue` and `apps/web/src/components/layout/Sidebar.vue`: remove drawer dependency after the widget exposes the lab policy create action.
- Create `apps/web/tests/unit/policiesStore.test.ts` and `apps/web/tests/unit/widgetPolicyManager.test.ts`.

## Task 1: Permission And ADR Boundary

**Files:**
- Create: `docs/architecture/decisions/ADR-2026-05-17-admin-policy-manager.md`
- Modify: `apps/api/app/auth/permissions.py`
- Modify: `apps/web/src/i18n/messages/en-US.ts`
- Modify: `apps/web/src/i18n/messages/pt-BR.ts`
- Test: `apps/api/tests/test_policies.py`

- [ ] **Step 1: Write the failing permission catalog test**

Add this to the top of `apps/api/tests/test_policies.py`:

```python
from app.auth.permissions import VALID_PERMISSION_SLUGS


def test_policy_manager_permission_is_registered() -> None:
    assert "policies.manage" in VALID_PERMISSION_SLUGS
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd apps/api && uv run pytest -q tests/test_policies.py::test_policy_manager_permission_is_registered
```

Expected: fail with an assertion that `policies.manage` is not in the catalog.

- [ ] **Step 3: Add the permission slug**

Append this `PermissionDef` to `PERMISSION_CATALOG` in `apps/api/app/auth/permissions.py`:

```python
    PermissionDef(
        slug="policies.manage",
        category="policies",
        label_key="settings.roles.permission.policies.manage.label",
        description_key="settings.roles.permission.policies.manage.description",
    ),
```

- [ ] **Step 4: Add i18n labels**

In `apps/web/src/i18n/messages/en-US.ts`, add under `settings.roles.permission`:

```ts
'policies.manage': {
  label: 'Manage SOC policies',
  description: 'Create, edit, disable, enable and remove provider policies.',
},
```

In `apps/web/src/i18n/messages/pt-BR.ts`, add under `settings.roles.permission`:

```ts
'policies.manage': {
  label: 'Gerenciar policies SOC',
  description: 'Criar, editar, desabilitar, habilitar e remover policies dos provedores.',
},
```

- [ ] **Step 5: Write the ADR**

Create `docs/architecture/decisions/ADR-2026-05-17-admin-policy-manager.md`:

```markdown
# ADR 2026-05-17: Administrative SOC Policy Manager

## Status

Accepted.

## Context

FortiDashboard currently limits FortiGate policy writes to FortiDashboard-owned
objects. The product direction now requires an administrative workspace widget
that can view and manage every policy exposed by connected SOC providers.

## Decision

FortiDashboard may let permitted administrators create, edit, enable, disable
and remove policies returned by connected SOC providers, including policies not
created by FortiDashboard. Reordering policy priority remains out of scope for
the MVP.

Every write must go through the BFF with permission `policies.manage`, CSRF
protection, preflight, provider-specific diff, explicit confirmation, audit
events and rollback guidance. Audit details must identify provider type,
integration id, native policy id, ownership and whether the policy was
FortiDashboard-owned or external/customer-owned.

AI, SIEM detections, background jobs and browser state may not apply or approve
policy changes by themselves.

## Consequences

The FortiGate policy orchestration ADR remains valid for governed writes, but
its FortiDashboard-owned-only restriction is superseded for human-confirmed
administrator actions through the SOC Policy Manager. Provider adapters must
disable unsupported actions and must reject stale reviews if provider state
changes between review and apply.
```

- [ ] **Step 6: Run the permission test**

Run:

```bash
cd apps/api && uv run pytest -q tests/test_policies.py::test_policy_manager_permission_is_registered
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/auth/permissions.py apps/api/tests/test_policies.py apps/web/src/i18n/messages/en-US.ts apps/web/src/i18n/messages/pt-BR.ts docs/architecture/decisions/ADR-2026-05-17-admin-policy-manager.md
git commit -m "feat(auth): add SOC policy management permission"
```

## Task 2: Backend Policy Contract And Router

**Files:**
- Create: `apps/api/app/policies/models.py`
- Create: `apps/api/app/policies/adapters.py`
- Create: `apps/api/app/policies/service.py`
- Create: `apps/api/app/routers/policies.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_policies.py`

- [ ] **Step 1: Add failing API tests with a fake service**

Append to `apps/api/tests/test_policies.py`:

```python
from fastapi.testclient import TestClient

from app.auth import dependencies as auth_dependencies
from app.main import app
from app.routers import policies as policies_router

client = TestClient(app)


def csrf_headers() -> dict[str, str]:
    response = client.get("/api/auth/csrf")
    return {"X-CSRF-Token": response.json()["csrfToken"]}


class FakePolicyService:
    def list_providers(self, *, owner_user_id: str) -> dict:
        assert owner_user_id == "usr_admin"
        return {
            "items": [
                {
                    "providerType": "fortigate",
                    "integrationId": "int_fgt_01",
                    "name": "FortiGate Lab",
                    "capabilities": ["list", "create", "edit", "enable", "disable", "delete"],
                    "policyKinds": ["firewall_policy", "lab_allow_log", "temporary_block"],
                }
            ]
        }

    def list_policies(self, *, owner_user_id: str, filters: dict) -> dict:
        assert owner_user_id == "usr_admin"
        assert filters["providerType"] == "fortigate"
        return {
            "items": [
                {
                    "id": "fortigate:int_fgt_01:policy:10",
                    "providerType": "fortigate",
                    "integrationId": "int_fgt_01",
                    "nativeId": "10",
                    "name": "LAN to WAN",
                    "kind": "firewall_policy",
                    "status": "enabled",
                    "action": "accept",
                    "direction": {"source": "port2", "destination": "port3"},
                    "scope": {"source": ["LAN_NET"], "destination": ["WAN_NET"], "service": ["HTTPS"]},
                    "ownership": "external",
                    "managedByFortiDashboard": False,
                    "isMutable": True,
                    "supports": ["edit", "disable", "delete"],
                    "risk": {"level": "medium", "reasons": ["Allows traffic"]},
                    "summary": "accept HTTPS from LAN_NET to WAN_NET",
                    "lastObservedAt": "2026-05-17T12:00:00.000Z",
                }
            ],
            "nextCursor": None,
        }

    def create_review(self, *, owner_user_id: str, payload):
        assert owner_user_id == "usr_admin"
        return {
            "id": "policy_review_01",
            "providerType": payload.provider_type,
            "integrationId": payload.integration_id,
            "policyId": payload.policy_id,
            "action": payload.action,
            "status": "pending_review",
            "title": "Disable LAN to WAN",
            "before": {"summary": "enabled"},
            "after": {"summary": "disabled"},
            "diff": [{"field": "status", "before": "enabled", "after": "disabled", "risk": "Stops traffic"}],
            "warnings": [{"severity": "high", "message": "External policy"}],
            "rollback": ["Set status back to enabled"],
            "reviewHash": "hash_01",
        }

    def apply_review(self, *, owner_user_id: str, review_id: str, payload):
        assert owner_user_id == "usr_admin"
        assert review_id == "policy_review_01"
        assert payload.confirmed is True
        return {
            "id": "policy_review_01",
            "status": "applied",
            "providerType": "fortigate",
            "integrationId": "int_fgt_01",
            "appliedResult": {"ok": True},
        }


def _admin_user() -> dict:
    return {
        "id": "usr_admin",
        "email": "admin@example.com",
        "displayName": "SOC Admin",
        "roles": ["admin"],
    }


def test_policy_manager_lists_providers_and_inventory() -> None:
    app.dependency_overrides[auth_dependencies.get_current_api_user] = _admin_user
    app.dependency_overrides[policies_router.get_policy_service] = lambda: FakePolicyService()
    try:
        providers = client.get("/api/policies/providers")
        inventory = client.get("/api/policies", params={"providerType": "fortigate"})
    finally:
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)
        app.dependency_overrides.pop(policies_router.get_policy_service, None)

    assert providers.status_code == 200
    assert providers.json()["items"][0]["providerType"] == "fortigate"
    assert inventory.status_code == 200
    assert inventory.json()["items"][0]["name"] == "LAN to WAN"


def test_policy_manager_review_and_apply_require_admin_confirmation() -> None:
    app.dependency_overrides[auth_dependencies.get_current_api_user] = _admin_user
    app.dependency_overrides[policies_router.get_policy_service] = lambda: FakePolicyService()
    try:
        review = client.post(
            "/api/policies/reviews",
            headers=csrf_headers(),
            json={
                "providerType": "fortigate",
                "integrationId": "int_fgt_01",
                "policyId": "fortigate:int_fgt_01:policy:10",
                "action": "disable",
                "payload": {},
            },
        )
        applied = client.post(
            "/api/policies/reviews/policy_review_01/apply",
            headers=csrf_headers(),
            json={"reviewHash": "hash_01", "confirmed": True},
        )
    finally:
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)
        app.dependency_overrides.pop(policies_router.get_policy_service, None)

    assert review.status_code == 201
    assert review.json()["status"] == "pending_review"
    assert applied.status_code == 200
    assert applied.json()["status"] == "applied"
```

- [ ] **Step 2: Run the tests to verify router is missing**

Run:

```bash
cd apps/api && uv run pytest -q tests/test_policies.py
```

Expected: fail because `app.routers.policies` does not exist.

- [ ] **Step 3: Create Pydantic models**

Create `apps/api/app/policies/models.py`:

```python
from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class PolicyProviderType(StrEnum):
    FORTIGATE = "fortigate"
    FORTIWEB = "fortiweb"


class PolicyAction(StrEnum):
    CREATE = "create"
    EDIT = "edit"
    ENABLE = "enable"
    DISABLE = "disable"
    DELETE = "delete"


class PolicyOwnership(StrEnum):
    FORTIDASHBOARD = "fortidashboard"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class PolicyProviderSummary(BaseModel):
    provider_type: PolicyProviderType = Field(alias="providerType")
    integration_id: str = Field(alias="integrationId")
    name: str
    capabilities: list[str]
    policy_kinds: list[str] = Field(alias="policyKinds")
    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)


class PolicyRow(BaseModel):
    id: str
    provider_type: PolicyProviderType = Field(alias="providerType")
    integration_id: str = Field(alias="integrationId")
    native_id: str = Field(alias="nativeId")
    name: str
    kind: str
    status: str
    action: str | None = None
    direction: dict[str, Any] = Field(default_factory=dict)
    scope: dict[str, Any] = Field(default_factory=dict)
    ownership: PolicyOwnership = PolicyOwnership.UNKNOWN
    managed_by_fortidashboard: bool = Field(default=False, alias="managedByFortiDashboard")
    is_mutable: bool = Field(default=False, alias="isMutable")
    supports: list[str] = Field(default_factory=list)
    risk: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    last_observed_at: str | None = Field(default=None, alias="lastObservedAt")
    raw: dict[str, Any] | None = None
    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)


class PolicyListResponse(BaseModel):
    items: list[PolicyRow]
    next_cursor: str | None = Field(default=None, alias="nextCursor")
    model_config = ConfigDict(populate_by_name=True)


class PolicyReviewCreateRequest(BaseModel):
    provider_type: PolicyProviderType = Field(alias="providerType")
    integration_id: str = Field(alias="integrationId")
    action: PolicyAction
    policy_id: str | None = Field(default=None, alias="policyId")
    payload: dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)


class PolicyReviewResponse(BaseModel):
    id: str
    provider_type: PolicyProviderType = Field(alias="providerType")
    integration_id: str = Field(alias="integrationId")
    policy_id: str | None = Field(default=None, alias="policyId")
    action: PolicyAction
    status: Literal["pending_review", "applied", "failed"]
    title: str
    before: dict[str, Any]
    after: dict[str, Any]
    diff: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    rollback: list[str]
    review_hash: str = Field(alias="reviewHash")
    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)


class PolicyReviewApplyRequest(BaseModel):
    review_hash: str = Field(alias="reviewHash")
    confirmed: bool
    model_config = ConfigDict(populate_by_name=True)
```

- [ ] **Step 4: Create adapter protocol and service**

Create `apps/api/app/policies/adapters.py`:

```python
from __future__ import annotations

from typing import Protocol

from app.policies.models import (
    PolicyListResponse,
    PolicyProviderSummary,
    PolicyReviewApplyRequest,
    PolicyReviewCreateRequest,
    PolicyReviewResponse,
)


class PolicyProviderAdapter(Protocol):
    provider_type: str

    def provider_summary(self, *, owner_user_id: str) -> list[PolicyProviderSummary]:
        pass

    def list_policies(self, *, owner_user_id: str, filters: dict) -> PolicyListResponse:
        pass

    def create_review(
        self,
        *,
        owner_user_id: str,
        payload: PolicyReviewCreateRequest,
    ) -> PolicyReviewResponse:
        pass

    def apply_review(
        self,
        *,
        owner_user_id: str,
        review_id: str,
        payload: PolicyReviewApplyRequest,
    ) -> dict:
        pass
```

Create `apps/api/app/policies/service.py`:

```python
from __future__ import annotations

from fastapi import HTTPException, status

from app.policies.adapters import PolicyProviderAdapter
from app.policies.models import PolicyListResponse, PolicyReviewApplyRequest, PolicyReviewCreateRequest


class PolicyService:
    def __init__(self, adapters: list[PolicyProviderAdapter]) -> None:
        self.adapters = {adapter.provider_type: adapter for adapter in adapters}

    def list_providers(self, *, owner_user_id: str) -> dict:
        items = []
        for adapter in self.adapters.values():
            items.extend(
                item.model_dump(mode="json", by_alias=True)
                for item in adapter.provider_summary(owner_user_id=owner_user_id)
            )
        return {"items": items}

    def list_policies(self, *, owner_user_id: str, filters: dict) -> dict:
        provider_type = filters.get("providerType")
        adapters = [self._adapter(provider_type)] if provider_type else list(self.adapters.values())
        rows = []
        for adapter in adapters:
            result: PolicyListResponse = adapter.list_policies(
                owner_user_id=owner_user_id,
                filters=filters,
            )
            rows.extend(row.model_dump(mode="json", by_alias=True) for row in result.items)
        return {"items": rows, "nextCursor": None}

    def create_review(self, *, owner_user_id: str, payload: PolicyReviewCreateRequest) -> dict:
        review = self._adapter(payload.provider_type).create_review(
            owner_user_id=owner_user_id,
            payload=payload,
        )
        return review.model_dump(mode="json", by_alias=True)

    def apply_review(
        self,
        *,
        owner_user_id: str,
        review_id: str,
        payload: PolicyReviewApplyRequest,
    ) -> dict:
        provider_type = review_id.split(":", 1)[0] if ":" in review_id else "fortigate"
        return self._adapter(provider_type).apply_review(
            owner_user_id=owner_user_id,
            review_id=review_id,
            payload=payload,
        )

    def _adapter(self, provider_type: str | None) -> PolicyProviderAdapter:
        if not provider_type or provider_type not in self.adapters:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Policy provider not available",
            )
        return self.adapters[provider_type]
```

- [ ] **Step 5: Create router and include it**

Create `apps/api/app/routers/policies.py`:

```python
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.auth.dependencies import get_current_api_user, require_csrf
from app.auth.permissions import require_permission
from app.policies.models import PolicyReviewApplyRequest, PolicyReviewCreateRequest
from app.policies.service import PolicyService

router = APIRouter(prefix="/api", tags=["policies"])


def get_policy_service() -> PolicyService:
    return PolicyService(adapters=[])


def _owner_user_id(current_user: dict) -> str:
    return str(current_user.get("id") or current_user.get("user_id"))


@router.get("/policies/providers")
def list_policy_providers(
    service: Annotated[PolicyService, Depends(get_policy_service)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    return service.list_providers(owner_user_id=_owner_user_id(current_user))


@router.get("/policies")
def list_policies(
    service: Annotated[PolicyService, Depends(get_policy_service)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    provider_type: Annotated[str | None, Query(alias="providerType")] = None,
    integration_id: Annotated[str | None, Query(alias="integrationId")] = None,
    kind: str | None = None,
    policy_status: Annotated[str | None, Query(alias="status")] = None,
    ownership: str | None = None,
    q: str | None = None,
) -> dict:
    return service.list_policies(
        owner_user_id=_owner_user_id(current_user),
        filters={
            "providerType": provider_type,
            "integrationId": integration_id,
            "kind": kind,
            "status": policy_status,
            "ownership": ownership,
            "q": q,
        },
    )


@router.post(
    "/policies/reviews",
    status_code=status.HTTP_201_CREATED,
)
def create_policy_review(
    _request: Request,
    service: Annotated[PolicyService, Depends(get_policy_service)],
    current_user: Annotated[dict, Depends(require_permission("policies.manage"))],
    _csrf: Annotated[None, Depends(require_csrf)],
    payload: PolicyReviewCreateRequest,
) -> dict:
    return service.create_review(owner_user_id=_owner_user_id(current_user), payload=payload)


@router.post("/policies/reviews/{review_id}/apply")
def apply_policy_review(
    review_id: str,
    _response: Response,
    service: Annotated[PolicyService, Depends(get_policy_service)],
    current_user: Annotated[dict, Depends(require_permission("policies.manage"))],
    _csrf: Annotated[None, Depends(require_csrf)],
    payload: PolicyReviewApplyRequest,
) -> dict:
    return service.apply_review(
        owner_user_id=_owner_user_id(current_user),
        review_id=review_id,
        payload=payload,
    )
```

Modify imports in `apps/api/app/main.py` to include `policies`, then add:

```python
app.include_router(policies.router)
```

next to the other router registrations.

- [ ] **Step 6: Run tests**

Run:

```bash
cd apps/api && uv run pytest -q tests/test_policies.py
```

Expected: tests pass.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/policies apps/api/app/routers/policies.py apps/api/app/main.py apps/api/tests/test_policies.py
git commit -m "feat(api): add SOC policy manager contract"
```

## Task 3: FortiGate Adapter Inventory And Actions

**Files:**
- Create: `apps/api/app/policies/fortigate_adapter.py`
- Modify: `apps/api/app/integrations/fortigate/client.py`
- Modify: `apps/api/app/integrations/fortigate/service.py`
- Modify: `apps/api/app/routers/policies.py`
- Test: `apps/api/tests/test_policies.py`

- [ ] **Step 1: Write FortiGate adapter tests**

Append these tests to `apps/api/tests/test_policies.py`:

```python
from app.policies.fortigate_adapter import FortiGatePolicyAdapter
from app.policies.models import PolicyReviewApplyRequest, PolicyReviewCreateRequest


class FakeFortiGatePolicyClient:
    def __init__(self) -> None:
        self.updated: list[tuple[str, dict]] = []
        self.deleted: list[str] = []

    def get_policies(self) -> list[dict]:
        return [{"policyid": 10, "name": "LAN to WAN", "status": "enable", "action": "accept", "srcintf": [{"name": "port2"}], "dstintf": [{"name": "port3"}], "srcaddr": [{"name": "LAN_NET"}], "dstaddr": [{"name": "WAN_NET"}], "service": [{"name": "HTTPS"}]}]

    def update_firewall_policy(self, policy_id: str, payload: dict) -> dict:
        self.updated.append((policy_id, payload))
        return {"updated": policy_id}

    def delete_firewall_policy(self, policy_id: str) -> dict:
        self.deleted.append(policy_id)
        return {"deleted": policy_id}


class FakeFortiGatePolicyService:
    def __init__(self, client: FakeFortiGatePolicyClient) -> None:
        self.client = client

    def list(self, *, owner_user_id: str) -> dict:
        assert owner_user_id == "usr_admin"
        return {"items": [{"id": "int_fgt_01", "name": "FortiGate Lab"}]}

    def client_for_integration(self, integration_id: str, *, owner_user_id: str):
        assert integration_id == "int_fgt_01"
        assert owner_user_id == "usr_admin"
        return self.client


def test_fortigate_policy_adapter_normalizes_inventory() -> None:
    adapter = FortiGatePolicyAdapter(FakeFortiGatePolicyService(FakeFortiGatePolicyClient()))

    result = adapter.list_policies(owner_user_id="usr_admin", filters={})
    row = result.items[0].model_dump(mode="json", by_alias=True)

    assert row["id"] == "fortigate:int_fgt_01:policy:10"
    assert row["providerType"] == "fortigate"
    assert row["ownership"] == "external"
    assert row["managedByFortiDashboard"] is False
    assert row["supports"] == ["edit", "disable", "delete"]
    assert row["scope"]["service"] == ["HTTPS"]


def test_fortigate_policy_adapter_creates_disable_review_and_apply() -> None:
    client = FakeFortiGatePolicyClient()
    adapter = FortiGatePolicyAdapter(FakeFortiGatePolicyService(client))

    review = adapter.create_review(
        owner_user_id="usr_admin",
        payload=PolicyReviewCreateRequest(
            providerType="fortigate",
            integrationId="int_fgt_01",
            policyId="fortigate:int_fgt_01:policy:10",
            action="disable",
            payload={},
        ),
    )
    applied = adapter.apply_review(
        owner_user_id="usr_admin",
        review_id=review.id,
        payload=PolicyReviewApplyRequest(reviewHash=review.review_hash, confirmed=True),
    )

    assert review.status == "pending_review"
    assert review.diff[0]["field"] == "status"
    assert client.updated == [("10", {"status": "disable"})]
    assert applied["status"] == "applied"
    assert applied["appliedResult"] == {"updated": "10"}
```

- [ ] **Step 2: Add FortiGate client helpers**

In `apps/api/app/integrations/fortigate/client.py`, add:

```python
def update_firewall_policy(self, policy_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    results = self._put(f"/api/v2/cmdb/firewall/policy/{policy_id}", json=payload)
    if not isinstance(results, dict):
        raise FortiGateApiError("FortiGate firewall policy update response was not an object")
    return results

def delete_firewall_policy(self, policy_id: str) -> dict[str, Any]:
    results = self._delete(f"/api/v2/cmdb/firewall/policy/{policy_id}")
    if not isinstance(results, dict):
        raise FortiGateApiError("FortiGate firewall policy delete response was not an object")
    return results
```

Add `_delete()` mirroring `_put()` with `client.delete(path)`.

Update the `FortiGateClient` Protocol and `MockFortiGateIntegrationService` in
`apps/api/app/integrations/fortigate/service.py` with matching methods.

- [ ] **Step 3: Implement adapter**

Create `apps/api/app/policies/fortigate_adapter.py` with:

```python
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from app.policies.models import (
    PolicyListResponse,
    PolicyOwnership,
    PolicyProviderSummary,
    PolicyReviewApplyRequest,
    PolicyReviewCreateRequest,
    PolicyReviewResponse,
    PolicyRow,
)


class FortiGatePolicyAdapter:
    provider_type = "fortigate"

    def __init__(self, fortigate_service) -> None:
        self.fortigate_service = fortigate_service
        self._reviews: dict[str, dict[str, Any]] = {}

    def provider_summary(self, *, owner_user_id: str) -> list[PolicyProviderSummary]:
        items = self.fortigate_service.list(owner_user_id=owner_user_id).get("items", [])
        return [
            PolicyProviderSummary(
                providerType="fortigate",
                integrationId=item["id"],
                name=item.get("name") or item.get("host") or item["id"],
                capabilities=["list", "create", "edit", "enable", "disable", "delete"],
                policyKinds=["firewall_policy", "lab_allow_log", "temporary_block"],
            )
            for item in items
        ]

    def list_policies(self, *, owner_user_id: str, filters: dict) -> PolicyListResponse:
        integration_id = filters.get("integrationId")
        rows: list[PolicyRow] = []
        integrations = self.fortigate_service.list(owner_user_id=owner_user_id).get("items", [])
        for integration in integrations:
            if integration_id and integration["id"] != integration_id:
                continue
            client = self.fortigate_service.client_for_integration(
                integration["id"],
                owner_user_id=owner_user_id,
            )
            for policy in client.get_policies():
                rows.append(_row(integration["id"], policy))
        return PolicyListResponse(items=rows, nextCursor=None)

    def create_review(
        self,
        *,
        owner_user_id: str,
        payload: PolicyReviewCreateRequest,
    ) -> PolicyReviewResponse:
        review_id = f"fortigate:{hashlib.sha256(json.dumps(payload.model_dump(mode='json'), sort_keys=True).encode()).hexdigest()[:12]}"
        before = {"summary": "current provider state"}
        after = {"summary": f"{payload.action} requested"}
        review_hash = hashlib.sha256(json.dumps({"id": review_id, "payload": payload.model_dump(mode="json")}, sort_keys=True).encode()).hexdigest()
        review = PolicyReviewResponse(
            id=review_id,
            providerType="fortigate",
            integrationId=payload.integration_id,
            policyId=payload.policy_id,
            action=payload.action,
            status="pending_review",
            title=f"{payload.action} FortiGate policy",
            before=before,
            after=after,
            diff=[{"field": "status", "before": before["summary"], "after": after["summary"], "risk": "Policy behavior changes"}],
            warnings=[{"severity": "high", "message": "This may modify an external/customer-owned policy."}],
            rollback=["Run a new review restoring the previous FortiGate policy fields."],
            reviewHash=review_hash,
        )
        self._reviews[review_id] = {"review": review, "payload": payload}
        return review

    def apply_review(
        self,
        *,
        owner_user_id: str,
        review_id: str,
        payload: PolicyReviewApplyRequest,
    ) -> dict:
        stored = self._reviews.get(review_id)
        if stored is None:
            raise KeyError("Policy review not found")
        review: PolicyReviewResponse = stored["review"]
        if review.review_hash != payload.review_hash:
            raise ValueError("Stale policy review")
        if not payload.confirmed:
            raise PermissionError("Explicit confirmation is required")
        request_payload: PolicyReviewCreateRequest = stored["payload"]
        client = self.fortigate_service.client_for_integration(
            review.integration_id,
            owner_user_id=owner_user_id,
        )
        native_id = _native_policy_id(request_payload.policy_id)
        if request_payload.action == "disable":
            result = client.update_firewall_policy(native_id, {"status": "disable"})
        elif request_payload.action == "enable":
            result = client.update_firewall_policy(native_id, {"status": "enable"})
        elif request_payload.action == "delete":
            result = client.delete_firewall_policy(native_id)
        elif request_payload.action == "edit":
            result = client.update_firewall_policy(native_id, request_payload.payload)
        else:
            raise ValueError(f"Unsupported FortiGate policy action: {request_payload.action}")
        return {"id": review_id, "status": "applied", "providerType": "fortigate", "integrationId": review.integration_id, "appliedResult": result}


def _row(integration_id: str, policy: dict[str, Any]) -> PolicyRow:
    native_id = str(policy.get("policyid") or policy.get("id") or policy.get("name"))
    name = str(policy.get("name") or f"Policy {native_id}")
    owned = name.startswith("FD_") or "fortidashboard" in str(policy.get("comments") or "").lower()
    return PolicyRow(
        id=f"fortigate:{integration_id}:policy:{native_id}",
        providerType="fortigate",
        integrationId=integration_id,
        nativeId=native_id,
        name=name,
        kind="firewall_policy",
        status="enabled" if policy.get("status") in ("enable", "enabled") else "disabled",
        action=str(policy.get("action") or ""),
        direction={"source": _names(policy.get("srcintf")), "destination": _names(policy.get("dstintf"))},
        scope={"source": _names(policy.get("srcaddr")), "destination": _names(policy.get("dstaddr")), "service": _names(policy.get("service"))},
        ownership=PolicyOwnership.FORTIDASHBOARD if owned else PolicyOwnership.EXTERNAL,
        managedByFortiDashboard=owned,
        isMutable=True,
        supports=["edit", "disable" if policy.get("status") in ("enable", "enabled") else "enable", "delete"],
        risk={"level": "medium", "reasons": ["Firewall policy controls traffic flow"]},
        summary=f"{policy.get('action', 'policy')} {name}",
        lastObservedAt=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    )


def _names(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item.get("name") if isinstance(item, dict) else item) for item in value]
    if value in (None, ""):
        return []
    return [str(value)]


def _native_policy_id(policy_id: str | None) -> str:
    if not policy_id:
        raise ValueError("policyId is required")
    return policy_id.rsplit(":", 1)[-1]
```

- [ ] **Step 4: Wire adapter in router dependency**

In `apps/api/app/routers/policies.py`, import integrations router and adapter:

```python
from app.policies.fortigate_adapter import FortiGatePolicyAdapter
from app.routers import integrations
```

Change `get_policy_service()`:

```python
def get_policy_service() -> PolicyService:
    return PolicyService(
        adapters=[
            FortiGatePolicyAdapter(integrations.get_fortigate_integration_service()),
        ]
    )
```

- [ ] **Step 5: Run tests**

```bash
cd apps/api && uv run pytest -q tests/test_policies.py tests/test_fortigate_client.py tests/test_fortigate_policy_orchestrator.py
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/policies/fortigate_adapter.py apps/api/app/routers/policies.py apps/api/app/integrations/fortigate/client.py apps/api/app/integrations/fortigate/service.py apps/api/tests/test_policies.py apps/api/tests/test_fortigate_client.py
git commit -m "feat(api): expose FortiGate policies through policy manager"
```

## Task 4: Frontend Client And Store

**Files:**
- Create: `apps/web/src/services/policiesClient.ts`
- Create: `apps/web/src/stores/usePoliciesStore.ts`
- Test: `apps/web/tests/unit/policiesStore.test.ts`

- [ ] **Step 1: Write store tests**

Create `apps/web/tests/unit/policiesStore.test.ts` with tests for loading providers, inventory, review and apply. Use `vi.stubGlobal('fetch', fetcher)`, assert calls include `credentials: 'include'`, and assert mutating calls include `X-CSRF-Token`.

- [ ] **Step 2: Create client**

Create `apps/web/src/services/policiesClient.ts` with exported types matching the API contract and functions:

```ts
export async function fetchPolicyProviders(): Promise<PolicyProviderSummary[]>
export async function fetchPolicies(filters: PolicyFilters = {}): Promise<PolicyListResponse>
export async function createPolicyReview(payload: PolicyReviewCreateRequest, csrfToken: string): Promise<PolicyReview>
export async function applyPolicyReview(reviewId: string, payload: PolicyReviewApplyRequest, csrfToken: string): Promise<PolicyApplyResult>
```

- [ ] **Step 3: Create Pinia store**

Create `apps/web/src/stores/usePoliciesStore.ts` with state:

```ts
providers: PolicyProviderSummary[]
policies: PolicyRow[]
selectedReview: PolicyReview | null
lastApplyResult: PolicyApplyResult | null
isLoading: boolean
error: string | null
```

Actions:

```ts
loadProviders()
loadPolicies(filters?: PolicyFilters)
reviewPolicy(payload: PolicyReviewCreateRequest)
applyReview(reviewId: string, reviewHash: string)
```

Use `useAuthStore().fetchCsrf()` before mutations.

- [ ] **Step 4: Run frontend store tests**

```bash
cd apps/web && pnpm test -- tests/unit/policiesStore.test.ts --runInBand
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/services/policiesClient.ts apps/web/src/stores/usePoliciesStore.ts apps/web/tests/unit/policiesStore.test.ts
git commit -m "feat(web): add SOC policy manager store"
```

## Task 5: Widget UI And Catalog

**Files:**
- Create: `apps/web/src/components/widgets/policies/WidgetSocPolicyManager.vue`
- Modify: `apps/web/src/components/canvas/DashboardCanvas.vue`
- Modify: `packages/contracts/fixtures/widget_catalog_soc.json`
- Modify: `apps/web/src/i18n/messages/en-US.ts`
- Modify: `apps/web/src/i18n/messages/pt-BR.ts`
- Test: `apps/web/tests/unit/widgetPolicyManager.test.ts`

- [ ] **Step 1: Write widget tests**

Create `apps/web/tests/unit/widgetPolicyManager.test.ts` asserting:

- mixed FortiGate/FortiWeb rows render provider labels;
- users without `policies.manage` do not see action buttons;
- users with `policies.manage` see create/edit/disable/delete actions;
- review warnings and rollback guidance render after store review result.

- [ ] **Step 2: Implement widget**

Create `WidgetSocPolicyManager.vue` using `WidgetShell` with:

- glance counters;
- drill inventory table;
- detail modal action form;
- action menu disabled when `!authStore.hasPermission('policies.manage')`.

Use existing Lucide icons such as `ShieldCheck`, `ListChecks`, `Pencil`, `Power`, `Trash2`.

- [ ] **Step 3: Register widget renderer**

In `DashboardCanvas.vue`, import:

```ts
import WidgetSocPolicyManager from '../widgets/policies/WidgetSocPolicyManager.vue'
```

Add to `widgetMap`:

```ts
'soc-policy-manager': WidgetSocPolicyManager,
```

- [ ] **Step 4: Add catalog preset**

Add to `packages/contracts/fixtures/widget_catalog_soc.json`:

```json
{
  "id": "soc-policy-manager",
  "title": "SOC Policy Manager",
  "kind": "admin",
  "source": "soc",
  "requiredCapabilities": ["policies"],
  "defaultSize": { "w": 7, "h": 5 },
  "dataEndpoint": "/api/policies"
}
```

- [ ] **Step 5: Add i18n strings**

Add `widgets.policyManager.*` keys in both locales for title, subtitle, empty state, filters, action labels, warning labels and rollback labels.

- [ ] **Step 6: Run widget tests**

```bash
cd apps/web && pnpm test -- tests/unit/widgetPolicyManager.test.ts tests/unit/widgetRenderers.test.ts --runInBand
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/components/widgets/policies/WidgetSocPolicyManager.vue apps/web/src/components/canvas/DashboardCanvas.vue packages/contracts/fixtures/widget_catalog_soc.json apps/web/src/i18n/messages/en-US.ts apps/web/src/i18n/messages/pt-BR.ts apps/web/tests/unit/widgetPolicyManager.test.ts
git commit -m "feat(web): add SOC policy manager widget"
```

## Task 6: Remove Integration Drawer Policy Wizard Path

**Files:**
- Modify: `apps/web/src/components/layout/Sidebar.vue`
- Modify: `apps/web/src/components/integrations/LabPolicyWizard.vue`
- Test: `apps/web/tests/unit/sidebarIntegrations.test.ts`

- [ ] **Step 1: Update sidebar test expectation**

Change the existing `sidebarIntegrations.test.ts` policy wizard expectation so it asserts the drawer no longer renders `fortigate-lab-policy-wizard-*` and instead includes a short policy-manager handoff message.

- [ ] **Step 2: Remove drawer render**

Remove:

```vue
<LabPolicyWizard :integration-id="intg.id" />
```

from `Sidebar.vue`.

- [ ] **Step 3: Delete the integration-drawer component**

Delete `apps/web/src/components/integrations/LabPolicyWizard.vue`. The policy
creation form now lives in `WidgetSocPolicyManager.vue` or in
`apps/web/src/components/widgets/policies/FortiGatePolicyForm.vue` if the widget
needs a focused child component.

- [ ] **Step 4: Run sidebar tests**

```bash
cd apps/web && pnpm test -- tests/unit/sidebarIntegrations.test.ts --runInBand
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/layout/Sidebar.vue apps/web/src/components/integrations/LabPolicyWizard.vue apps/web/tests/unit/sidebarIntegrations.test.ts
git commit -m "refactor(web): move policy workflow out of integrations drawer"
```

## Task 7: FortiWeb Adapter Integration Checkpoint

**Files after FortiWeb branch merge:**
- Create: `apps/api/app/policies/fortiweb_adapter.py`
- Modify: `apps/api/app/routers/policies.py`
- Modify: `apps/web/src/components/widgets/policies/WidgetSocPolicyManager.vue`
- Test: `apps/api/tests/test_policies.py`
- Test: `apps/web/tests/unit/widgetPolicyManager.test.ts`

- [ ] **Step 1: Verify FortiWeb files exist**

Run:

```bash
test -f apps/api/app/integrations/fortiweb/service.py
test -f apps/api/tests/test_fortiweb_integrations.py
```

Expected: both commands exit 0. If either file is missing, pause this task and continue only after the FortiWeb connector branch is merged.

- [ ] **Step 2: Add FortiWeb adapter tests**

Add tests that assert FortiWeb provider summary includes `server_policy`, `ip_blocklist` and `source_ip_block`, and that block review/apply/remove contracts are reachable through `/api/policies/reviews`.

- [ ] **Step 3: Implement `FortiWebPolicyAdapter`**

Map:

- `targetServerPolicy` to a `server_policy` row;
- `managedIpListPolicy` to an `ip_blocklist` row;
- list block requests to `source_ip_block` rows;
- `create` to source-IP block review;
- `delete` to source-IP block remove;
- `enable`/`disable` to the adapter-supported equivalent, or return `409` if the connector cannot perform that action safely.

- [ ] **Step 4: Wire FortiWeb adapter**

In `get_policy_service()`, append:

```python
FortiWebPolicyAdapter(integrations.get_fortiweb_integration_service())
```

only after the FortiWeb integration service dependency exists in this worktree.

- [ ] **Step 5: Run tests**

```bash
cd apps/api && uv run pytest -q tests/test_policies.py tests/test_fortiweb_integrations.py
cd apps/web && pnpm test -- tests/unit/widgetPolicyManager.test.ts --runInBand
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/policies/fortiweb_adapter.py apps/api/app/routers/policies.py apps/api/tests/test_policies.py apps/web/src/components/widgets/policies/WidgetSocPolicyManager.vue apps/web/tests/unit/widgetPolicyManager.test.ts
git commit -m "feat(policies): connect FortiWeb policy management"
```

## Task 8: Final Verification

**Files:**
- No planned source edits.

- [ ] **Step 1: Run API checks**

```bash
cd apps/api && uv run ruff check . && uv run pytest -q tests/test_policies.py tests/test_fortigate_client.py tests/test_fortigate_policy_orchestrator.py tests/test_fortigate_integrations.py
```

- [ ] **Step 2: Run web checks**

```bash
cd apps/web && pnpm test -- tests/unit/policiesStore.test.ts tests/unit/widgetPolicyManager.test.ts tests/unit/sidebarIntegrations.test.ts --runInBand
cd apps/web && pnpm build
```

- [ ] **Step 3: Run repo checks**

```bash
git diff --check
docker compose config --quiet
```

- [ ] **Step 4: Commit verification/doc adjustments**

If verification changes docs or tests, commit them:

```bash
git add docs/product/feature-map.md docs/product/roadmap.md docs/product/release-notes.md
git commit -m "docs(product): document SOC policy manager"
```

Do not create an empty commit when verification requires no documentation
changes.
