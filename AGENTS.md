# Repository Guidelines

## Language And Scope

Keep this file in English. It is the shared contributor and agent guide for the
FortiDashboard monorepo. Keep it concise, current, and action-oriented. Detailed
design notes belong in `docs/`, not in this file.

FortiDashboard is a modular NG-SOC cockpit. FortiGate remains the first real
read-only Fortinet provider. The unavailable FortiSIEM, FortiSOAR, FortiEDR and
FortiXDR capabilities are represented by internal SOC-lite services, not by fake
Fortinet integrations.

Product map:

```txt
apps/web              -> Vue cockpit, workspace, widgets and SOC UX
apps/api              -> FastAPI BFF, auth/session gateway, integrations and public API
apps/siem_kowalski   -> SIEM-lite: events, detections, incidents and timelines
apps/soar_skipper    -> SOAR-lite: playbooks, dry-runs, approvals and run history
apps/xdr_rico        -> XDR/EDR-lite manager: endpoints, telemetry and timelines
apps/agent_private   -> optional endpoint sensor TUI/CLI feeding xdr_rico
FortiGate            -> first live Fortinet provider, read-only
```

## Non-Negotiable Security Rules

- Never commit hostnames, lab IPs, API keys, tokens, passwords, keytabs, FortiGate secrets, Keycloak secrets or endpoint enrollment tokens.
- FortiGate access is read-only for the MVP. No destructive or write action against FortiGate is allowed without explicit product approval.
- Vue never receives Keycloak access tokens, refresh tokens, client secrets or persisted passwords.
- Browser auth stays BFF-based with HTTP-only cookies, server-side sessions, CSRF protection for mutating requests and audit logs for sensitive actions.
- All state-changing SOC actions must write audit events: auth, integrations, workspace, incidents, playbooks, playbook runs, endpoint enrollment, admin views and approvals.
- `soar_skipper` actions default to `dry_run`. Sensitive or destructive future actions require RBAC, explicit approval and audit.
- AI-generated playbooks and widgets are drafts only until a permitted human validates and applies them.

## Project Structure

```txt
apps/
  api/                 # FastAPI BFF and gateway
  web/                 # Vue 3 + Vite cockpit
  siem_kowalski/       # SIEM-lite service
  soar_skipper/        # SOAR-lite service
  xdr_rico/            # XDR/EDR-lite manager
  agent_private/       # Endpoint sensor TUI/CLI

packages/
  contracts/           # Shared schemas and fixtures
  widget-catalog/      # Visual/widget metadata
  soc-catalog/         # SOC event classes, severities and playbook metadata

docs/
  api/                 # API and internal-service decisions
  architecture/        # Data flow and threat model
  superpowers/         # Planning/spec artifacts
```

Runtime shape:

```txt
Browser -> apps/api -> FortiGate
Browser -> apps/api -> optional Penguin tool integrations
apps/api -> siem_kowalski | soar_skipper | xdr_rico
agent_private -> apps/api or xdr_rico enrollment endpoint
```

Use one shared Postgres instance for the MVP, but keep service-owned modules and
tables. Redis is available for workers. Do not introduce Kafka, OpenSearch,
service mesh or separate databases before the product needs them.

## Stack

Backend services use Python 3.12+, FastAPI, Pydantic, SQLAlchemy, Alembic,
Postgres and Pytest. Use Ruff for linting. Prefer `httpx`, `tenacity`, `orjson`
and typed Pydantic contracts at IO boundaries.

Frontend uses Vue 3, Vite, Composition API with `<script setup>`, Pinia,
Tailwind CSS, Motion for Vue and Lucide Vue.

Useful SOC-lite dependencies:

- `rule-engine` or a constrained Sigma-like evaluator for detections.
- `dramatiq` + Redis for background workers.
- `transitions` for incident/playbook state machines.
- `jinja2` for safe templating of notes, notifications and dry-run payloads.
- `psutil`, `watchdog`, `httpx` and `tenacity` for `agent_private`.

Do not use Wazuh, Shuffle, StackStorm, OpenSearch or Kafka as the core of this
MVP. They may become future integrations.

## Auth, Sessions And SSO

Keycloak is the identity provider, but users interact with FortiDashboard Vue
screens rather than hosted Keycloak forms.

Mandatory auth model:

- Vue calls `/api/auth/login`, `/api/auth/register`, `/api/auth/logout`, `/api/auth/me`, `/api/auth/csrf` and SSO entrypoints through `apps/api`.
- Vue sends `credentials: "include"` and `X-CSRF-Token` for mutating requests.
- Keycloak tokens stay encrypted server-side in `auth_sessions`.
- `auth_sessions.expires_at` follows refresh-token lifetime when available.
- Product roles come from the BFF session. Missing or malformed Keycloak roles fall back to `analyst`, never `admin`.
- Admin-only APIs require role `admin` and must audit successful reads/actions.

