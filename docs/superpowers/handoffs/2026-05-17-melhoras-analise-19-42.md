# MELHORAS-ANALISE-19:42

**Date:** 2026-05-17
**Base analyzed:** `origin/main` at `be0a79aa84a25669a36fb8b2d6aff8729fa5dd4c`
**Commit subject:** `fix(fortiweb): probe supported system status endpoint`
**Worktree:** `/tmp/fortidashboard-main-analysis`

## Context

This document records the deep analysis requested against the current GitHub
`main`. No code was changed during the analysis pass. The goal is to preserve
the inconsistencies, risks and improvement opportunities that should feed the
next hardening branch.

Verification that completed:

- `docker compose config --quiet` passed.
- `git diff --check` passed before creating this document.

Verification that could not run in the local environment:

- `cd apps/api && uv run pytest ...` and `uv run ruff check ...` could not run
  because `uv` was not installed.
- `cd apps/web && pnpm test` could not run because `pnpm` was not installed.
- `corepack pnpm --version` attempted to fetch from `registry.npmjs.org` and
  failed due to restricted network access.

## Critical Findings

### 1. CSRF is missing on administrative mutating endpoints

FortiDashboard's BFF model requires CSRF protection for browser-originated
mutations. Most SOC routes follow this, but the newer administrative surfaces do
not consistently include `Depends(require_csrf)`.

Affected code:

- `apps/api/app/routers/marketplace.py`
  - `POST /api/marketplace/addons/refresh`
  - `POST /api/marketplace/addons/{addon_id}/install`
  - `DELETE /api/marketplace/addons/{addon_id}`
- `apps/api/app/routers/roles.py`
  - `POST /api/roles`
  - `PATCH /api/roles/{role_id}`
  - `DELETE /api/roles/{role_id}`
  - `POST /api/roles/{role_id}/members`
  - `DELETE /api/roles/{role_id}/members/{user_id}`
- `apps/api/app/routers/users.py`
  - `PATCH /api/users/{user_id}/roles`

Impact:

- A logged-in administrator could be induced to perform role, marketplace or
  add-on state changes from a malicious page.
- This violates the non-negotiable auth model in `AGENTS.md`.

Recommended fix:

- Add `Annotated[None, Depends(require_csrf)]` to every state-changing route
  above.
- Add regression tests that first call without `X-CSRF-Token` and assert the
  request is rejected.

### 2. The multi-step AI agent exposes scripted mode outside the lab gate

The legacy AI provider factory blocks `scripted` unless
`FORTIDASHBOARD_ENABLE_LAB_DEMO_TOOLS=true`. The newer `/api/ai/agent/*`
runtime exposes only `scripted`, marks it ready, and allows sessions without
checking the lab flag.

Affected code:

- `apps/api/app/routers/ai_agent.py`
  - `_AVAILABLE_BACKENDS = ("scripted",)`
  - `GET /api/ai/agent/backends` reports scripted as ready.
  - `POST /api/ai/agent/sessions` accepts scripted sessions.

Impact:

- Production/customer stacks can silently use deterministic lab behavior.
- This conflicts with the AI runtime rule: real providers must be explicitly
  configured and scripted AI is lab/test-only.

Recommended fix:

- Reuse the existing AI provider readiness logic for the agent runtime.
- Hide or reject `scripted` unless lab demo tools are enabled.
- If no real backend is configured, return an actionable configure-AI state.

### 3. Kerberos SSO drops admin roles and ignores refresh-token lifetime

Password login parses product roles from the access token, but authorization
code exchange does not. `get_userinfo()` also returns `roles=["analyst"]`, so
SSO users with the Keycloak `admin` role can be downgraded to analyst in the
BFF session.

Affected code:

- `apps/api/app/auth/keycloak.py`
  - `exchange_code()` does not set `refresh_expires_in`.
  - `exchange_code()` does not set `roles=self._realm_roles(access_token)`.
  - `get_userinfo()` returns `roles=["analyst"]`.
- `apps/api/app/auth/service.py`
  - `sso_exchange()` depends on `tokens.roles or ["analyst"]`.

Impact:

- Kerberos/SPNEGO admin users may lose admin capabilities after SSO login.
- SSO sessions may expire on access-token TTL instead of refresh-token TTL.

Recommended fix:

- In `exchange_code()`, capture `refresh_expires_in` and parsed roles exactly
  like password login.
- Add tests for SSO callback creating an admin session when the access token
  carries the `admin` realm role.

### 4. SOC Policy Manager reviews are in-memory and audit payloads are too thin

The accepted ADR for the administrative SOC policy manager requires preflight,
diff, explicit confirmation, audit, rollback guidance and stale-review
rejection. The current adapters keep review state in module-level dictionaries.

Affected code:

- `apps/api/app/policies/fortigate_adapter.py`
  - `_REVIEWS: dict[str, dict[str, Any]] = {}`
  - FortiGate review `before` is a generic summary, not provider state.
- `apps/api/app/policies/fortiweb_adapter.py`
  - `_REVIEWS: dict[str, dict[str, Any]] = {}`
- `apps/api/app/routers/policies.py`
  - apply audit only records review id, provider type, integration id and
    status.

Impact:

