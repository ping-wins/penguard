# LangGraph Triage Readiness Notes

Date: 2026-05-14

## Goal

Document what is already ready for a future LangGraph ticket triage workflow and
what still needs a dedicated implementation slice. The workflow should reuse the
same audited FortiDashboard boundaries that the cockpit uses today; it must not
call SIEM, SOAR, XDR or FortiGate internals directly from a model runtime.

## Ready Boundaries

### Ticket and incident context

The gateway already exposes the ticket-oriented incident surface:

- `GET /api/soc/tickets`
- `GET /api/soc/tickets/{ticketId}`
- `PATCH /api/soc/tickets/{ticketId}`
- `POST /api/soc/incidents/{incidentId}/analyze`
- `POST /api/soc/incidents/{incidentId}/containment-suggestions`

These endpoints handle BFF auth, CSRF for mutations, locale-aware AI output and
audit events. A LangGraph node can call them through an internal tool wrapper
instead of duplicating incident sanitization logic.

### SOAR playbook lifecycle

The cockpit now exercises the same SOAR lifecycle a durable workflow needs:

- List playbooks through `GET /api/soc/playbooks`.
- Create a disabled/draft dry-run playbook through `POST /api/soc/playbooks`.
- Simulate through `POST /api/soc/playbooks/{playbookId}/simulate`.
- Start a dry-run through
  `POST /api/soc/incidents/{incidentId}/playbooks/{playbookId}/run`.
- Pause on approval gates and resume through
  `POST /api/soc/playbook-runs/{runId}/approve`.

The new SOAR Playbooks console also includes a linear n8n-like builder that
creates `trigger.incident_created -> step_1 -> step_2 ...` graphs using the
existing safe node types. That UI is intentionally dry-run only and should map
cleanly to a future LangGraph "draft containment playbook" node.

### Internal AI tool registry

`apps/api/app/ai/tools/` is the shared internal tool boundary for cockpit chat,
LangGraph and future MCP. Today it is strongest for widget drafting. Incident
analysis and containment suggestions are implemented as gateway routes and AI
provider methods, but are not yet exported as formal tool specs.

## Required LangGraph Slice

A future implementation should add a small set of typed internal tools before
wiring the graph:

1. `get_ticket_context(ticketId)`
   - Reads the gateway ticket detail.
   - Returns sanitized incident fields, timeline, entities and current triage
     state.
2. `analyze_ticket(ticketId, locale)`
   - Reuses the existing analysis route/provider path.
   - Persists/returns `aiAnalysisId` exactly like the cockpit flow.
3. `suggest_containment(ticketId, locale)`
   - Reuses the existing containment suggestion route/provider path.
   - Must return draft steps only.
4. `draft_dry_run_playbook(ticketId, suggestion)`
   - Reuses the `_SOAR_NODE_MAPPING` / linear graph semantics already used by
     the gateway and cockpit builder.
   - Produces a disabled or dry-run-only playbook until explicit user
     confirmation.
5. `simulate_playbook(playbookId)`
   - Returns step previews and approval gates.
6. `request_human_approval(runId | playbookId)`
   - Suspends the graph. LangGraph must not self-approve sensitive steps.

## Safety Rules For The Graph

- Never approve sensitive SOAR steps automatically.
- Never mutate FortiGate or endpoints directly; SOAR stays dry-run for the MVP.
- Never expose raw Keycloak tokens, FortiGate credentials, endpoint enrollment
  tokens or API keys in graph state.
- Persist only sanitized ticket/workflow state, not raw provider secrets or
  full widget payloads.
- Every state-changing node must use gateway routes that already audit success,
  partial and failure outcomes.
- AI-created widgets/playbooks remain drafts until a permitted human confirms
  them.

## UX Readiness

The cockpit now has the minimum operator surfaces that a LangGraph workflow can
link back to:

- SOC Tickets drawer for triage, analysis and containment suggestions.
- SOAR Playbooks drawer for playbook list/detail, simulation, dry-run execution,
  approval resume and linear draft creation.
- Audit drawer for SOC/playbook events.
- Locale-aware labels for the new playbook console in `pt-BR` and `en-US`.

## Remaining Gaps

- Export `analyze_incident`, `suggest_containment` and playbook drafting through
  `apps/api/app/ai/tools/registry.py` as formal tool specs.
- Add persistent LangGraph run storage/checkpointing and correlation ids.
- Add a cockpit view for graph run state: queued, analyzing, waiting approval,
  contained, failed/partial.
- Add rate limits/token budget accounting for AI-heavy graph nodes.
- Add tests that prove graph approval pauses cannot be bypassed by model output.