SSO/Kerberos support:

- `GET /api/auth/sso/kerberos/init` starts the Authorization Code flow with Keycloak.
- `GET /api/auth/sso/kerberos/callback` validates state, exchanges the code, creates the HTTP-only BFF session and redirects to the configured frontend URL.
- `SessionMiddleware` stores OAuth state in the `f_session` cookie.
- Local AD/Kerberos lab values live in `docker-compose.yml`, `krb5.conf`, `.env` or local host configuration. Do not move secrets or lab-specific keytabs into tracked docs.
- `fortidashboard.keytab` must remain untracked.

Relevant config keys:

```txt
FORTIDASHBOARD_KEYCLOAK_BASE_URL
FORTIDASHBOARD_KEYCLOAK_BROWSER_BASE_URL
FORTIDASHBOARD_KEYCLOAK_VERIFY_SSL
FORTIDASHBOARD_OIDC_ISSUER
FORTIDASHBOARD_SSO_REDIRECT_URI
FORTIDASHBOARD_SSO_POST_LOGIN_URL
FORTIDASHBOARD_SESSION_COOKIE_SAMESITE
FORTIDASHBOARD_SESSION_COOKIE_HTTPONLY
```

## FortiGate Provider

FortiGate integration is real and read-only.

Preserve these capabilities:

- Persist FortiGate integrations per authenticated user.
- Encrypt API keys at rest and never return them.
- Probe read-only before saving live integrations.
- Expose system status, sessions, interfaces, policies, risk, events and anomaly widgets.
- Use short cache TTLs for volatile widgets and expose `refreshIntervalSeconds`.
- Allow local deletion of integrations without changing FortiGate.
- Audit successful and failed integration actions.
- Feed normalized FortiGate events into `siem_kowalski` when SIEM ingestion is used.

## Penguin Tool Integrations

Penguin tools are optional providers, like FortiGate. They are not fixed global
dashboard tabs. A user connects `siem_kowalski`, `xdr_rico` or `soar_skipper`
from the integrations drawer. Only connected providers expose widget presets and
data fields to the workspace.

Connector contract:

```txt
POST /api/integrations/penguin-tools/test
POST /api/integrations/penguin-tools
GET  /api/integrations
DELETE /api/integrations/{integrationId}
```

Workspace widgets for Penguin tools always require `integrationId`. Do not add
global/demo SOC widgets that bypass the integration model.

First setup behavior:

- Penguin widgets are live, not frontend mocks.
- The lite services start with empty in-memory stores.
- Empty incident, endpoint, entity or playbook widgets are expected until `seed_soc_demo.py`, FortiGate ingest or endpoint telemetry populates them.
- Useful logs include `soc_service_*`, `soc_widget_data_*`, `siem_*`, `xdr_*` and `soar_*`.

## SOC-Lite Services

### siem_kowalski

Purpose: convert telemetry into incidents.

Current capabilities:

- Ingest normalized events from FortiGate, endpoint telemetry, manual/demo events and future providers.
- Persist raw events, generated incidents and incident timelines in service-owned SQL tables.
- Apply safe declarative detections for port scan, denied-traffic burst, repeated failed login, suspicious endpoint connection and FortiGate resource pressure.
- Generate incidents with severity, status, timeline and related entities.
- Expose incident widgets: severity counts, recent incidents and top entities.

Gateway API:

```txt
POST  /api/soc/events
GET   /api/soc/events
GET   /api/soc/rules
GET   /api/soc/incidents
GET   /api/soc/incidents/{incidentId}
PATCH /api/soc/incidents/{incidentId}
```

### soar_skipper

Purpose: run safe response workflows over incidents.

Current capabilities:

- Store playbooks as validated JSON graphs/lists.
- Support default disabled playbooks for port scan and suspicious endpoint triage.
- Simulate playbooks and run dry-run workflows.
- Track step state and approval waits.
- Require approval for sensitive steps.
- Audit create, update, simulate, run and approve actions through the BFF.

Gateway API:

```txt
GET  /api/soc/playbooks
POST /api/soc/playbooks
GET  /api/soc/playbooks/{playbookId}
PUT  /api/soc/playbooks/{playbookId}
POST /api/soc/playbooks/{playbookId}/simulate
POST /api/soc/incidents/{incidentId}/playbooks/{playbookId}/run
GET  /api/soc/playbook-runs/{runId}
POST /api/soc/playbook-runs/{runId}/approve
```

