# Penguin Endpoint Correlation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correlate `siem_kowalski` incidents with `xdr_rico` endpoints so Penguard can show endpoint context for SOC investigations.

**Architecture:** `xdr_rico` owns endpoint matching because it owns endpoint identity, heartbeat and timeline state. `apps/api` exposes a browser-facing read endpoint that fetches an incident from `siem_kowalski`, sends its entities to `xdr_rico`, and returns a normalized context payload. This keeps the browser behind the BFF and avoids direct service calls.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, Pytest, existing `SocServiceClient`.

---

## File Structure

- Modify `apps/xdr_rico/app/main.py`: add correlation request/response models and matching helpers.
- Modify `apps/xdr_rico/tests/test_core.py`: add tests for IP, hostname, username and no-match correlation.
- Modify `apps/api/app/routers/soc.py`: add `GET /api/soc/incidents/{incidentId}/endpoint-context`.
- Modify `apps/api/tests/test_soc_gateway.py`: add gateway tests for SIEM-to-XDR context lookup.
- Modify `AGENTS.md`: mark endpoint/incident correlation progress.

## Task 1: XDR Correlation Contract

- [x] Write failing `xdr_rico` tests that ingest endpoint telemetry and call `POST /correlations/endpoint-context`.
- [x] Verify the tests fail with `404 Not Found`.
- [x] Add typed response models: matched field, endpoint context item and response envelope.
- [x] Match endpoint candidates by `endpointId`, IP-like entity fields, hostname and username/current user.
- [x] Return matches sorted by score with newest endpoint timeline items.
- [x] Run `cd apps/xdr_rico && uv run pytest tests/test_core.py -q`.

## Task 2: API Gateway Endpoint

- [x] Write a failing gateway test for `GET /api/soc/incidents/{incidentId}/endpoint-context`.
- [x] Verify the test fails with `404 Not Found`.
- [x] Implement the route by fetching `GET /incidents/{incidentId}` from SIEM and posting incident entities to XDR.
- [x] Return `incidentId`, `incident`, `items` and `total`.
- [x] Run `cd apps/api && uv run pytest tests/test_soc_gateway.py -q`.

## Task 3: Backlog And Verification

- [x] Update `AGENTS.md` to mark endpoint/incident correlation as done once tests pass.
- [x] Run `cd apps/xdr_rico && uv run pytest -q`.
- [x] Run `cd apps/api && uv run pytest tests/test_soc_gateway.py tests/test_soc_widgets.py -q`.
- [x] Run `git diff --check`.
