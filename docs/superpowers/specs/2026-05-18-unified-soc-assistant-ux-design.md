# Unified SOC Assistant UX And Governance Design

**Status:** Approved in brainstorming, pending written spec review

**Date:** 2026-05-18

**Owner:** luskotav-cloud

**Related:** [`2026-05-13-ai-agent-architecture-design.md`](2026-05-13-ai-agent-architecture-design.md), [`2026-05-17-real-llm-agent-runtime-design.md`](2026-05-17-real-llm-agent-runtime-design.md), [`2026-05-17-roles-permissions-manager-design.md`](2026-05-17-roles-permissions-manager-design.md), [`2026-05-17-soar-playbook-canvas-engine-design.md`](2026-05-17-soar-playbook-canvas-engine-design.md)

## Goal

Replace the visible multi-agent/backend experience with one operational **SOC
Assistant**. The assistant should be able to inspect and manage FortiDashboard
through governed tools, while inheriting the logged-in user's permissions and
requiring human confirmation before any state-changing action.

The current UX exposes implementation details: agent roles, scripted/backend
selection, per-user AI preferences, and optional Claude/Codex CLI wiring. That
creates duplicate concepts and can prevent real provider routing from working
because the frontend can force a backend that the backend only supports for
`scripted`. The redesign makes the product promise simple:

> The SOC Assistant can help do what the logged-in user is allowed to do in
> FortiDashboard, and writes happen only after review and confirmation.

## Decisions

| Question | Decision |
|---|---|
| Visible assistant model | One visible **SOC Assistant**, not multiple user-facing agents. |
| Agent profile selection | No user-facing agent role selector. Internal capabilities are derived from RBAC. |
| Provider configuration | One active enterprise provider for the whole deployment. |
| Who configures AI | Admin or any role with new permission `ai.agent.manage`. |
| Provider fields | Provider, model, encrypted API key, test status. |
| CLI integration | Remove/defer Claude Code and Codex CLI from product UX for now. |
| Permission model | Assistant inherits the logged-in user's effective permissions. |
| Writes | Every mutating tool requires confirmation before execution. |
| Playbook design | Assistant can build custom playbooks node by node using the existing SOAR graph contract. |

## User Experience

### SOC Assistant Panel

The sidebar keeps one entry: **SOC Assistant**.

Remove these controls from the assistant panel:

- Agent role selector.
- Backend selector.
- Runtime/debug wording such as `scripted`, `backend`, or provider internals.

The assistant panel should show:

- Conversation history.
- A clear operating status when the enterprise provider is not configured.
- Streaming response text as coherent assistant messages, not one message per
  token chunk.
- Tool activity as an operational trail, for example "Reading incidents",
  "Preparing playbook patch", "Waiting for confirmation", and "Applied change".
- Confirmation cards for mutating actions, with human-readable summaries and
  diffs instead of raw JSON arguments.
- Model/status metadata in a secondary location, useful but not dominant.

If AI is not configured:

- Non-admin users see that the SOC Assistant is not configured and should
  contact an administrator.
- Users with `ai.agent.manage` see a link or CTA to the Settings tab.

### Settings

The Settings modal gets an administrative **SOC Assistant** configuration panel.
It is visible/editable only to admins or users with `ai.agent.manage`.

Fields:

- Active provider: one selected provider for the whole deployment.
- Model name.
- API key, write-only in the UI.
- Saved-key state.
- Remove/replace key action.
- Test connection action.
- Last test status and timestamp.

CLI local mode is removed from this panel. Claude Code and Codex CLI may be
documented later as lab-only experiments, but they are not part of the product
configuration flow.

### Roles Manager

The role manager remains the source of governance. Add permissions instead of
adding visible assistant personas.

New permissions:

- `ai.agent.manage`: configure the enterprise AI provider/model/key and view
  provider health.
- `playbooks.manage`: create, update, and validate SOAR playbook definitions.

Existing permissions continue to gate assistant tools:

- `policies.manage`: FortiGate/FortiWeb policy orchestration tools.
- `integrations.write`: integration create/update/delete tools.
- `roles.manage`: role and user-role management tools.
- `playbooks.execute`: playbook simulation/run/approval execution flows.
- `tickets.manage`: ticket and incident workflow updates.
- `workspaces.share`: workspace sharing/publishing tools where applicable.
- `audit.read`: audit inspection tools.

## Architecture

### Runtime Shape

The frontend creates one kind of assistant session:

```txt
POST /api/ai/agent/sessions
  no backend field
  no user-facing role field
```

The backend creates a `soc-assistant` session internally.

Provider resolution:

```txt
enterprise_ai_agent_settings -> provider/model/api key -> AgentBackend
```

Tool resolution:

```txt
logged-in user -> effective permission slugs -> allowed assistant tools
```

The assistant must not bypass BFF APIs, RBAC, CSRF, approval, or audit. Tools
call the same service boundaries the UI calls, or backend-owned service
functions that enforce the same permissions and auditing.

### Enterprise AI Settings

Introduce a singleton enterprise configuration, for example
`ai_agent_settings`.

Suggested fields:

- `id`: constant singleton id, such as `default`.
- `provider`: `anthropic` or `openai` initially.
- `model`: model string.
- `api_key_blob`: encrypted with the existing token cipher pattern.
- `last_tested_at`.
- `last_test_status`.
- `last_test_error`.
- `updated_by`.
- `updated_at`.

The existing `user_ai_preferences` table may remain temporarily for legacy
`/api/ai/chat` compatibility, but the SOC Assistant should stop depending on
per-user AI preferences.

### Tool Capability Model

Tools have two independent pieces of metadata:

- `category`: `read`, `draft`, `write`, or `execute`.
- `required_permissions`: one or more permission slugs.

At runtime, the runner exposes a tool only when the logged-in user has the
required permission set. This replaces user-facing "agent roles" as the primary
capability mechanism.

Write and execute categories require extra guardrails:

- `write`: always requires confirmation before invocation.
- `execute`: requires confirmation when it changes state or triggers live/dry-run
  workflow execution.
- Sensitive FortiGate/FortiWeb operations still use the existing governed BFF
  orchestration boundary with preflight, summary/diff, approval, rollback
  guidance, and audit.

### Confirmation Contract

Before a mutating tool executes, the runner emits an approval event with:

- Tool name.
- Target resource.
- Action summary.
- Before/after or proposed patch when available.
- Required permissions.
- Risk label.
- Audit preview.

The UI presents Approve and Deny. Approval resolves the pending tool call and
the backend executes the tool under the same user identity. Denial returns a
tool result the model can react to.

Every tool call writes an audit event containing:

- User id and email.
- Session id.
- Tool name.
- Required permission slugs.
- Action category.
- Target ids.
- Arguments keys or redacted summary, never secrets.
- Approval outcome when relevant.
- Result status and error summary.

## Playbook Designer By Assistant

The assistant can create and update custom SOAR playbooks using the existing
SOAR graph model. It must not invent a parallel playbook schema.

Source of truth:

- `GET /api/soc/playbook-node-types`
- `GET /api/soc/playbooks/{playbookId}`
- `POST /api/soc/playbooks`
- `PUT /api/soc/playbooks/{playbookId}`
- `POST /api/soc/playbooks/{playbookId}/simulate`

Graph contract:

- `nodes[]`
- `edges[]`
- node `type`
- node `config`
- node `position`
- edge `from`
- edge `to`
- edge `condition`
- node type `configSchema`
- node type `boundary`
- node type `executionMode`
- node type `liveAvailable`

### Flow

1. User asks the SOC Assistant to create or modify a playbook.
2. Assistant reads available node types and, when editing, the existing
   playbook.
3. Assistant drafts the graph node by node.
4. Assistant validates the graph against node ids, edges, trigger presence, and
   node config schemas.