### xdr_rico

Purpose: provide endpoint context and correlate host telemetry with SOC incidents.

Current capabilities:

- Create enrollment tokens.
- Ingest endpoint events.
- Persist endpoint enrollment token hashes, inventory, heartbeat, hostname, OS, IPs, current user, health and timelines in service-owned SQL tables.
- Correlate endpoints with SIEM incidents by endpoint ID, IP, hostname and username.
- Expose endpoint timelines, incident endpoint context and health widgets.
- Provide simulator data for demos without installing the agent.

Gateway API:

```txt
GET  /api/weapons/endpoints
GET  /api/weapons/endpoints/{endpointId}
GET  /api/weapons/endpoints/{endpointId}/timeline
GET  /api/soc/incidents/{incidentId}/endpoint-context
POST /api/weapons/enrollments
POST /api/weapons/endpoint-events
```

### agent_private

Purpose: optional endpoint sensor for lab/demo telemetry.

Current capabilities:

- TUI-first operator flow.
- CLI commands for automation and tests.
- Heartbeat, process snapshot, network connection snapshot and deterministic simulator mode.
- Retry/backoff when the backend is offline.

Do not add hidden behavior, credential harvesting, persistence tricks or
destructive response actions.

## Frontend Direction

The Vue app is the cockpit. Do not build separate web UIs for each Penguin tool
in the MVP.

Required UX direction:

- Keep the Power BI-like workspace with drag/drop widgets, data fields, zoom, pan, minimap and custom visuals.
- Treat Visuals as presets and Data fields as bindable provider fields.
- SOC widgets and fields must come from connected providers through `apps/api`.
- Keep the integrations drawer grouped and collapsible.
- Audit drawer stays real-time/polling and must include Penguin tool actions.
- Future SOC consoles should cover incidents, endpoints and playbooks without turning the app into a toy automation demo.

## Workspace Manifests And Sharing

Each user should eventually have a contextual workspace manifest. Treat it as a
versioned workspace configuration document that can be persisted, shared,
imported, exported and rendered by the cockpit.

Manifest intent:

- Store the user's workspace layout, widgets, custom visuals, field bindings,
  visual settings, filters and presentation metadata.
- Keep runtime provider data outside the manifest. The manifest references
  providers, fields and widgets; it must not embed live telemetry or secrets.
- Support sharing a workspace with another user or team without leaking API
  keys, Keycloak tokens, endpoint enrollment tokens or FortiGate credentials.
- Support export/import flows for backup, handoff, marketplace-like templates
  and future presentation generation.
- Support presentation export as a view of the manifest, not as a separate
  dashboard model.

Manifest design rules:

- Use a typed schema with `schemaVersion`, `ownerUserId`, `workspaceId`,
  `name`, `widgets[]`, `layout`, `fieldBindings[]`, `filters`, `dataSources[]`
  and `metadata`.
- Bind widgets to stable provider field IDs and provider types. Avoid binding a
  shared manifest directly to another user's private `integrationId`; resolve
  those bindings when a recipient opens or imports the workspace.
- Store permissions separately from the manifest content: owner, editors,
  viewers and public/export states should be auditable access-control records.
- Add import validation before persistence: schema version, widget catalog IDs,
  visual template IDs, provider compatibility, size limits and unknown fields.
- Redact or reject secrets on import/export. A workspace manifest is never a
  secret transport mechanism.
- Audit create, update, share, unshare, import, export and presentation-export
  actions.

Expected API direction:

```txt
GET    /api/workspaces                                   # list current user workspaces
GET    /api/workspaces/{workspaceId}                     # full workspace incl. origin + presentation
PUT    /api/workspaces/{workspaceId}                     # update layout/widgets
DELETE /api/workspaces/{workspaceId}                     # remove (ws_default protected)
PUT    /api/workspaces/{workspaceId}/presentation       # save presentation metadata
GET    /api/workspaces/{workspaceId}/export             # download manifest JSON
POST   /api/workspaces/import                           # create workspace from manifest
POST   /api/workspaces/{workspaceId}/publish            # publish as community template
GET    /api/workspaces/community                        # list community templates
POST   /api/workspaces/community/{templateId}/install   # clone template into user account
DELETE /api/workspaces/community/{templateId}           # remove template (owner only)
```

Current implementation status:

- Manifest schema lives in `apps/api/app/workspaces/manifest.py` with
  `schemaVersion=1`, `redact_secrets()`, `MANIFEST_MAX_BYTES=256KB` and
  `MANIFEST_MAX_WIDGETS=200`.
