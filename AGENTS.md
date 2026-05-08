# Repository Guidelines

## Product Direction

FortiDashboard is evolving from a FortiGate-focused dashboard into a modular NG-SOC cockpit. The product still keeps FortiGate as the first real read-only provider, but the MVP no longer depends on access to FortiSIEM, FortiSOAR, FortiEDR, or FortiXDR. Those products were not available as reliable self-service trials, so the repository will implement internal lite SOC tools named after cartoon penguins.

The product narrative is:

```txt
FortiDashboard -> visual cockpit, auth gateway, workspace, widgets and UX
siem_kowalski  -> SIEM-lite: analysis, event ingestion, rules, incidents and timelines
soar_skipper   -> SOAR-lite: command, low-code playbooks, dry-run actions and approvals
xdr_rico       -> XDR/EDR-lite manager: endpoint inventory, telemetry, response context and correlation
agent_private  -> optional endpoint sensor feeding xdr_rico
FortiGate      -> first live Fortinet provider, read-only
```

Keep the implementation honest: FortiGate integration is real; the Penguin tools are our own SOC-lite capabilities. Do not pretend unavailable Fortinet products are integrated.

Name mapping:

| Tool | App path | Role | Why this name |
| --- | --- | --- | --- |
| `siem_kowalski` | `apps/siem_kowalski` | SIEM-lite | Analytical brain that turns telemetry into incidents |
| `soar_skipper` | `apps/soar_skipper` | SOAR-lite | Operational commander that coordinates response workflows |
| `xdr_rico` | `apps/xdr_rico` | XDR/EDR-lite manager | Arsenal/context holder for endpoint and response telemetry |
| `agent_private` | `apps/agent_private` | Endpoint sensor | Field operator that reports host telemetry back to `xdr_rico` |

## Non-Negotiable Security Rules

- Never hardcode hostnames, lab IPs, API keys, tokens, passwords, FortiGate secrets, Keycloak secrets, or endpoint enrollment tokens.
- FortiGate access remains read-only for the MVP. No destructive or write action against FortiGate is allowed without explicit product approval.
- Browser auth stays BFF-based: Vue never receives Keycloak access tokens, refresh tokens, client secrets, or persisted passwords.
- Sessions use HTTP-only cookies, server-side session storage, CSRF protection for mutating requests, and audit logs for sensitive actions.
- All SOC actions that change state must write audit events: auth, integration changes, workspace changes, incident changes, playbook changes, playbook runs, endpoint enrollment, admin views and approvals.
- `soar_skipper` actions default to `dry_run`. Any future destructive step needs explicit approval, RBAC and audit.
- AI-generated playbooks and widgets are drafts only. A human admin or analyst with permission must validate and activate/apply them.

## Contributors and Ownership

The backlog is no longer limited to Felipe/backend and Lucas/frontend. Any human or AI contributor can own a work item if the issue defines scope, write boundaries and acceptance criteria.

Expected roles:

- Product/architecture lead: owns scope, tradeoffs, merges and demo narrative.
- Backend contributors: FastAPI services, contracts, workers, persistence, security and tests.
- Frontend contributors: Vue cockpit, workspace, widgets, SOC consoles and UX polish.
- Security reviewers: threat model, RBAC, secrets, audit, destructive-action checks and test gaps.
- AI agents: work only from explicit issues with allowed write paths and verification commands.

Every task must state:

```txt
Goal
Allowed write scope
Do not touch
API/schema contract
Acceptance criteria
Verification commands
```

## Monorepo Scaffolding

Target structure:

```txt
apps/
  api/                 # FastAPI BFF: auth, session, gateway, workspace and public API
  web/                 # Vue 3 + Vite cockpit: dashboard, canvas, SOC consoles and widgets
  siem_kowalski/       # SIEM-lite headless app
  soar_skipper/        # SOAR-lite headless workflow app
  xdr_rico/            # XDR/EDR-lite manager app
  agent_private/       # Optional endpoint sensor/CLI

packages/
  contracts/           # Shared schemas, fixtures and generated API clients
  widget-catalog/      # Visual/widget metadata
  soc-catalog/         # Event classes, severities, playbook nodes and SOC widgets

docs/
  api/                 # Payload examples and API decisions
  architecture/        # SOC-lite architecture and threat model
```

