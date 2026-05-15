# Análise de Maturidade — MVP → Produto Real

> Historical analysis. For the current source of truth, use
> `docs/product/feature-map.md`, `docs/product/roadmap.md`,
> `docs/product/timeline.md` and `docs/product/release-notes.md`.
> This file is kept as rationale/context and may mention older MVP framing.

> Snapshot em 2026-05-13 da postura do FortiDashboard frente ao que um cliente
> real precisaria para rodar em produção. Tudo aqui está aterrissado em
> arquivos existentes do repo; nenhuma sugestão sem evidência.
>
> **Atualização 2026-05-13:** Sprint 1 fechada. Antes de partir pra Sprint 2
> (CI / observabilidade) o foco pivotou para **validação de telemetria
> real** — sair do `/demo/replay` e fazer um port scan / brute force / etc
> de verdade aparecer no cockpit. Roadmap reordenado na §4.

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

## 4. Roadmap proposto — reordenado em 2026-05-13

A ordem original (CI → observabilidade → telemetria real) faz sentido pra
ship pra cliente externo. Como ainda não existe cliente externo e a stack
ainda só foi exercitada via `/demo/replay`, vale **antecipar a Sprint de
telemetria real** — porque sem ela, nem dá pra demonstrar a tese central
do produto ("FortiGate → SIEM → IA → contenção").

| Sprint | Tema                          | Status         | Itens                                                                                                                  |
|--------|-------------------------------|----------------|------------------------------------------------------------------------------------------------------------------------|
| **1**  | Não-vergonha-em-prod          | ✅ entregue    | Secrets bootstrap · SOAR SQL · TLS reverse-proxy + cookie secure · `docker-compose.prod.yml`                            |
| **1.5** | Quality-of-life entregue     | ✅ entregue    | Real chat Gemini/Anthropic · CVSS+MITRE na análise · Rename workspace · Resize panels · Cross-platform fixes            |
| **2**  | **Validação de telemetria real (NOVA)** | 🔴 next | Lab setup que captura port scan REAL · Auto-ingest FortiGate (Dramatiq) · agent_private rodando + reportando · Runbook de "primeiro scan" com screenshots · UX dos states vazios da SOC-lite (mostra "aguardando primeiro evento" em vez de gráfico zerado) |
| **3**  | CI + observabilidade          | ⏸ adiada       | GitHub Actions · structured JSON logging · Prometheus `/metrics` · `/health/ready` separado · rate-limit SSO/AI/replay  |
| **4**  | Polish pré-cliente            | ⏸             | Onboarding wizard · i18n aba Integrações · AI token budget · Playwright golden path · CHANGELOG                         |

### Sprint 2 detalhada — Validação de telemetria real

Objetivo concreto: gravar um vídeo (ou demonstrar ao vivo) onde:

1. Um nmap rodando de uma VM Kali bate no FortiGate (WAN).
2. Em 5-10 minutos, o cockpit pisca incidente `denied_traffic_burst`.
3. A IA analisa, sugere CVSS + MITRE, e o analista contém via playbook.

Sem `/demo/replay` envolvido. O que precisa fechar para chegar lá:

#### 2.1 Topologia de lab que realmente trafega via FortiGate

Bloqueador documentado em `AGENTS.md → Known Lab Setup Issues`:

- Bridge-mode VMs no mesmo /24 da management interface ficam no L2 →
  FortiGate nunca roteia → Forward Traffic vazio.
- Policy precisa ter `set logtraffic all`.
- VMware NAT põe o FortiGate WAN atrás do host.

Entregável: um doc novo `docs/lab/real-scan-setup.md` com:

- Diagrama da topologia que **funciona** (port1 vmnet8 NAT, port2 LAN
  segregada com guest Linux, Kali no NAT como atacante "externo").
- Comandos `config firewall policy` exatos (incluindo `set logtraffic all`).
- Comando nmap esperado (ex: `nmap -p- -sS -T4 <forti-wan-ip>`).
- Print do log `Forward Traffic` populado.

#### 2.2 Auto-ingest FortiGate via Dramatiq

Hoje `POST /api/soc/fortigate/{id}/ingest-events` precisa ser chamado
manualmente. Stack já tem Redis (compose) e `tenacity` para retry.

Entregável: worker que, para cada integração FortiGate conectada, faz poll
a cada N segundos (default 60s, configurável) e empurra eventos
agregados para o SIEM. Tabela `fortigate_ingest_state(integration_id,
last_seen_at)` evita reprocessar. Job tolerante a falha de rede com backoff.

Pipeline:

```
[FortiGate REST /api/v2/log/...] ──poll a cada 60s─→ [Dramatiq worker BFF]
   └─→ _aggregate_fortigate_events() ──→ [siem_kowalski POST /events]
                                              └─→ regra denied_traffic_burst → incidente
```

UX: na aba Integrações, badge "última ingestão há 12s · 47 eventos" por
integração.

#### 2.3 agent_private end-to-end na VM Windows

