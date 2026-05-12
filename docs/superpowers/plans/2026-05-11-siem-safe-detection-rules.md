# SIEM Safe Detection Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `siem_kowalski` hardcoded detection branches with a safe declarative rule evaluator and add a FortiGate CPU/memory pressure rule.

**Architecture:** `siem_kowalski` owns detection rules and evaluates only constrained field paths and operators. Rules are static defaults for this cut, listable through the service and BFF, and do not execute user code, Python expressions, SQL or shell. The gateway exposes read-only rule metadata for future UI/AI use.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, Pytest, existing BFF `SocServiceClient`.

---

## File Structure

- Modify `apps/siem_kowalski/app/main.py`: add detection rule models, evaluator helpers, default rule catalog and `GET /rules`.
- Modify `apps/siem_kowalski/tests/test_events_incidents.py`: add red/green coverage for rule listing, safe numeric evaluation and high resource pressure.
- Modify `apps/api/app/routers/soc.py`: add `GET /api/soc/rules`.
- Modify `apps/api/tests/test_soc_gateway.py`: add gateway forwarding test for rule listing.
- Modify `AGENTS.md`: mark SIEM rule model and high resource rule complete.

## Task 1: SIEM Rule Model

- [x] Write failing `siem_kowalski` tests for `GET /rules`, high CPU/memory incident creation and non-numeric `gte` safety.
- [x] Verify the tests fail before production code changes.
- [x] Add `RuleCondition` and `DetectionRule` Pydantic models.
- [x] Convert current detections into default declarative rules.
- [x] Add constrained operators: `equals`, `gte`, `exists` and `contains`.
- [x] Add `fortigate.resource_pressure` rule for high CPU or memory telemetry.
- [x] Run `cd apps/siem_kowalski && uv run pytest tests/test_events_incidents.py -q`.

## Task 2: API Gateway Rule Listing

- [x] Write a failing gateway test for `GET /api/soc/rules`.
- [x] Verify the test fails with `404 Not Found`.
- [x] Implement the gateway route by forwarding `GET /rules` to `siem_kowalski`.
- [x] Run `cd apps/api && uv run pytest tests/test_soc_gateway.py -q`.

## Task 3: Backlog And Verification

- [x] Update `AGENTS.md` SIEM capabilities and backlog.
- [x] Run `cd apps/siem_kowalski && uv run pytest -q`.
- [x] Run `cd apps/siem_kowalski && uv run ruff check .`.
- [x] Run `cd apps/api && uv run pytest tests/test_soc_gateway.py -q`.
- [x] Run `cd apps/api && uv run ruff check app/routers/soc.py tests/test_soc_gateway.py`.
- [x] Run `git diff --check`.