Runtime shape for the MVP:

```txt
Browser -> apps/api -> internal Penguin services
Browser -> apps/api -> FortiGate provider
Penguin services -> Postgres + Redis
agent_private -> apps/api or xdr_rico enrollment endpoint
```

Use a shared Postgres instance for MVP, but keep service-owned tables/modules. Add Redis when background workers land. Avoid Kafka, OpenSearch, service mesh, or multi-database complexity before the demo.

## Stack

Backend services use Python 3.12+, FastAPI, Pydantic, SQLAlchemy, Alembic, Postgres and Pytest. Use Ruff for linting. Prefer `httpx`, `tenacity`, `orjson`, and typed Pydantic contracts for IO boundaries.

Frontend uses Vue 3, Vite, Composition API with `<script setup>`, Pinia, Tailwind CSS, Motion for Vue and Lucide Vue.

Recommended SOC-lite dependencies:

- `rule-engine` or a constrained Sigma-like evaluator for detection rules.
- `dramatiq` + Redis for workers when async processing is needed.
- `transitions` for incident/playbook state machines.
- `jinja2` for safe templating of notes, notifications and dry-run payloads.
- `psutil`, `watchdog`, `httpx` and `tenacity` for `agent_private`.
- `pySigma` may be used for parsing/importing Sigma-style rules, but do not make the MVP depend on a full SIEM platform.

Do not use Wazuh, Shuffle, StackStorm, OpenSearch, Kafka or similar platforms as core dependencies for this MVP. They can be future integrations, but using them as the core would change the product narrative.

## Auth, RBAC and Session Model

Keycloak remains the identity provider, but users interact with FortiDashboard Vue screens, not hosted Keycloak forms.

Mandatory model:

- `apps/api` is the BFF/auth gateway.
- Vue calls `/api/auth/login`, `/api/auth/register`, `/api/auth/logout`, `/api/auth/me` and `/api/auth/csrf`.
- Vue sends `credentials: "include"` and `X-CSRF-Token` for mutating requests.
- Keycloak tokens stay server-side in encrypted session storage.
- `auth_sessions.expires_at` follows refresh-token lifetime when available, not short access-token lifetime.
- Product roles come from the BFF session. Missing/malformed Keycloak roles must fall back to `analyst`, never `admin`.
- Admin-only APIs require role `admin` and must audit successful reads/actions.

Known dev user for local PoC may exist in the Keycloak realm, but production admin creation/promotion happens in Keycloak, not public registration.

## FortiGate Provider

FortiGate remains the first live provider and must keep working while the Penguin tools are added.

Current capabilities to preserve:

- Persist FortiGate integrations per authenticated user.
- Encrypt API keys at rest and never return them.
- Probe read-only before saving a live integration.
- Expose system status, sessions, interfaces, policies, risk, events and anomaly widgets.
- Use short cache TTLs for volatile widgets and expose `refreshIntervalSeconds`.
- Allow local deletion of integrations without changing FortiGate.
- Audit successful and failed integration actions.

FortiGate event outputs should feed `siem_kowalski` as normalized security events when SIEM-lite ingestion lands.

## Penguin Tools Architecture

### siem_kowalski: SIEM-lite

Purpose: convert telemetry into incidents.

Capabilities:

- Ingest normalized security events from FortiGate, endpoint telemetry, manual/demo events and future providers.
- Store raw and normalized event payloads.
- Apply detection rules on event fields and simple time windows.
- Generate incidents with severity, status, timeline and related entities.
- Correlate by source IP, destination IP, hostname, username, integration ID and endpoint ID.
- Expose fields for dashboard widgets and investigation views.

MVP limits:

- No massive log pipeline.
- No full query language.
- No long-term retention guarantees beyond demo needs.
- No claim of being a full enterprise SIEM.

External API through `apps/api`:

