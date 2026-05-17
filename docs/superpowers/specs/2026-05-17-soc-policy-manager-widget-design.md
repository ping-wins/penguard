# SOC Policy Manager Widget Design

**Status:** Accepted for planning
**Date:** 2026-05-17
**Related:**
[`2026-05-15-fortigate-policy-orchestration-design.md`](2026-05-15-fortigate-policy-orchestration-design.md),
[`../../architecture/decisions/ADR-2026-05-15-fortigate-policy-orchestration.md`](../../architecture/decisions/ADR-2026-05-15-fortigate-policy-orchestration.md),
[`2026-05-17-roles-permissions-manager-design.md`](2026-05-17-roles-permissions-manager-design.md)

## Context

FortiDashboard already has governed FortiGate policy orchestration, but the
main creation flow lives in `apps/web/src/components/integrations/LabPolicyWizard.vue`
inside the integrations drawer. That makes policy work feel like setup
plumbing instead of a daily SOC/admin workflow. The canvas already has a
read-only FortiGate firewall policies widget, but administrators need a
first-class administrative policy console inside the workspace.

The first version must support FortiGate and FortiWeb. FortiGate already has
policy preflight/review/apply endpoints. FortiWeb work is being developed in a
parallel branch and exposes the product shape that matters for this design:
server policy context, a managed IP-list policy, and source-IP block
review/apply/remove actions. This spec defines the common product and backend
contract so both providers can plug into one workspace widget without forcing
FortiGate and FortiWeb into the same internal object model.

## Confirmed Product Decisions

- The policy manager is a workspace canvas widget, not a hidden integration
  drawer helper.
- It is administrative: users with the correct admin permission can view,
  create, edit, enable, disable and remove policies.
- It shows the full policy inventory returned by each connected provider,
  including policies not created by FortiDashboard.
- Administrators can manage all provider policies in the MVP, not only
  FortiDashboard-owned policies.
- Reordering policies is out of scope for the MVP.
- FortiGate and FortiWeb are real first-cut providers.
- The widget uses one common inventory and review UX, with provider-specific
  editors for create/edit forms.
- Every write still requires server-side permission checks, CSRF protection,
  preflight, diff/review, explicit confirmation, audit, and rollback guidance.

## Boundary Change

The current FortiGate ADR limits live writes to FortiDashboard-owned objects and
policies. This feature intentionally expands the administrator boundary:
permitted administrators may manage any policy exposed by a connected SOC
provider.

Before implementation is considered complete, add a new ADR or amend
`ADR-2026-05-15-fortigate-policy-orchestration.md` with this decision:

- admin policy management can target customer/provider-owned policies;
- reordering stays excluded in the MVP;
- every change must present a provider-specific diff and risk warning;
- audit must distinguish FortiDashboard-owned from external/customer-owned
  targets;
- rollback guidance is mandatory for edit, disable and delete actions.

This does not weaken the AI and automation boundary. AI, SIEM detections,
browser state and background jobs still cannot apply policy changes without a
permitted human admin confirming the review.

## Goals

- Replace the FortiGate `LabPolicyWizard` integration-drawer flow with a
  workspace policy manager action.
- Add a new `soc-policy-manager` widget preset to the catalog.
- Show FortiGate and FortiWeb policy inventory in one normalized table.
- Provide provider-specific create/edit forms inside a shared review flow.
- Support create, edit, enable, disable and remove actions for FortiGate and
  FortiWeb.
- Keep policy writes auditable and reviewable even when an admin targets
  customer-owned policies.
- Introduce a backend policy provider contract that future SOC providers can
  implement.

## Non-Goals

- No policy reordering or priority moves in the MVP.
- No raw arbitrary JSON editor in the frontend.
- No bulk policy changes in the MVP.
- No AI approval or auto-apply path.
- No direct browser-to-provider calls.
- No FortiManager policy-package orchestration in this slice.
- No frontend plugin runtime for add-on-provided policy editors. Editors live in
  the dashboard codebase for now.

## Permission Model

Add a new permission slug to the roles/permissions catalog:

```txt
policies.manage
```

