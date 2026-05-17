# FortiWeb Provider Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add FortiWeb as a plug-and-play provider and let admins apply and remove a FortiWeb source-IP block from WAF/DoS incidents.

**Architecture:** Keep vendor API details isolated behind `apps/api/app/integrations/fortiweb/`. Add a FortiWeb store, client, block workflow, and integration routes that follow the existing FortiGate BFF/audit/RBAC pattern. Start with backend contracts and then wire the integration drawer and incident action UI to those contracts.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Alembic, httpx, Pytest, Vue 3, Pinia, vue-i18n.

---

## File Structure

- Create `apps/api/app/integrations/fortiweb/client.py`: FortiWeb API adapter, response decoding, and stable errors.
- Create `apps/api/app/integrations/fortiweb/store.py`: SQLAlchemy and in-memory stores for FortiWeb integrations and block requests.
- Create `apps/api/app/integrations/fortiweb/block_models.py`: Pydantic request/response models for preflight, review, apply, remove.
- Create `apps/api/app/integrations/fortiweb/block_workflow.py`: source-IP block preflight/apply/remove orchestration.
- Create `apps/api/app/integrations/fortiweb/service.py`: provider create/test/list/delete/health plus block workflow access.
- Modify `apps/api/app/db/models.py`: FortiWeb integration and block request ORM models.
- Create `apps/api/migrations/versions/20260517_0015_create_fortiweb_provider_tables.py`: database tables.
- Modify `apps/api/app/routers/integrations.py`: FortiWeb integration and block endpoints.
- Create `apps/api/tests/test_fortiweb_client.py`: API client decoding/error tests.
- Create `apps/api/tests/test_fortiweb_block_workflow.py`: pure workflow tests.
- Create `apps/api/tests/test_fortiweb_integrations.py`: route tests for provider create/test and block apply/remove RBAC.
- Modify `apps/web/src/stores/useIntegrationsStore.ts`: FortiWeb provider and block API calls.
- Modify `apps/web/src/components/layout/Sidebar.vue`: FortiWeb connection form in the integrations drawer.
- Modify `apps/web/src/services/ticketsClient.ts` and `apps/web/src/components/tickets/TicketsPanel.vue`: render FortiWeb block actions for WAF incidents.
- Modify `apps/web/src/i18n/messages/pt-BR.ts` and `apps/web/src/i18n/messages/en-US.ts`: new strings.

## Task 1: Backend Provider And Storage

**Files:**
- Modify: `apps/api/app/db/models.py`
- Create: `apps/api/migrations/versions/20260517_0015_create_fortiweb_provider_tables.py`
- Create: `apps/api/app/integrations/fortiweb/store.py`
- Create: `apps/api/app/integrations/fortiweb/client.py`
- Create: `apps/api/app/integrations/fortiweb/service.py`
- Create: `apps/api/tests/test_fortiweb_integrations.py`

- [ ] Add failing tests for FortiWeb connection test, create, list, delete, and secret redaction.
- [ ] Add ORM models and Alembic migration for `fortiweb_integrations` and `fortiweb_block_requests`.
- [ ] Implement `FortiWebApiClient` with API-key auth and stable `FortiWebApiError`.
- [ ] Implement `FortiWebIntegrationService` and stores with encrypted API key handling.
- [ ] Add FortiWeb routes and include FortiWeb items in `/api/integrations`.
- [ ] Run `cd apps/api && uv run pytest -q tests/test_fortiweb_integrations.py`.
- [ ] Commit with `feat(fortiweb): add provider integration backend`.

## Task 2: Backend Block Workflow

**Files:**
- Create: `apps/api/app/integrations/fortiweb/block_models.py`
- Create: `apps/api/app/integrations/fortiweb/block_workflow.py`
- Modify: `apps/api/app/integrations/fortiweb/service.py`
- Modify: `apps/api/app/routers/integrations.py`
- Create: `apps/api/tests/test_fortiweb_block_workflow.py`

- [ ] Add failing tests for preflight, review, admin-only apply, active persistence, admin-only remove, and remove persistence.
- [ ] Implement source-IP validation and `FD_IP_BLOCKLIST` diff creation.
- [ ] Implement apply using FortiWeb client methods for managed IP list creation/update.
- [ ] Implement remove using FortiWeb client methods and local state transitions.
- [ ] Add audit events for review/apply/remove success and failure.
- [ ] Run `cd apps/api && uv run pytest -q tests/test_fortiweb_block_workflow.py tests/test_fortiweb_integrations.py`.
- [ ] Commit with `feat(fortiweb): orchestrate source IP blocks`.

## Task 3: Frontend Provider Setup

**Files:**
- Modify: `apps/web/src/stores/useIntegrationsStore.ts`
- Modify: `apps/web/src/components/layout/Sidebar.vue`
- Modify: `apps/web/src/i18n/messages/pt-BR.ts`
- Modify: `apps/web/src/i18n/messages/en-US.ts`

- [ ] Add store methods `testFortiweb`, `addFortiweb`, `fetchFortiwebBlocks`, `reviewFortiwebBlock`, `applyFortiwebBlock`, and `removeFortiwebBlock`.
- [ ] Add FortiWeb form fields: name, host, API key, TLS verification, target policy, managed IP list.
- [ ] Render connected FortiWeb integrations with status and target policy.
- [ ] Localize all new strings in pt-BR and en-US.
- [ ] Run `cd apps/web && pnpm test`.
- [ ] Commit with `feat(web): add FortiWeb provider setup`.

## Task 4: Frontend Incident Action

**Files:**
- Modify: `apps/web/src/services/ticketsClient.ts`
- Modify: `apps/web/src/components/tickets/TicketsPanel.vue`
- Modify: `apps/web/src/i18n/messages/pt-BR.ts`
- Modify: `apps/web/src/i18n/messages/en-US.ts`

- [ ] Detect WAF incidents with `ruleId` in `fortiweb_dos_activity`, `fortiweb_waf_attack`, or `fortiweb_blocked_request` and a `sourceIp`.
- [ ] Show `Block source on FortiWeb` only when a connected FortiWeb integration exists.
- [ ] Render the review modal from backend diff response.
- [ ] Show active block state and `Remove FortiWeb block`.
- [ ] Hide apply/remove controls from non-admin users.
- [ ] Run `cd apps/web && pnpm test && pnpm build`.
- [ ] Commit with `feat(web): add FortiWeb incident block action`.

## Verification

- [ ] `git diff --check`
- [ ] `docker compose config --quiet`
- [ ] `cd apps/api && uv run ruff check . && uv run pytest -q`
- [ ] `cd apps/web && pnpm test && pnpm build`
- [ ] Lab: `ab -n 500 -c 50 http://10.10.20.30/`, approve block, confirm attacker fails, remove block, confirm access returns.