```txt
POST /api/soc/events
GET  /api/soc/events
GET  /api/soc/incidents
GET  /api/soc/incidents/{incidentId}
PATCH /api/soc/incidents/{incidentId}
```

Initial event shape:

```json
{
  "source": "fortigate",
  "eventType": "network.deny",
  "severity": "medium",
  "occurredAt": "2026-05-08T12:00:00.000Z",
  "entities": {
    "sourceIp": "192.0.2.10",
    "destinationIp": "198.51.100.20",
    "hostname": "endpoint-01",
    "username": "analyst"
  },
  "attributes": {
    "policyId": "12",
    "action": "deny",
    "count": 25
  }
}
```

Initial incident shape:

```json
{
  "id": "inc_01",
  "title": "Possible port scan",
  "severity": "high",
  "status": "open",
  "source": "kowalski",
  "entities": {
    "sourceIp": "192.0.2.10",
    "endpointId": "end_01"
  },
  "summary": "Multiple denied connections from the same source in a short window.",
  "createdAt": "2026-05-08T12:01:00.000Z"
}
```

### soar_skipper: SOAR-lite

Purpose: run safe response workflows over incidents.

Capabilities:

- Store playbooks as validated JSON graphs.
- Support low-code construction in FortiDashboard.
- Execute triggers, conditions, enrichment steps, approvals, notes, notifications and dry-run recommendations.
- Track step-level state: `pending`, `running`, `waiting_approval`, `completed`, `failed`.
- Audit every playbook creation, update, simulation, approval and run.
- Provide simulation before activation.

MVP limits:

- No destructive actions by default.
- No automatic FortiGate writes.
- No arbitrary Python/user code execution in playbooks.
- No workflow loops until guardrails are implemented.

Playbook graph shape:

```json
{
  "id": "pb_port_scan_triage",
  "name": "Port Scan Triage",
  "enabled": false,
  "trigger": { "type": "incident.created", "filters": { "severity": ["high", "critical"] } },
  "nodes": [
    { "id": "enrich_ip", "type": "enrich.ip", "config": { "field": "entities.sourceIp" } },
    { "id": "approval", "type": "approval.required", "config": { "role": "admin" } },
    { "id": "recommend", "type": "fortigate.recommend_block", "config": { "mode": "dry_run" } }
  ],
  "edges": [
    { "from": "enrich_ip", "to": "approval" },
    { "from": "approval", "to": "recommend" }
  ]
}
```

External API through `apps/api`:

```txt
GET  /api/soc/playbooks
POST /api/soc/playbooks
GET  /api/soc/playbooks/{playbookId}
PUT  /api/soc/playbooks/{playbookId}
POST /api/soc/playbooks/{playbookId}/simulate
POST /api/soc/incidents/{incidentId}/playbooks/{playbookId}/run
GET  /api/soc/playbook-runs/{runId}
```

Future AI/MCP direction:

- The internal AI can suggest and draft playbooks.
- Drafts must be disabled by default.
- `soar_skipper` validates schema and simulates behavior before activation.
- A future MCP server may expose tools such as `list_incidents`, `draft_playbook`, `validate_playbook`, `simulate_playbook`, `create_case_note`, `list_data_fields` and `draft_widget`.
- AI cannot activate a playbook or approve destructive actions.

### xdr_rico: XDR/EDR-lite Manager

Purpose: provide endpoint context and correlate host telemetry with network incidents.

Capabilities:

- Register endpoints.
- Track heartbeat, hostname, OS, local IPs, logged-in user and health.
- Ingest endpoint events: process snapshot, connection snapshot, login event, file change, suspicious process and health signal.
- Correlate endpoint IDs with SIEM incidents using IP, hostname and username.
- Expose endpoint timeline and investigation widgets.

MVP limits:

- No kernel driver.
- No malware prevention claim.
- No real host isolation.
- No remote command execution in the first cut.

External API through `apps/api`:

```txt
GET  /api/weapons/endpoints
GET  /api/weapons/endpoints/{endpointId}
GET  /api/weapons/endpoints/{endpointId}/timeline
POST /api/weapons/endpoint-events
POST /api/weapons/enrollments
```

