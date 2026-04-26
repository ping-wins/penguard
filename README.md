# FortiDashboard

FortiDashboard é um dashboard modular para NG-SOC, focado em centralizar visibilidade de rede e inteligência de ameaças. O primeiro alvo de integração é FortiGate via REST API.

## Estrutura do Monorepo

- `apps/api`: Backend FastAPI (Em breve)
- `apps/web`: Frontend Vue 3 + Vite
- `packages/contracts`: Fixtures e schemas compartilhados
- `packages/widget-catalog`: Registro neutro de widgets

## Comandos

- `docker compose up -d db`: sobe Postgres local.
- `cd apps/web && pnpm install`: instala dependências frontend.
- `cd apps/web && pnpm dev`: roda o frontend Vite.

Veja `AGENTS.md` para mais detalhes de arquitetura.
