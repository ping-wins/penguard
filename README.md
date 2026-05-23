# Penguard

> **License and intellectual property:** this public repository is provided only
> for academic evaluation in the FIAP Challenge developed in partnership with
> Fortinet. This project is not open source. Commercial use, redistribution,
> sublicensing, production deployment, derivative works, AI/model training use,
> and ownership transfer are not authorized. See `LICENSE.md`.

Penguard é um dashboard modular para NG-SOC, focado em centralizar visibilidade de rede e inteligência de ameaças. O primeiro alvo de integração é FortiGate via REST API, com backend FastAPI e frontend Vue 3 + Vite.

> **Modelo de deploy:** single-tenant por instância. Cada cliente roda sua
> própria stack (Postgres, Redis, Keycloak, BFF, lite services). Não é um
> SaaS multi-tenant — não há coluna `tenant_id` nas tabelas SOC. Veja
> `docs/maturity-analysis.md` para o contexto da decisão.

## Primeiro setup (uma vez por deploy)

Antes de subir o stack, gere segredos fortes para a instalação:

```bash
# Linux / macOS / WSL
./scripts/bootstrap-secrets.sh

# Windows PowerShell
./scripts/bootstrap-secrets.ps1
```

O script grava um `.env` na raiz (já no `.gitignore`) com valores aleatórios
para `PENGUARD_SECRET_KEY`, `PENGUARD_TOKEN_ENCRYPTION_KEY`,
`PENGUARD_KEYCLOAK_CLIENT_SECRET`, `KC_BOOTSTRAP_ADMIN_PASSWORD` e
`POSTGRES_PASSWORD`. Para rotacionar mais tarde, rode com `--force` (bash)
ou `-Force` (PowerShell).

A BFF **recusa subir** quando algum desses segredos ainda bate com o default
de dev (`apps/api/app/core/config.py:DANGEROUS_DEFAULT_SECRETS`). Em
desenvolvimento, defina `PENGUARD_MOCK_MODE=true` para bypass.

Depois do primeiro `docker compose up`, sincronize o client secret do
Keycloak com o valor que está no `.env` (o realm import vem com o literal
`dev-client-secret` para deploys novos):

```bash
# Linux / macOS / WSL (precisa de curl + jq):
./scripts/sync-keycloak-client-secret.sh
```

```powershell
# Windows PowerShell (sem dependências externas):
./scripts/sync-keycloak-client-secret.ps1
```

O script usa a admin REST API do Keycloak para sobrescrever o secret do
client `penguard-bff` com o que está no `.env`. Sem ele, BFF e
Keycloak ficam com secrets diferentes e qualquer chamada que toque o
provider (login, register, callback SSO) falha com `invalid_client`
(502 Bad Gateway na cockpit).

## Subir em produção (TLS + reverse proxy)

Para deploy real (cliente final), use o overlay `docker-compose.prod.yml`
junto com o compose base. Ele adiciona um Caddy na frente fazendo TLS,
flipa o cookie de sessão para `Secure=true` e aponta as URLs do Keycloak
para o hostname público:

```bash
# 1. Garanta que o .env já foi gerado pelo bootstrap-secrets
# 2. Defina o hostname público
export PENGUARD_PUBLIC_HOSTNAME=forti.example.com
export CADDY_TLS_MODE=        # vazio = ACME / Let's Encrypt
export CADDY_ADMIN_EMAIL=ops@example.com

docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Defaults (CADDY_TLS_MODE=internal) emitem cert self-signed via a CA interna
do Caddy — bom para lab on-prem sem domínio público. Para internet, deixe
`CADDY_TLS_MODE` vazio e aponte o DNS A do hostname para o host Docker.

Rotas atrás do Caddy:

- `https://<host>/`         → cockpit Vue
- `https://<host>/api/*`    → BFF FastAPI
- `https://<host>/auth/*`   → Keycloak

Antes da primeira release real, leia `docs/maturity-analysis.md` —
existem itens de observabilidade, rate-limit e onboarding que ainda estão
em Sprint 2 e 3 do roadmap.

## IA real (Gemini / Anthropic / OpenAI-compat)

