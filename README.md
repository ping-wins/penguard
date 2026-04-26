# FortiDashboard

FortiDashboard é um dashboard modular para NG-SOC, focado em centralizar visibilidade de rede e inteligência de ameaças. O primeiro alvo de integração é FortiGate via REST API, com backend FastAPI e frontend Vue 3 + Vite.

## Estrutura do Monorepo

- `apps/api`: backend FastAPI com healthcheck, BFF auth, sessões server-side persistidas e endpoints mockados de contrato.
- `apps/web`: frontend Vue 3 + Vite para workspace livre, canvas, widgets e sidebar.
- `packages/contracts`: fixtures e schemas compartilhados entre backend e frontend.
- `packages/widget-catalog`: registro neutro de widgets FortiGate.
- `docker-compose.yml`: ambiente local com API, web, Postgres e Keycloak.

## Desenvolvimento com Docker

```bash
docker compose up --build
```

Serviços locais:

- API: `http://localhost:8000`
- Docs OpenAPI: `http://localhost:8000/docs`
- Web: `http://localhost:5173`
- Keycloak: `http://localhost:8080`
- Postgres: `localhost:5432`

Para testar o caminho real com Keycloak em vez de fixtures:

```bash
FORTIDASHBOARD_MOCK_MODE=false docker compose up -d --build api
```

A API aplica migrations Alembic no startup do container para desenvolvimento local.

## Backend

```bash
docker compose up -d db keycloak
cd apps/api
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Checks úteis:

```bash
cd apps/api
uv run pytest
uv run ruff check .
uv run alembic upgrade head
```

## Frontend

```bash
cd apps/web
pnpm install
pnpm dev
```

O frontend pode usar fixtures de `packages/contracts/fixtures` enquanto o FortiGate real não estiver integrado.

## Autenticação

O Vue implementa as telas próprias de login/register, mas chama FastAPI em vez de falar direto com Keycloak:

- `GET /api/auth/csrf`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/logout`

Para `register`, `login` e `logout`, chame `GET /api/auth/csrf` primeiro e envie o valor em `X-CSRF-Token`. A sessão do browser usa cookie `fortidashboard_session` com `HttpOnly`; tokens Keycloak ficam server-side e são persistidos em Postgres como `token_blob` criptografado.

## Contratos

Mudanças de payload devem atualizar:

- Pydantic models/endpoints em `apps/api`.
- Fixtures em `packages/contracts/fixtures`.
- Notas em `AGENTS.md` e `docs/api/README.md`.
- Consumidores em `apps/web`, quando aplicável.
