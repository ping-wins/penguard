# Functional Playbook Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the workspace playbook builder self-explanatory and make the safe node set execute real Penguard effects, including Discord webhook notifications.

**Architecture:** Keep playbook graph storage and run history in `soar_skipper`, but execute external effects through the BFF because it owns auth, audit, SIEM access, policy orchestration and encrypted secrets. Store outbound webhook destinations in the API database with encrypted URLs; playbook nodes reference destination IDs rather than exposing Discord URLs in Vue state.

**Tech Stack:** FastAPI, SQLAlchemy/Alembic, httpx, Pydantic, Pytest, Vue 3, Pinia, Vitest, vue-i18n, Vue Flow.

---

### Task 1: BFF Webhook Destinations

**Files:**
- Create: `apps/api/app/playbooks/webhook_destinations.py`
- Modify: `apps/api/app/db/models.py`
- Create: `apps/api/migrations/versions/20260517_0019_playbook_webhook_destinations.py`
- Modify: `apps/api/app/routers/soc.py`
- Test: `apps/api/tests/test_playbook_webhook_destinations.py`

- [x] Write failing tests for creating, listing and sending a Discord destination without returning the webhook URL.
- [x] Add `PlaybookWebhookDestinationModel` with encrypted `url_blob`.
- [x] Add a small destination store/service using `TokenCipher`.
- [x] Add `GET /api/soc/playbook-webhook-destinations`, `POST /api/soc/playbook-webhook-destinations` and `POST /api/soc/playbook-webhook-destinations/{destinationId}/test`.
- [x] Audit create/test actions with redacted URL metadata only.
- [x] Run `cd apps/api && uv run pytest -q tests/test_playbook_webhook_destinations.py`.

### Task 2: Functional Playbook Effects

**Files:**
- Create: `apps/api/app/playbooks/effects.py`
- Modify: `apps/api/app/routers/soc.py`
- Test: `apps/api/tests/test_soc_playbook_effects.py`

- [x] Write failing tests for `notify.webhook` sending to a Discord destination during `/api/soc/incidents/{incidentId}/playbooks/{playbookId}/run`.
- [x] Write failing tests for `case.note` patching `/incidents/{incidentId}/triage`.
- [x] Write failing tests for `audit.note` creating an audit event.
- [x] Implement effect execution after the BFF creates the `soar_skipper` run.
- [x] Implement safe placeholder rendering for values such as `{incident.id}`, `{incident.severity}` and `{entities.sourceIp}`.
- [x] Make policy nodes return governed `requiresApproval`/`reviewRequired` effect records rather than applying provider changes silently.
- [x] Run `cd apps/api && uv run pytest -q tests/test_soc_playbook_effects.py tests/test_soc_gateway.py`.

### Task 3: Self-Explaining Node Catalog

**Files:**
- Modify: `apps/soar_skipper/app/node_catalog.py`
- Modify: `apps/soar_skipper/app/models.py`
- Test: `apps/soar_skipper/tests/test_playbooks.py`

- [x] Write failing tests that every node type exposes a description, effect summary, example config and required input labels.
- [x] Extend `NodeTypeDefinition` with optional metadata fields that older consumers can ignore.
- [x] Populate metadata for all nodes, including Discord-oriented `notify.webhook`.
- [x] Run `cd apps/soar_skipper && uv run pytest -q`.

### Task 4: Guided Builder UI

**Files:**
- Modify: `apps/web/src/services/playbooksClient.ts`
- Modify: `apps/web/src/components/playbooks/canvas/PlaybookCanvasLayer.vue`
- Modify: `apps/web/src/components/playbooks/canvas/PlaybookNodePropertiesPanel.vue`
- Modify: `apps/web/src/stores/usePlaybookCanvasStore.ts`
- Modify: `apps/web/src/i18n/messages/en-US.ts`
- Modify: `apps/web/src/i18n/messages/pt-BR.ts`
- Test: `apps/web/tests/unit/playbookCanvasLayer.test.ts`
- Test: `apps/web/tests/unit/playbookNodePropertiesPanel.test.ts`

- [x] Write failing tests for node drawer metadata, required field validation, schema-driven inputs and JSON advanced mode.
- [x] Add schema-driven form controls for string, integer, enum and string-array fields.
- [x] Show boundary/effect chips and missing required fields without instructional tutorial content.
- [x] Add a destination selector field for `notify.webhook`.
- [x] Add inline webhook destination create/test controls for Discord.
- [x] Keep advanced JSON editing available for operators.
- [x] Run `cd apps/web && pnpm exec vitest run tests/unit/playbookCanvasLayer.test.ts tests/unit/playbookNodePropertiesPanel.test.ts`.

### Task 5: Verification And Handoff

- [x] Run `git diff --check`.
- [x] Run `docker compose config --quiet`.
- [x] Run scoped API Ruff for changed files plus focused API tests.
- [x] Run `cd apps/soar_skipper && uv run pytest -q`.
- [x] Run `cd apps/web && pnpm test && pnpm build`.
- [x] Start the web dev server on an available port and report the URL.
- [x] Explain to Felipe how to create a Discord webhook destination and build the playbook using the polished builder.

Note: `cd apps/api && uv run ruff check .` is still blocked by pre-existing lint
failures outside this branch's scope; changed API files pass scoped Ruff.
