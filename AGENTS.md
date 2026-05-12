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
- Docker Compose mounts `infra/keycloak/empty-keytab.placeholder` by default so
  Linux/Windows developers can boot the stack before AD exists. Real Kerberos
  labs must set `FORTIDASHBOARD_KEYTAB_PATH=./fortidashboard.keytab`.
- **Full setup guide:** `configSSOKerberosKeycloak.md` at the repo root has
  the step-by-step for Active Directory (svc account, SPN, `ktpass` keytab,
  DNS records, enctype tuning), the Keycloak side (realm import, Kerberos
  user federation, browser flow), `.env` / `docker-compose` wiring,
  workstation Group Policy / Firefox `network.negotiate-auth.trusted-uris`,
  smoke test (`kvno HTTP/fortidashboard.local@FORTIDASHBOARD.LOCAL`) and a
  troubleshooting matrix (clock skew, duplicate SPN, enctype mismatch,
  redirect URI loops, `state_mismatch`). Anyone picking up the lab from a
  clean machine should read it before touching `krb5.conf` or the realm
  import file.

Relevant config keys:

```txt
FORTIDASHBOARD_KEYCLOAK_BASE_URL
FORTIDASHBOARD_KEYCLOAK_INTERNAL_BASE_URL
FORTIDASHBOARD_KEYCLOAK_BROWSER_BASE_URL
FORTIDASHBOARD_KEYCLOAK_VERIFY_SSL
FORTIDASHBOARD_KEYTAB_PATH
FORTIDASHBOARD_OIDC_ISSUER
FORTIDASHBOARD_SSO_REDIRECT_URI
FORTIDASHBOARD_SSO_POST_LOGIN_URL
FORTIDASHBOARD_SESSION_COOKIE_SAMESITE
FORTIDASHBOARD_SESSION_COOKIE_HTTPONLY
```

Compose URL rules:

- `FORTIDASHBOARD_KEYCLOAK_BASE_URL` is the API-to-Keycloak URL. In Docker
  Compose it is sourced from `FORTIDASHBOARD_KEYCLOAK_INTERNAL_BASE_URL` and
  must default to `http://keycloak:8080`, not a browser hostname.
- `FORTIDASHBOARD_KEYCLOAK_BROWSER_BASE_URL`,
  `FORTIDASHBOARD_OIDC_ISSUER`, `FORTIDASHBOARD_SSO_REDIRECT_URI` and
  `FORTIDASHBOARD_SSO_POST_LOGIN_URL` are browser/host-facing values. The
  default local demo path is `localhost`; AD/Kerberos labs may override them to
  `fortidashboard.local`.
- Kerberos/SPNEGO requires the browser-facing Keycloak hostname to match the
  service principal in `infra/keycloak/realm-fortidashboard.json`
  (`HTTP/fortidashboard.local@FORTIDASHBOARD.LOCAL`). Do not point
  `FORTIDASHBOARD_KEYCLOAK_BASE_URL` at that browser hostname from inside the
  API container.

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

Realization plan:

- Keep `docs/architecture/penguin-tools-realization-plan.md` updated when a
  demo/scripted boundary becomes a real provider capability.
- Demo data must be labeled as demo-only. Live data should identify its source:
  FortiGate, Windows/AD, `agent_private`, manual event or simulator.

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
- `POST /api/soc/demo/replay` injects canned events directly into
  `siem_kowalski`: an inbound port scan (`network.deny`, count 42), repeated
  SSH login failures (`auth.failed_login`, count 9) and an
  `endpoint.suspicious_connection` from the demo endpoint back to the
  attacker IP. Every payload carries `source="demo.replay"`, an
  `attackType` attribute (`port_scan` / `brute_force` / `c2_beacon`) and a
  fresh `demoRunId` so dashboards can filter the seed out of real telemetry.
  The endpoint accepts an optional JSON body
  `{"attackTypes": ["port_scan", ...]}` so the analyst can replay a single
  attack at a time (or the full canonical chain when the body is omitted).
  The call audit-logs `soc.demo.replay` with the run id, event count and
  the per-attack selection, and fails closed (502 + failure audit) if the
  SIEM rejects any of the events.