Endpoint event shape:

```json
{
  "endpointId": "end_01",
  "eventType": "process.snapshot",
  "occurredAt": "2026-05-08T12:00:00.000Z",
  "hostname": "demo-endpoint-01",
  "ipAddresses": ["192.0.2.50"],
  "attributes": {
    "processes": [
      { "pid": 1200, "name": "powershell.exe", "username": "SOC-DEMO\\analyst" }
    ]
  }
}
```

### agent_private

Purpose: optional endpoint sensor that connects a host to `xdr_rico`.

Capabilities:

- Register host with an enrollment token.
- Send heartbeat and host identity.
- Collect lightweight telemetry using `psutil` and optional `watchdog`.
- Send process snapshots, connection snapshots, user/session data and monitored file changes.
- Retry safely when offline.

MVP limits:

- No privileged persistence requirement.
- No destructive response.
- No credential harvesting.
- No hidden behavior. The agent is for lab/demo telemetry.

For demo speed, provide both a real Python CLI and a simulator mode that emits believable telemetry.

## Frontend Direction

The Vue app remains the cockpit. Do not build separate web UIs for each Penguin tool in the MVP.

Required UX areas:

- Existing Power BI-like workspace with drag/drop widgets, zoom, pan, minimap and custom visuals.
- SOC overview page or workspace templates for incidents, endpoint posture and playbooks.
- AI assistant panel that can inspect current dashboard state, explain data, suggest actions and draft visualizations.
- Incident console: severity, status, timeline, entities, related endpoint, recommended playbook.
- Playbook builder: start with simple low-code form/list builder; visual graph editor can follow.
- Playbook run view: step status, dry-run results, approval state and audit trail.
- Endpoint view: inventory, heartbeat, process/connection snapshots and related incidents.
- Audit drawer remains real-time/polling and must include Penguin tool actions.

The frontend should consume `apps/api` only. It should not call `siem_kowalski`, `soar_skipper` or `xdr_rico` directly from the browser.

## FortiDashboard AI Agent

The internal AI agent is a cockpit assistant, not an autonomous operator. It should understand the current workspace, available data fields, widgets, incidents, endpoints, playbooks and audit context. It can propose useful views and safe actions, but sensitive changes require explicit user confirmation and RBAC.

AI goals:

- Explain what the analyst is seeing in the dashboard.
- Find relevant widgets, incidents, endpoint context and playbook runs.
- Draft custom widgets from the Power BI-like data model.
- Suggest playbooks or response steps.
- Summarize incident timelines and endpoint activity.
- Help build workspace layouts from natural language.

AI tool surface should be explicit and auditable. Do not give the model direct database access, arbitrary HTTP access or arbitrary code execution. Each tool must have a schema, permission level, timeout, sanitized output and audit behavior.

Initial tool groups:

```txt
Dashboard/view tools:
  get_workspace
  list_widgets
  get_widget_data
  list_widget_catalog
  list_data_fields
  search_dashboard

SOC investigation tools:
  list_incidents
  get_incident
  summarize_incident_timeline
  list_endpoints
  get_endpoint
  get_endpoint_timeline

SOAR tools:
  list_playbooks
  get_playbook
  draft_playbook
  validate_playbook
  simulate_playbook
  create_case_note

Widget authoring tools:
  draft_widget
  validate_widget
  simulate_widget_data
  add_widget_draft_to_workspace
```

Forbidden AI operations:

- Activate playbooks.
- Approve sensitive playbook steps.
- Run destructive actions.
- Modify FortiGate configuration.
- Reveal API keys, tokens, passwords or enrollment secrets.
- Execute arbitrary Python, shell, SQL or browser code.
- Persist a widget/playbook as active without user confirmation.

### AI-Created Custom Widgets

Custom widget creation is a first-class AI capability. The AI must use the same Power BI-like model available in the Build Panel:

```txt
Provider -> data groups -> fields -> visual template -> field bindings -> workspace widget
```

The AI should be able to answer requests like:

```txt
"Create a card showing active critical incidents."
"Build a bar chart comparing denied traffic by source IP."
"Add an endpoint health table for hosts involved in open incidents."
"Create a timeline widget for this incident."
```

