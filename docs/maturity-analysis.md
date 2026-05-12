# Análise de Maturidade — MVP → Produto Real

> Snapshot em 2026-05-12 da postura do FortiDashboard frente ao que um cliente
> real precisaria para rodar em produção. Tudo aqui está aterrissado em
> arquivos existentes do repo; nenhuma sugestão sem evidência.

## Sumário executivo

O fluxo MVP demo funciona ponta a ponta (replay → incidente → IA → ticket →
playbook → contido). Antes de qualquer cliente externo rodar a aplicação,
três grupos de problemas precisam fechar:

| Grupo                       | Status atual                                       | Risco se não fechar                                              |
|----------------------------|----------------------------------------------------|------------------------------------------------------------------|
| 🔴 Bloqueadores de produção | Secrets default, SOAR in-memory, sem HTTPS, sem CI | Vazamento de credenciais, perda de histórico em restart, MITM    |
| 🟡 Maturidade técnica       | Tenant frouxo, AI sem cap, sem observabilidade     | Custo de IA descontrolado, debugging impossível em incidente real|
| 🟢 Polish                   | Onboarding zero, empty states crus, i18n parcial   | Primeira impressão ruim, churn precoce                           |

---

## 1. Bloqueadores reais (impedem rollout)

### 1.1 Secrets default em arquivos versionados

Onde mora hoje:

- `infra/keycloak/realm-fortidashboard.json:28` → `"secret": "dev-client-secret"`
- `infra/keycloak/realm-fortidashboard.json:80` → senha `correct-horse-battery-staple`
  para `analyst@example.com` e `admin@example.com`.
- `docker-compose.yml:159-160` → `KC_BOOTSTRAP_ADMIN_USERNAME/PASSWORD: admin/admin`.
- `.env.example:16` → `FORTIDASHBOARD_SECRET_KEY=change-me-in-local-env`.
- `.env.example:17` → `FORTIDASHBOARD_TOKEN_ENCRYPTION_KEY=` (vazio).

Por que isso é bloqueador: qualquer auditoria estática (gitleaks, trivy,
revisor humano de cliente) marca como `critical`. O fato de o Keycloak realm
import estar versionado com `"secret": "dev-client-secret"` significa que o
client secret é público no GitHub.

Ação proposta:

- Script de bootstrap (`scripts/bootstrap-secrets.sh`) que, no primeiro `up`,
  gera valores aleatórios e grava em `.env.local` (gitignored).
- `apps/api/app/core/config.py` recusa subir quando qualquer secret em uso
  bate com a constante default (`change-me-in-local-env`, `dev-client-secret`,
  string vazia).
- `gitleaks` no CI bloqueia PR.

### 1.2 SOAR perde estado em restart

`apps/soar_skipper/app/main.py:179-180`:

```python
playbooks: dict[str, Playbook] = _default_playbooks()
playbook_runs: dict[str, PlaybookRun] = {}
```

Qualquer `docker compose restart soar-skipper` apaga todo histórico de
playbooks customizados, runs dry-run e estado de aprovação. Para um SOC
real, isso significa perder rastreabilidade de contenção, o que invalida
auditoria.

Ação proposta: copiar o padrão SQL já usado em `siem_kowalski` e `xdr_rico`
(ambos têm `store.py` com SQLAlchemy). Adicionar Alembic migration nova com
`playbooks` e `playbook_runs`.

### 1.3 Sem HTTPS e cookie inseguro

- `docker-compose.yml:12` → `FORTIDASHBOARD_SESSION_COOKIE_SECURE: "false"`.
- Sem reverse-proxy TLS no compose. Tudo trafega em `http://...`.

Em rede de cliente, a sessão HTTP-only ainda vaza no clear. Não atende
LGPD/GDPR mesmo para uso interno.

Ação proposta:

- Adicionar service `traefik` (ou `caddy`) ao `docker-compose.prod.yml`
  com TLS automático via Let's Encrypt para deploys públicos, ou cert
  mTLS interno para deploys on-prem.
- Flip `FORTIDASHBOARD_SESSION_COOKIE_SECURE=true` no prod override e
  trocar nome do cookie para `__Host-fortidashboard_session`.

### 1.4 Sem CI

`.github/workflows/` não existe no repo (`ls .github/workflows` → not found).
Quem comita não tem garantia de que `pytest`, `vue-tsc`, `ruff` ou
`test_mvp_demo_chain.py` ainda passam. A regressão é silenciosa até alguém
tentar dar deploy.

Ação proposta: workflow GitHub Actions mínimo:

```yaml
# .github/workflows/ci.yml (esboço)
on: [push, pull_request]
jobs:
  api:
    steps:
      - uv sync && uv run pytest && uv run ruff check
  web:
    steps:
      - pnpm install && pnpm test && pnpm exec vue-tsc --noEmit
  smoke:
    steps:
      - pnpm/uv run apps/api/tests/test_mvp_demo_chain.py
```

---

## 2. Maturidade técnica (habilita escala)

### 2.1 Multi-tenancy frouxo

Workspaces são por usuário (FK `user_id`). Mas as lite services
(`siem_kowalski`, `xdr_rico`, `soar_skipper`) não têm coluna `tenant_id`:
incidentes e endpoints de um cliente apareceriam para outro se a instância
fosse compartilhada.

**Decisão tomada em 2026-05-12: single-tenant per deploy.** README e
onboarding devem deixar isso explícito. PRs que tentem introduzir
fan-out cross-tenant devem reabrir essa decisão antes de qualquer código.

Histórico das opções avaliadas (mantido como contexto):

- **Opção A — single-tenant per deploy (escolhida):** cada cliente roda
  sua stack via docker compose. Documenta como tal. Não exige código novo.
- **Opção B — multi-tenant real:** adiciona `tenant_id` em todas as
  tabelas SOC, RLS no Postgres ou filtro em todas as queries. Sprint
  inteira de trabalho.

### 2.2 Ingestão FortiGate manual

`POST /api/soc/fortigate/{id}/ingest-events` precisa ser chamado à mão. O
stack já tem Redis (`docker-compose.yml`) e a documentação cita Dramatiq
como dep oficial (`AGENTS.md:83`). Falta wiring.

Ação proposta: worker Dramatiq que faz `poll` a cada N segundos por
integração e chama o helper `_aggregate_fortigate_events()` que já existe.

### 2.3 AI sem cap de orçamento

`apps/api/app/ai/provider.py` chama Anthropic/OpenAI sem `max_tokens` por
sessão. Um bug de loop ou prompt injection numa descrição de incidente
pode gerar centenas de chamadas. Cliente acorda com US$1k de fatura.

Ação proposta:

- `Settings.ai_daily_token_budget: int = 100_000`.
- Tabela `ai_usage` com agregação por usuário/dia.
- Recusa chamada com 429 quando estoura.
- Audit log de prompt + tokens (já existe parcialmente — falta tokens).

### 2.4 Sem observabilidade

- Logs são `logger.info("soar_playbooks_list returned=%s", len(results))`
  — formato livre, sem `requestId`/`incidentId` correlation.
- Sem `/metrics` Prometheus.
- `/health` retorna `{"status": "ok"}` sem checar dependências
  (Postgres, Redis, Keycloak, SOC-lite).

Quando der ruim em produção, ninguém vai conseguir correlacionar logs do
BFF com logs do SOAR/SIEM.

Ação proposta:

- Middleware FastAPI que injeta `X-Request-ID` no log context.
- `prometheus-fastapi-instrumentator` (lib pequena, dep estável).
- `/health/ready` faz ping em Postgres/Redis/Keycloak; `/health/live`
  responde sempre 200.

### 2.5 Sem backup/restore