- `workspace_specs` table gained `presentation` (JSON) and `origin` (JSON)
  columns through migrations `20260511_0008` and `20260511_0009`.
- `workspace_templates` table backs the community library and tracks publisher,
  install count and visibility.
- Import and template install resolve widget `providerType` against the
  recipient's own FortiGate and Penguin integrations. Widgets without a
  matching integration leave `integrationId` empty and the workspace `origin`
  carries `missingProviderTypes` so the cockpit can prompt the user to connect
  the missing providers.
- Workspace ownership and provenance are surfaced in the sidebar Workspaces
  panel (active workspace badge, origin author, missing providers banner,
  workspace switcher, delete control, presentation editor and community
  library browser).
- Presentation mode renders a fullscreen briefing at
  `/presentation/{workspaceId}` with keyboard nav and severity-aware title
  slide. Slides reference widget instance IDs and carry narration plus
  highlighted field IDs.
- Widgets expose a per-instance rebind action
  (`PATCH /api/workspaces/{workspaceId}/widgets/{instanceId}/integration`)
  so the cockpit can switch a widget's `integrationId` (and its field
  bindings' `integrationId`) to one of the recipient's existing
  integrations without re-importing the workspace. The rebind picker is
  available from the widget header and the "Connection invalid" overlay.

## AI Assistant Roadmap

The internal AI assistant is a cockpit assistant, not an autonomous operator.

Allowed direction:

- Explain current dashboard state.
- Summarize widget data, incidents, endpoint timelines and playbook runs.
- Suggest safe actions and draft playbooks.
- Draft custom widgets using the same Power BI-like data model as the Build Panel.

Forbidden operations:

- Activate playbooks.
- Approve sensitive steps.
- Run destructive actions.
- Modify FortiGate configuration.
- Reveal secrets.
- Execute arbitrary Python, shell, SQL, HTTP or browser code.
- Persist widgets or playbooks as active without user confirmation.

AI-created widgets must be drafts with `fieldBindings[]`, allowed provider field
references, layout suggestions and validation before insertion into
workspace manifests.

## Known Lab Setup Issues

These bit us during the FortiGate live-fire test on 2026-05-12 and should be
fixed (or documented as deliberate constraints) before relying on real scans
for the MVP video. Until then, prefer synthetic events over depending on the
end-to-end nmap pipeline for demo footage.

- **Single-tenant scans are silent against bridged hosts.** Bridge-mode VMs on
  the same `/24` as the FortiGate management interface stay on the L2 segment,
  so the firewall never routes the packets and Forward Traffic logs stay
  empty. Scans only show up when traffic crosses interfaces (e.g. LAN → WAN
  via `port2 → port1`).
- **VMware NAT puts the FortiGate WAN behind the host.** With `port1` on
  vmnet8 (DHCP, `192.168.23.0/24`) and `port2` bridged on the real LAN, the
  FortiGate itself can reach the internet, but VMs on the LAN need the
  FortiGate as their default gateway and a working `port2 → port1` policy.
- **A policy with `set logtraffic all` is mandatory.** Even when packets cross
  interfaces, an accept policy without that flag leaves the dashboard widgets
  empty.
- **The current FortiGate→SIEM ingest is manual.** Operators must call
  `POST /api/soc/fortigate/{integrationId}/ingest-events`. Auto-ingest is part
  of the MVP demo backlog below.
- **`denied_traffic_burst` detection requires `attributes.count >= 20` on a
  single event.** `_fortigate_event_to_siem_event` writes one event per deny
  with `count=1`, so the rule will not fire from raw FortiGate ingestion until
  we aggregate denies per source before forwarding. Use synthetic events with
  inflated counts (or run the seed script) when the demo flow needs an
  incident.
- **VMware bridge ARP can show the host's MAC for a bridged guest.** When the
  scan from Debian reports the Samsung OUI for `192.168.0.100`, that is a
  bridge quirk — `ssh admin@192.168.0.100` and the FortiGate banner are the
  authoritative check.
- **The lab FortiGate VM warned "File System Check Recommended" after an
  unsafe reboot.** Run `execute disk list` / `execute disk scan <ref>` before
  long demos to avoid mid-recording reboots.

## MVP Demo Video Roadmap

Goal: record a single end-to-end video that shows:

1. A workstation triggers an incident (real scan or seeded synthetic event).
2. FortiDashboard pops an alert with an AI-generated incident analysis.
3. The analyst converts the alert into an incident ticket with a triage level
   (T1/T2/T3).
