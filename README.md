# FortiDashboard

FortiDashboard is a modular NG-SOC dashboard focused first on FortiGate visibility through a FastAPI backend and a Vue-based frontend workspace.

## Current State

The committed implementation starts the backend foundation:

- `apps/api`: FastAPI service with healthcheck and mock contract endpoints.
- `packages/contracts/fixtures`: JSON fixtures shared by backend tests and frontend mocks.
- `packages/widget-catalog`: neutral FortiGate widget catalog seed data.
- `docker-compose.yml`: local Postgres service for the future persistence layer.

## Backend Development

```bash
docker compose up -d db
cd apps/api
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Useful backend checks:

```bash
cd apps/api
uv run pytest
uv run ruff check .
uv run alembic upgrade head
```

The API exposes OpenAPI at `http://localhost:8000/openapi.json` and interactive docs at `http://localhost:8000/docs`.

## Contract Fixtures

Frontend work can proceed without the live backend by reading the JSON examples in `packages/contracts/fixtures`. Keep these fixtures in sync with FastAPI responses and update `AGENTS.md` when endpoint shapes change.