5. Assistant simulates the graph when possible.
6. UI shows a graph preview or patch/diff in the existing playbook canvas
   experience.
7. User confirms.
8. Backend persists the graph through the BFF SOAR route.
9. New playbooks default to `enabled=false`; enabling requires an explicit
   separate confirmation.

### Playbook Tools

Initial tool set:

- `list_playbook_node_types` (`read`, no special permission beyond playbook
  visibility).
- `get_playbook` (`read`).
- `draft_playbook_graph` (`draft`, requires `playbooks.manage`).
- `validate_playbook_graph` (`draft`, requires `playbooks.manage`).
- `propose_playbook_patch` (`draft`, requires `playbooks.manage`).
- `apply_playbook_patch` (`write`, requires `playbooks.manage`, confirmation
  required).
- `simulate_playbook` (`execute`, requires `playbooks.execute`, confirmation
  optional for dry-run simulation).
- `run_playbook` (`execute`, requires `playbooks.execute`, confirmation
  required).

The model should prefer small patch operations over regenerating a whole
playbook when editing an existing graph. The patch preview must show added,
removed, and changed nodes/edges.

## Migration From Current Implementation

### Frontend

- Rename "AI Agent" / "Agente IA" user-facing strings to "SOC Assistant" /
  "Assistente SOC".
- Remove `selectedRole` and `selectedBackend` from `AgentPanel.vue`.
- Update `useAiAgentStore.startSession()` so it does not pass role/backend.
- Render streaming text into the current assistant message.
- Render tool calls as operational status rows with summaries.
- Replace raw approval args with confirmation cards.
- Replace `AiPreferencesPanel.vue` with an enterprise SOC Assistant settings
  panel.
- Remove CLI local mode controls and `probeCliBinary` UI.
- Gate settings visibility/actions with `ai.agent.manage`.

### Backend

- Add `ai.agent.manage` and `playbooks.manage` to `PERMISSION_CATALOG` and i18n
  catalogs.
- Add enterprise AI settings persistence with encrypted API key.
- Add endpoints to get/update/test SOC Assistant configuration, gated by
  `ai.agent.manage`.
- Update `/api/ai/agent/sessions` so frontend no longer controls backend or
  user-facing agent role.
- Update backend routing to use enterprise provider settings instead of
  per-user preferences for the SOC Assistant.
- Replace role-based tool filtering with permission-based filtering.
- Keep internal session policy defaults, such as token budget and step limit,
  but do not expose them as user-selectable agents.
- Add dashboard management tools incrementally: playbooks, policies,
  integrations, workspaces, tickets, roles/users, and widgets.
- Deprecate CLI probe and `CliAIProvider` from the normal product path.
- Keep `/api/ai/chat` temporarily only for legacy call sites while cockpit UX
  moves to the streaming SOC Assistant.

## Security And Guardrails

- API keys remain encrypted at rest and are never returned to the frontend.
- The assistant never asks users to paste API keys into chat.
- The assistant never receives broader permissions than the logged-in user.
- Tools never receive provider credentials unless the tool specifically needs a
  provider client built server-side.
- Every state-changing tool requires confirmation.
- Sensitive Fortinet actions continue through governed BFF orchestration.
- AI-generated widgets and playbooks remain drafts until confirmed.
- Role/user changes require `roles.manage`, explicit confirmation, and audit.
- Policy changes require `policies.manage`, preflight, diff/summary, explicit
  confirmation, rollback guidance, and audit.
- New playbooks are disabled by default unless a separate confirmation enables
  them.

## Error Handling

| Case | Behavior |
|---|---|
| No enterprise provider configured | Assistant panel shows configure state; no scripted fallback in product UX. |
| Provider auth failure | Session emits actionable error; admins can test/update settings. |
| User lacks permission for requested action | Assistant explains the missing permission and does not expose or execute the tool. |
| User denies confirmation | Tool result records denial; assistant can suggest a safer alternative. |
| Validation fails for playbook graph | Assistant shows validation errors and revises the draft without persisting. |
| Simulation fails | Assistant keeps the playbook as draft and shows the failure reason. |
| Backend loses provider connectivity mid-turn | Emit recoverable provider error; do not execute pending writes. |

