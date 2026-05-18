# Playbook Builder Main Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Move SOAR Playbooks out of the widget drawer flow and make the sidebar entry render a full playbook builder surface with CRUD for non-system playbooks.

**Architecture:** `DashboardView` owns the active main surface (`workspace` or `playbooks`). `Sidebar` emits surface changes instead of opening a playbooks drawer. `PlaybookCanvasLayer` stays the graph editor but gains a main-surface layout and a playbook library that can create, view, update and delete custom playbooks while system playbooks remain visible and protected.

**Tech Stack:** Vue 3, Pinia, Vitest, FastAPI BFF, soar_skipper FastAPI service, pytest.

---

### Task 1: Surface Navigation

**Files:**
- Modify: `apps/web/src/views/DashboardView.vue`
- Modify: `apps/web/src/components/layout/Sidebar.vue`
- Create: `apps/web/src/components/playbooks/PlaybookBuilderSurface.vue`
- Test: `apps/web/tests/unit/dashboardViewPlaybooks.test.ts`

- [x] **Step 1: Write the failing test**

Create a Vitest test that mounts `DashboardView`, clicks the sidebar SOAR Playbooks button, expects `DashboardCanvas` to disappear, expects `PlaybookBuilderSurface` to appear, and expects clicking the dashboard icon to restore the workspace.

- [x] **Step 2: Run test to verify it fails**

Run: `cd apps/web && pnpm exec vitest run tests/unit/dashboardViewPlaybooks.test.ts`

Expected: FAIL because the playbooks sidebar button currently opens a drawer and no main-surface builder exists.

- [x] **Step 3: Implement navigation**

Add `activeSurface` to `DashboardView`. Pass it to `Sidebar`. Render `DashboardCanvas` for `workspace` and `PlaybookBuilderSurface` for `playbooks`. Remove `PlaybooksPanel` from `Sidebar` and emit `select-surface`.

- [x] **Step 4: Verify**

Run: `cd apps/web && pnpm exec vitest run tests/unit/dashboardViewPlaybooks.test.ts`

Expected: PASS.

### Task 2: Playbook CRUD With Protected System Templates

**Files:**
- Modify: `apps/soar_skipper/app/models.py`
- Modify: `apps/soar_skipper/app/store.py`
- Modify: `apps/soar_skipper/app/main.py`
- Modify: `apps/api/app/routers/soc.py`
- Modify: `apps/web/src/services/playbooksClient.ts`
- Modify: `apps/web/src/stores/usePlaybooksStore.ts`
- Modify: `apps/web/src/components/playbooks/canvas/PlaybookCanvasLayer.vue`
- Modify: `apps/web/src/i18n/messages/en-US.ts`
- Modify: `apps/web/src/i18n/messages/pt-BR.ts`
- Test: `apps/soar_skipper/tests/test_playbooks.py`
- Test: `apps/api/tests/test_soc_gateway.py`
- Test: `apps/web/tests/unit/playbookCanvasLayer.test.ts`

- [x] **Step 1: Write failing tests**

Add pytest coverage that system playbooks include `system: true`, cannot be updated, and cannot be deleted. Add BFF coverage that `DELETE /api/soc/playbooks/{id}` forwards and audits. Add Vitest coverage that custom playbooks render a delete action and system playbooks render a protected badge without a delete action.

- [x] **Step 2: Run tests to verify they fail**

Run:
`cd apps/soar_skipper && uv run pytest -q tests/test_playbooks.py`
`cd apps/api && uv run pytest -q tests/test_soc_gateway.py::test_soar_playbook_delete_forwards_and_audits`
`cd apps/web && pnpm exec vitest run tests/unit/playbookCanvasLayer.test.ts`

Expected: FAIL because delete endpoints, `system` metadata, and UI delete controls are missing.

- [x] **Step 3: Implement backend and UI**

Add `system` to the playbook contract, mark seeded playbooks as system, add store delete support, add `DELETE /playbooks/{playbook_id}` in soar_skipper, add `DELETE /api/soc/playbooks/{playbook_id}` in the BFF with audit, add client/store delete methods, and render CRUD controls in the builder.

- [x] **Step 4: Verify**

Run the three focused test commands again.

Expected: PASS.

### Task 3: Remove Builder Widget Registration

**Files:**
- Modify: `packages/contracts/fixtures/widget_catalog_soc.json`
- Modify: `apps/api/app/routers/widgets.py`
- Modify: `apps/api/tests/test_soc_widgets.py`
- Modify: `apps/web/src/components/canvas/DashboardCanvas.vue`
- Modify: `apps/web/src/utils/widgetLayout.ts`
- Modify: `apps/web/tests/unit/dashboardBuildPane.test.ts`
- Delete: `apps/web/src/components/widgets/soc/WidgetPlaybookBuilder.vue`

- [x] **Step 1: Write failing tests**

Change API and web tests to assert `soar-playbook-builder` is absent from the widget catalog and dashboard build pane.

- [x] **Step 2: Run tests to verify they fail**

Run:
`cd apps/api && uv run pytest -q tests/test_soc_widgets.py`
`cd apps/web && pnpm exec vitest run tests/unit/dashboardBuildPane.test.ts`

Expected: FAIL while the widget catalog still exposes `soar-playbook-builder`.

- [x] **Step 3: Remove widget registration**

Delete the widget component, remove it from `DashboardCanvas`, remove its fixture entry, remove self-managed BFF data handling, and remove layout constraints.

- [x] **Step 4: Verify full focused set**

Run:
`git diff --check`
`cd apps/web && pnpm exec vitest run tests/unit/dashboardViewPlaybooks.test.ts tests/unit/dashboardBuildPane.test.ts tests/unit/playbookCanvasLayer.test.ts`
`cd apps/api && uv run pytest -q tests/test_soc_widgets.py tests/test_soc_gateway.py::test_soar_playbook_delete_forwards_and_audits`
`cd apps/soar_skipper && uv run pytest -q tests/test_playbooks.py`
`cd apps/web && pnpm build`