A cockpit suporta provider de IA real para o chat do sidebar e os botões
"Analisar" / "Sugerir contenção" no ticket drawer. Default é `scripted`
(offline, determinístico). Pra ligar Gemini ou Claude, edita `.env`:

```env
# Gemini (free tier no AI Studio, key: https://aistudio.google.com/apikey)
PENGUARD_AI_PROVIDER=openai_compat
PENGUARD_AI_API_KEY=AIza...
PENGUARD_AI_MODEL=gemini-2.5-flash
PENGUARD_AI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
```

```env
# Anthropic Claude (key: https://console.anthropic.com)
PENGUARD_AI_PROVIDER=anthropic
PENGUARD_AI_API_KEY=sk-ant-...
PENGUARD_AI_MODEL=claude-haiku-4-5-20251001
```

Depois:

```powershell
docker compose up -d --build api
# valida que o container leu as vars novas:
curl http://localhost:8000/api/ai/status
```

`/api/ai/status` retorna `{"provider":"openai","model":"gemini-2.5-flash","ready":true}`.
Na cockpit, abre o sidebar "Assistente IA" — o pill no topo do chat
mostra `<provider> · <model>` em verde quando o backend está ligado.

⚠️ Pegadinhas observadas:

- **Gemini exige o sufixo `/v1beta/openai`** no `PENGUARD_AI_BASE_URL`.
  Sem ele o endpoint vira 404 e o Google retorna 400 "API key not valid"
  como red herring.
- **Claude Pro (claude.ai) ≠ API**. Assinatura UI não dá acesso à API.
  Precisa criar key paga em `console.anthropic.com`.
- **Gemini Pro (gemini.google.com) ≠ API**. Mesmo modelo: free tier do
  AI Studio (60 req/min) é separado da assinatura UI.

## Estrutura do Monorepo

- `apps/api`: backend FastAPI com healthcheck, BFF auth, sessões server-side persistidas e modo mock opt-in para contratos.
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

O Docker Compose sobe em modo live por padrão. Para usar fixtures mockadas de frontend de forma explícita:

```bash
PENGUARD_MOCK_MODE=true docker compose up -d --build api
```

A API aplica migrations Alembic no startup do container para desenvolvimento local.

As portas podem ser trocadas sem editar o compose, útil quando outro serviço já usa a porta no Windows ou Linux:

```bash
PENGUARD_WEB_PORT=5174 PENGUARD_API_PORT=8001 docker compose up --build
```

O serviço `web` usa uma imagem própria com `pnpm` pinado e mantém `node_modules` em volumes Docker para evitar diferenças entre filesystem Linux e Windows.

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

O frontend pode usar fixtures de `packages/contracts/fixtures` quando `PENGUARD_MOCK_MODE=true`, mas o default local valida Keycloak, sessão e conexão FortiGate reais.

Widgets FortiGate em modo live são atualizados automaticamente pelo intervalo retornado em `meta.refreshIntervalSeconds`; métricas voláteis de sistema, sessões e rede usam polling curto de 2s.

## Autenticação

O Vue implementa as telas próprias de login/register, mas chama FastAPI em vez de falar direto com Keycloak:

- `GET /api/auth/csrf`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/logout`

Para `register`, `login` e `logout`, chame `GET /api/auth/csrf` primeiro e envie o valor em `X-CSRF-Token`. A sessão do browser usa cookie `penguard_session` com `HttpOnly`; tokens Keycloak ficam server-side e são persistidos em Postgres como `token_blob` criptografado.

No frontend, use `apps/web/src/services/authClient.ts` para o fluxo completo. Ele busca CSRF com cookie, faz uma nova tentativa quando o CSRF expira, chama `login/register/logout` com `credentials: include` e confirma `login/register` com `GET /api/auth/me`.

Em modo live, o realm dev dá ao service account `penguard-bff` permissão `manage-users`/`view-users` para criar usuários via BFF. Se você já tinha subido Keycloak antes dessa configuração, recrie os volumes para reimportar o realm:

```bash
docker compose down -v
docker compose up --build
```

## Contratos

Mudanças de payload devem atualizar:

- Pydantic models/endpoints em `apps/api`.
- Fixtures em `packages/contracts/fixtures`.
- Notas em `AGENTS.md` e `docs/api/README.md`.
- Consumidores em `apps/web`, quando aplicável.
