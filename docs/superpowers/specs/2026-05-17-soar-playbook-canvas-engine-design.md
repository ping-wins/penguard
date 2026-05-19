# SOAR Playbook Canvas Engine Design

**Status:** Approved for implementation
**Date:** 2026-05-17
**Owner:** Codex agent
**Related:**
- `AGENTS.md`
- `docs/superpowers/specs/2026-05-15-fortigate-policy-orchestration-design.md`
- `docs/superpowers/specs/2026-05-17-roles-permissions-manager-design.md`

## Goal

Turn the current SOAR playbook console into a first-class, n8n-like automation
experience inside the Penguard workspace canvas. Analysts should be able
to place widgets and playbook nodes side by side, connect automation edges,
configure nodes through safe forms, run or simulate playbooks, inspect node-level
run state, and use inbound and outbound webhooks without bypassing
Penguard RBAC, audit, approval, or provider orchestration boundaries.

## Context

Today `soar_skipper` persists playbooks and runs, exposes a node catalog, and
supports dry-run, approval and FortiGate policy orchestration handoff. The
frontend has a `PlaybooksPanel`, but the builder is linear, drawer-based, and
requires raw JSON config. That makes it hard to understand and hard to operate
from the same workspace where analysts already monitor widgets.

The workspace canvas was recently split into `canvas` and `grid` modes. This
design preserves that direction. The canvas remains the main product surface;
the new work adds automation objects to the same canvas rather than creating a
separate SOAR application.

## Decisions

- Build a Penguard-owned n8n-like builder and runtime. Do not embed the
  real n8n product in the MVP.
- Keep widgets and playbook nodes in the same workspace canvas.
- Evolve `soar_skipper` into a graph runtime with branches, loops, retries,
  webhooks, approval pauses, cancellation and node-level run state.
- Keep `apps/api` as the mandatory BFF for browser auth, CSRF, RBAC,
  permissions, webhook endpoints, secrets, provider calls and audit.
- Store webhook and provider secrets only on the backend.
- Treat FortiGate and FortiWeb live changes as sensitive actions that must pass
  through approval and existing governed orchestration paths.

## Non-Goals

- No direct browser-to-provider secret handling.
- No arbitrary Python, shell, SQL, JavaScript or HTTP execution by AI.
- No automatic sensitive FortiGate or FortiWeb change from a webhook, loop,
  background job, SIEM detection or AI response.
- No full n8n compatibility layer in the first implementation.
- No workflow marketplace in this spec.
- No multi-tenant redesign. The project remains single-tenant per customer
  stack for now.

## Documentation Inputs

Current docs checked while shaping this design:

- Vue Flow docs: custom nodes and edges, `v-model:nodes`,
  `v-model:edges`, controls, minimap, background and connect handlers.
  Source: https://github.com/bcakmakoglu/vue-flow
- n8n docs: workflows use nodes, positions, credentials and connections.
  Source: https://github.com/n8n-io/n8n-docs

Vue Flow is the recommended frontend graph library because it is Vue-native and
already provides the graph interaction primitives this feature needs. The
runtime and safety model remain Penguard-owned.

## Workspace Model

The workspace manifest needs to support heterogeneous canvas objects. Existing
widgets stay compatible with the current `widgets[]` contract. Playbook graph
state is added as a separate section rather than overloading widget records.

Proposed manifest addition:

```json
{
  "playbooks": [
    {
      "id": "pb_port_scan_response",
      "name": "Port scan response",
      "enabled": false,
      "layout": {
        "x": 1200,
        "y": 200,
        "w": 980,
        "h": 620,
        "z": 180
      },
      "nodes": [
        {
          "id": "trigger",
          "type": "trigger.incident_created",
          "position": { "x": 0, "y": 80 },
          "config": {}
        }
      ],
      "edges": [
        {
          "id": "edge_trigger_condition",
          "from": "trigger",
          "to": "severity",
          "condition": "success"
        }
      ],
      "metadata": {
        "source": "workspace-canvas",
        "createdBy": "user"
      }
    }
  ]
}
```

