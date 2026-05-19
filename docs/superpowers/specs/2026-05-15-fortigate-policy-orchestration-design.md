# FortiGate Policy Orchestration Design

## Context

Penguard is a SOC orchestrator. The FortiGate connector must be able to
create governed firewall policies from inside the cockpit instead of stopping at
CLI drafts or manual FortiGate UI instructions.

The immediate lab need is a FortiGate-mediated nmap validation flow:

```txt
BlackArch attacker -> FortiGate -> Arch victim
Penguard creates allow+log lab policy
nmap crosses the FortiGate
FortiGate emits accepted traffic logs
SIEM detects an allowed port scan
Ticket suggests containment
Analyst approves a temporary FortiGate block from the ticket drawer
```

The accepted boundary is documented in
`docs/architecture/decisions/ADR-2026-05-15-fortigate-policy-orchestration.md`.
Live FortiGate policy writes are allowed only through the BFF with admin RBAC,
CSRF protection, preflight, diff/summary, explicit human approval and audit.

## Goals

- Replace the current FortiGate traffic-policy draft helper with real governed
  policy orchestration.
- Add a Lab Policy Wizard that creates a Penguard-owned `allow + log`
  policy between selected FortiGate interfaces and networks.
- Add SIEM detection for allowed port scans by counting unique destination ports
  over a short window.
- Link SOC ticket approval to a FortiGate Policy Change Review for temporary
  containment policies.
- Support both temporary source-only blocks and scoped
  source-to-destination/service blocks.
- Preserve a clear future path for autonomous AI agents to prepare suggestions
  while keeping approval and live apply human-controlled.

## Non-Goals

- No full FortiGate policy editor in the first release.
- No automatic FortiGate write triggered only by SIEM detection, AI output,
  background jobs or browser state.
- No route, interface, VPN, admin/global setting or feature-disable changes.
- No silent policy reorder across customer-managed policies.
- No FortiWeb live-write behavior in this spec.

## Product Flow

### 1. Lab Policy Wizard

The FortiGate integration card gets a real wizard replacing the existing
traffic-policy draft helper.

Wizard inputs:

- FortiGate integration.
- Source interface.
- Destination interface.
- Source network or host.
- Destination network or host.
- Service: default `ALL`, with future support for selected FortiGate services.
- Action: first release defaults to `accept`.
- Logging: fixed to `logtraffic all` for the first release.
- Optional label/purpose.

Wizard output before apply:

- Existing FortiGate state summary.
- Proposed address objects.
- Proposed firewall policy.
- Placement summary.
- Warnings for conflicts, missing interfaces, broad CIDRs or missing logging.
- Audit-safe diff/summary.

Apply behavior:

- Requires authenticated admin.
- Creates or reuses Penguard-owned address objects.
- Creates or updates only Penguard-owned lab policy objects.
- Does not alter customer-owned policies.
- Writes audit before and after apply.
- Returns FortiGate API response plus rollback guidance.

### 2. Allowed Port Scan Detection

The SIEM must detect scans from accepted traffic logs, not only denied traffic.

Detection contract:

```txt
event source: FortiGate syslog or FortiGate event ingestion
input eventType: network.event
required attributes.action: accept
group key: integrationId + sourceIp + destinationIp
window: 60 seconds
threshold: >= 20 unique destination ports
output eventType: network.scan
incident title: Possible port scan
severity: high
```

The incident entities must include:

- `integrationId`
- `sourceIp`
- `destinationIp`

The incident attributes must include:

- observed unique destination ports, capped for display.
- observed port count.
- scan window.
- policy id/name when available.
- `attackType: port_scan`.

### 3. Ticket To Policy Change Review

The current ticket drawer already has an approval button for playbook runs. That
surface becomes the bridge to FortiGate containment.

Flow:

1. SIEM creates `Possible port scan`.
2. Ticket drawer shows source/destination entities and observed ports.
3. SOAR suggestion includes a FortiGate containment intent.
4. Analyst runs/applies the playbook and it pauses at approval.
5. The existing approval button creates a FortiGate Policy Change Review instead
   of silently marking the ticket contained.