Não existe runbook para restaurar Postgres/Redis. Cockpit faz export de
manifest, mas não há doc dizendo "para restaurar tudo, faça X".

---

## 3. Polish (afeta percepção)

### 3.1 Onboarding zero

Primeiro login cai num dashboard vazio. Sem walkthrough, sem CTA "conecte
seu FortiGate". Operador novo fica perdido.

Ação: tour passo-a-passo (Vue componente simples) que detecta
"zero integrações" e mostra wizard.

### 3.2 Empty/error/loading states pobres

Item já tracked em `AGENTS.md → Frontend Cockpit backlog`. Promove para
MVP-blocker — é primeira impressão.

### 3.3 Aba Integrações sem i18n

Tudo no cockpit foi traduzido (commit `e555d4f`) exceto a aba
Integrações em `Sidebar.vue` — restam strings hard-coded misturadas em PT
e EN. Item já no backlog.

### 3.4 Sem changelog / release notes

Cliente não saberá o que mudou entre versões. Adicionar
`CHANGELOG.md` seguindo Keep a Changelog antes de qualquer release tag.

---

## 4. Roadmap proposto — próximas 3 sprints

| Sprint | Tema                       | Itens                                                                                                       |
|--------|----------------------------|-------------------------------------------------------------------------------------------------------------|
| **1**  | Não-vergonha-em-prod       | Secrets bootstrap script · SOAR migrado para SQL · TLS reverse-proxy + cookie secure · `docker-compose.prod.yml` |
| **2**  | CI + observabilidade       | GitHub Actions (lint+test+smoke) · structured JSON logging · Prometheus `/metrics` · `/health/ready` separado · rate-limit em SSO/AI/replay |
| **3**  | Telemetria real + UX       | Auto-ingest FortiGate via Dramatiq · onboarding wizard · empty states ricos · i18n integrações · AI token budget · Playwright golden path |

## 5. Métricas para "MVP pronto para cliente"

A aplicação pode ser oferecida para um cliente real quando:

- `git ls-files | xargs gitleaks detect` retorna zero achados.
- Todos os secrets vêm de `.env.local` (gerado) ou `vault`.
- `docker compose restart soar-skipper` mantém playbooks e runs.
- `docker compose -f docker-compose.prod.yml up` sobe com TLS válido.
- GitHub Actions verde no `main` para `pytest`, `vue-tsc`, `pnpm test` e
  `test_mvp_demo_chain.py`.
- `/metrics` expõe contadores de incidentes, requests e AI calls.
- Auto-ingest FortiGate cria incidentes sem chamada manual.
- Tela vazia tem CTA acionável; primeiro login dispara onboarding.
- `CHANGELOG.md` documenta a release tag.

## 6. O que **já está pronto** (para não reinventar)

Para evitar refazer trabalho — checklist do que o repo já tem hoje:

- ✅ Keycloak BFF + sessions + CSRF + RBAC (`apps/api/app/auth/`).
- ✅ Kerberos SSO documentado em `configSSOKerberosKeycloak.md`.
- ✅ Detecções declarativas no `siem_kowalski`.
- ✅ Playbooks SOAR com state machine e gate de aprovação.
- ✅ XDR endpoint enrollment, heartbeat, timeline e correlação com SIEM.
- ✅ AI provider abstraction (Anthropic / OpenAI-compatible / scripted).
- ✅ Cockpit Vue 3 com Pinia, workspaces, tickets, audit, presentation.
- ✅ i18n pt-BR/en-US cobrindo 95% da cockpit.
- ✅ MVP demo replay com picker de ataques individuais.
- ✅ Smoke test ponta a ponta (`test_mvp_demo_chain.py`).
- ✅ Alembic migrations para BFF (`apps/api/migrations/versions/`).
- ✅ Docker Compose dev funcional.

Não comece nada que esteja nessa lista sem antes verificar o código atual.