Rules:

- Workspace export/import includes playbook graph definitions but never live
  telemetry, run payloads, webhook secrets or provider credentials.
- A shared workspace cannot bind playbook nodes to another user's private
  integration secret. Bindings must be resolved by the recipient.
- Unknown playbook node types are rejected during import.
- Import validates graph size, node count, edge count, config schemas and loop
  limits before persistence.

## Frontend UX

The workspace canvas renders widgets and playbook graphs together.

### Canvas Behavior

- `Canvas` mode shows widgets and playbook nodes together.
- `Grid` mode remains a compact widget-first view. It may show playbook run
  summary widgets, but it does not attempt to compact a graph editor.
- The canvas toolbar adds visibility filters: `All`, `Widgets`, `Playbooks`,
  `Runs`.
- The build pane gains an `Automation` section backed by
  `/api/soc/playbook-node-types`.
- Users drag automation nodes from the build pane onto the canvas.
- Users connect nodes with edges.
- Users edit node config in a properties panel using schema-driven forms.
- Raw JSON may exist behind an advanced/debug affordance, but it is not the
  primary UI.

### Node Presentation

Nodes show:

- label and node type.
- category: trigger, condition, action, approval, loop, webhook.
- boundary badge: dry-run, live-capable, approval-required, webhook.
- configured integration or webhook alias when applicable.
- validation state.
- latest run status overlay when a run is selected.

Edges show:

- default `success` path.
- `true` and `false` paths for conditions.
- `approved` and `rejected` paths for approvals.
- `loop_next` and `loop_done` paths for loops.
- `failure` path for configured error branches.

### Playbook Actions

The canvas exposes playbook-level actions:

- Save draft.
- Simulate.
- Run dry-run.
- Run live-capable flow only when required approvals are present.
- Pause or cancel a run.
- Approve or reject waiting approval gates when the user has permission.
- Open run details.

### i18n

All new user-facing strings must be added to:

- `apps/web/src/i18n/messages/pt-BR.ts`
- `apps/web/src/i18n/messages/en-US.ts`

## Backend Runtime Model

`soar_skipper` evolves from ordered-node execution to graph execution.

### Node Categories

`trigger`
: Starts a playbook. Examples: manual run, incident created, inbound webhook.

`condition`
: Chooses an outgoing path based on run context.

`action`
: Performs work. Examples: enrich IP, create case note, outbound webhook,
  prepare FortiGate or FortiWeb policy review.

`approval`
: Pauses until an allowed human approves or rejects.

`loop`
: Repeats a subgraph with explicit limits.

`webhook`
: Inbound trigger or outbound action. Webhook nodes have their own safety rules.

### Run Statuses

Playbook run status:

- `pending`
- `running`
- `waiting_approval`
- `completed`
- `failed`
- `timed_out`
- `cancelled`

Node run status:

- `pending`
- `running`
- `completed`
- `skipped`
- `failed`
- `waiting_approval`
- `timed_out`
- `cancelled`

Edge conditions:

- `success`
- `failure`
- `true`
- `false`
- `approved`
- `rejected`
- `loop_next`
- `loop_done`

### Loop Semantics

Loops are allowed, but they are bounded:

- `maxIterations` is required.
- `timeoutSeconds` is required.
- `nodeTimeoutSeconds` applies to each node execution inside the loop.
- A loop must have a deterministic exit condition.
- A loop that reaches its limit exits through `loop_done` with a limit marker,
  or fails if the node config says the limit is fatal.
- Loop execution records iteration number per node step.

### Retry Semantics

Retry is configured per node:

```json
{
  "retry": {
    "maxAttempts": 3,
    "backoffSeconds": 5,
    "backoffMultiplier": 2
  }
}
```

Rules:

- Retries are opt-in per node.
- Retries never re-run approval decisions automatically.
- Retries never re-apply a sensitive provider action.
- Retry attempts are audited and visible in run details.

### Cancellation

Runs need cancellation support:

- Cancel marks pending nodes as `cancelled`.
- Running external calls should stop when possible; otherwise the run records
  that cancellation was requested and waits for the call timeout.