The implementation must produce a draft `WorkspaceWidget` with:

- `catalogId` or `templateId`.
- `title`.
- `visualType`.
- `fieldBindings[]`.
- `query` or `source` references to allowed provider fields.
- `layout` suggestion.
- `explanation` of what the widget shows.
- `status: "draft"` until the user applies it.

The AI must call `list_data_fields` before drafting a widget unless the available fields are already in context. It must call `validate_widget` before a draft can be added to the workspace. The frontend should render drafts distinctly and require user confirmation to persist them into `workspace_specs`.

Example draft widget:

```json
{
  "status": "draft",
  "title": "Open Incidents by Severity",
  "visualType": "bar_chart",
  "source": "siem_kowalski",
  "fieldBindings": [
    { "fieldId": "incident.severity", "role": "category" },
    { "fieldId": "incident.count", "role": "value" }
  ],
  "layout": { "x": 120, "y": 120, "w": 420, "h": 280 },
  "explanation": "Compares currently open incidents grouped by severity."
}
```

## Commands

Existing commands:

- `docker compose up --build`: run API, web, Postgres and Keycloak.
- `docker compose up -d --build api`: run backend stack for live API development.
- `FORTIDASHBOARD_MOCK_MODE=true docker compose up -d --build api`: opt into mock fixtures.
- `cd apps/api && uv sync`: install API dependencies.
- `cd apps/api && uv run pytest`: run API tests.
- `cd apps/api && uv run ruff check .`: lint API.
- `cd apps/api && uv run alembic upgrade head`: apply API migrations.
- `cd apps/web && pnpm install`: install frontend dependencies.
- `cd apps/web && pnpm dev`: run Vite frontend.
- `cd apps/web && pnpm test`: run frontend tests.
- `cd apps/web && pnpm build`: build frontend.

Penguin tool commands:

- `docker compose up -d --build siem-kowalski soar-skipper xdr-rico redis`
- `docker compose exec api uv run --no-dev python scripts/seed_soc_demo.py`: seed demo SOC events, endpoint telemetry and default playbooks from inside the Compose network.
- `cd apps/siem_kowalski && uv run pytest`
- `cd apps/soar_skipper && uv run pytest`
- `cd apps/xdr_rico && uv run pytest`
- `cd apps/agent_private && uv run pytest`
- `cd apps/agent_private && uv run agent-private simulate --endpoint-id demo-endpoint-01`: print deterministic endpoint telemetry without sending it.
- `cd apps/agent_private && uv run agent-private heartbeat --endpoint-id demo-endpoint-01 --api-url http://localhost:8000 --enrollment-token <token> --post`: send one heartbeat through the BFF to `xdr_rico`.

Keep Docker Compose portable across Linux and Windows. Do not mount host `node_modules` into containers.

## Roadmap

Development should optimize for clean architecture over emergency delivery. Work remains parallel by contract, but features should land in coherent phases.

| Phase | Product Goal | Backend/Tools | Frontend | Quality Gate |
| --- | --- | --- | --- | --- |
| 1 | Contracts and platform foundation | SOC schemas, `packages/soc-catalog`, service scaffolds, Redis, health checks | Fixtures and empty states | Contracts documented and tested |
| 2 | SIEM-lite core | `siem_kowalski` ingest, rules, incidents and timelines | Incident list/detail and incident widgets | Rule and incident tests pass |
| 3 | XDR-lite context | `xdr_rico` endpoint inventory, telemetry, timeline and simulator | Endpoint inventory/timeline widgets | Endpoint correlation tests pass |
| 4 | SOAR-lite workflow engine | `soar_skipper` playbooks, simulation, dry-run runs and approvals | Playbook builder and run viewer | Sensitive actions require approval |
| 5 | Endpoint sensor | `agent_private` enrollment, heartbeat and telemetry collection | Endpoint onboarding UX | Linux/Windows-safe agent docs/tests |
| 6 | AI cockpit assistant | Tool registry, safe AI actions, widget drafting and playbook drafting | AI panel and draft review UX | AI cannot perform forbidden operations |
| 7 | Enterprise hardening | DNS TXT ownership, SSO/IdP, retention, admin policy, audit export | SaaS onboarding and admin UX | Threat model and security tests updated |

