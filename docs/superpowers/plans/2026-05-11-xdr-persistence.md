# XDR Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist `xdr_rico` enrollments, endpoints and endpoint timelines beyond process memory.

**Architecture:** Add a small SQLAlchemy-backed store owned by `xdr_rico`. The store keeps token hashes, endpoint snapshots and timeline payloads in service-owned tables. Tests use in-memory SQLite; Docker Compose points the service at the shared Postgres database.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLAlchemy, SQLite for tests, Postgres/psycopg in Compose, Pytest and Ruff.

---

## File Structure

- Create `apps/xdr_rico/app/store.py`: SQLAlchemy engine, tables and CRUD helpers.
- Modify `apps/xdr_rico/app/main.py`: replace `XdrStore` dict usage with store methods.
- Modify `apps/xdr_rico/tests/test_core.py`: add persistence regression tests for enrollment tokens, endpoints and timeline.
- Modify `apps/xdr_rico/pyproject.toml` and `uv.lock`: add SQLAlchemy and Postgres driver.
- Modify `docker-compose.yml` and `.env.example`: configure `XDR_RICO_DATABASE_URL`.
- Modify `AGENTS.md`: mark XDR persistence complete.

## Task 1: Persistence Regression Tests

- [x] Add tests that create enrollments/endpoints/timeline, clear legacy dicts and verify data remains usable.
- [x] Verify tests fail against the current in-memory implementation.

## Task 2: SQLAlchemy Store

- [x] Add service-owned tables `xdr_rico_enrollments`, `xdr_rico_endpoints` and `xdr_rico_timeline`.
- [x] Store token hashes without plaintext tokens.
- [x] Store full endpoint/timeline JSON plus indexed fields.
- [x] Implement reset, lookup, upsert, list and delete operations.

## Task 3: Service Wiring And Configuration

- [x] Replace direct dict access in `app/main.py` with store methods.
- [x] Add `XDR_RICO_DATABASE_URL` to Compose and `.env.example`.
- [x] Update `AGENTS.md` backlog and capability notes.

## Task 4: Verification

- [x] Run `cd apps/xdr_rico && uv run pytest -q`.
- [x] Run `cd apps/xdr_rico && uv run ruff check .`.
- [x] Run `docker compose config --quiet`.
- [x] Run `docker compose build xdr-rico`.
- [x] Run `git diff --check`.