- Waiting approvals become `cancelled`.
- Cancellation emits audit.

## Webhooks

Webhooks are split into inbound triggers and outbound actions.

### Inbound Webhook Trigger

`webhook.inbound_trigger` creates a BFF-owned public endpoint for a playbook.

Endpoint shape:

```txt
POST /api/soc/webhooks/{webhookId}
```

Required behavior:

- Secret validation.
- Rate limit.
- Payload size limit.
- Idempotency key support.
- Redaction before audit.
- Optional schema validation.
- Run creation through the same `soar_skipper` path as manual execution.

Secrets:

- Generated by the backend.
- Stored encrypted.
- Never returned after creation except once, if the implementation provides a
  one-time reveal.
- Rotatable.

### Outbound Webhook Action

`webhook.outbound_call` calls an external URL from the backend.

Required behavior:

- URL configured by an allowed user.
- Optional allowlist or explicit destination approval.
- Timeout.
- Payload size limit.
- Header and body redaction.
- Retry policy support.
- No browser-side secret exposure.

Outbound webhook response handling:

- Store status code.
- Store redacted response summary.
- Store error class for failures.
- Allow branches on success/failure.

## Permissions And RBAC

The roles/permissions system is now present in `origin/main`. This feature must
use named permissions rather than adding new `admin` checks only.

Recommended permission slugs:

| Permission | Purpose |
|---|---|
| `playbooks.read` | List playbooks, node catalog, runs and run details. |
| `playbooks.write` | Create, update, delete and import playbooks. |
| `playbooks.execute` | Simulate, run, pause and cancel playbooks. |
| `playbooks.approve` | Approve or reject approval gates. |
| `playbooks.webhooks.manage` | Create, rotate and delete inbound webhook secrets. |
| `playbooks.webhooks.invoke` | Internal permission used by inbound webhook endpoint after secret validation. |

Bootstrap `admin` behavior remains as defined by the roles spec.

## Security Rules

- Webhook secrets, provider secrets and headers stay server-side.
- Browser receives only redacted webhook metadata.
- State-changing playbook endpoints require CSRF unless they are inbound
  webhook endpoints authenticated by webhook secret.
- Inbound webhook endpoints do not accept browser sessions as authentication.
- Sensitive actions require approval even when triggered by webhook.
- AI can draft playbooks but cannot enable, approve, execute live actions or
  create webhook secrets without explicit user action.
- Every create, update, import, export, run, cancel, approve, reject, webhook
  creation, webhook rotation and webhook invocation emits an audit event.
- Audit details redact secrets and large payloads.
- Payload limits protect inbound webhook and outbound webhook nodes.
- Timeouts protect long-running nodes and loops.

## API Surface

Existing endpoints remain compatible:

```txt
GET  /api/soc/playbooks
POST /api/soc/playbooks
GET  /api/soc/playbooks/{playbookId}
PUT  /api/soc/playbooks/{playbookId}
POST /api/soc/playbooks/{playbookId}/simulate
POST /api/soc/incidents/{incidentId}/playbooks/{playbookId}/run
GET  /api/soc/playbook-runs/{runId}
POST /api/soc/playbook-runs/{runId}/approve
GET  /api/soc/playbook-node-types
```

New or expanded endpoints:

```txt
DELETE /api/soc/playbooks/{playbookId}
POST   /api/soc/playbook-runs/{runId}/cancel
POST   /api/soc/playbook-runs/{runId}/approval/{nodeRunId}/approve
POST   /api/soc/playbook-runs/{runId}/approval/{nodeRunId}/reject
GET    /api/soc/playbook-runs/{runId}/nodes
POST   /api/soc/playbooks/{playbookId}/webhooks
GET    /api/soc/playbooks/{playbookId}/webhooks
POST   /api/soc/playbooks/{playbookId}/webhooks/{webhookId}/rotate
DELETE /api/soc/playbooks/{playbookId}/webhooks/{webhookId}
POST   /api/soc/webhooks/{webhookId}
```

