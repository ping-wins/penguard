# SIEM Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist `siem_kowalski` events, incidents and incident timelines beyond process memory.

**Architecture:** Add a small SQLAlchemy-backed store owned by `siem_kowalski`. The MVP stores canonical Pydantic payloads as JSON in service-owned tables, with indexed columns for list filters. Tests use in-memory SQLite; Docker Compose points the service at the shared Postgres database while keeping table names service-prefixed.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLAlchemy, SQLite for tests, Postgres/psycopg in Compose, Pytest and Ruff.

---

## File Structure

- Create `apps/siem_kowalski/app/store.py`: SQLAlchemy engine, schema and CRUD helpers.
- Modify `apps/siem_kowalski/app/main.py`: replace module-level lists with store calls.
- Modify `apps/siem_kowalski/tests/test_events_incidents.py`: add regression tests for persistence after legacy memory clear.
- Modify `apps/siem_kowalski/pyproject.toml` and `uv.lock`: add SQLAlchemy and Postgres driver.
- Modify `docker-compose.yml` and `.env.example`: configure `SIEM_KOWALSKI_DATABASE_URL`.
- Modify `AGENTS.md`: mark SIEM raw event persistence as done.

## Task 1: Persistence Regression Tests

- [x] Add tests that create events/incidents, clear legacy in-memory lists and verify data remains queryable.
- [x] Verify the tests fail against the current in-memory implementation.

## Task 2: SQLAlchemy Store

- [x] Add service-owned tables `siem_kowalski_events` and `siem_kowalski_incidents`.
- [x] Store full event/incident JSON plus indexed fields.
- [x] Implement list, detail and update operations through the store.
- [x] Initialize schema on service startup for MVP local/dev environments.

## Task 3: Compose And Docs

- [x] Add `SIEM_KOWALSKI_DATABASE_URL` to Compose and `.env.example`.
- [x] Update `AGENTS.md` backlog and current capability notes.

## Task 4: Verification

- [x] Run `cd apps/siem_kowalski && uv run pytest -q`.
- [x] Run `cd apps/siem_kowalski && uv run ruff check .`.
- [x] Run `docker compose config --quiet`.
- [x] Run `docker compose build siem-kowalski`.
- [x] Run `git diff --check`.
