# FortiDashboard

FortiDashboard is a modular NG-SOC dashboard focused first on FortiGate visibility through a FastAPI backend and a Vue-based frontend workspace.

## Current State

The committed implementation starts the backend foundation:

- `apps/api`: FastAPI service with healthcheck, BFF auth, persisted server-side sessions, and mock contract endpoints.
- `packages/contracts/fixtures`: JSON fixtures shared by backend tests and frontend mocks.
- `packages/widget-catalog`: neutral FortiGate widget catalog seed data.
- `docker-compose.yml`: local Postgres and Keycloak services for backend development.

## Backend Development

```bash
docker compose up --build api
```

For local Python-only backend work:

```bash
docker compose up -d db keycloak
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

## Auth Model

The Vue app owns the visual login/register pages, but it must call FastAPI instead of Keycloak directly:

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/logout`

FastAPI acts as a BFF/auth gateway. The browser receives a `fortidashboard_session` cookie marked `HttpOnly`; Keycloak tokens stay server-side and are persisted in Postgres as an encrypted `token_blob`. The default Compose mode still uses fixtures so frontend work can proceed without Keycloak/FortiGate dependencies.

Keycloak runs locally at `http://localhost:8080` with temporary development admin credentials from `docker-compose.yml`. Replace these before any shared or deployed environment.

To exercise the Keycloak-backed code path, run:

```bash
FORTIDASHBOARD_MOCK_MODE=false docker compose up -d --build api
```

The API applies Alembic migrations at container startup for local development.

## Contract Fixtures

Frontend work can proceed without the live backend by reading the JSON examples in `packages/contracts/fixtures`. Keep these fixtures in sync with FastAPI responses and update `AGENTS.md` when endpoint shapes change.
