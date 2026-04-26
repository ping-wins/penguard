# FortiDashboard

FortiDashboard is a modular NG-SOC dashboard focused first on FortiGate visibility through a FastAPI backend and a Vue-based frontend workspace.

## Current State

The committed implementation starts the backend foundation:

- `apps/api`: FastAPI service with healthcheck, auth-session mocks, and mock contract endpoints.
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

FastAPI acts as a BFF/auth gateway. The browser receives a `fortidashboard_session` cookie marked `HttpOnly`; Keycloak tokens must stay server-side and must not be returned to JavaScript. The current implementation uses mock session fixtures so frontend work can proceed before live Keycloak wiring is complete.

Keycloak runs locally at `http://localhost:8080` with temporary development admin credentials from `docker-compose.yml`. Replace these before any shared or deployed environment.

To exercise the Keycloak-backed code path, set `FORTIDASHBOARD_MOCK_MODE=false` for the API service. The current default remains mock mode so the frontend can develop against stable fixtures while live session persistence is still being built.

## Contract Fixtures

Frontend work can proceed without the live backend by reading the JSON examples in `packages/contracts/fixtures`. Keep these fixtures in sync with FastAPI responses and update `AGENTS.md` when endpoint shapes change.