## Testing

Backend:

- Permission catalog includes `ai.agent.manage` and `playbooks.manage`.
- Non-admin without `ai.agent.manage` cannot read/update/test assistant
  settings.
- Admin or permitted role can update provider/model/key; GET redacts the key.
- Session creation does not accept frontend-selected backend/role as product
  controls.
- Missing enterprise provider produces a not-configured error instead of silent
  scripted fallback.
- Tool filtering uses effective permissions for the logged-in user.
- Write tools emit awaiting-confirmation before execution.
- Denied write tools do not mutate state.
- Playbook graph draft/validate/apply tools preserve the existing SOAR schema.
- New playbooks created by the assistant default to disabled.

Frontend:

- Assistant panel has no backend or agent role selectors.
- Settings shows SOC Assistant config only when user has `ai.agent.manage`.
- CLI local mode is absent from product settings.
- Missing-provider state renders for normal users and admin users.
- Confirmation cards render target, summary, risk, and diff.
- Streaming deltas append to one assistant message.
- Playbook graph preview uses existing canvas contracts.

Integration:

- Configure Anthropic/OpenAI provider, start assistant session, ask read-only
  dashboard question, verify streamed answer.
- Ask assistant to create a playbook; verify draft graph, validation,
  confirmation, persistence, and disabled default.
- Ask assistant to perform a policy change without `policies.manage`; verify
  denial before tool execution.
- Ask assistant to perform a permitted policy change; verify confirmation,
  governed BFF orchestration, and audit.

## Phased Delivery

### Phase 1: Unify UX And Enterprise Configuration

- Add `ai.agent.manage`.
- Add enterprise AI settings storage and endpoints.
- Remove CLI from settings UX.
- Remove backend/role selectors from the assistant panel.
- Create sessions as one SOC Assistant.
- Route the streaming assistant through the enterprise provider.

### Phase 2: RBAC-Driven Tools

- Add `playbooks.manage`.
- Add `required_permissions` to assistant tools.
- Filter tools by effective user permissions.
- Require confirmation for every mutating tool.
- Improve audit records for tool calls and approvals.

### Phase 3: Dashboard Management Tools

- Add tools for policies, integrations, workspaces, tickets, widgets, roles, and
  users.
- Keep each tool behind existing service boundaries and permission checks.
- Add human-readable diffs and previews for writes.

### Phase 4: Agentic Playbook Designer

- Add playbook node catalog, draft graph, validate graph, propose patch, apply
  patch, simulate, and run tools.
- Integrate graph previews with the existing playbook canvas.
- Keep new playbooks disabled by default.

### Phase 5: Legacy Cleanup

- Deprecate `/api/ai/chat` as the primary cockpit assistant path.
- Isolate or remove `user_ai_preferences` after legacy call sites are migrated.
- Remove `CliAIProvider` from product code paths or explicitly gate it as lab
  tooling.

## Acceptance Criteria

1. Users see one **SOC Assistant** and no agent/backend selector.
2. Only admins or roles with `ai.agent.manage` can configure provider/model/API
   key.
3. The SOC Assistant uses one enterprise provider configuration.
4. CLI Claude/Codex is absent from the product settings flow.
5. Assistant tools are available only when the logged-in user has the required
   permissions.
6. Every write tool pauses for explicit confirmation before execution.
7. Tool calls and confirmations are audited with the real user identity.
8. The assistant can draft custom SOAR playbooks node by node using existing
   node types and graph schemas.
9. Assistant-created playbooks persist only after confirmation and default to
   disabled.
10. Policy orchestration tools keep the existing FortiDashboard BFF governance
    boundary.