Bloqueador também na lista de Known Lab Setup Issues: existe TUI/CLI mas
nunca foi exercitado contra o `xdr_rico` real em uma VM.

Entregável:

- Tutorial em `docs/lab/agent-private-windows.md`: como enrolar,
  como o heartbeat aparece no widget Endpoints.
- Smoke: rodar nmap **na própria workstation** Windows; agent_private
  detecta processo `nmap.exe` + conexão saindo; `xdr_rico` correlaciona
  com o evento do FortiGate via sourceIp; cockpit mostra os dois lados
  do mesmo incidente.

#### 2.4 Empty/error/loading states da SOC-lite

Hoje quando não tem evento, os widgets renderizam "0" ou ficam vazios —
parece bug. Antes de gravar o vídeo, cada widget SOC-lite (incidents,
endpoints, playbook runs, audit trail) precisa de:

- Estado vazio explicando *por que* está vazio ("aguardando primeiro
  evento de FortiGate" / "agent_private não conectado").
- Loading skeleton com motion suave.
- Error state com CTA de retry e link pra docs.

Item já no AGENTS.md backlog Frontend Cockpit — promovido a MVP-blocker
visual nesta sprint.

#### 2.5 Runbook do "primeiro scan"

Arquivo novo `docs/lab/first-real-scan-walkthrough.md` com checklist
passo-a-passo:

1. Pré-requisitos (compose up, FortiGate conectada, agent_private
   instalado).
2. Comando nmap do Kali.
3. Onde olhar no cockpit (sidebar Tickets → lane T1 deve piscar).
4. Tempo esperado entre scan e incidente (esperar 60-120s pelo poll).
5. Troubleshooting (Forward Traffic vazio? policy? logtraffic?).

## 5. Métricas para "MVP pronto para cliente"

A aplicação pode ser oferecida para um cliente real quando:

- **`docs/lab/first-real-scan-walkthrough.md` foi executado com sucesso por
  alguém que não escreveu o código** (esse é o teste-mor).
- Todos os secrets vêm de `.env` gerado pelo bootstrap.
- `docker compose restart soar-skipper` mantém playbooks e runs.
- `docker compose -f docker-compose.prod.yml up` sobe com TLS válido.
- Auto-ingest FortiGate cria incidentes sem chamada manual.
- Widgets vazios mostram "aguardando dados" em vez de zeros.
- (Sprint 3+) GitHub Actions verde no `main`.
- (Sprint 3+) `/metrics` expõe contadores de incidentes, requests e AI calls.
- (Sprint 4+) Tela vazia tem CTA acionável; primeiro login dispara onboarding.
- (Sprint 4+) `CHANGELOG.md` documenta a release tag.

## 6. O que **já está pronto** (para não reinventar)

Para evitar refazer trabalho — checklist do que o repo já tem hoje:

- ✅ Keycloak BFF + sessions + CSRF + RBAC (`apps/api/app/auth/`).
- ✅ Kerberos SSO documentado em `configSSOKerberosKeycloak.md`.
- ✅ Detecções declarativas no `siem_kowalski` (port_scan, denied_traffic_burst,
  brute_force, suspicious_connection, high_severity_event).
- ✅ Playbooks SOAR com state machine, gate de aprovação e SQL persistence.
- ✅ XDR endpoint enrollment, heartbeat, timeline e correlação com SIEM.
- ✅ AI provider abstraction (Anthropic / OpenAI-compatible / scripted) +
  chat real funcionando contra Gemini OpenAI-compat e Anthropic.
- ✅ CVSS v3.1 + MITRE ATT&CK no output da análise de incidente.
- ✅ Cockpit Vue 3 com Pinia, workspaces (renomeáveis), tickets, audit,
  presentation, painéis redimensionáveis, minimap colapsável.
- ✅ i18n pt-BR/en-US cobrindo 95% da cockpit.
- ✅ MVP demo replay com picker de ataques individuais.
- ✅ Smoke test ponta a ponta (`test_mvp_demo_chain.py`).
- ✅ Alembic migrations para BFF (`apps/api/migrations/versions/`).
- ✅ Docker Compose dev + `docker-compose.prod.yml` overlay com Caddy.
- ✅ Bootstrap de secrets (`scripts/bootstrap-secrets.{sh,ps1}`) e
  sync de Keycloak client secret (`scripts/sync-keycloak-client-secret.{sh,ps1}`).
- ✅ Boot guard recusa subir com secrets default
  (`apps/api/app/core/config.py:DANGEROUS_DEFAULT_SECRETS`).
- ✅ Decisão arquitetural: single-tenant per deploy (sem `tenant_id`).
- ✅ Cross-Platform Compatibility (non-negotiable) policy em `AGENTS.md`.
- ✅ Aggregator `_aggregate_fortigate_events()` no router de integrações
  (pronto para reuso no auto-ingest da Sprint 2).

Não comece nada que esteja nessa lista sem antes verificar o código atual.
