# Audit Admin RBAC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Keycloak-backed administrator roles and an admin-only cross-user audit log endpoint.

**Architecture:** FastAPI remains the BFF and session authority. Keycloak realm roles are parsed server-side during login/register and stored in `auth_sessions`; admin-only routes use a reusable dependency that checks the session user roles. Audit events remain sanitized on write and read.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Keycloak dev realm JSON, Pytest, httpx MockTransport.

---

## File Structure

- Modify `apps/api/app/auth/keycloak.py`: parse realm roles from Keycloak access tokens and use them for public users.
- Modify `apps/api/app/auth/dependencies.py`: add `require_admin_user`.
- Modify `apps/api/app/auth/audit.py`: support optional filters for audit listing.
- Modify `apps/api/app/routers/audit.py`: add `/admin/audit/events`.
- Modify `infra/keycloak/realm-fortidashboard.json`: seed dev admin user.
- Modify `apps/api/tests/test_keycloak_client.py`: role extraction tests.
- Modify `apps/api/tests/test_keycloak_realm_config.py`: dev admin config tests.
- Modify `apps/api/tests/test_audit_log.py`: admin endpoint, filters, redaction, and audit-read event tests.
- Modify `AGENTS.md`: document admin audit/RBAC behavior and backlog progress.

## Task 1: Keycloak Role Extraction

**Files:**
- Modify: `apps/api/app/auth/keycloak.py`
- Test: `apps/api/tests/test_keycloak_client.py`

- [ ] **Step 1: Write failing tests**

Add tests proving `KeycloakClient.login()` exposes parsed roles from a JWT-like access token and falls back to `analyst` when role claims are absent.

Run: `cd apps/api && uv run pytest tests/test_keycloak_client.py -q`
Expected: FAIL because `KeycloakTokenSet` has no `roles` attribute and role parsing does not exist.

- [ ] **Step 2: Implement minimal role parsing**

Add `roles: list[str]` to `KeycloakTokenSet`, decode the middle JWT segment without verifying the signature, read `realm_access.roles`, filter to strings, and default to `["analyst"]` when empty or malformed.

- [ ] **Step 3: Verify green**

Run: `cd apps/api && uv run pytest tests/test_keycloak_client.py -q`
Expected: PASS.

## Task 2: Store Real Roles in BFF Sessions

**Files:**
- Modify: `apps/api/app/auth/service.py`
- Test: `apps/api/tests/test_auth_service.py`

- [ ] **Step 1: Write failing test**

Add a test where `KeycloakIdentityProvider.login()` receives token roles `["admin"]` and returns public user roles `["admin"]`.

Run: `cd apps/api && uv run pytest tests/test_auth_service.py -q`
Expected: FAIL because userinfo currently returns static `["analyst"]`.

- [ ] **Step 2: Implement minimal session role propagation**

Make `KeycloakIdentityProvider.login()` pass `tokens.roles` into the public user payload. Keep `register()` analyst-only in this cut.

- [ ] **Step 3: Verify green**

Run: `cd apps/api && uv run pytest tests/test_auth_service.py -q`
Expected: PASS.

## Task 3: Admin Dependency and Admin Audit Endpoint

**Files:**
- Modify: `apps/api/app/auth/dependencies.py`
- Modify: `apps/api/app/auth/audit.py`
- Modify: `apps/api/app/routers/audit.py`
- Test: `apps/api/tests/test_audit_log.py`

- [ ] **Step 1: Write failing API tests**

Add tests for:

- `analyst` receives `403` from `GET /api/admin/audit/events`.
- `admin` can read events from multiple users.
- `admin` can filter by `actorUserId`, `action`, and `outcome`.
- successful admin read records `audit.events.viewed`.
- admin response redacts secrets.

Run: `cd apps/api && uv run pytest tests/test_audit_log.py -q`
Expected: FAIL because `/api/admin/audit/events` does not exist.

- [ ] **Step 2: Implement dependency and filtering**

Add `require_admin_user()` that calls `get_current_api_user()` and requires `"admin"` in `roles`. Extend audit store `list_events()` with optional `action`, `outcome`, and `actor_user_id` filters.

- [ ] **Step 3: Implement admin endpoint**

Add `GET /api/admin/audit/events` to `apps/api/app/routers/audit.py`. It uses `require_admin_user`, applies filters, returns the same payload shape as `/api/audit/events`, and records `audit.events.viewed` with filter details.

- [ ] **Step 4: Verify green**

Run: `cd apps/api && uv run pytest tests/test_audit_log.py -q`
Expected: PASS.

## Task 4: Keycloak Dev Admin User

**Files:**
- Modify: `infra/keycloak/realm-fortidashboard.json`
- Test: `apps/api/tests/test_keycloak_realm_config.py`

- [ ] **Step 1: Write failing realm config test**

Add a test asserting `admin@example.com` exists, is enabled, has verified email, has a non-temporary password credential, and has realm role `admin`.

Run: `cd apps/api && uv run pytest tests/test_keycloak_realm_config.py -q`
Expected: FAIL because the seeded admin user does not exist.

- [ ] **Step 2: Add dev admin user**

Add `admin@example.com` to the realm import with role `admin` and a documented demo password.

- [ ] **Step 3: Verify green**

Run: `cd apps/api && uv run pytest tests/test_keycloak_realm_config.py -q`
Expected: PASS.

## Task 5: Documentation and Contract Updates

**Files:**
- Modify: `AGENTS.md`
- Optionally modify: `packages/contracts/fixtures/auth_me_authenticated.json`, `packages/contracts/fixtures/auth_login_response.json`

- [ ] **Step 1: Update docs**

Document:

- admin dev account exists only for local PoC.
- `/api/admin/audit/events` is admin-only.
- public register remains analyst-only.
- production admins are managed through Keycloak.

- [ ] **Step 2: Verify docs are consistent**

Run: `rg -n "admin/audit|admin@example|audit.events.viewed|roles" AGENTS.md packages/contracts/fixtures`
Expected: shows the new contract and no contradictory statement that all users are analysts.

## Task 6: Full Verification and Commit

**Files:**
- All changed files.

- [ ] **Step 1: Run backend tests**

Run: `cd apps/api && uv run pytest -q`
Expected: PASS.

- [ ] **Step 2: Run diff checks**

Run: `git diff --check`
Expected: no output.

- [ ] **Step 3: Commit implementation**

Run:

```bash
git add AGENTS.md docs/superpowers/plans/2026-04-29-audit-admin-rbac.md apps/api/app/auth/keycloak.py apps/api/app/auth/service.py apps/api/app/auth/dependencies.py apps/api/app/auth/audit.py apps/api/app/routers/audit.py infra/keycloak/realm-fortidashboard.json apps/api/tests/test_keycloak_client.py apps/api/tests/test_auth_service.py apps/api/tests/test_keycloak_realm_config.py apps/api/tests/test_audit_log.py
git commit -m "feat(audit): add admin rbac audit view"
```

Expected: commit succeeds with only audit/RBAC related files staged.
