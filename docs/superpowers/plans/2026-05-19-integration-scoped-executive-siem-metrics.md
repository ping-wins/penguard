# Integration-Scoped Executive SIEM Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scope SIEM executive metrics by integration and provider source while keeping existing widget payloads backward compatible.

**Architecture:** `siem_kowalski` keeps the aggregate endpoint and adds optional `integrationId`/`providerType` filters before calculating severity, recent incidents, top entities, SLA and response times. The BFF continues validating widget integration ownership and passes the validated integration ID to SIEM. Vue widgets do not need API-shape changes.

**Tech Stack:** FastAPI, Pydantic, pytest, SQLAlchemy Core, Ruff.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `apps/siem_kowalski/app/main.py` | Modify | Add scoped metric query params, filtering helpers and scoped logging |
| `apps/siem_kowalski/tests/test_events_incidents.py` | Modify | Add scoped SIEM metric tests |
| `apps/api/app/routers/widgets.py` | Modify | Pass validated widget `integrationId` to `/metrics/executive` |
| `apps/api/tests/test_soc_widgets.py` | Modify | Assert BFF sends `integrationId` to SIEM and still blocks invalid integrations |
| `docs/superpowers/specs/2026-05-19-integration-scoped-executive-siem-metrics-design.md` | Existing | Source spec |

---

## Tasks

### Task 1: SIEM Scoped Metrics

- [ ] Add failing SIEM tests for unscoped behavior, `integrationId`, related-event fallback, `providerType`, combined filters and unknown integration IDs.
- [ ] Run the focused SIEM tests and confirm they fail because query params are ignored or unsupported.
- [ ] Implement provider type validation and filtering helpers in `apps/siem_kowalski/app/main.py`.
- [ ] Reuse related event lookup once per metric request.
- [ ] Re-run the focused SIEM tests.

### Task 2: BFF Integration Scope

- [ ] Add/update BFF widget tests to assert `/metrics/executive` receives `integrationId`.
- [ ] Run the focused BFF test and confirm it fails before implementation.
- [ ] Update `_siem_executive_metrics()` signature and call sites in `apps/api/app/routers/widgets.py`.
- [ ] Re-run focused BFF tests.

### Task 3: Verification And Commit

- [ ] Run SIEM tests for `tests/test_events_incidents.py`.
- [ ] Run API tests for `tests/test_soc_widgets.py`.
- [ ] Run Ruff on changed API/SIEM files.
- [ ] Run `git diff --check`.
- [ ] Stage only files in this feature scope and commit.