6. The review panel appears inline in the ticket drawer.
7. Analyst chooses or confirms scope:
   - source-only temporary block.
   - source to destination temporary block.
   - source to destination/service temporary block.
8. Analyst clicks Apply Policy.
9. BFF applies the FortiGate policy.
10. SIEM ticket timeline records the containment result.
11. Audit records the approval, request, FortiGate response and rollback
    guidance.

The AI agent can later generate the containment intent, but it cannot approve or
apply the policy.

## Policy Scope

Penguard-owned policies use stable prefixes and metadata:

- Lab allow/log policies: `PG_LAB_ALLOW_*`.
- Temporary block policies: `PG_TMP_BLOCK_*`.
- Address objects: `PG_ADDR_*`.
- Comments include JSON-like metadata where FortiGate field limits allow:
  `createdBy=Penguard`, `incidentId`, `playbookRunId`, `expiresAt`,
  `purpose`.

First-release policy types:

### Lab Allow And Log

```txt
srcintf: selected source interface
dstintf: selected destination interface
srcaddr: Penguard-owned source address object
dstaddr: Penguard-owned destination address object
service: selected service, default ALL
action: accept
schedule: always
logtraffic: all
nat: disable
status: enable
```

### Temporary Source Block

```txt
srcintf: derived from incident or chosen in review
dstintf: derived from incident or chosen in review
srcaddr: attacker host object
dstaddr: all or selected destination
service: ALL or selected service
action: deny
schedule: always or generated temporary schedule
logtraffic: all
status: enable
expiresAt: required in Penguard metadata
```

### Temporary Source To Destination/Service Block

Same as source block, but destination and service are explicit. This is the
preferred default when the incident has reliable `destinationIp` and
`destinationPort`/service evidence.

## Placement Rules

Policy order is security-sensitive. The first release uses conservative
placement:

- Lab allow/log policy is created inside the Penguard-owned lab policy
  group or appended as a Penguard-owned policy when no owned group exists.
- Temporary block policy is placed before the matching Penguard-owned
  lab allow/log policy when that policy exists.
- If Penguard cannot find a safe owned placement target, the review is
  blocked and asks the analyst to choose placement or create the lab policy
  first.
- Penguard does not reorder customer-owned policies silently.

## Backend Design

Add a focused policy orchestration layer under the FortiGate integration:

```txt
apps/api/app/integrations/fortigate/policy_orchestrator.py
apps/api/app/integrations/fortigate/policy_models.py
```

Core types:

- `FortiGatePolicyIntent`: normalized user/SOAR request.
- `FortiGatePolicyPreflight`: interfaces, services, address objects, policies
  and safe placement analysis.
- `FortiGatePolicyChangeReview`: diff/summary shown to the user.
- `FortiGatePolicyApplyResult`: FortiGate response, created/updated object ids,
  rollback guidance and audit-safe metadata.

Extend the FortiGate API client with CMDB write helpers:

- list/get/create/update firewall address objects.
- list/get/create/update firewall policies.
- optional move helper only for Penguard-owned placement targets.

BFF endpoints:

```txt
POST /api/integrations/fortigate/{integrationId}/policy/preflight
POST /api/integrations/fortigate/{integrationId}/policy/review
POST /api/integrations/fortigate/{integrationId}/policy/apply
POST /api/soc/playbook-runs/{runId}/policy-review
POST /api/soc/playbook-runs/{runId}/policy-apply
```

The integration endpoints power the Lab Policy Wizard. The SOC endpoints link
ticket approval and playbook runs to policy reviews and application.

Every apply endpoint requires `admin`, CSRF and explicit confirmation. Apply
requests include the review id or review hash so the backend can detect stale
preflight data before writing to FortiGate.

## Persistence

Add a small table for review/apply lifecycle:

```txt
fortigate_policy_change_requests
  id
  owner_user_id
  integration_id
  incident_id nullable
  playbook_run_id nullable
  status: review_pending | applied | failed | cancelled | expired
  intent_json
  preflight_summary_json
  proposed_changes_json
  review_hash
  applied_result_json nullable
  expires_at nullable
  created_at
  updated_at
```

This table is not a policy source of truth. FortiGate remains the source of
truth for live firewall state. The table records Penguard's orchestration
decision and audit trail.