## Backlog

### Shared Contracts and Architecture

- [x] Create `packages/soc-catalog` with severities, event classes, entity fields, playbook node types and widget metadata.
- [x] Add schemas/fixtures for `SecurityEvent`, `Incident`, `Endpoint`, `EndpointEvent`, `Playbook`, `PlaybookRun` and `PlaybookStepRun`.
- [x] Document internal-service auth between `apps/api` and Penguin tools.
- [x] Add architecture doc for FortiDashboard + Penguin tools data flow.
- [x] Register threat model for phishing, supply-chain, insider, malicious playbook, endpoint spoofing and secret leakage.
- [ ] Keep `AGENTS.md` updated whenever contracts, service boundaries or backlog ownership changes.

### Platform and Infrastructure

- [x] Add Redis to Docker Compose for workers.
- [x] Add `apps/siem_kowalski` scaffold with FastAPI, Pytest, Ruff and Dockerfile.
- [x] Add `apps/soar_skipper` scaffold with FastAPI, Pytest, Ruff and Dockerfile.
- [x] Add `apps/xdr_rico` scaffold with FastAPI, Pytest, Ruff and Dockerfile.
- [x] Add `apps/agent_private` scaffold as Python CLI package.
- [x] Add service health checks for each Penguin service.
- [x] Add local seed command for demo incidents, endpoints and playbooks.

### siem_kowalski: SIEM-lite

- [x] Implement first in-memory event ingestion with normalized payload storage.
- [ ] Add persisted raw event payload storage before production hardening.
- [ ] Implement detection rule model with safe expression evaluation.
- [x] Add initial hardcoded rules: port scan, denied-traffic burst, repeated failed login, suspicious endpoint connection.
- [ ] Add high CPU/memory risk rule from FortiGate/system telemetry.
- [x] Generate incidents from detection matches.
- [x] Add incident status transitions: `open`, `triaged`, `contained`, `resolved`, `false_positive`.
- [x] Add incident timeline events.
- [ ] Ingest FortiGate normalized events from the existing provider.
- [ ] Expose incident widgets for count by severity, recent incidents and top entities.

### soar_skipper: SOAR-lite

- [x] Implement playbook schema as validated graph/list of nodes.
- [x] Implement node types: trigger, condition, enrich IP, case note, approval, notify, recommend FortiGate block, webhook dry-run.
- [x] Implement playbook simulation endpoint.
- [x] Implement first dry-run playbook run state machine and step history.
- [x] Require human approval for any step marked sensitive.
- [x] Audit playbook create/update/simulate/run actions through the BFF gateway.
- [ ] Add approval endpoint and audit playbook approve actions.
- [x] Add default disabled playbooks for port scan triage and suspicious endpoint triage.
- [ ] Prepare API boundary for future AI/MCP playbook drafting.

### xdr_rico: XDR/EDR-lite

- [x] Implement endpoint enrollment token flow.
- [x] Implement endpoint inventory and heartbeat.
- [x] Implement endpoint event ingestion.
- [x] Add endpoint timeline.
- [ ] Correlate endpoints with incidents by IP, hostname and username.
- [ ] Add endpoint health widgets.
- [x] Add simulator endpoint/source for demo without installing the agent.
- [x] Ensure endpoint tokens are hashed and never returned after creation.

### agent_private

- [x] Implement CLI config and enrollment-token based posting.
- [x] Send heartbeat with hostname, OS, local IPs and current user.
- [x] Collect process snapshot with `psutil`.
- [x] Collect network connection snapshot with `psutil`.
- [ ] Optional: monitor selected directories with `watchdog`.
- [x] Add retry/backoff for offline backend.
- [x] Add simulator mode for deterministic demo data.
- [x] Document safe installation/run commands for Linux and Windows.

### apps/api Gateway