- Pending reviews disappear on API restart or multi-worker deployment.
- Stale review detection cannot survive process boundaries.
- Audit does not include policy ownership, before/after summary, rollback
  guidance or provider response status as required by
  `docs/architecture/decisions/ADR-2026-05-17-admin-policy-manager.md`.

Recommended fix:

- Persist policy reviews in SQL, or reuse provider-owned review tables where
  available.
- Store review hash, provider state digest, ownership and proposed diff.
- Expand audit details to include the fields listed in the ADR.
- Convert `KeyError`, `ValueError` and `PermissionError` from adapters into
  stable HTTP errors in the router.

## Important Findings

### 5. Vendor connector tests depend on a sibling private repository

`apps/api/tests/test_addon_vendor_connectors.py` reads packages from a sibling
`fortidashboard-addons` checkout. Some test cases skip when the package is
missing, but the FortiWeb-specific tests read files directly without a skip.

Impact:

- A clean checkout of this repository cannot reliably run the API test suite
  unless a private sibling repo exists in the expected path.

Recommended fix:

- Either gate the entire file behind a fixture that skips when the package repo
  is missing, or move these checks to a cross-repo CI job that explicitly checks
  out both repositories.

### 6. Marketplace documentation is stale relative to the implementation

`docs/marketplace/README.md` still says Backend Plan A is pending, but the code
already includes the install service, DB row, loader and endpoints. The product
feature map still marks Marketplace as `planned`.

Affected docs/code:

- `docs/marketplace/README.md`
- `docs/product/feature-map.md`
- `apps/api/app/addons/install_service.py`
- `apps/api/app/routers/marketplace.py`

Impact:

- Contributors can make incorrect decisions about whether Plan A is still
  design-only.
- Roadmap/status documents understate shipped backend behavior.

Recommended fix:

- Update marketplace docs to mark Plan A backend infrastructure as implemented
  and clarify what remains for frontend UX and FortiGate extraction.
- Update feature-map status from `planned` to the accurate current status
  (`beta` or `in-progress`, depending on product confidence).

### 7. Lab IPs remain hardcoded in Compose

`docker-compose.yml` hardcodes `192.168.56.10` for Keycloak extra hosts. This
conflicts with the repo rule that lab IPs must not be committed as durable
defaults.

Impact:

- Fresh Windows/Linux setups inherit a specific lab topology that may be wrong.
- The main Compose file mixes product defaults with lab-only AD/Kerberos
  assumptions.

Recommended fix:

- Move these host mappings to a lab override compose file, or parameterize them
  with `${FORTIDASHBOARD_LAB_DC_IP:-...}` only in a clearly labeled lab path.

### 8. New cockpit UI strings are not fully localized

Several user-facing strings in the newer agent and canvas surfaces are
hardcoded, including Portuguese-only strings inside `AgentPanel.vue` and mixed
English/Portuguese labels inside `DashboardCanvas.vue`.

Impact:

- The `pt-BR`/`en-US` locale switch cannot produce a consistent UI.
- This violates the rule that newly added user-facing UI must use the i18n
  catalogs in the same PR.

Recommended fix:

- Move `AgentPanel.vue` strings into `apps/web/src/i18n/messages/pt-BR.ts` and
  `apps/web/src/i18n/messages/en-US.ts`.
- Replace hardcoded build-pane labels in `DashboardCanvas.vue` with `t(...)`
  keys.
- Add/extend web tests that mount these components with both locales.

## Strategic Cleanup

### Vendor code still lives in the monorepo

`AGENTS.md` and marketplace docs state the direction that vendor connectors
should move out of the monorepo and load from add-on packages. The current
codebase still has substantial FortiGate and FortiWeb implementation under
`apps/api/app/integrations/`.

This is expected during the transition, but new work should avoid deepening
those vendor paths. The next clean step is a Plan B branch for FortiGate
extraction and boot-time auto-install/migration.

### Health and observability are still below customer-readiness goals

`/health` returns a static OK response. The roadmap still calls for
`/health/live`, `/health/ready`, Prometheus `/metrics`, structured JSON logs and
correlation IDs.

Recommended next work:

- Add readiness checks for Postgres, Redis, Keycloak and SOC-lite services.
- Add request/integration/incident correlation IDs to BFF logs.
- Add retention and backup/restore runbooks before customer deployment.

## Suggested Execution Order

1. Patch CSRF gaps on marketplace, roles and users routes.
2. Gate `/api/ai/agent` scripted backend behind lab mode or real provider
   readiness.
3. Fix SSO role extraction and refresh-token TTL.
4. Persist SOC Policy Manager reviews and expand audit payloads.
5. Stabilize vendor connector tests so clean checkouts can run them.
6. Update marketplace and product docs to match current implementation.
7. Move lab IPs out of default Compose.
8. Finish i18n for AgentPanel and DashboardCanvas build-pane strings.

## Notes For The Next Agent

- Keep fixes scoped. The CSRF and AI-agent gate issues are independent and can
  ship before the larger policy-manager persistence work.
- Do not delete legacy FortiGate/FortiWeb modules until the marketplace Plan B
  extraction has an accepted migration path.
- Prefer regression tests around security boundaries before refactoring.
