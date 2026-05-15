# Repository Guidelines

## Purpose

This file is the FortiDashboard contributor and AI-agent guide. Keep it short,
current and action-oriented. It is not a changelog, release note, sprint log or
MVP diary.

Use this split:

- `AGENTS.md`: durable rules, architecture boundaries, commands and current
  priorities for contributors.
- `docs/product/`: feature map, roadmap, timeline and release notes.
- `docs/architecture/`: architecture decisions, data flow and threat model.
- `docs/operations/`: operator runbooks and lab/customer setup checklists.
- `docs/lab/` or `docs/mvp/archive/`: synthetic replay, demo-only paths and
  historical recording scripts.
- `docs/superpowers/`: implementation plans/specs used by AI-agent workflows.

FortiDashboard is a modular NG-SOC cockpit. FortiGate is the first real Fortinet
provider. FortiSIEM/FortiSOAR/FortiEDR/FortiXDR are not faked; unavailable
Fortinet capabilities are represented by internal SOC-lite services with clear
labels and safe boundaries.

## Product Snapshot

```txt
apps/web              -> Vue cockpit, workspace, widgets and SOC UX
apps/api              -> FastAPI BFF, auth/session gateway, integrations and API
apps/siem_kowalski   -> SIEM-lite: events, detections, incidents and timelines
apps/soar_skipper    -> SOAR-lite: playbooks, dry-runs, approvals and history
apps/xdr_rico        -> XDR/EDR-lite: endpoints, telemetry and timelines
apps/agent_private   -> optional endpoint sensor TUI/CLI feeding xdr_rico
FortiGate            -> live firewall provider, inventory/widgets/log ingestion
```

Runtime shape:

```txt
Browser -> apps/api -> FortiGate
Browser -> apps/api -> siem_kowalski | soar_skipper | xdr_rico
FortiGate -> syslog UDP collector in apps/api -> siem_kowalski
agent_private -> apps/api or xdr_rico enrollment endpoint
```

MVP deployment is single-tenant per customer stack. Use one shared Postgres
instance with service-owned modules/tables. Redis is available for workers. Do
not introduce Kafka, OpenSearch, service mesh or separate databases before the
product need is explicit.

## Non-Negotiable Security Rules

- Never commit hostnames, lab IPs, API keys, tokens, passwords, keytabs,
  FortiGate secrets, Keycloak secrets or endpoint enrollment tokens.
- Vue never receives Keycloak access tokens, refresh tokens, client secrets or
  persisted passwords.
- Browser auth stays BFF-based with HTTP-only cookies, server-side sessions,
  CSRF protection for mutating requests and audit logs for sensitive actions.
- Product roles come from the BFF session. Missing or malformed Keycloak roles
  fall back to `analyst`, never `admin`.
- Admin-only APIs require role `admin` and must audit successful reads/actions.
- Every state-changing SOC action must write audit events: auth, integrations,
  workspace, incidents, playbooks, playbook runs, endpoint enrollment, admin
  views and approvals.
- `soar_skipper` actions default to `dry_run`. Sensitive FortiGate/FortiWeb
  actions may become live only through FortiDashboard-owned APIs with RBAC,
  explicit approval, preflight, diff/summary, rollback guidance and audit.
- AI-generated playbooks and widgets are drafts until a permitted human reviews
  and applies them.
- AI must not reveal secrets, execute arbitrary code, directly apply FortiGate
  policies, approve sensitive actions or run destructive operations.

### FortiGate policy orchestration boundary

FortiDashboard is a SOC orchestrator. FortiGate integrations are allowed to
perform real, audited FortiGate policy orchestration for customer/lab traffic
validation and approved response workflows. Do not replace this with mock,
draft-only or out-of-band CLI guidance as the product path.

Allowed for the MVP:

- Read-only API probes, inventory, widgets, logs and health checks.
- Safe/additive syslog or log-forwarding setup only when all of these are true:
  preflight has read the current FortiGate state, the user explicitly confirms,
  existing customer configuration is not silently overwritten, and before/after
  details are audited with secrets redacted.