The inbound webhook endpoint is intentionally under `apps/api`, not
`soar_skipper`, so the BFF owns public exposure, rate limiting, secret
validation, redaction and audit.

## Data Model

`soar_skipper` needs durable graph and run tables. The current SQL-backed store
can evolve, but the payload format must be versioned.

Recommended tables:

### `soar_skipper_playbooks`

Existing table can remain, but payload schema becomes versioned:

- `schemaVersion`
- `id`
- `name`
- `enabled`
- `nodes[]`
- `edges[]`
- `runtimePolicy`
- `createdAt`
- `updatedAt`

### `soar_skipper_playbook_runs`

Existing table can remain, expanded payload:

- `id`
- `playbookId`
- `trigger`
- `status`
- `context`
- `startedAt`
- `completedAt`
- `cancelRequestedAt`
- `nodeRuns[]`
- `edgeTraversals[]`
- `error`

### `playbook_webhooks` in `apps/api`

Lives in the BFF database because it stores externally exposed endpoint metadata
and encrypted secrets.

Fields:

- `id`
- `playbook_id`
- `owner_user_id`
- `name`
- `secret_hash`
- `secret_ciphertext` only if one-time reveal or rotation flow requires it
- `enabled`
- `rate_limit_per_minute`
- `max_payload_bytes`
- `created_at`
- `updated_at`
- `last_invoked_at`

## Runtime Validation

Before save or run, validate:

- Unique node IDs.
- Edges reference existing node IDs.
- At least one trigger.
- No orphan required nodes unless explicitly allowed.
- Every condition has valid branch edges.
- Every approval has approved/rejected or success path semantics.
- Loop nodes have limits and exit path.
- Retry values are within safe bounds.
- Webhook nodes have valid config and no plaintext secret in node config.
- Sensitive provider nodes have approval boundary.
- Graph size is below configured node and edge limits.

## Frontend File Direction

Expected new files:

```txt
apps/web/src/components/playbooks/canvas/PlaybookCanvasLayer.vue
apps/web/src/components/playbooks/canvas/PlaybookFlowNode.vue
apps/web/src/components/playbooks/canvas/PlaybookFlowEdge.vue
apps/web/src/components/playbooks/canvas/PlaybookNodePropertiesPanel.vue
apps/web/src/components/playbooks/canvas/PlaybookRunOverlay.vue
apps/web/src/stores/usePlaybookCanvasStore.ts
apps/web/src/services/playbookWebhooksClient.ts
apps/web/src/utils/playbookGraph.ts
```

Expected modified files:

```txt
apps/web/package.json
apps/web/src/components/canvas/DashboardCanvas.vue
apps/web/src/components/playbooks/PlaybooksPanel.vue
apps/web/src/services/playbooksClient.ts
apps/web/src/stores/usePlaybooksStore.ts
apps/web/src/i18n/messages/pt-BR.ts
apps/web/src/i18n/messages/en-US.ts
apps/web/tests/unit/playbooksPanel.test.ts
apps/web/tests/unit/dashboardBuildPane.test.ts
```

`PlaybooksPanel.vue` should become a management/run history surface. The visual
builder belongs on the workspace canvas.

## Backend File Direction

Expected new or split files:

```txt
apps/soar_skipper/app/models.py
apps/soar_skipper/app/node_catalog.py
apps/soar_skipper/app/runtime.py
apps/soar_skipper/app/graph_validation.py
apps/soar_skipper/tests/test_graph_runtime.py
apps/soar_skipper/tests/test_webhook_nodes.py
apps/api/app/routers/playbook_webhooks.py
apps/api/app/playbooks/webhooks.py
apps/api/migrations/versions/20260517_0016_create_playbook_webhooks.py
apps/api/tests/test_playbook_webhooks.py
apps/api/tests/test_soc_gateway_playbook_runtime.py
```

Expected modified files:

```txt
apps/soar_skipper/app/main.py
apps/soar_skipper/app/store.py
apps/api/app/routers/soc.py
apps/api/app/main.py
apps/api/app/auth/permissions.py
apps/api/app/db/models.py
```