4. From the ticket, the AI suggests containment actions. The analyst approves
   and the AI drafts a `soar_skipper` playbook that contains the incident.
5. The playbook runs (dry-run for the MVP), reports success, and the ticket
   transitions to "Contained" with an audit trail.

The work below is grouped in phases. Each phase ends with something
demo-ready, so the video can be recorded after Phase 4 even if Phase 5 polish
slips. Treat the phases as sequential dependencies; do not start a later
phase before the previous one is mergeable.

### Phase 1 — Reliable incident generation

Status: **in progress — backend done, frontend wiring next.**

Delivered in this branch (`lucas/mvp-demo-roadmap`):

- `apps/api/app/routers/integrations.py` now ships
  `_aggregate_fortigate_events()` which groups raw FortiGate widget records
  by `(eventType, sourceIp)` and emits one SIEM event per group with the
  accumulated `attributes.count` plus a `uniqueDestinationCount` summary,
  highest observed `severity` and the most recent `occurredAt`. The old
  `_fortigate_event_to_siem_event` helper is preserved as a one-record
  passthrough on top of the aggregator for callers/tests that operated on a
  single line.
- `POST /api/soc/fortigate/{integrationId}/ingest-events` now responds with
  `rawEventCount` and `createdCount` (aggregated) and records both in the
  `soc.fortigate_events.ingested` audit detail (`count` retained as an alias
  of `aggregatedCount` for backwards-compat with the existing test suite).
- `POST /api/soc/demo/replay` injects a canned 3-event burst directly into
  `siem_kowalski`: an inbound port scan (`network.deny`, count 42), repeated
  SSH login failures (`auth.failed_login`, count 9) and an
  `endpoint.suspicious_connection` from the demo endpoint back to the
  attacker IP. Every payload carries `source="demo.replay"` and a fresh
  `demoRunId` so dashboards can filter the seed out of real telemetry. The
  call audit-logs `soc.demo.replay` with the run id and event count, and
  fails closed (502 + failure audit) if the SIEM rejects any of the events.

Delivered cockpit-side:

- `services/workspaceClient.ts:replayDemoIncident()` wraps the new endpoint
  and reuses the workspace CSRF helpers.
- `components/workspace/WorkspacePanel.vue` shows a yellow "MVP demo" panel
  with a `Zap` "Replay" button. After a successful replay it surfaces the
  last `demoRunId` and event count so the operator can re-run the recording
  confident the seed actually fired.

Still pending (next phase or stretch):

- Gate the replay button by role (lab/admin only) once Phase 3 introduces a
  richer settings story; for the MVP video it stays open to any
  authenticated analyst.
- Reuse the aggregator in `apps/siem_kowalski` if/when a deduplication step
  is needed on the SIEM side.
- The real-nmap path stays as a stretch goal once the lab-setup issues above
  are resolved; until then, `POST /api/soc/demo/replay` is the documented
  demo trigger.

### Phase 2 — Incident tickets and triage console

Status: **delivered.**

Backend:

- `apps/siem_kowalski/app/main.py` extends `Incident` with `triageLevel`
  (T1/T2/T3), `ticketStatus` (new/investigating/contained/closed),
  `assigneeUserId` and `aiAnalysisId`. `_triage_from_severity()` maps
  `critical|high → T1`, `medium → T2`, otherwise → `T3` at incident
  creation; `ticketStatus` defaults to `new`.
- `GET /incidents` now accepts `triageLevel` and `ticketStatus` filters and
  applies them in-memory after the SQL filter on legacy `status`/`severity`.
- New `PATCH /incidents/{id}/triage` updates any subset of triage fields,
  appends timeline notes for each change (and an optional analyst note), and
  is idempotent when nothing changes.
- Gateway `apps/api/app/routers/soc.py` adds:
  - `GET /api/soc/tickets?triage=T1&status=new&severity=high` — proxies the
    SIEM list and normalizes the response to `{items: [...]}`.
  - `GET /api/soc/tickets/{ticketId}` — proxies the SIEM detail.
  - `PATCH /api/soc/tickets/{ticketId}` — whitelists `triageLevel`,
    `ticketStatus`, `assigneeUserId`, `aiAnalysisId` and `note`; audits via
    `soc.ticket.updated`, `soc.ticket.status_changed` or `soc.ticket.assigned`
    depending on the patch payload.

Frontend:

- New `services/ticketsClient.ts` + `stores/useTicketsStore.ts` that wrap the
  gateway endpoints, manage an 8-second poll and expose `patchTicket()`.