It gates all policy write/review/apply endpoints and the widget's mutating UI.
Legacy Keycloak `admin` continues to bypass through the existing bootstrap rule.

Read access to the widget can be allowed for authenticated users, but mutating
controls must require `policies.manage`. If the product wants inventory
visibility to be admin-only later, the same permission can also gate
`GET /api/policies`.

## Provider Policy Contract

The backend exposes a provider-agnostic policy service. It does not pretend all
providers have the same native policy model. Each adapter maps native provider
objects into normalized inventory rows and accepts provider-specific action
payloads for review.

### Normalized Policy Row

```json
{
  "id": "fortigate:int_fgt_01:policy:10",
  "providerType": "fortigate",
  "integrationId": "int_fgt_01",
  "nativeId": "10",
  "name": "LAN to WAN",
  "kind": "firewall_policy",
  "status": "enabled",
  "action": "accept",
  "direction": {
    "source": "port2",
    "destination": "port3"
  },
  "scope": {
    "source": ["LAN_NET"],
    "destination": ["WAN_NET"],
    "service": ["HTTPS"]
  },
  "ownership": "external",
  "managedByFortiDashboard": false,
  "isMutable": true,
  "supports": ["edit", "disable", "delete"],
  "risk": {
    "level": "medium",
    "reasons": ["Allows traffic to external network"]
  },
  "summary": "accept HTTPS from LAN_NET to WAN_NET",
  "lastObservedAt": "2026-05-17T12:00:00.000Z",
  "raw": {
    "redacted": true
  }
}
```

Field rules:

- `id` is a stable FortiDashboard row id, not necessarily the native provider
  id.
- `ownership` values: `fortidashboard`, `external`, `unknown`.
- `isMutable` means the adapter believes the connected credential can attempt
  writes. A review can still fail.
- `supports` is action-level capability: `create`, `edit`, `enable`, `disable`,
  `delete`.
- `raw` must be redacted and safe for UI display. It must never contain secrets.

### Policy Review

Every mutation creates a review before apply:

```json
{
  "id": "policy_review_01",
  "providerType": "fortigate",
  "integrationId": "int_fgt_01",
  "policyId": "fortigate:int_fgt_01:policy:10",
  "action": "edit",
  "status": "pending_review",
  "title": "Edit FortiGate firewall policy LAN to WAN",
  "before": { "summary": "accept HTTPS from LAN_NET to WAN_NET" },
  "after": { "summary": "accept HTTPS, HTTP from LAN_NET to WAN_NET" },
  "diff": [
    {
      "field": "service",
      "before": ["HTTPS"],
      "after": ["HTTPS", "HTTP"],
      "risk": "Expands allowed services"
    }
  ],
  "warnings": [
    {
      "severity": "high",
      "message": "This policy was not created by FortiDashboard."
    }
  ],
  "rollback": [
    "Restore service list to HTTPS",
    "Re-run review before applying rollback"
  ],
  "reviewHash": "sha256..."
}
```

The backend compares `reviewHash` during apply. If provider state changed after
review creation, apply must fail with a stale-review error and ask the admin to
run review again.

## Backend API

Add a policy router under `apps/api/app/routers/policies.py`.

```txt
GET  /api/policies/providers
GET  /api/policies
GET  /api/policies/{policyId}
POST /api/policies/reviews
GET  /api/policies/reviews/{reviewId}
POST /api/policies/reviews/{reviewId}/apply
```

### `GET /api/policies/providers`

Returns connected integrations and their policy capabilities:

```json
{
  "items": [
    {
      "providerType": "fortigate",
      "integrationId": "int_fgt_01",
      "name": "FortiGate Lab",
      "capabilities": ["list", "create", "edit", "enable", "disable", "delete"],
      "policyKinds": ["firewall_policy", "lab_allow_log", "temporary_block"]
    },
    {
      "providerType": "fortiweb",
      "integrationId": "int_fweb_01",
      "name": "FortiWeb Lab",
      "capabilities": ["list", "create", "edit", "enable", "disable", "delete"],
      "policyKinds": ["server_policy", "ip_blocklist", "source_ip_block"]
    }
  ]
}
```

### `GET /api/policies`

