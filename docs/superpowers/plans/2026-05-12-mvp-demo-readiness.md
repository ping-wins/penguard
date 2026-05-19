# MVP Demo Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the MVP demo cockpit clearer and more complete by surfacing data provenance, endpoint-related incidents, endpoint-to-SIEM suspicious activity forwarding, and approval-driven containment completion.

**Architecture:** Keep Penguard single-cockpit and BFF-centered. Backend changes stay in `apps/api/app/routers/soc.py` plus existing SIEM/XDR/SOAR contracts; frontend changes stay in Vue clients/stores/components already backing tickets, endpoints, and widgets.

**Tech Stack:** FastAPI, Pytest, Vue 3, Pinia, Vitest.

---

### Task 1: Normalize Source Badges In The Cockpit

**Files:**
- Create: `apps/web/src/utils/sourceBadges.ts`
- Modify: `apps/web/src/components/widgets/WidgetGenericData.vue`
- Modify: `apps/web/src/components/tickets/TicketsPanel.vue`
- Test: `apps/web/tests/unit/widgetRenderers.test.ts`

- [ ] Write a failing Vitest case proving SOC rows with `source="demo.replay"` render `Seeded demo`, rows with `attributes.source="simulator"` render `Simulator`, normal FortiGate/SIEM rows render `Live`, and AI analysis rendered from scripted provider can render `Scripted AI` once the backend exposes provider metadata.
- [ ] Implement `sourceBadgeFor(value)` that inspects `source`, `attributes.source`, `attributes.demoRunId`, `demoRunId`, `origin.kind`, and `provider`.
- [ ] Render compact badges in generic SOC widgets and ticket/AI detail sections without replacing existing severity/status badges.
- [ ] Run `pnpm --dir apps/web test -- widgetRenderers.test.ts`.

### Task 2: Endpoint Related Incidents

**Files:**
- Modify: `apps/api/app/routers/soc.py`
- Modify: `apps/api/tests/test_soc_gateway.py`
- Modify: `apps/web/src/services/endpointsClient.ts`
- Modify: `apps/web/src/stores/useEndpointsStore.ts`
- Modify: `apps/web/src/components/endpoints/EndpointsPanel.vue`
- Test: `apps/web/tests/unit/endpointsClient.test.ts`
- Test: `apps/web/tests/unit/endpointsPanel.test.ts`

- [ ] Write a failing API test for `GET /api/weapons/endpoints/{endpointId}/related-incidents` that filters SIEM incidents by endpoint ID, hostname, username, or IP using the XDR endpoint record.
- [ ] Implement the BFF route by fetching the endpoint from XDR, listing SIEM incidents, and returning `{endpointId, items, total}` with no secrets.
- [ ] Write failing frontend tests for the client/store/panel loading related incidents when an endpoint is selected.
- [ ] Render a compact `Related incidents` section above the endpoint timeline with title, severity, triage, ticket status, and source badge.
- [ ] Run `cd apps/api && uv run pytest tests/test_soc_gateway.py -q -k related_incidents` and `pnpm --dir apps/web test -- endpointsClient.test.ts endpointsPanel.test.ts`.

### Task 3: Endpoint Suspicious Activity Forwarding

**Files:**
- Modify: `apps/api/app/routers/soc.py`
- Modify: `apps/api/tests/test_soc_gateway.py`
- Modify: `apps/xdr_rico/app/main.py`
- Test: `apps/xdr_rico/tests/test_core.py`

- [ ] Write a failing API test proving an authenticated `suspicious.process` or suspicious `connection.snapshot` endpoint event forwards a SIEM event with `eventType="endpoint.suspicious_connection"`.
- [ ] Preserve `observedSourceIp`, `xdrTimelineItemId`, `originKind`, `originSource`, and endpoint identity fields in the forwarded SIEM event.
- [ ] Add or normalize XDR simulator labels so simulator timeline items consistently carry `attributes.source="simulator"`.
- [ ] Run `cd apps/api && uv run pytest tests/test_soc_gateway.py -q -k suspicious_connection` and `cd apps/xdr_rico && uv run pytest tests/test_core.py -q`.

### Task 4: Approval Completion For Containment

**Files:**
- Modify: `apps/api/app/routers/soc.py`
- Modify: `apps/api/tests/test_soc_gateway.py`
- Modify: `apps/api/tests/test_mvp_demo_chain.py`
- Modify: `apps/web/src/services/ticketsClient.ts`
- Modify: `apps/web/src/components/tickets/TicketsPanel.vue`

- [ ] Write a failing API test proving `POST /api/soc/playbook-runs/{runId}/approve` PATCHes the linked SIEM ticket to `ticketStatus="contained"` when SOAR returns `status="completed"`.
- [ ] Preserve partial success semantics if SOAR approves but SIEM patch fails, and audit success/partial/failure.
- [ ] Expose a ticket-side approve button when an applied playbook returns `waiting_approval`.
- [ ] Run `cd apps/api && uv run pytest tests/test_soc_gateway.py tests/test_mvp_demo_chain.py -q` and targeted ticket frontend tests.

### Task 5: Backlog And Demo Documentation

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/mvp/walkthrough.md`
- Modify: `docs/mvp/windows-server-agent-smoke.md`

- [ ] Mark delivered items from this cut in `AGENTS.md`.
- [ ] Document that demo/simulator/live/scripted labels are visible and how the operator should interpret them.
- [ ] Document endpoint related incidents and approval-driven containment in the walkthrough.
- [ ] Run `git diff --check`.