- New `components/tickets/TicketsPanel.vue` rendered inside the sidebar as
  the **SOC Tickets** tab (`Ticket` lucide icon, 480px drawer). The panel
  shows three lanes for T1/T2/T3, filter dropdowns for ticket status and
  severity, and a detail drawer with triage/status buttons that call the
  PATCH endpoint plus a timeline view.
- `Sidebar.vue` registers the new tab next to Workspaces, starts/stops the
  poll on open/close and exposes the lucide `Ticket` icon in the icon rail.

Open items for later phases:

- Wire `aiAnalysisId` to the Phase 3 AI flow so the detail drawer can deep
  link into the analysis.
- Surface ticket origin (incident `eventIds`) inline with a "View source
  events" link.

### Phase 3 — AI assistant integration

- Add a typed provider abstraction at `apps/api/app/ai/` with adapters for the
  Anthropic API (default), an OpenAI-compatible endpoint and an offline
  "scripted" provider used in tests and demos without network access. The
  provider lives behind `Settings.ai_provider` and `Settings.ai_api_key`.
- Implement the cockpit assistant tools listed in the AI backlog
  (`list_data_fields`, `draft_widget`, `validate_widget`,
  `simulate_widget_data`, `add_widget_draft_to_workspace`) plus
  `analyze_incident` and `suggest_containment` for the new flow. All tools
  return drafts; nothing persists until a human confirms.
- Surface AI output through `POST /api/soc/incidents/{incidentId}/analyze` and
  `POST /api/soc/incidents/{incidentId}/containment-suggestions`. Persist the
  analysis on the incident so the ticket and the popup share the same record.
- Frontend: replace the mock chat in `Sidebar.vue` with a real chat that calls
  these endpoints, render the analysis as a toast/popup when an incident is
  raised, and offer a "Open as ticket" CTA that transitions Phase 2 ticket
  creation.

### Phase 4 — AI-drafted containment playbooks

- Add `POST /api/soc/tickets/{ticketId}/draft-playbook` that asks the AI
  provider for a containment plan, validates the response against
  `packages/soc-catalog/playbook-node-types.json`, and stores it as a `draft`
  playbook owned by the requesting user.
- Frontend: from the ticket detail, surface a "Suggest containment" button
  that shows the draft playbook diff with an explanation. The CTA splits into
  "Simulate" (dry-run) and "Approve & run" (still dry-run for MVP). Both
  flows go through the existing `soar_skipper` approval pipeline.
- On successful dry-run, automatically transition the ticket to
  `contained` and append a "Threat contained" timeline entry referencing the
  playbook run. The audit trail must record both the AI suggestion and the
  human approval.
- Keep destructive steps gated behind `dry_run`. Real execution stays out of
  the MVP demo; the AI must never bypass the AGENTS.md AI safety rules.

### Phase 5 — Demo polish and recording prep

- Add toast/banner notifications for new SIEM incidents using a Pinia store
  fed by a 5s poll of `GET /api/soc/incidents?since=`.
- Add a "Walkthrough" demo recipe in `docs/` that lists the exact clicks for
  the video and the synthetic event commands. Keep it next to the
  troubleshooting playbook above.
- Add a smoke test (`apps/web/tests` + `apps/api/tests`) covering the demo
  chain: seed event → incident → AI analysis → ticket → draft playbook →
  dry-run → contained. The test should run in CI without an AI provider via
  the scripted adapter from Phase 3.
- Record the video against a known-good docker compose snapshot. Capture
  before/after screenshots in `docs/mvp/` and link them from the README once
  the recording is locked.

Done when Phase 4 demo video is captured and Phase 5 smoke test is green in
CI. Until then, the synthetic-event path is the recommended demo source.

## Commands

Repository:

```bash
docker compose config --quiet
docker compose up --build
docker compose up -d --build api
FORTIDASHBOARD_MOCK_MODE=true docker compose up -d --build api
```

API:

```bash
cd apps/api && uv sync
cd apps/api && uv run ruff check .
cd apps/api && uv run pytest -q
cd apps/api && uv run alembic upgrade head
```

Web:

```bash
cd apps/web && pnpm install
cd apps/web && pnpm dev
cd apps/web && pnpm test
cd apps/web && pnpm build
cd apps/web && pnpm smoke:canvas
```

Penguin services:

```bash
docker compose up -d --build siem-kowalski soar-skipper xdr-rico redis
docker compose exec api uv run --no-dev python scripts/seed_soc_demo.py
cd apps/siem_kowalski && uv run ruff check . && uv run pytest -q
cd apps/soar_skipper && uv run ruff check . && uv run pytest -q
cd apps/xdr_rico && uv run ruff check . && uv run pytest -q
cd apps/agent_private && uv run pytest -q
cd apps/agent_private && uv run agent-private
```