- Safe/additive firewall traffic-policy orchestration only when all of these are
  true: preflight has read interfaces, address objects, services and current
  policy order; the requested change is shown as a diff/summary; an `admin`
  explicitly confirms; FortiDashboard creates or updates only FortiDashboard-
  owned objects/policies; existing customer policies are not silently
  overwritten; the action, target entities, before/after summary, FortiGate
  response and rollback guidance are audited with secrets redacted.
- Temporary or lab-only policies should support expiry/cleanup metadata when
  possible, especially for scan-validation or containment rules.

Not allowed:

- Silent or automatic policy changes triggered only by AI, SIEM detections,
  background jobs or browser state.
- Blocking IPs, changing routes/interfaces, changing auth/admin/global settings
  or disabling FortiGate features without a separate accepted architecture
  decision and product approval.
- Any destructive or stealthy response action.

Traffic-policy helpers should apply real FortiGate changes through the governed
BFF orchestration path. Documentation-only CLI snippets are acceptable in
operations runbooks, but they are not the product implementation.

## Project Structure

```txt
apps/
  api/                 # FastAPI BFF, auth/session gateway, integrations, AI API
  web/                 # Vue 3 + Vite cockpit
  siem_kowalski/       # SIEM-lite service
  soar_skipper/        # SOAR-lite service
  xdr_rico/            # XDR/EDR-lite manager
  agent_private/       # Endpoint sensor TUI/CLI

packages/
  contracts/           # Shared schemas and fixtures
  widget-catalog/      # Visual/widget metadata
  soc-catalog/         # SOC event classes, severities, playbook metadata

docs/
  api/                 # API and internal-service documentation
  architecture/        # Decisions, data flow, threat model
  operations/          # Operator runbooks and lab/customer setup
  product/             # Feature map, roadmap, release notes, timeline
  superpowers/         # AI-agent implementation plans/specs
```

## Stack And Conventions

Backend services use Python 3.12+, FastAPI, Pydantic, SQLAlchemy, Alembic,
Postgres and Pytest. Use Ruff for linting. Prefer `httpx`, `tenacity`, `orjson`
and typed Pydantic contracts at IO boundaries.

Frontend uses Vue 3, Vite, Composition API with `<script setup>`, Pinia,
Tailwind CSS, Motion for Vue and Lucide Vue.

SOC-lite dependencies already in use or approved when needed:

- `rule-engine` or a constrained Sigma-like evaluator for detections.
- `dramatiq` + Redis for background workers when the lightweight scheduler is no
  longer enough.
- `transitions` for incident/playbook state machines.
- `jinja2` for safe templating of notes, notifications and dry-run payloads.
- `psutil`, `watchdog`, `httpx` and `tenacity` for `agent_private`.

Do not use Wazuh, Shuffle, StackStorm, OpenSearch or Kafka as core MVP services.
They may become future integrations.

Coding conventions:

- Backend modules/functions/variables use `snake_case`.
- Pydantic and ORM classes use `PascalCase`.
- Frontend components use `PascalCase.vue`.
- Frontend utility files use `camelCase.ts`.
- Visual components receive normalized payloads, not provider-specific clients.
- Any endpoint change must update schemas/fixtures and consuming code.
- Shared payloads belong in `packages/contracts`.
- Widget metadata belongs in `packages/widget-catalog` or `packages/soc-catalog`.

## Auth, Sessions And SSO

Keycloak is the identity provider, but users interact with FortiDashboard Vue
screens rather than hosted Keycloak forms.

Mandatory auth model:

- Vue calls `/api/auth/login`, `/api/auth/register`, `/api/auth/logout`,
  `/api/auth/me`, `/api/auth/csrf` and SSO entrypoints through `apps/api`.
- Vue sends `credentials: "include"` and `X-CSRF-Token` for mutating requests.
- Keycloak tokens stay encrypted server-side in `auth_sessions`.
- `auth_sessions.expires_at` follows refresh-token lifetime when available.
- Admin-only routes require BFF role `admin` and audit successful reads/actions.

Kerberos/SPNEGO support:

- `GET /api/auth/sso/kerberos/init` starts Authorization Code flow with
  Keycloak.
- `GET /api/auth/sso/kerberos/callback` validates state, exchanges code,
  creates the HTTP-only BFF session and redirects to the frontend URL.