Query params:

```txt
providerType optional
integrationId optional
kind optional
status optional
ownership optional
q optional
```

Returns normalized policy rows. The first cut can return all rows without
server-side pagination if provider inventory is small, but the response shape
must allow `nextCursor` in the first implementation so pagination can be added
without changing the client contract.

### `POST /api/policies/reviews`

Creates a provider-specific review.

Common fields:

```json
{
  "providerType": "fortigate",
  "integrationId": "int_fgt_01",
  "action": "edit",
  "policyId": "fortigate:int_fgt_01:policy:10",
  "payload": {}
}
```

`payload` is validated by the selected provider adapter. Invalid provider/action
combinations return `422`.

### `POST /api/policies/reviews/{reviewId}/apply`

Body:

```json
{
  "reviewHash": "sha256...",
  "confirmed": true
}
```

Apply requires `policies.manage`, CSRF and `confirmed=true`.

## Backend Structure

Create focused files under `apps/api/app/policies/`:

```txt
apps/api/app/policies/models.py
  Pydantic request/response models and enums.

apps/api/app/policies/adapters.py
  Protocols: PolicyProviderAdapter, PolicyInventoryResult, PolicyReviewResult.

apps/api/app/policies/service.py
  Adapter registry, list fan-out, review creation, apply dispatch.

apps/api/app/policies/fortigate_adapter.py
  Maps current FortiGate policy service/orchestrator to the common contract.

apps/api/app/policies/fortiweb_adapter.py
  Maps FortiWeb integration/block contracts once the FortiWeb branch lands.
```

Persistence can start with the existing FortiGate policy request table for
FortiGate and the FortiWeb block request table for FortiWeb if that keeps the
first cut smaller. If the implementation needs one common table, use:

```txt
soc_policy_reviews
  id
  owner_user_id
  provider_type
  integration_id
  policy_id nullable
  action
  status
  request_json
  before_json
  after_json
  diff_json
  warnings_json
  rollback_json
  review_hash
  applied_result_json nullable
  created_at
  updated_at
  applied_at nullable
```

The common table is preferred if both providers are implemented in this branch.

## FortiGate Adapter

Inventory:

- Use `FortiGateService` and the existing client `get_policies()` path.
- Normalize native firewall policies into `firewall_policy` rows.
- Detect FortiDashboard-owned policies via `FD_` prefixes and comments.
- Mark external policies as mutable if the integration credential supports
  policy writes.

Actions:

- `create`: supports at least `lab_allow_log` and generic firewall policy create.
- `edit`: updates editable firewall policy fields without moving policy order.
- `enable` / `disable`: toggles status.
- `delete`: removes the selected firewall policy after review.

Review details:

- Existing policy orchestration preflight can be reused for lab allow/log and
  temporary block actions.
- Generic edit/delete reviews must fetch the current native policy, generate a
  field diff, warn on `ownership=external`, and include rollback guidance.
- No policy move helper is exposed in the MVP.

## FortiWeb Adapter

Inventory:

- Server policy row for the configured `targetServerPolicy`.
- Managed IP list row for `managedIpListPolicy`.
- Active block rows from FortiWeb block request/list contracts.
- Rows should include linked server policy and protection profile names when the
  adapter can read them.

Actions:

- `create`: create a source-IP block review, and create/manage a
  FortiDashboard-managed IP list if missing.
- `edit`: edit block reason/metadata or managed IP list entries where the
  FortiWeb adapter supports it.
- `enable` / `disable`: activate/deactivate a managed block or policy-supported
  equivalent.
- `delete`: remove source-IP block or managed IP-list entry.

Review details:

- Review should show target server policy, inline protection profile, managed
  IP list, source IP and whether the IP list is attached.
- If the selected FortiWeb object is not managed by FortiDashboard, warn that
  the admin is modifying provider/customer-owned configuration.
- Apply/remove reuse the FortiWeb connector's review/apply/remove contracts once
  that branch is merged.

## Frontend UX

Add a new widget component:

```txt
apps/web/src/components/widgets/policies/WidgetSocPolicyManager.vue
```

It must use `WidgetShell`.

### Glance