## Implementation Phases

Because this is a large feature, implementation should be staged.

### Phase 1: Runtime Contract Foundation

- Move SOAR models and node catalog out of `main.py`.
- Add graph validation.
- Add versioned playbook payloads.
- Add node-level run status for linear and branched graphs.
- Preserve existing list, simulate, run and approve endpoint behavior.

### Phase 2: Branches, Loops, Retries And Cancellation

- Add condition edge routing.
- Add bounded loop execution.
- Add retry policy.
- Add run cancellation.
- Add node run detail endpoint.

### Phase 3: Webhooks

- Add inbound webhook BFF tables and endpoints.
- Add outbound webhook node.
- Add redaction, idempotency, rate limit and payload limits.
- Add audit events.

### Phase 4: Canvas Builder

- Add Vue Flow dependency.
- Render playbook graphs on the same canvas as widgets.
- Add automation node catalog in build pane.
- Add node properties panel.
- Save graph edits through existing BFF playbook endpoints.
- Render run overlays.

### Phase 5: Permission Hardening And Polish

- Add named playbook permissions to the permission catalog.
- Gate frontend actions with `useAuthStore.hasPermission`.
- Add import/export validation and documentation.
- Run full API, SOAR and web verification.

## Testing Strategy

### `apps/soar_skipper`

- Graph validation rejects unknown node types and bad edges.
- Branch execution follows true/false paths.
- Failure branch receives failed node output.
- Loop stops at exit condition.
- Loop stops at max iterations.
- Retry records attempts and then succeeds.
- Retry records attempts and then fails.
- Approval pauses and resumes.
- Approval rejection follows rejected path or fails safely.
- Cancellation updates pending and waiting nodes.
- Existing default playbooks still list, simulate and run.

### `apps/api`

- Playbook endpoints enforce permission and CSRF.
- Inbound webhook validates secret.
- Inbound webhook rejects oversized payload.
- Inbound webhook deduplicates idempotency key.
- Inbound webhook creates a playbook run through `soar_skipper`.
- Outbound webhook redacts secrets in audit.
- Webhook secret rotation never returns old secret.
- Sensitive provider action still requires approval and policy review.

### `apps/web`

- Automation node catalog renders in the build pane.
- Dragging a node onto the canvas creates a playbook node.
- Connecting nodes creates an edge.
- Properties panel edits config through form fields.
- Invalid node config shows validation state.
- Save sends a graph payload without plaintext secrets.
- Run overlay renders node statuses.
- Approval action appears only when permitted.
- Widgets and playbook nodes coexist in canvas mode.
- Grid mode remains usable and does not try to pack graph nodes.

### Smoke

- `docker compose config --quiet`
- `cd apps/soar_skipper && uv run ruff check . && uv run pytest -q`
- `cd apps/api && uv run ruff check . && uv run pytest -q`
- `cd apps/web && pnpm test && pnpm build`
- `cd apps/web && pnpm smoke:canvas`

## Open Risks

- Vue Flow may conflict with the existing custom infinite canvas scroll/zoom
  behavior. The implementation plan must decide whether Vue Flow owns only the
  playbook sub-layer or the entire canvas interaction model for automation
  objects.
- Loops and outbound webhooks create operational risk. Defaults must be
  conservative and observable.
- The runtime may outgrow synchronous request/response execution. Redis worker
  or Dramatiq integration may be needed after the first durable runtime slice.
- Workspace import/export can become a secret leakage path if graph config is
  not strictly validated.

## Acceptance Criteria

- An analyst can create a playbook graph with trigger, condition, action,
  approval, loop and webhook nodes.
- Widgets and playbook nodes are visible together on the same workspace canvas.
- The playbook can be saved, simulated and executed.
- The run records node-level statuses and edge traversal.
- Inbound webhook can trigger a playbook without browser session auth.
- Outbound webhook can call an external endpoint from the backend with redacted
  audit.
- Loops cannot run forever.
- Sensitive FortiGate/FortiWeb actions cannot run without human approval.
- Existing SOAR APIs and tests remain compatible.