- `SessionMiddleware` stores OAuth state in the `f_session` cookie.
- Local AD/Kerberos values live in `.env`, `docker-compose.yml`, `krb5.conf` or
  local host config. Do not track real keytabs or lab secrets.
- `fortidashboard.keytab` must remain untracked.
- `configSSOKerberosKeycloak.md` is the detailed AD/Kerberos lab setup guide.

Important Keycloak URL rules:

- `FORTIDASHBOARD_KEYCLOAK_BASE_URL` is API-to-Keycloak. In Compose it should
  point to `http://keycloak:8080`.
- Browser-facing values are `FORTIDASHBOARD_KEYCLOAK_BROWSER_BASE_URL`,
  `FORTIDASHBOARD_OIDC_ISSUER`, `FORTIDASHBOARD_SSO_REDIRECT_URI` and
  `FORTIDASHBOARD_SSO_POST_LOGIN_URL`.
- Kerberos/SPNEGO requires the browser-facing Keycloak hostname to match the
  service principal in the realm import.

## FortiGate Provider

FortiGate is the first live provider and must feel plug-and-play without hiding
security-sensitive changes.

Preserve these capabilities:

- Persist integrations per authenticated user.
- Encrypt API keys at rest and never return them.
- Probe before saving live integrations.
- Expose system status, sessions, interfaces, policies, risk, events and anomaly
  widgets.
- Use short cache TTLs for volatile widgets and expose `refreshIntervalSeconds`.
- Allow local deletion of integrations without changing FortiGate.
- Audit successful and failed integration actions.
- Feed normalized FortiGate syslog events into `siem_kowalski` as the primary
  realtime telemetry path.
- Keep scheduled/manual event ingestion as a fallback/operator diagnostic path,
  not the normal dashboard refresh mechanism.
- Surface ingestion/log-forwarding health in the cockpit: last success, raw
  events, created SIEM events, last received syslog event and last error.

Product setup direction:

1. Connect with API key.
2. Probe FortiGate state.
3. Show required log-forwarding/syslog settings and the current state.
4. Apply safe/additive log forwarding only with explicit confirmation.
5. Verify receipt of logs.
6. If no incidents appear, guide the operator through FortiDashboard policy
   orchestration to create or verify a log-enabled traffic path such as a
   lab deny/log or allow/log policy. Do not require out-of-band FortiGate UI
   changes for the normal validation flow.

Lab topology caveats and real-scan checklists belong in `docs/operations/`, not
in this file.

## SOC-Lite Services

### siem_kowalski

Purpose: convert telemetry into incidents.

Current capabilities:

- Ingest normalized events from FortiGate, endpoint telemetry, manual events and
  future providers.
- Persist raw events, generated incidents and incident timelines.
- Apply safe declarative detections for port scans, denied-traffic bursts,
  repeated failed logins, suspicious endpoint connections, AD activity and
  FortiGate resource pressure.
- Generate incidents with severity, status, triage level, ticket status,
  timeline and related entities.
- Expose incident widgets and ticket APIs through the gateway.

Gateway API:

```txt
POST  /api/soc/events
GET   /api/soc/events
GET   /api/soc/rules
GET   /api/soc/incidents
GET   /api/soc/incidents/{incidentId}
PATCH /api/soc/incidents/{incidentId}
GET   /api/soc/tickets
GET   /api/soc/tickets/{ticketId}
PATCH /api/soc/tickets/{ticketId}
```

### soar_skipper

Purpose: run safe response workflows over incidents.

Current capabilities:

- Store playbooks and run history in SQL-backed tables.
- Validate playbook graphs/lists.
- Simulate playbooks and run dry-run workflows.
- Expose node metadata with `executionMode`, `liveAvailable` and `boundary`.
- Require approval for sensitive steps.
- Audit create, update, simulate, run and approve actions through the BFF.
- Completed approved runs can update the linked SIEM ticket to `contained`; if
  SIEM patching fails, the response is partial and audited.