## Frontend Design

### Integration Drawer

Replace the current "Traffic policy helper" card with "Lab Policy Wizard".

States:

- Select path.
- Review change.
- Applying.
- Applied.
- Blocked by preflight.
- Failed with FortiGate error.

The wizard should be compact and operational, not a marketing modal. It belongs
inside the FortiGate integration details where the operator already sees
ingestion/log-forwarding health.

### Ticket Drawer

Extend the existing playbook approval section:

- If the playbook run has a FortiGate policy intent, the approval button creates
  or loads a Policy Change Review.
- Render review details inline:
  source, destination, service, duration, policy name, placement and warnings.
- Show one final "Apply FortiGate Policy" button.
- After apply, show result and rollback guidance.

This avoids sending the analyst away from the incident during the demo while
still preserving an explicit review step.

## SOAR Contract

Introduce a live-capable FortiGate node type, separate from the existing
recommendation node:

```txt
fortigate.temporary_block
```

Node metadata:

- category: action.
- sensitive: true.
- boundary: fortigate_policy_orchestration.
- executionMode: approval_required.
- liveAvailable: true.
- config schema includes `scope`, `durationMinutes`, `sourceField`,
  `destinationField`, `serviceField`.

`soar_skipper` still does not call FortiGate directly. It persists the run and
returns the intent. `apps/api` owns FortiGate writes through the policy
orchestration endpoints.

## AI Boundary

AI may:

- Summarize why the incident looks like a scan.
- Suggest a containment intent.
- Choose a reasonable default scope from incident entities.
- Prepare the Policy Change Review payload.

AI may not:

- Approve the playbook run.
- Apply a FortiGate policy.
- Override preflight warnings.
- Hide scope, duration or placement from the analyst.

## Error Handling

- Missing integration: `404`.
- Non-admin apply attempt: `403`.
- Missing CSRF: `403`.
- Stale review hash: `409`, require new review.
- Unsafe placement: `422`, include explanation and safe next action.
- FortiGate permission failure: `400` with stable message and audit failure.
- FortiGate network failure: `502` with stable message and audit failure.
- Partial apply: return `status=partial`, created objects and rollback guidance.

## Audit And Timeline

Audit actions:

- `integration.fortigate.policy_reviewed`
- `integration.fortigate.policy_applied`
- `integration.fortigate.policy_apply_failed`
- `soc.playbook_run.policy_reviewed`
- `soc.playbook_run.policy_applied`

Ticket timeline notes:

- Policy review created.
- Policy applied.
- Policy apply failed or partial.
- Rollback guidance generated.

Audit details must redact secrets and avoid storing raw FortiGate API tokens.

## Testing Strategy

Backend:

- Unit tests for intent normalization and CIDR/host validation.
- Unit tests for preflight conflict detection and safe placement.
- Client tests for FortiGate CMDB write helpers using `httpx.MockTransport`.
- Router tests for RBAC, CSRF, review hash and audit behavior.
- SIEM tests for accepted port-scan detection with unique destination ports.
- SOC gateway tests for ticket approval creating/applying a FortiGate policy
  review.

Frontend:

- Store/client tests for policy preflight/review/apply.
- Lab Policy Wizard tests for review/apply/error states.
- Ticket drawer tests proving approval shows Policy Change Review and apply
  updates the ticket result.

Lab:

- Create allow/log policy from Penguard.
- Run nmap from attacker to victim.
- Confirm FortiGate logs accepted traffic.
- Confirm SIEM incident `Possible port scan`.
- Confirm ticket approval applies a temporary block policy.
- Re-run nmap and confirm containment effect.

## Open Implementation Notes

- The first implementation must remove visible frontend use of the old
  `traffic-policy-draft` endpoint. The backend route should either be deleted
  in the same cut or return a stable deprecation response that points callers to
  the policy review/apply contract.
- The current realtime syslog path forwards one event at a time. Allowed scan
  detection should live in `siem_kowalski` as a sliding-window enrichment/rule,
  not in browser polling.
- Expired temporary policies need a later cleanup worker. The first cut can
  record expiry and show cleanup guidance, but customer-facing beta should add
  automated cleanup with audit.