- [x] Keep Keycloak BFF auth, CSRF, sessions and admin RBAC.
- [x] Keep FortiGate integration, widgets, workspace persistence and audit log.
- [x] Add gateway routes for SIEM-lite events/incidents.
- [x] Add gateway routes for SOAR-lite playbooks/runs.
- [x] Add gateway routes for XDR-lite endpoints/timeline.
- [x] Add service-to-service client with timeouts and error normalization.
- [x] Add retries/backoff for internal Penguin service calls.
- [x] Extend audit log actions for first Penguin mutating gateway routes.
- [ ] Add admin-only audit filters for SOC actions.

### Frontend Cockpit

- [x] Keep workspace, custom visuals, FortiGate widgets, integration CRUD and audit drawer.
- [ ] Add SOC navigation area for Incidents, Endpoints and Playbooks.
- [ ] Add incident list and incident detail panel.
- [ ] Add endpoint inventory and endpoint timeline panel.
- [ ] Add basic playbook builder using forms/list of steps.
- [ ] Add playbook simulation and run result UI.
- [ ] Add SOC widgets to the catalog: incidents by severity, recent incidents, endpoint health, active playbook runs.
- [ ] Add empty/loading/error states for each SOC-lite tool.
- [ ] Keep the UX enterprise/SOC-oriented, not a toy automation demo.

### AI and MCP Roadmap

- [ ] Define AI-safe operations: explain dashboard, summarize widget data, explain incident, summarize timeline, suggest playbook, draft playbook, validate playbook, draft widget and validate widget.
- [ ] Define forbidden AI operations: activate playbook, approve sensitive action, run destructive action, reveal secrets.
- [ ] Add `draft` status for AI-generated playbooks.
- [ ] Add `draft` status for AI-generated widgets.
- [ ] Implement AI tool registry with explicit schemas, permissions, timeouts and audit behavior.
- [ ] Implement `list_data_fields`, `draft_widget`, `validate_widget`, `simulate_widget_data` and `add_widget_draft_to_workspace`.
- [ ] Ensure AI-created widgets use the same `fieldBindings[]` model as Build Panel custom visuals.
- [ ] Add confirmation UX before persisting AI-generated widgets to `workspace_specs`.
- [ ] Add validation errors that are readable by both UI and future AI tooling.
- [ ] Plan MCP server only after stable APIs exist for incidents and playbooks.

### Quality and Review

- [x] Add unit tests for event normalization and detection rules.
- [x] Add unit tests for incident state transitions.
- [x] Add unit tests for playbook schema validation and run state machine.
- [x] Add tests proving sensitive playbook actions require approval.
- [x] Add tests proving audit logs redact secrets and endpoint tokens.
- [x] Add tests for endpoint spoofing/invalid enrollment token.
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
- Visual components should receive normalized payloads, not provider-specific clients.

Contracts:

- Any endpoint change must update schemas/fixtures and the consuming code.
- Shared payloads belong in `packages/contracts`.
- Widget metadata belongs in `packages/widget-catalog` or `packages/soc-catalog`.

## Git Flow for Humans and AI Agents

- Always inspect current branch and `git status` before editing.
- Run `git fetch origin` before starting merge-sensitive work.
- Do not work directly on `main` for feature work.
- Branch names should include owner and scope, for example `agent/eyes-incident-engine`, `felipe/arms-playbook-runner`, `lucas/soc-console`.
- Keep write scopes isolated. Do not edit another agent's files unless the task says so.
- Stage only files from the task scope.
- Use small imperative commits, for example `feat(eyes): add incident detection engine`.
- Do not commit `.env`, secrets, dumps, local certificates or lab-specific values.
- Do not use `git push --force` without explicit approval.
- If `AGENTS.md` conflicts, merge instructions into one coherent document instead of replacing another contributor's section blindly.

## Pull Requests and Handoffs

Every PR or handoff must include:

- What changed.
- Which app/service was affected.
- Contract changes with request/response examples when relevant.
- Verification commands run.
- Known gaps or follow-up tasks.
- Screenshots or short recordings for UI changes.

For AI-authored work, include the original task prompt or issue link and confirm the allowed write scope was respected.