- FortiGate response nodes may request FortiDashboard-owned policy orchestration
  after approval. They must not bypass the BFF, RBAC, preflight or audit path.

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
GET  /api/soc/playbook-node-types
```

### xdr_rico

Purpose: provide endpoint context and correlate host telemetry with SOC
incidents.

Current capabilities:

- Create enrollment tokens and store only token hashes after creation.
- Persist endpoint inventory, heartbeat, hostname, OS, IPs, current user,
  health and timelines.
- Ingest endpoint events.
- Correlate endpoints with incidents by endpoint ID, IP, hostname and username.
- Expose endpoint timelines, related incidents, incident endpoint context and
  health widgets.
- Allow local deletion of stale endpoints from the cockpit; sensors may reappear
  on the next heartbeat.
- Provide simulator data only for lab/test paths.

Gateway API:

```txt
GET    /api/weapons/endpoints
GET    /api/weapons/endpoints/{endpointId}
GET    /api/weapons/endpoints/{endpointId}/timeline
GET    /api/weapons/endpoints/{endpointId}/related-incidents
DELETE /api/weapons/endpoints/{endpointId}
GET    /api/soc/incidents/{incidentId}/endpoint-context
POST   /api/weapons/enrollments
POST   /api/weapons/endpoint-events
```

### agent_private

Purpose: optional endpoint sensor for lab/demo/customer telemetry.

Current direction:

- Cockpit owns endpoint onboarding.
- Analysts create a Windows enrollment from the cockpit and receive a copyable
  PowerShell/bootstrap command.
- `agent_private run` is the operator-facing TUI.
- `agent_private run-headless` is the automation/test entrypoint.
- Onboarding environment variables from the cockpit override stale saved local
  TUI config.
- Windows background execution should start as an explicit Scheduled Task
  installer before a true Windows Service.

Do not add hidden behavior, credential harvesting, stealth persistence or
destructive response actions.

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

Data source labels must distinguish live provider data, manual events,
simulator/lab data and scripted/lab AI output.

## Frontend Cockpit

The Vue app is the cockpit. Do not build separate web UIs for each Penguin tool
in the MVP.

Required UX direction:

- Keep the Power BI-like workspace with drag/drop widgets, data fields, zoom,
  pan, minimap and custom visuals.
- Treat Visuals as presets and Data fields as bindable provider fields.
- SOC widgets and fields come from connected providers through `apps/api`.
- Keep the integrations drawer grouped and collapsible.
- SOC tickets and workspace widgets refresh from the BFF realtime event stream
  when FortiGate/SIEM telemetry arrives; do not add dashboard polling loops.
- Audit drawer may keep bounded polling until audit events move to realtime.
- SOC consoles cover incidents, endpoints and playbooks without becoming a toy
  automation demo.
- All new user-facing strings must use `vue-i18n` catalogs in
  `apps/web/src/i18n/messages/pt-BR.ts` and `apps/web/src/i18n/messages/en-US.ts`.

### Widget shell pattern

All workspace widgets share the tiered shell in
`apps/web/src/components/widgets/shell/WidgetShell.vue`:

- `glance`: required fast-scan view.
- `drill`: optional inline expansion.
- `detail`: optional teleported modal with focus trap and `Esc` close.

Reuse shared shell components (`WidgetSparkline`, `WidgetKpiTile`,
`WidgetSlaBadge`, `WidgetEntityChip`, `WidgetEmptyState`, `WidgetDrillModal`)
instead of duplicating tiles or empty states.

SOC analyst helpers live in `apps/web/src/composables/useSocMetrics.ts`.
Severity tokens live in `apps/web/src/lib/severityTokens.ts`; never hardcode
Tailwind severity classes.

### Widget series buffer

Client-side sparklines and "vs last update" deltas use
`apps/web/src/stores/useWidgetSeriesStore.ts` and samplers in
`apps/web/src/lib/widgetSeries.ts`.

Rules:

- Samplers must be pure, null-safe and numeric-only.
- Never push IPs, hostnames, usernames or full payloads into the buffer.
- The buffer is in-memory only and is not exported in workspace manifests.
- Label short trend windows honestly.

### Marketplace Add-on Packages

Direction (2026-05-14 onward): vendor connectors are not part of the monorepo.
Each provider integration is a versioned **package** (manifest + Python
connector code + fixtures) hosted in the private registry repo
`ping-wins/fortidashboard-addons`. The dashboard ships zero vendor
connectors and gains them at runtime via install endpoints that fetch a
GitHub tarball, extract it onto a Docker volume, register the row in
`installed_addons`, and dynamically import the package as
`fortidashboard_addons.<id>`.

Rules for contributors and agents:

- **Authoritative docs:** `docs/marketplace/README.md` is the working
  overview. Architecture details live in the spec at
  `docs/superpowers/specs/2026-05-14-marketplace-addon-packages-design.md`.
  Implementation is phased — see plans under `docs/superpowers/plans/`.
- **Schema status (apps/api/app/addons/manifest.py):** `AddonManifest`
  carries `id`, `version`, `name`, `vendor`, `category`, `description`,
  optional `icon`, optional `minDashboardVersion`, `provider`
  (`type` + `auth.kind` + `auth.fields[]`), optional `compatibility`
  (`minProviderVersion` + `testedVersions[]` + `notes`), `routes[]`
  (each with optional per-route `minProviderVersion`), `widgets[]`,
  `siemEventTypes[]`, `entrypoint` (default `"connector"`, non-empty), and
  `requirements[]`. Plan A loader will consume `entrypoint` +
  `compatibility` at install time; do not add fields without dual-writing
  the registry-repo packages first.
- **Read before writing:** the spec lists decisions that are locked
  (Python-code packages, tarball-by-tag fetch, importlib loader, one active
  version per add-on, duck-typed Protocol contract, frontend widgets stay
  in dashboard). Do not relitigate in PRs — amend the spec first.
- **Do not extend the legacy bundled registry.** The local-dir loader at
  `apps/api/app/addons/registry.py` and the `addons/<id>/` directory in
  this repo are transitional. New add-ons go to the registry repo as
  packages, not as JSON files inside this repo.
- **Do not import vendor code paths.** After the FortiGate extraction
  plan lands, `apps/api/app/integrations/fortigate/{client,normalizers,
  widgets}.py` are deleted. New code calls the
  `ConnectorRegistry.get(addon_id, integration_id, config)` and uses the
  duck-typed connector interface.
- **Schema changes are dual-write.** Adding fields to `AddonManifest`
  must (1) ship as optional with sensible defaults so older manifests
  keep parsing, and (2) be reflected in every existing package in the
  registry repo before consumers depend on the field.
- **Backend container rebuilds.** No source bind mount —
  `docker compose up -d --build api` after every edit under
  `apps/api/`.
- **Secrets:** the `MARKETPLACE_GH_TOKEN` env var carries the registry
  read token. It must never appear in committed files, .env templates
  with real values, or logs.

## Workspace Manifests And Sharing

The workspace manifest is the canonical versioned workspace configuration. It
stores layout, widgets, custom visuals, field bindings, filters, data sources
and presentation metadata. It never embeds live telemetry or secrets.

Design rules:

- Use typed schemas with `schemaVersion`, `ownerUserId`, `workspaceId`, `name`,
  `widgets[]`, `layout`, `fieldBindings[]`, `filters`, `dataSources[]` and
  `metadata`.
- Bind widgets to stable provider field IDs and provider types.
- Do not bind shared manifests directly to another user's private
  `integrationId`; resolve bindings for the recipient.
- Store permissions separately from manifest content.
- Validate import before persistence: schema version, widget catalog IDs, visual
  templates, provider compatibility, size limits and unknown fields.
- Redact or reject secrets on import/export.
- Audit create, update, share, unshare, import, export and presentation export.

Expected API surface:

```txt
GET    /api/workspaces
GET    /api/workspaces/{workspaceId}
PUT    /api/workspaces/{workspaceId}
DELETE /api/workspaces/{workspaceId}
PUT    /api/workspaces/{workspaceId}/presentation
GET    /api/workspaces/{workspaceId}/export
POST   /api/workspaces/import
POST   /api/workspaces/{workspaceId}/publish
GET    /api/workspaces/community
POST   /api/workspaces/community/{templateId}/install
DELETE /api/workspaces/community/{templateId}
PATCH  /api/workspaces/{workspaceId}/widgets/{instanceId}/integration
```

## AI Assistant

The internal AI assistant is a cockpit assistant, not an autonomous operator.
Use three layers:

1. Pydantic AI cockpit agent for short-running dashboard chat, widget drafting,
   dashboard explanation and ticket summaries.
2. LangGraph triage workflow later for durable incident triage, endpoint
   correlation, containment planning, retryable AI failures and human approval
   pauses.
3. MCP server later, after stable audited and permission-aware tools exist.

Shared internal tool contracts live in `apps/api/app/ai/tools/` and must be
reused by the cockpit agent, triage graph and future MCP server. Do not let
model runtimes call service internals directly.

Allowed:

- Explain current dashboard state.
- Summarize widget data, incidents, endpoint timelines and playbook runs.
- Suggest safe actions and draft playbooks.
- Draft custom widgets using the workspace data model.
- Suggest FortiGate/FortiWeb response actions for a permitted human to approve
  in FortiDashboard.

Forbidden:

- Activate playbooks or approve sensitive steps.
- Run destructive actions.
- Directly apply or approve FortiGate/FortiWeb policy/config changes. Live
  policy changes must be initiated by a permitted human through FortiDashboard's
  governed orchestration UI/API.
- Reveal secrets.
- Execute arbitrary Python, shell, SQL, HTTP or browser code.
- Persist widgets or playbooks as active without user confirmation.

AI runtime rules:

- Production/customer deployments must configure a real provider explicitly.
- Scripted AI is lab/test-only and must not be the silent production fallback.
- If AI is not configured, the UI should show an actionable "configure AI"
  state instead of pretending analysis is available.
- AI calls must pass the cockpit locale and return localized user-facing text
  while preserving strict JSON schemas where required.
- Add budget/rate limits before customer rollout.

Current AI endpoints:

```txt
GET  /api/ai/tools
POST /api/ai/tools/draft-widget
POST /api/ai/chat
POST /api/soc/incidents/{incidentId}/analyze
POST /api/soc/incidents/{incidentId}/containment-suggestions
POST /api/soc/tickets/{ticketId}/draft-playbook
POST /api/soc/tickets/{ticketId}/apply-containment
```

## Lab, Demo And Simulator Boundaries

Do not present lab/demo paths as product setup.

- Synthetic replay endpoints are lab-only and must be registered only when
  `FORTIDASHBOARD_ENABLE_LAB_DEMO_TOOLS=true`.
- Replay/seed scripts belong under lab tooling, not normal operator flows.
- Simulator data must be visibly labeled.
- Docs that teach synthetic demos belong in `docs/lab/` or
  `docs/mvp/archive/`.
- Product docs should lead with real FortiGate/syslog and `agent_private`
  telemetry.

Known FortiGate lab caveats such as VMware bridge visibility, `set logtraffic
all`, FortiOS log path differences, admin lockout behavior and disk scan checks
belong in `docs/operations/fortigate-scan-detection.md` or another operations
runbook.

## Settings And Localization

The cockpit settings live behind the sidebar gear icon with these tabs:

- Profile: current Keycloak BFF session and sign-out shortcut.
- Appearance: theme/layout builder.
- Language: pt-BR/en-US picker persisted to `localStorage` under
  `fortidashboard:locale`.

Translation layer:

- Use `vue-i18n`.
- Message catalogs live in `apps/web/src/i18n/messages/pt-BR.ts` and
  `apps/web/src/i18n/messages/en-US.ts`.
- Components call `useI18n().t('namespace.key')`.
- `setLocale()` keeps `<html lang>` in sync.
- Backend AI calls read `X-FortiDashboard-Locale` with `Accept-Language`
  fallback.

Any newly added user-facing UI must be translated in the same PR.

## Documentation Model For Features And Timeline

Use this documentation model going forward:

```txt
docs/product/feature-map.md
  Current feature inventory. One row per feature with owner, status, source of
  truth, customer visibility, lab/demo dependencies and verification command.

