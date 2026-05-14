# MVP Readiness Hardening Implementation Plan

> **For Hermes:** Use test-driven-development for every behavior change and commit each completed slice.

**Goal:** Close the highest-risk gaps found in the 2026-05-14 codebase review so FortiDashboard moves from demo-only toward a trustworthy MVP.

**Architecture:** Treat this as a hardening sprint, not a rewrite. Fix server-side trust boundaries first, then persistence/error handling, contracts, CI and UX truthfulness. Keep safety defaults: FortiGate remains read-only, SOAR remains dry-run, AI output remains draft/confirmed.

**Tech Stack:** Python 3.12/FastAPI/Pydantic/SQLAlchemy/Pytest/Ruff, Vue 3/Pinia/Vitest/vue-tsc/Vite, Docker Compose, GitHub Actions.

---

## Review Snapshot

Branch: `agent/mvp-readiness-hardening`

Baseline verification before changes:

- `docker compose config --quiet` — pass
- `cd apps/api && uv run ruff check .` — pass
- `cd apps/api && uv run pytest -q` — 154 passed
- `cd apps/web && pnpm test -- --run` — 116 passed
- `cd apps/web && pnpm build` — pass, with chunk warning at 546.96 kB
- `apps/siem_kowalski`, `apps/soar_skipper`, `apps/xdr_rico`, `apps/agent_private` — ruff + pytest pass

## Sprint Scope

### P0/P1 selected for immediate development

1. [x] Bind XDR enrollment tokens to endpoint identity to stop spoofing.
2. [x] Gate `/api/soc/demo/replay` to admin/lab mode and add tests.
3. [x] Make the OAuth `f_session` cookie honor secure/samesite settings.
4. [x] Make workspace saves fail visibly on HTTP errors.
5. [x] Add CI workflow for the test/lint/build commands that currently pass locally.
6. [x] Refresh the most misleading contract fixtures for SIEM/SOAR.
7. Expand audit action i18n for MVP SOC/workspace actions.

### Deferred but tracked

- Real production compose overlay: remove dev commands, direct port publishes and seed realm imports.
- PresentationView real widget rendering.
- SIEM/SOAR/XDR migrations instead of `metadata.create_all`.
- Service pagination/limits.
- Full integrations/build-pane i18n.
- Prometheus/readiness health checks.
- AI token budget/rate limits.

---

## Task 1: Stop XDR endpoint spoofing

Status: **implemented** in commit `fix(xdr): bind enrollment tokens to endpoints`.

**Objective:** A bearer enrollment token can only report for the endpoint it first claimed, or for the endpoint pre-bound to that enrollment.

**Files:**
- Modify: `apps/xdr_rico/app/store.py`
- Modify: `apps/xdr_rico/app/main.py`
- Test: `apps/xdr_rico/tests/test_core.py`

**TDD steps:**

1. Add a failing test `test_enrollment_token_cannot_report_for_a_different_endpoint_after_first_use`:
   - Create enrollment token.
   - POST heartbeat for `end_01` with that token — expect 201.
   - POST heartbeat for `end_02` with same token — expect 403.
   - Assert `GET /endpoints/end_02` is 404.
2. Run only that test and verify it fails.
3. Add store helpers to load enrollment by token hash and update its payload with `claimedEndpointId` on first use.
4. Change authorization to return the enrollment record and reject endpoint mismatch.
5. Run xdr tests and ruff.
6. Commit: `fix(xdr): bind enrollment tokens to endpoints`.

## Task 2: Gate demo replay

Status: **implemented** in commit `fix(api): gate synthetic SOC replay`.

**Objective:** Synthetic replay must be impossible in normal analyst sessions unless demo mode is explicitly enabled.

**Files:**
- Modify: `apps/api/app/core/config.py` if a dedicated setting is needed
- Modify: `apps/api/app/routers/soc.py`
- Test: `apps/api/tests/test_mvp_demo_chain.py` and/or SOC gateway tests

**TDD steps:**

1. Add a failing test proving an analyst user gets 403 from `POST /api/soc/demo/replay` when demo replay is disabled.
2. Add a passing-path test for admin or explicit demo-mode setting.
3. Implement minimal gate: allow admin role OR `settings.mock_mode`/`settings.demo_replay_enabled`.
4. Keep CSRF and audit behavior unchanged.
5. Run targeted API tests, then full API tests.
6. Commit: `fix(api): gate synthetic SOC replay`.