Docker Compose must stay portable across Linux and Windows. Do not mount host
`node_modules` into containers.

## Backlog

### Platform And Architecture

- [x] Add `packages/soc-catalog` with severities, event classes, entity fields, playbook node types and widget metadata.
- [x] Add schemas/fixtures for `SecurityEvent`, `Incident`, `Endpoint`, `EndpointEvent`, `Playbook`, `PlaybookRun` and `PlaybookStepRun`.
- [x] Document internal-service auth in `docs/api/internal-service-auth.md`.
- [x] Add architecture docs for Penguin tools data flow and threat model.
- [x] Add Redis and health checks for Penguin services.
- [ ] Persist Penguin service data beyond the current in-memory MVP stores.
- [ ] Keep this file updated when contracts, service boundaries or ownership changes.

### siem_kowalski

- [x] Implement event ingestion and incident generation.
- [x] Add initial hardcoded detection rules.
- [x] Add incident status transitions and timelines.
- [x] Ingest normalized FortiGate events through the gateway.
- [x] Expose incident widgets.
- [x] Add persisted raw event payload storage.
- [x] Implement a safe detection rule model/expression evaluator.
- [x] Add high CPU/memory risk rule from FortiGate/system telemetry.

### soar_skipper

- [x] Implement validated playbook schema.
- [x] Implement initial node types.
- [x] Implement simulation endpoint.
- [x] Implement dry-run playbook run state machine.
- [x] Require approval for sensitive steps.
- [x] Audit create/update/simulate/run/approve actions.
- [x] Add default disabled playbooks.
- [ ] Prepare AI/MCP-safe playbook drafting boundary.

### xdr_rico And agent_private

- [x] Implement endpoint enrollment token flow.
- [x] Implement endpoint inventory, heartbeat and timeline.
- [x] Implement endpoint event ingestion.
- [x] Persist endpoint inventory, timeline and enrollment token hashes.
- [x] Add endpoint health widgets.
- [x] Add simulator source.
- [x] Hash endpoint tokens and never return them after creation.
- [x] Implement TUI-first `agent_private` flow plus CLI automation commands.
- [x] Collect heartbeat, process snapshot and network connection snapshot.
- [x] Correlate endpoints with incidents by endpoint ID, IP, hostname and username.
- [ ] Add optional directory monitoring with `watchdog`.

### apps/api Gateway

- [x] Keep Keycloak BFF auth, CSRF, sessions and admin RBAC.
- [x] Add Kerberos/SPNEGO SSO via Keycloak Authorization Code flow.
- [x] Keep FortiGate integration, widgets, workspace persistence and audit log.
- [x] Add optional Penguin tool integrations.
- [x] Add gateway routes for SIEM, SOAR and XDR-lite.
- [x] Add service-to-service client with timeouts, retries and error normalization.
- [x] Extend audit log actions for first Penguin mutating routes.
- [x] Require matching `integrationId` before serving Penguin widget data.
- [x] Add provider data fields for Penguin tools.
- [x] Define and persist versioned workspace manifests as the canonical workspace format.
- [x] Add manifest share/import/export endpoints with schema validation and secret rejection.
- [x] Add RBAC and audit events for workspace share, unshare, import, export and presentation export.
- [x] Add provider-binding resolution so shared manifests do not expose another user's private `integrationId`.
- [ ] Add admin-only audit filters for SOC actions.

### Frontend Cockpit

- [x] Keep workspace, custom visuals, FortiGate widgets, integration CRUD and audit drawer.
- [x] Add SSO button to login.
- [x] Add Penguin connector cards.
- [x] Group and collapse integration sections.
- [x] Load widget catalog from connected provider types.
- [x] Insert widgets with matching provider `integrationId`.
- [x] Group Visual presets by provider category.
- [x] Load SOC data fields and bind custom visuals with field-specific `integrationId`.
- [x] Add generic SOC renderers for bar, feed, table and status-list widgets.
- [ ] Add SOC navigation area for incidents, endpoints and playbooks.
- [ ] Add incident list/detail panel.
- [ ] Add endpoint inventory/timeline panel.
- [ ] Add basic playbook builder and run result UI.
- [x] Add workspace sharing UX: workspace list, origin badges, author details and community library.
- [x] Add manifest import/export UX with validation errors that users can understand.
- [x] Add presentation export UX based on the current workspace manifest.
- [x] Allow per-widget integration rebind so imported workspaces can be reconnected without re-importing.
- [ ] Add richer loading/error/empty states for each SOC-lite tool.