Delivered cockpit-side:

- `services/workspaceClient.ts:replayDemoIncident()` wraps the new endpoint
  and reuses the workspace CSRF helpers.
- `components/workspace/WorkspacePanel.vue` shows a yellow "MVP demo" panel
  with a `Zap` "Replay" button. Clicking it opens an inline attack picker:
  one chip per individual attack (`Port scan`, `Brute force SSH`, `Beacon
  C2 do endpoint`) plus a highlighted "Cadeia completa / Full chain"
  button. Each chip injects only its attack so the analyst can re-record a
  single phase without resetting the lab. After a successful replay the
  panel surfaces the last `demoRunId`, the event count and the per-attack
  list so the operator can re-run the recording confident the seed
  actually fired.

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

Status: **delivered (incident analysis + containment). Chat replacement still
pending.**

Backend:

- New `apps/api/app/ai/` package with an `AIProvider` Protocol and three
  built-in adapters:
  - `ScriptedAIProvider` — deterministic, network-free; extracts IPs from the
    incident as IoCs and emits a canned 3-step plan. Used in tests and as the
    fallback whenever the configured remote provider misbehaves.
  - `AnthropicAIProvider` — talks to `POST /v1/messages` on the configured
    `ai_base_url` (default `https://api.anthropic.com`) and parses Claude
    text content.
  - `OpenAICompatibleAIProvider` — works against the OpenAI chat completions
    surface (also covers Groq, vLLM, Ollama's OpenAI shim, etc.) with
    `response_format=json_object`.
  - `_extract_json` is forgiving: it pulls the largest JSON blob out of the
    raw model output so a chatty model still produces structured data.
- `Settings` (apps/api/app/core/config.py) gains `ai_provider`, `ai_api_key`,
  `ai_model` and `ai_base_url`. Defaults to the scripted adapter so the lab
  works without API keys.
- Two gateway endpoints in `apps/api/app/routers/soc.py`:
  - `POST /api/soc/incidents/{incidentId}/analyze` — fetches the incident,
    builds a sanitized `IncidentContext`, asks the provider, audits
    `soc.incident.analyzed` (success / partial / failure), assigns a fresh
    `aiAnalysisId` and writes it back on the incident via the new triage
    PATCH endpoint. Best-effort persistence: if the SIEM PATCH fails, the
    analyst still receives the analysis with a partial audit entry.
  - `POST /api/soc/incidents/{incidentId}/containment-suggestions` — same
    flow for `suggest_containment`; failures audit and 502.

Frontend:

- `services/ticketsClient.ts` exposes `analyzeIncident` and
  `suggestContainment` plus typed `IncidentAnalysis` /
  `ContainmentSuggestion` shapes.
- `components/tickets/TicketsPanel.vue` ticket detail drawer ships an
  "AI assistant" block with two buttons:
  - **Analyze** renders headline, summary, risk score, suggested triage +
    ticket status (with an "Apply" CTA wired to `patchTicket`), IoCs, next
    steps and references.
  - **Suggest containment** renders a numbered draft plan, each step badged
    by severity and a `requires approval` flag. Steps explicitly stay as
    drafts until Phase 4 wires them into soar_skipper.
- AI state resets whenever the selected ticket changes.

Open items for later:

- Replace the mock chat box in `Sidebar.vue` with a session-aware chat that
  reuses the same provider abstraction.
- Persist analyses as their own table so the audit + drawer can deep-link
  to a stable URL.
- Add a global toast when a new high-risk analysis is produced.

### Phase 4 — AI-drafted containment playbooks

Status: **delivered.**

Backend:

- `apps/api/app/routers/soc.py` ships `_SOAR_NODE_MAPPING` plus
  `_map_ai_step_to_soar_node()` which translates the AI-emitted
  `playback_node_type` ("firewall.block_ip", "notify.slack",
  "endpoint.collect_telemetry", etc.) into a soar_skipper-compatible
  `NodeType` and a default `sensitive` flag. Unknown types collapse to
  `case.note` so the draft is always inert.
- `POST /api/soc/tickets/{ticketId}/draft-playbook`:
  - Re-fetches the incident, sanitizes it through `_build_incident_context`
    and asks the AI provider for a containment plan.
  - Builds a linear playbook graph starting with
    `trigger.incident_created`. Steps marked sensitive or AI-flagged
    `requires_approval=true` are gated by a synthetic `approval.required`
    node so soar_skipper waits for analyst approval.
  - Posts the playbook to soar_skipper `disabled=false → false`, captures
    the simulation preview and returns `{playbook, simulation, suggestion}`
    together. Failures audit `soc.ticket.playbook_drafted` with
    `outcome="failure"` and 502.
- `POST /api/soc/tickets/{ticketId}/apply-containment`:
  - Body must include `playbookId`.
  - Runs `POST /incidents/{ticketId}/playbooks/{playbookId}/run` (always
    dry-run at the soar_skipper layer).
  - On `completed`: PATCHes the ticket to `ticketStatus="contained"` with a
    timeline note referencing the run id, audits `soc.ticket.contained`.
  - On `waiting_approval`: keeps the ticket in `investigating`, audits
    `soc.ticket.containment_paused`.
  - SIEM PATCH errors degrade to `outcome="partial"` audit but still
    return the run payload.

Frontend:

- `services/ticketsClient.ts` exposes `draftContainmentPlaybook` and
  `applyContainmentPlaybook` plus the new `PlaybookDraftResponse` and
  `ApplyContainmentResponse` shapes (including the dry-run simulation
  steps with sensitivity flags).
- `TicketsPanel.vue` containment block gains a "Draft playbook" button
  that calls the new endpoint and renders the playbook id, simulation
  status and the per-step preview list. A green "Apply (dry-run)" button
  triggers `apply-containment` and, on success, swaps the ticket state in
  place and shows a green banner: "Threat contained" (or "Containment
  paused at approval gate" if the run waits on approval). All
  cockpit-side state resets when the operator switches ticket.

Safety:

- Real soar_skipper runs always execute as `dry_run=True`; the MVP never
  pushes a real config change to FortiGate or endpoints.
- AI-drafted nodes inherit `requires_approval=true` whenever the AI marks
  the step sensitive or whenever the mapped soar node type sits in the
  sensitive set. Approval gates pause execution and are surfaced in the
  banner copy.
- Every mutating route audits success, partial and failure paths so the
  audit drawer mirrors the live MVP video.

Open items for later:

- Connect the analyst "Approve" button to the existing
  `/playbook-runs/{runId}/approve` endpoint so an approval gate can be
  cleared from the same drawer.
- Add an explicit "Threat contained" success ticket linked back to the
  incident timeline (separate from the existing PATCH note).

### Phase 5 — Demo polish and recording prep

Status: **delivered (pre-recording prep). Actual video capture is the only
remaining manual step.**

Delivered:

- `apps/web/src/stores/useIncidentToastsStore.ts` polls `listTickets()` every
  5 seconds; the first poll bootstraps the known-id set so the cockpit does
  not spam the operator with a backlog. New incidents trigger a toast
  capped at 5 visible items with a 12 second TTL.
- `apps/web/src/components/notifications/IncidentToastContainer.vue` renders
  the toast queue in the bottom-right of the dashboard, color-coded by
  severity (`critical`/`high`/`medium`/`low`) with a triage badge, manual
  dismiss and a slide-in transition. Mounted from `views/DashboardView.vue`
  so it appears on every authenticated dashboard route.
- `docs/mvp/walkthrough.md` ships the click-by-click recording script
  (replay → toast → ticket → analyze → apply triage → suggest containment
  → draft playbook → apply dry-run → contained banner → audit trail proof
  → workspace export). The doc also lists what stays off-camera and how to
  fall back to the synthetic replay if a take goes sideways.
- `apps/api/tests/test_mvp_demo_chain.py` is the end-to-end smoke test. It
  swaps the SIEM and SOAR gateway clients for in-memory fakes, keeps the
  AI provider on the deterministic scripted adapter, and asserts the full
  chain: replay creates events and incidents → tickets list includes the
  new ticket with a triage level → analyze persists `aiAnalysisId` on the
  incident → containment suggestion returns at least one step → draft
  playbook creates a SOAR playbook + simulation → apply transitions the
  ticket into `contained` (or `investigating` if the AI parked a sensitive
  step at an approval gate) → audit trail contains every link in the
  chain.

Open items (the only ones blocking the actual video drop):

- Record the video against a fresh `docker compose down -v && docker
  compose up -d --build` snapshot. Capture two takes: scripted AI for the
  baseline recording, Anthropic API for the "AI in the loop" beauty shot.
- Drop the captured `.mp4` into `docs/mvp/recordings/` and link it from
  the README under "MVP demo".

Done when the recording is filed alongside this doc. Until then, the
synthetic-event path is the recommended demo source.

## Settings And Localization

The cockpit settings live behind the gear icon in the sidebar footer. Clicking
it opens `components/settings/SettingsModal.vue` with three tabs:

- **Profile** — read-only view of the current Keycloak BFF session (email,
  display name, roles, authentication state) plus a sign-out shortcut and a
  hint linking to the Keycloak account console for password changes.
- **Appearance** — entry point to the existing `ThemeBuilderModal.vue` so the
  theme/layout builder is a sub-section of settings instead of the gear icon's
  only behavior.
- **Language** — Portuguese (Brazil) / English (US) picker that persists to
  `localStorage` under the key `fortidashboard:locale`.

The translation layer is `vue-i18n` (`apps/web/src/i18n/`) with message
catalogs in `messages/pt-BR.ts` and `messages/en-US.ts`. Components use
`useI18n().t('namespace.key')`. The default locale follows the browser; if it
starts with `en` the cockpit boots in English, otherwise it falls back to
pt-BR. `setLocale()` also keeps `<html lang>` in sync for accessibility.

Translated surfaces:

- `views/LoginView.vue` + SSO failure popup.
- `views/RegisterView.vue` (full form, error fallbacks, switch-link copy).
- `views/PresentationView.vue` (title slide, content slide, navigation
  controls, keyboard hint, severity labels).
- `components/layout/Sidebar.vue` icon-bar tooltips (Dashboard, Assistant,
  Integrations, Workspaces, Tickets, Audit, Settings, Sign out).
- `components/settings/SettingsModal.vue` (every label, locale picker).
- `components/tickets/TicketsPanel.vue` header, subtitle, filters, lane
  labels and descriptions (driven by `computed(t)` so they live-switch
  when the locale changes), ticket cards (status + severity badges),
  detail drawer (open date, triage/status sections, entities + timeline
  headers, all AI assistant copy including buttons, IoCs, next steps,
  references and the containment plan, draft playbook + simulation block,
  and the final "Threat contained" / "Containment paused at approval
  gate" banner). References returned by the AI now render as clickable
  anchors (`target="_blank"` + `rel="noopener noreferrer"`) so MITRE
  ATT&CK, Fortinet docs and CVE links open in a new tab.
- `components/workspace/WorkspacePanel.vue` fully translated: flash
  messages, header/subtitle, MVP demo replay block, origin pill +
  "Detalhes da origem" dialog, workspace list (badges, widget count,
  briefing pill, delete tooltip, loading state), and every modal body
  (export, import preview, publish form fields/placeholders, community
  library filter + cards + install/remove buttons, presentation editor
  including severity options, slide title/narration placeholders and
  "Iniciar apresentação" / "Salvar"). Action labels (`actions` computed)
  and `originBadge()` pull from `t()` so they live-switch with locale.
- `components/audit/AuditFeed.vue` + `components/audit/auditFormat.ts`
  fully translated: header title/subtitle (with per-scope variants —
  admin vs `mine` audit trail — wired from `Sidebar.vue`), loading,
  error and empty states, refresh aria-label, action labels for every
  audit event (`login`, `register`, `logout`, FortiGate
  created/deleted/health-checked, workspace updated, audit viewed) and
  fallback strings (unknown actor / IP unavailable / user agent
  unavailable / time unavailable). `formatAuditEvent()` reads from the
  global `i18n` instance so the formatter stays a pure function.
  `createdAtLabel()` now uses `getLocale()` for `Intl.DateTimeFormat`
  so dates render in the active locale.
- `components/layout/Sidebar.vue` chat box (assistant tab) fully
  translated: header, initial greeting, "Analisando..." indicator,
  input placeholder, integration-required warning, "Adicionei o painel
  X" success and the "no match" fallback. Audit drawer title/subtitle
  props swap between `audit.adminTitle` / `audit.mineTitle` based on
  the `isAdmin` flag.

The AI provider locale switch:

- `IncidentAnalysis` and `ContainmentSuggestion` outputs now speak the
  user's language. The backend `AIProvider.analyze_incident()` and
  `suggest_containment()` methods accept a `locale` kwarg, and the
  scripted adapter produces fully bilingual output (pt-BR / en-US).
- The Anthropic and OpenAI-compatible adapters inject the locale into the
  prompt instructions so the model is told to reply in the requested
  language while still emitting strict JSON. References are explicitly
  requested as URLs to MITRE ATT&CK, Fortinet docs and CVEs so the
  cockpit can render them as hyperlinks.
- The cockpit attaches the current locale to every AI call via the
  `X-FortiDashboard-Locale` HTTP header; the gateway's
  `_request_locale()` reads it (with an `Accept-Language` fallback)
  before invoking the provider.

Components still pending translation (incremental work tracked in the
backlog): the integrations tab in `Sidebar.vue` (Fortinet/Penguin/
endpoint sections, connection state badges, form labels, test/connect
buttons and error strings).

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
- [x] Document demo/scripted boundaries and real Penguin tool use cases.
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
- [x] Add Windows/AD event normalization for failed logons, privileged logons and server file-change signals.
- [x] Add rules for AD failed-login bursts, privileged logon on unusual host and critical server file changes.
- [ ] Label demo events, simulator events and live provider events distinctly in incidents and widgets.

### soar_skipper

- [x] Implement validated playbook schema.
- [x] Implement initial node types.
- [x] Implement simulation endpoint.
- [x] Implement dry-run playbook run state machine.
- [x] Require approval for sensitive steps.
- [x] Audit create/update/simulate/run/approve actions.
- [x] Add default disabled playbooks.
- [x] Persist playbooks and run history in SQL tables.
- [x] Expose `GET /node-types` and `/api/soc/playbook-node-types` as the contract for the future n8n-like visual builder.
- [ ] Add safe real connector boundaries for case note, audit note, notification dry-run and webhook dry-run.
- [ ] Add explicit live-vs-dry-run UI/API flags for every playbook step.
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
- [ ] Add Windows Server lab enrollment smoke path for `agent_private` and validate it manually on the VirtualBox Windows Server VM.
- [x] Add Windows Security Event collection for failed logons and privileged logons.
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
- [x] Forward Windows/AD endpoint events from `xdr_rico` to `siem_kowalski` after authenticated agent ingestion.
- [x] Define and persist versioned workspace manifests as the canonical workspace format.
- [x] Add manifest share/import/export endpoints with schema validation and secret rejection.
- [x] Add RBAC and audit events for workspace share, unshare, import, export and presentation export.
- [x] Add provider-binding resolution so shared manifests do not expose another user's private `integrationId`.
- [ ] Add Windows Server AD/Kerberos SSO smoke test and operator checklist.
- [ ] Add scheduled FortiGate event ingestion control with aggregation status.
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
- [ ] Add visible badges for live, seeded demo, simulator and scripted AI data.
- [ ] Add endpoint detail panel with timeline and related incidents.
- [ ] Add richer loading/error/empty states for each SOC-lite tool.

### AI And MCP

- [ ] Define AI-safe operations and forbidden operations as API/tool contracts.
- [ ] Add `draft` status for AI-generated playbooks and widgets.
- [ ] Implement AI tool registry with explicit schemas, permissions, timeouts and audit behavior.
- [ ] Implement `list_data_fields`, `draft_widget`, `validate_widget`, `simulate_widget_data` and `add_widget_draft_to_workspace`.
- [ ] Implement `analyze_incident` and `suggest_containment` tools for the MVP demo flow (Phase 3).
- [x] Implement `draft_containment_playbook` that emits a soar_skipper-compatible draft via `_SOAR_NODE_MAPPING` + linear graph builder (Phase 4).
- [ ] Replace the mock chat in `Sidebar.vue` with a real AI chat backed by the provider abstraction.
- [ ] Require confirmation before persisting AI-generated widgets.
- [ ] Plan MCP server only after stable APIs exist for incidents and playbooks.

### Settings & i18n

- [x] Add a sidebar `SettingsModal` with Profile / Appearance / Language tabs.
- [x] Add `vue-i18n` with pt-BR + en-US catalogs and a persistent locale picker.
- [x] Translate LoginView, SSO popup, sidebar tooltips and SettingsModal.
- [x] Translate RegisterView, PresentationView and TicketsPanel (header, lanes, filters, detail drawer, AI assistant block).
- [x] Render AI analysis references as clickable hyperlinks (`target="_blank"`).
- [x] Pass the cockpit locale to AI calls (`X-FortiDashboard-Locale` header) so scripted/Anthropic/OpenAI providers reply in the user's language.
- [x] Translate the WorkspacePanel dialog bodies (export preview, publish form, community library entries, presentation editor labels).
- [x] Translate the audit drawer (AuditFeed header, scope-aware admin/mine titles, action labels in `auditFormat.ts`, fallback strings, locale-aware date formatting).
- [x] Translate the Sidebar chat box (assistant tab) including bot replies and input placeholder.
- [ ] Translate the Sidebar integrations tab (Fortinet/Penguin/endpoint sections, connection-state badges, form labels, test/connect buttons and error strings).
- [ ] Add automated tests for locale persistence (localStorage roundtrip + `<html lang>` sync).

### MVP Demo (cross-cutting)

- [x] Phase 1 — Deterministic synthetic incident seed + `/api/soc/demo/replay` endpoint with cockpit "Replay" button in the Workspaces panel.
- [x] Phase 1 — Aggregate FortiGate denies per source IP before SIEM forwarding so `denied_traffic_burst` fires from real ingestion (`_aggregate_fortigate_events`).
- [x] Phase 2 — Add `triageLevel`, `ticketStatus`, `assigneeUserId` and `aiAnalysisId` to the SIEM incident model + ticket CRUD gateway.
- [x] Phase 2 — Add a SOC Tickets navigation panel with T1/T2/T3 lanes, filters and detail drawer.
- [x] Phase 3 — AI provider abstraction (`apps/api/app/ai/`) with Anthropic, OpenAI-compatible and scripted adapters.
- [x] Phase 3 — `POST /api/soc/incidents/{id}/analyze` + AI panel on the ticket detail drawer with risk score, suggested triage and IoCs.
- [x] Phase 3 — `POST /api/soc/incidents/{id}/containment-suggestions` exposed in the ticket drawer as draft steps (no auto-execution).
- [x] Phase 4 — `POST /api/soc/tickets/{id}/draft-playbook` + ticket-side "Draft playbook" / "Apply (dry-run)" flow that auto-contains the ticket on success.
- [x] Phase 5 — Toast/banner notifications for new SIEM incidents (`useIncidentToastsStore` + `IncidentToastContainer.vue`).
- [x] Phase 5 — Demo walkthrough doc (`docs/mvp/walkthrough.md`) + smoke test covering seed → incident → AI → ticket → playbook → contained (`apps/api/tests/test_mvp_demo_chain.py`).

### Production Readiness (MVP → real customer)

The MVP demo flow works end-to-end, but several gaps must close before a
customer can run FortiDashboard against their own SOC. Track each as a
deliverable, not a nice-to-have. Order roughly by blast radius.

Security hardening:

- [x] Rotate every default secret out of tracked files. Shipped in Sprint 1:
      `scripts/bootstrap-secrets.{sh,ps1}` generate strong random values
      for `FORTIDASHBOARD_SECRET_KEY`, `FORTIDASHBOARD_TOKEN_ENCRYPTION_KEY`,
      `FORTIDASHBOARD_KEYCLOAK_CLIENT_SECRET`, `KC_BOOTSTRAP_ADMIN_PASSWORD`
      and `POSTGRES_PASSWORD`. `apps/api/app/core/config.py:_reject_dangerous_defaults`
      refuses to boot when any critical secret still equals a dev default
      (unless `FORTIDASHBOARD_MOCK_MODE=true`). `scripts/sync-keycloak-client-secret.sh`
      aligns Keycloak with `.env` after first `docker compose up`. Tests in
      `apps/api/tests/test_config_secret_validation.py`. The seeded
      analyst/admin credentials in the dev realm import are intentionally
      kept for local demos — disable the realm import on prod and create
      users through the admin console.
- [ ] Disable `allow_weak_crypto` + `java-security-override.properties` and
      the AES128 fallback once the lab is on AES256 only. Document the
      production `krb5.conf` separately.
- [x] Force `FORTIDASHBOARD_SESSION_COOKIE_SECURE=true` and require HTTPS
      end-to-end. Sprint 1.3 ships `infra/caddy/Caddyfile` and
      `docker-compose.prod.yml`: Caddy fronts api/web/keycloak on :443,
      `tls internal` by default for on-prem labs (swap `CADDY_TLS_MODE=""`
      to use ACME/Let's Encrypt for internet-facing deploys). The overlay
      pins Keycloak's `KC_HOSTNAME`/`KC_PROXY_HEADERS` and overrides the
      BFF SSO URLs to `https://${FORTIDASHBOARD_PUBLIC_HOSTNAME}/...` so
      OIDC flows survive the proxy hop. `__Host-` cookie prefix and HSTS
      headers are still open work for Sprint 2 hardening.
- [ ] Extend the auth rate limiter to cover SSO callback, AI endpoints and
      `POST /api/soc/demo/replay` (currently only `/login` is throttled).
- [ ] Cap AI token usage per user/incident (`max_tokens`, budget per day) so
      a runaway prompt cannot bankrupt the customer. Audit prompt + token
      counts.
- [ ] Add a secrets scanner to CI (e.g. `gitleaks`) so keytabs, JWTs and
      FortiGate API keys cannot reach a PR.

Persistence + multi-tenancy:

- [x] Replace the in-memory store in `apps/soar_skipper/app/main.py` with
      SQL-backed storage matching the `siem_kowalski` / `xdr_rico` pattern.
      Shipped in Sprint 1.2: `apps/soar_skipper/app/store.py` defines
      `soar_skipper_playbooks` and `soar_skipper_playbook_runs` tables and
      the `SoarStore` class. `apps/soar_skipper/app/main.py` boots the
      default disabled playbooks idempotently via `_seed_default_playbooks()`
      and the route handlers now read/write through the store.
      `SOAR_SKIPPER_DATABASE_URL` follows the same env-var convention as the
      SIEM/XDR services (sqlite in-memory by default, Postgres in compose).
      `apps/soar_skipper/tests/test_persistence.py` proves playbooks and
      runs survive a "restart" by pointing two `SoarStore` instances at the
      same on-disk SQLite file.
- [x] **Architecture decision (2026-05-12):** FortiDashboard ships as
      **single-tenant per deploy**. Each customer runs its own stack
      (Postgres, Redis, Keycloak, lite services). Row-level `tenant_id`
      columns are intentionally **not** going to be added; PRs that try
      to introduce cross-tenant fan-out must re-open this decision
      first. README and onboarding must call this out so customers do
      not expect SaaS multi-tenancy.
- [ ] Add a row-level retention policy (incidents, audit, demo replays)
      with configurable TTL — required for LGPD/GDPR conversations.
- [ ] Add Alembic migrations for every new SOC column added during the MVP
      phases (verify `apps/api/migrations/versions/` covers ticket fields
      and the new `attackType` audit detail).
- [ ] Backup + restore runbook for Postgres + Redis. The cockpit imports
      manifests, but there is no documented disaster recovery.

Real telemetry path (so the customer can stop using `demo/replay`):

- [ ] Auto-ingest FortiGate events on a schedule instead of requiring a
      manual `POST /api/soc/fortigate/{id}/ingest-events`. Use Dramatiq +
      Redis (already in stack) to poll per integration.
- [ ] Resolve the lab-setup issues in this file (`set logtraffic all`,
      bridged-host visibility) by shipping a one-page operator checklist
      embedded in the cockpit "Integrations → FortiGate" panel.
- [ ] Wire `agent_private` heartbeats into the same XDR ingestion path
      currently exercised by the simulator so a customer can install the
      sensor and see live endpoint data.
- [ ] Surface ingestion lag in the cockpit (last successful poll per
      integration, last incident raised) so the analyst knows the pipeline
      is alive without grepping logs.

Observability + ops:

- [ ] Add structured JSON logging across BFF + lite services with a shared
      `requestId` / `incidentId` correlation id. Today logs are
      f-string-formatted and hard to ship to a SIEM.
- [ ] Expose Prometheus metrics (`/metrics`) for request latency, AI call
      durations, queue depth and detection rule hit counts.
- [ ] Add `/health/ready` + `/health/live` separation (Postgres, Redis,
      Keycloak, SIEM/SOAR/XDR reachability) and wire into the Docker
      Compose healthchecks so dependent services start in the right order.
- [ ] Ship docker-compose overrides (`docker-compose.prod.yml`) that flip
      `start-dev` to `start`, pin image digests and drop the dev volumes.

CI/CD + quality gates:

- [ ] Add a GitHub Actions workflow that runs `pnpm test`, `vue-tsc`,
      `pytest` and `ruff` on every PR. Today there is no `.github/workflows`
      directory, so the test suite is informal.
- [ ] Run the `test_mvp_demo_chain.py` smoke test inside CI so the demo
      flow does not silently break between commits.
- [ ] Add Playwright tests for the cockpit golden paths (login → replay
      demo → triage → contain). Frontend currently has ~13 spec files —
      enough for components but not for the demo path.
- [ ] Run `git diff --check` and the secrets scanner in pre-commit so
      whitespace and credential leaks are caught before push.

Customer-facing UX gaps:

- [ ] First-run / onboarding flow: bootstrap the first admin user, walk
      through integration setup, surface "what to do next" instead of
      dropping the user on an empty dashboard.
- [ ] Richer empty/error/loading states per SOC-lite tool (already tracked
      in Frontend Cockpit backlog — promote to MVP-blocking).
- [ ] Finish the Sidebar integrations tab translation (`workspaces` is
      done; the integrations form is still PT/EN-mixed hard-coded copy).
- [ ] Document supported deployments (single-host docker compose vs
      managed Postgres + managed Keycloak). Today `README.md` only covers
      the dev stack.
- [ ] Customer-facing changelog/release notes — required before any
      external rollout so customers know what shipped.

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