## Task 3: Harden OAuth state cookie settings

Status: **implemented** in commit `fix(api): honor secure session cookie settings`.

**Objective:** Starlette `SessionMiddleware` must use the same secure/samesite posture as the BFF session in production.

**Files:**
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_auth_sso.py` or new config test

**TDD steps:**

1. Add a failing test that reloads/builds the app with `FORTIDASHBOARD_SESSION_COOKIE_SECURE=true` and verifies `SessionMiddleware` is configured with `https_only=True`.
2. Implement settings-driven `same_site` and `https_only` in `app.main`.
3. Run targeted test and API suite.
4. Commit: `fix(auth): honor secure setting for oauth state cookie`.

## Task 4: Surface workspace save failures

Status: **implemented** in commit `fix(web): expose workspace save failures`.

**Objective:** Workspace persistence HTTP failures should not be swallowed.

**Files:**
- Modify: `apps/web/src/stores/useDashboardStore.ts`
- Test: `apps/web/tests/unit/dashboardStore.test.ts`

**TDD steps:**

1. Add a failing Vitest case where `fetch` returns `ok: false`; assert the store records a save error or rejects `saveWorkspace()`.
2. Implement minimal error state, e.g. `workspaceSaveError`, set on failure, clear on success.
3. Ensure callers that await save can detect failure; debounced saves should log and retain error state.
4. Run targeted test and web tests.
5. Commit: `fix(web): expose workspace save failures`.

## Task 5: Add CI quality gate

Status: **implemented** in commit `ci: add baseline quality gate`.

**Objective:** GitHub Actions must run the same commands that currently pass locally.

**Files:**
- Create: `.github/workflows/ci.yml`

**Steps:**

1. Add workflow with jobs for compose validation, API, SOC-lite services and web.
2. Use `astral-sh/setup-uv` and `pnpm/action-setup`/Node setup.
3. Keep first pass simple and deterministic; no Docker service boot required beyond `docker compose config --quiet`.
4. Validate YAML locally if possible and run representative commands locally.
5. Commit: `ci: add baseline quality gate`.

## Task 6: Refresh stale contract fixtures

Status: **implemented** in commit `fix(contracts): align SOC fixtures with services`.

**Objective:** Shared fixtures must match actual MVP service response shapes.

**Files:**
- Modify: `packages/contracts/fixtures/incident.json`
- Modify: `packages/contracts/fixtures/playbook.json`
- Modify: `packages/contracts/fixtures/playbook_run.json`
- Test: add/adjust existing contract tests if present

**TDD steps:**

1. Add a small test/script that validates fixture keys against current models or expected live shapes.
2. Watch it fail on stale fields (`incident.created`, `createdAt`, `status`, `mode`).
3. Update fixtures to use current SIEM/SOAR shapes.
4. Run contract/API tests.
5. Commit: `fix(contracts): align SOC fixtures with services`.

## Task 7: Translate MVP audit actions

**Objective:** Audit feed should not show raw technical action names for delivered MVP flows.

**Files:**
- Modify: `apps/web/src/components/audit/auditFormat.ts`
- Modify: `apps/web/src/i18n/messages/pt-BR.ts`
- Modify: `apps/web/src/i18n/messages/en-US.ts`
- Test: `apps/web/tests/unit/auditFeed.test.ts`

**TDD steps:**

1. Add tests for `soc.demo.replay`, `soc.incident.analyzed`, `soc.ticket.playbook_drafted`, `soc.ticket.contained`, `workspace.imported`, `workspace.exported`, `workspace.presentation.updated`, `workspace.widget.rebound`.
2. Watch tests fail because titles are raw action strings.
3. Add `ACTION_KEYS` entries and translations.
4. Run audit tests and web tests.
5. Commit: `fix(web): translate MVP audit actions`.

---

## Verification Before Handoff

Run:

```bash
docker compose config --quiet
cd apps/api && uv run ruff check . && uv run pytest -q
cd apps/siem_kowalski && uv run ruff check . && uv run pytest -q
cd apps/soar_skipper && uv run ruff check . && uv run pytest -q
cd apps/xdr_rico && uv run ruff check . && uv run pytest -q
cd apps/agent_private && uv run ruff check . && uv run pytest -q
cd apps/web && pnpm test -- --run && pnpm build
```

Handoff must include changed apps/services, contract changes, verification commands and remaining known gaps.
