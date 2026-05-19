# Executive SIEM Template Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve curated templates and make `siem_kowalski` calculate executive SOC metrics that feed the existing executive widgets.

**Architecture:** Add a SIEM aggregate endpoint, route existing SOC widget IDs through that endpoint in the BFF, update the two existing executive widgets to consume calculated fields, and upsert curated template rows from JSON via migration. Widget API URLs remain under `/api/widgets/{widgetId}/data`.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy Core, Alembic, pytest, Vue 3 Composition API, Vitest, Tailwind CSS.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `apps/siem_kowalski/app/store.py` | Modify | Add event lookup by IDs for MTTD calculations |
| `apps/siem_kowalski/app/main.py` | Modify | Add executive metrics models, calculations and endpoint |
| `apps/siem_kowalski/tests/test_events_incidents.py` | Modify | Add failing tests for SIEM executive metrics |
| `apps/api/app/routers/widgets.py` | Modify | Route SIEM widgets to `/metrics/executive` sections |
| `apps/api/app/integrations/penguin_tools.py` | Modify | Map SLA and MTTD widgets to `siem_kowalski` |
| `apps/api/tests/test_soc_widgets.py` | Modify | Add/update BFF widget tests for executive metrics |
| `packages/contracts/fixtures/widget_catalog_soc.json` | Modify | Give SLA and MTTD widgets first-class data endpoints |
| `apps/api/app/workspaces/presets/*.json` | Modify | Improve curated template layouts and descriptions |
| `apps/api/migrations/versions/20260519_0022_update_curated_workspace_templates.py` | Create | Upsert curated template rows from preset JSON |
| `apps/web/src/components/widgets/soc/WidgetSocMttdMttr.vue` | Modify | Prefer SIEM-calculated response-time fields |
| `apps/web/src/components/widgets/soc/WidgetSocSlaBreach.vue` | Modify | Prefer SIEM-calculated SLA fields |
| `apps/web/src/lib/widgetSeries.ts` | Modify | Sample SIEM-calculated SLA/response-time numbers |
| `apps/web/tests/unit/widgetRenderers.test.ts` | Modify | Cover renderer registration/loaded calculated payloads if needed |

---

## Tasks

### Task 1: SIEM Executive Metrics

- [ ] Write failing tests in `apps/siem_kowalski/tests/test_events_incidents.py`:
  - `test_executive_metrics_calculates_widget_sections`
  - `test_executive_metrics_classifies_sla_breaches`
- [ ] Run:
  `cd apps/siem_kowalski && uv run pytest tests/test_events_incidents.py::test_executive_metrics_calculates_widget_sections -q`
  Expected: fail with `404 Not Found` for `/metrics/executive`.
- [ ] Implement `SiemStore.list_events_by_ids(ids)` in `store.py`.
- [ ] Add metrics helpers and `GET /metrics/executive` in `main.py`.
- [ ] Re-run the two SIEM tests and keep existing SIEM tests green.

### Task 2: BFF Widget Routing

- [ ] Write failing tests in `apps/api/tests/test_soc_widgets.py` for:
  - `soc-mttd-mttr` returning `responseTimes`
  - `soc-sla-breach` returning `sla`
  - severity/recent/top entities using `/metrics/executive`
- [ ] Run the focused tests and confirm the new widget IDs currently fail.
- [ ] Add the two widget IDs to `SOC_WIDGET_IDS`.
- [ ] Add `expected_tool_type_for_widget()` mapping for both IDs.
- [ ] Add `_siem_executive_metrics()` and section routing in `_soc_widget_data()`.
- [ ] Update SOC widget summary/empty-state helpers for the two widgets.

### Task 3: Catalog, Presets and Migration

- [ ] Update `packages/contracts/fixtures/widget_catalog_soc.json` so SLA and
  MTTD use `/api/widgets/soc-sla-breach/data` and
  `/api/widgets/soc-mttd-mttr/data`.
- [ ] Improve curated preset JSON files, with the executive template carrying
  severity, MTTD/MTTR, SLA breach, risk posture, recent incidents and top
  entities.
- [ ] Add migration `20260519_0022_update_curated_workspace_templates.py` that
  reads `apps/api/app/workspaces/presets/*.json` and upserts curated template
  rows by slug while preserving install counts.
- [ ] Validate JSON with `python -m json.tool` for each preset.

### Task 4: Vue Consumption of Calculated Fields

- [ ] Update `WidgetSocMttdMttr.vue` to prefer `mttdAvgMs`,
  `mttrAvgMs`, `mttdMedianMs`, `mttrMedianMs`, `sampleSize` and `perIncident`
  from SIEM, falling back to current browser estimates only when absent.
- [ ] Update `WidgetSocSlaBreach.vue` to prefer SIEM `breaches`, `red`,
  `amber` and `open` fields, falling back to current incident-derived behavior.
- [ ] Update `widgetSeries.ts` samplers for `soc-sla-breach` and
  `soc-mttd-mttr` to use calculated fields first.

### Task 5: Verification

- [ ] Run:
  `cd apps/siem_kowalski && uv run pytest tests/test_events_incidents.py -q`
- [ ] Run:
  `cd apps/api && uv run pytest tests/test_soc_widgets.py tests/test_workspace_persistence.py -q`
- [ ] Run:
  `cd apps/api && uv run ruff check app tests/test_soc_widgets.py`
- [ ] Run:
  `cd apps/web && pnpm test -- widgetRenderers`
- [ ] Run:
  `git diff --check`

---

## Self-Review

The plan covers the spec sections: SIEM aggregate endpoint, BFF routing, preset
updates, migration, Vue consumption and focused verification. No extra provider,
polling loop or live action path is introduced.