docs/product/roadmap.md
  Now / Next / Later roadmap. No historical essays. Each item has acceptance
  criteria and links to implementation plans or issues.

docs/product/timeline.md
  Chronological product timeline of important decisions/releases only. Keep it
  short: date, decision/shipped outcome, links. Do not paste sprint logs.

docs/product/release-notes.md
  Customer-facing changelog grouped by version/date.

docs/architecture/decisions/ADR-YYYY-MM-DD-title.md
  Architecture decisions such as FortiGate write boundary, single-tenant per
  deploy, AI provider fallback policy and syslog ingestion model.

docs/operations/*.md
  Operator checklists: FortiGate onboarding, syslog forwarding, VMware lab,
  backup/restore, production deploy, Kerberos SSO.

docs/lab/*.md or docs/mvp/archive/*.md
  Demo replay, synthetic events, recording scripts and historical MVP notes.
```

Status vocabulary for feature docs:

- `planned`: accepted direction, not started.
- `in-progress`: active working tree/branch work.
- `demo-only`: works only for lab/synthetic/demo.
- `beta`: implemented, usable, needs hardening.
- `production-ready`: documented, tested, observable, secure defaults.
- `deferred`: intentionally not being built now.

AGENTS.md should link to those docs but not duplicate their contents.

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
cd apps/siem_kowalski && uv run ruff check . && uv run pytest -q
cd apps/soar_skipper && uv run ruff check . && uv run pytest -q
cd apps/xdr_rico && uv run ruff check . && uv run pytest -q
cd apps/agent_private && uv run pytest -q
cd apps/agent_private && uv run agent-private
```

Before handoff or PR:

```bash
git diff --check
docker compose config --quiet
cd apps/api && uv run ruff check . && uv run pytest -q
cd apps/web && pnpm test && pnpm build
```

## Cross-Platform Compatibility

The codebase has active contributors on Windows (PowerShell + Docker Desktop)
and Linux (bash + Docker Engine). Every change must boot cleanly on both.

Rules:

- Compose secrets and connection strings must use `${VAR:-fallback}` so `.env`
  can override them.
- Developer scripts under `scripts/` need both `.sh` and `.ps1` versions unless
  they are CI/container-only.
- Use forward slashes in Compose, Dockerfiles and Python paths.
- Do not mount host `node_modules` or `.venv` into containers; use named Docker
  volumes.
- Document `fortidashboard.local` hosts-file setup for both Windows and Linux.
- Bash here-docs are acceptable only inside container `command:` fields. Local
  scripts must not assume bash unless a PowerShell mirror exists.

Acceptance criterion: a fresh Windows 11 PowerShell checkout and a fresh Linux
bash checkout both reach a healthy `docker compose ps` after the documented
commands.

## Current Priorities

### Now: real telemetry cutover and stabilization

- Keep FortiGate syslog/log-forwarding ingestion safe, audited and visible.
- Remove demo replay and scripted AI from normal product paths; keep them lab
  gated.
- Fix failing lint/tests before committing.
- Update docs so product setup starts with real FortiGate + endpoint telemetry.
- Finish i18n for any new integration/onboarding UI.

### Next: customer readiness

- First-run onboarding: first admin, FortiGate connection, log forwarding
  verification and endpoint enrollment.
- Structured JSON logging with request/integration/incident correlation IDs.
- `/health/live`, `/health/ready` and Prometheus `/metrics`.
- Retention policies for incidents, raw events, audit and AI analyses.
- Backup/restore runbook for Postgres, Redis and Keycloak.
- CI quality gates: API tests, web tests, build, Ruff, `git diff --check`,
  secrets scanner and demo/customer smoke tests.

### Later: automation expansion

- LangGraph ticket triage workflow on top of the formal AI tool registry.
- MCP server after stable audited APIs exist for incidents/playbooks.
- More live connector boundaries, always with RBAC, approval and audit.

## Git Flow For Humans And AI Agents

- Always inspect current branch and `git status` before editing.
- Run `git fetch origin` before merge-sensitive work.
- Do not work directly on `main` for feature work.
- Branch names should include owner and scope, for example
  `agent/siem-incident-engine`, `felipe/soar-playbook-runner`,
  `lucas/soc-console`.
- Keep write scopes isolated.
- Stage only files from the task scope.
- Use small imperative commits, for example `feat(siem): add incident detection
  engine`.
- Do not commit `.env`, secrets, dumps, keytabs, local certificates or
  lab-specific values.
- Do not use `git push --force` without explicit approval.
- If this file conflicts, merge instructions into one coherent document instead
  of replacing another contributor's section blindly.

Every PR or handoff must include what changed, affected apps/services, contract
changes, verification commands, known gaps and screenshots/recordings for UI
changes.