### AI And MCP

- [ ] Define AI-safe operations and forbidden operations as API/tool contracts.
- [ ] Add `draft` status for AI-generated playbooks and widgets.
- [ ] Implement AI tool registry with explicit schemas, permissions, timeouts and audit behavior.
- [ ] Implement `list_data_fields`, `draft_widget`, `validate_widget`, `simulate_widget_data` and `add_widget_draft_to_workspace`.
- [ ] Implement `analyze_incident` and `suggest_containment` tools for the MVP demo flow (Phase 3).
- [ ] Implement `draft_containment_playbook` that emits a soar_skipper-compatible draft validated against `packages/soc-catalog/playbook-node-types.json` (Phase 4).
- [ ] Replace the mock chat in `Sidebar.vue` with a real AI chat backed by the provider abstraction.
- [ ] Require confirmation before persisting AI-generated widgets.
- [ ] Plan MCP server only after stable APIs exist for incidents and playbooks.

### MVP Demo (cross-cutting)

- [x] Phase 1 — Deterministic synthetic incident seed + `/api/soc/demo/replay` endpoint with cockpit "Replay" button in the Workspaces panel.
- [x] Phase 1 — Aggregate FortiGate denies per source IP before SIEM forwarding so `denied_traffic_burst` fires from real ingestion (`_aggregate_fortigate_events`).
- [x] Phase 2 — Add `triageLevel`, `ticketStatus`, `assigneeUserId` and `aiAnalysisId` to the SIEM incident model + ticket CRUD gateway.
- [x] Phase 2 — Add a SOC Tickets navigation panel with T1/T2/T3 lanes, filters and detail drawer.
- [ ] Phase 3 — AI provider abstraction (`apps/api/app/ai/`) with Anthropic, OpenAI-compatible and scripted adapters.
- [ ] Phase 3 — `POST /api/soc/incidents/{id}/analyze` + popup component on the dashboard.
- [ ] Phase 4 — `POST /api/soc/tickets/{id}/draft-playbook` + ticket-side "Suggest containment" flow with dry-run only.
- [ ] Phase 5 — Toast/banner notifications for new SIEM incidents.
- [ ] Phase 5 — Demo walkthrough doc + smoke test covering seed → incident → AI → ticket → playbook → contained.

### Quality

- [x] Add unit tests for event normalization, detection rules and incident transitions.
- [x] Add playbook validation and run state machine tests.
- [x] Add tests proving sensitive playbook actions require approval.
- [x] Add tests proving audit logs redact secrets and endpoint tokens.
- [x] Add tests for endpoint spoofing/invalid enrollment tokens.
- [x] Add API tests for Penguin integrations and widget `integrationId` enforcement.
- [x] Add frontend tests for Penguin connector cards and connected-provider widget catalogs.
- [ ] Add smoke test for full demo chain: FortiGate/demo event -> incident -> endpoint context -> playbook dry-run -> dashboard render.
- [ ] Run `git diff --check` before every commit.

## Coding Conventions

Backend:

- Use typed Python.
- Use Pydantic for request/response boundaries.
- Use SQLAlchemy/Alembic for persisted models.
- Use `snake_case` for modules, functions and variables.
- Use `PascalCase` for Pydantic and ORM classes.
- Keep service modules small and testable.

Frontend:

- Use Vue SFCs with `<script setup>`.
- Use Pinia stores for shared state.
- Components use `PascalCase.vue`.
- Utility files use `camelCase.ts`.
- Visual components receive normalized payloads, not provider-specific clients.

Contracts:

- Any endpoint change must update schemas/fixtures and consuming code.
- Shared payloads belong in `packages/contracts`.
- Widget metadata belongs in `packages/widget-catalog` or `packages/soc-catalog`.

## Git Flow For Humans And AI Agents

- Always inspect current branch and `git status` before editing.
- Run `git fetch origin` before merge-sensitive work.
- Do not work directly on `main` for feature work.
- Branch names should include owner and scope, for example `agent/siem-incident-engine`, `felipe/soar-playbook-runner`, `lucas/soc-console`.
- Keep write scopes isolated.
- Stage only files from the task scope.
- Use small imperative commits, for example `feat(siem): add incident detection engine`.
- Do not commit `.env`, secrets, dumps, keytabs, local certificates or lab-specific values.
- Do not use `git push --force` without explicit approval.
- If `AGENTS.md` conflicts, merge instructions into one coherent document instead of replacing another contributor's section blindly.

Every PR or handoff must include what changed, affected apps/services,
contract changes, verification commands, known gaps and screenshots/recordings
for UI changes.