Fast-scan content:

- total policies across selected providers;
- disabled policies count;
- external/customer-owned policies count;
- pending reviews count;
- last successful policy action;
- provider health chips for FortiGate/FortiWeb.

### Drill

Inventory table:

- provider;
- integration;
- policy name;
- kind;
- status;
- action/effect;
- source/destination/service summary;
- ownership;
- risk;
- actions menu.

Filters:

- provider;
- integration;
- status;
- ownership;
- kind;
- search by name/native id.

### Detail Modal

The detail modal contains the provider-specific editor and the review/apply
panel.

Flow:

1. Admin clicks create/edit/enable/disable/delete.
2. Widget opens the provider-specific form.
3. Admin submits for review.
4. UI renders diff, warnings and rollback guidance.
5. Admin confirms apply.
6. Widget refreshes inventory and shows the audit/result status.

Provider-specific forms:

- FortiGate firewall policy form: source interface, destination interface,
  source addresses, destination addresses, service, action, schedule, logging,
  status.
- FortiGate lab allow/log shortcut: replaces the current `LabPolicyWizard`.
- FortiWeb source block form: integration, source IP, reason, optional incident
  id.
- FortiWeb managed IP list form: list name, entry add/remove, linked server
  policy context when available.

All new strings must be added to `pt-BR` and `en-US` i18n catalogs.

## Widget Catalog

Add a catalog item:

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

The widget should be available when at least one connected integration reports
policy capabilities. If no provider is connected, it renders an empty state with
a link-style action to open the integrations drawer.

## Audit Events

Add policy-manager audit actions:

```txt
policy.review_created
policy.apply_succeeded
policy.apply_failed
policy.inventory_read
```

Audit details must include:

- provider type;
- integration id;
- policy id/native id;
- action;
- ownership;
- whether the target was external/customer-owned;
- review id;
- diff summary;
- rollback summary;
- provider response status with secrets redacted.

Inventory reads are sensitive because they expose provider configuration. Record
successful admin-wide reads if the route is permission-gated. If normal analysts
can view inventory, only audit reads that open full detail or raw redacted
provider payloads.

## Error Handling

- Missing permission: `403 Permission required: policies.manage`.
- Provider unavailable: show provider row as degraded and keep other providers
  loaded.
- Unsupported action: disable the action in UI and return `409` if called.
- Stale review hash: return `409` and require a fresh review.
- Provider write failure: return `502`, keep review visible, record failed audit.
- External/customer-owned write: allow only after warning is displayed in the
  review and included in the confirmation payload.

## Testing

Backend:

- Permission test for `policies.manage` gating review/apply.
- Policy service test listing FortiGate and FortiWeb rows together.
- FortiGate adapter tests for create/edit/enable/disable/delete review payloads.
- FortiGate stale review hash test.
- FortiWeb adapter tests against the FortiWeb block review/apply/remove
  contract.
- Audit tests for review/apply success/failure.

Frontend:

- Store/client tests for providers, inventory, review and apply.
- Widget renderer tests for empty, mixed-provider inventory, pending review and
  apply success states.
- Permission UI test: users without `policies.manage` can view inventory but
  cannot see mutating controls.
- i18n smoke for new keys in `pt-BR` and `en-US`.

Validation commands:

```bash
docker compose config --quiet
cd apps/api && uv run ruff check . && uv run pytest -q tests/test_policies.py tests/test_fortigate_policy_orchestrator.py tests/test_fortigate_integrations.py
cd apps/web && pnpm test -- tests/unit/policiesStore.test.ts tests/unit/widgetPolicyManager.test.ts --runInBand
cd apps/web && pnpm build
```

## Rollout Notes

- Keep the existing FortiGate policy endpoints during migration.
- Remove `LabPolicyWizard` from `Sidebar.vue` only after the canvas widget can
  create the lab allow/log review.
- If FortiWeb provider work is not merged when implementation starts, build the
  common contract and FortiGate adapter first, then add FortiWeb adapter as soon
  as the branch lands.
- Product docs must update the feature map from "Governed FortiGate
  traffic-policy orchestration" to a broader "SOC policy manager" capability.
