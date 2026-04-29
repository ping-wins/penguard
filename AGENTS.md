# Repository Guidelines

## Produto: FortiDashboard

FortiDashboard é um dashboard modular para NG-SOC, focado em centralizar visibilidade de rede e inteligência de ameaças. O primeiro alvo de integração é FortiGate via REST API. A arquitetura deve permitir adicionar outras soluções Fortinet depois sem reescrever o produto.

A experiência principal é uma workspace livre, estilo Power BI/Photoshop: o analista conecta integrações, consulta um catálogo de widgets e posiciona cartões de monitoramento no canvas. O frontend também terá um fluxo de chat/IA para instanciar widgets por linguagem natural, sem substituir a workspace inteira.

## Feedback de Produto - Cristiano (2026-04-26)

Feedback incorporado como requisito de produto, segurança e UX:

- O modo "as a service" precisa provar titularidade de domínio. Para qualquer fluxo de claim de domínio, tenant, branding ou confiança por domínio, exigir desafio DNS TXT antes da ativação. Sem isso, o produto pode ser confundido com ferramenta de phishing.
- O dashboard precisa ser mais rico que um conector plug and play. A experiência deve priorizar widgets úteis para SOC: postura de risco, anomalias, eventos recentes, health do FortiGate, políticas, interfaces e trilhas de investigação.
- Plug and play não pode ampliar dano em ataque supply-chain. Integrações devem usar credenciais de menor privilégio, inicialmente read-only, com escopo por tenant/workspace e sem ações destrutivas no primeiro corte.
- Insider ou conta comprometida dentro do SOC deve deixar rastros. Toda ação sensível precisa gerar audit log: login, falha de login, criação/remoção de integração, troca de API key, alteração de workspace, export e ação administrativa.
- SSO, IdP, LDAP e federação entram como evolução natural via Keycloak depois que o BFF FastAPI com sessão HTTP-only estiver estável.
- O design precisa parecer um produto SOC enterprise pronto para cliente. Lucas deve priorizar polimento visual, estados vazios/loading/erro, hierarquia de informação e clareza operacional.

Perguntas abertas para refinamento, sem bloquear o desenvolvimento atual:

- O primeiro deploy será single-tenant local, multi-tenant SaaS ou ambos?
- Qual retenção mínima de audit logs será exigida no PoC?
- A integração FortiGate inicial será estritamente read-only no FortiGate API user?

## Responsabilidades

- Felipe/backend agent: backend FastAPI, dados, contratos de API, persistência, segurança de credenciais e integração FortiGate.
- Lucas/frontend UX: experiência visual, canvas livre, drag-and-drop, catálogo, chat e widgets Vue.
- Gemini/Antigravity do Lucas: seguir a stack e as regras de branch deste arquivo antes de alterar `apps/web`.
- Contratos compartilhados ficam em `packages/contracts`; mudanças de payload devem ser combinadas antes de alterar frontend ou backend.
- Nunca hardcode host, API key, IP de laboratório ou token FortiGate no código, docs ou fixtures públicas.

## Scaffolding do Monorepo

Estrutura-alvo:

```txt
apps/
  api/                 # FastAPI: integrações, widgets, workspaces e dados normalizados
  web/                 # Vue 3 + Vite: dashboard, canvas, catálogo, chat e widgets
packages/
  contracts/           # OpenAPI/JSON schemas e clientes gerados para o frontend
  widget-catalog/      # Registro neutro de widgets, tamanhos, capabilities e mappers
docs/
  api/                 # Payloads, decisões de contrato e exemplos de integração
```

Backend: Python 3.12+, FastAPI, Pydantic, SQLAlchemy, Alembic, Postgres e Docker Compose. Frontend: Vue 3 com Vite, Composition API com `<script setup>`, Pinia, Tailwind CSS, Motion for Vue, Lucide Vue e gráficos com Chart.js ou ECharts após decisão do Lucas.

## Autenticação e Sessão

Keycloak será o provider de identidade, mas o usuário não deve interagir com telas hospedadas pelo Keycloak. O Lucas implementa páginas Vue próprias de `login` e `register`; essas páginas chamam a API FastAPI. A API executa a autenticação contra o Keycloak e cria uma sessão contextualizada do browser.

Modelo obrigatório:

- FastAPI atua como BFF/auth gateway.
- Vue nunca recebe `access_token`, `refresh_token`, client secret ou senha persistida.
- Sessão do browser deve ser cookie `HttpOnly`, `Secure` em produção e `SameSite=Lax` ou mais restritivo.
- Tokens Keycloak, quando necessários, ficam server-side em store de sessão ou registro criptografado.
- Endpoints protegidos usam a sessão da API, não validação JWT feita no browser.
- A API deve aplicar CSRF para métodos mutáveis, rate limit em login/register e auditoria de tentativas.
- Sessões live usam Postgres na tabela `auth_sessions`; `token_blob` deve ser criptografado, `expires_at` deve invalidar sessões vencidas e tokens nunca podem aparecer em texto claro.
- Frontend deve usar `apps/web/src/services/authClient.ts` para `login`, `register`, `logout`, CSRF e `/auth/me`. Não duplique chamadas auth direto em views.
- Frontend deve chamar `GET /api/auth/csrf` com `credentials: "include"` antes de `login`, `register` ou `logout` e enviar o valor em `X-CSRF-Token`.
- Se `login/register/logout` retornar `403` com falha de CSRF, o client pode buscar novo CSRF e tentar novamente uma única vez.
- Depois de `login` ou `register`, o frontend deve confirmar a sessão com `GET /api/auth/me`; o estado autenticado vem da sessão HTTP-only, não só do response inicial.
- API deve normalizar erros de provider em JSON estável: `401 Invalid email or password`, `409 Email already registered`, `429 Too many authentication attempts`, `502 Identity provider rejected FortiDashboard service account` e `503 Identity provider unavailable`.
- No register live, o BFF deve criar o usuário Keycloak com perfil completo para login imediato: `emailVerified: true`, `requiredActions: []`, `firstName` e `lastName` derivados de `displayName`.

Fluxo esperado:

```txt
Vue login/register -> FastAPI /api/auth/*
FastAPI -> Keycloak Admin API ou token endpoint
FastAPI -> cria/atualiza sessão server-side
FastAPI -> Set-Cookie HttpOnly
Vue -> chama /api/auth/me e demais endpoints usando cookie
```

Observação de segurança: formulário próprio com Keycloak costuma exigir Direct Access Grant/Resource Owner Password Credentials no backend. A documentação atual do Keycloak alerta que esse fluxo não é recomendado para OAuth moderno porque a aplicação passa a lidar com credenciais do usuário. Para este produto, se mantivermos UX própria, essa escolha deve ficar confinada ao BFF FastAPI; se MFA, social login, required actions ou identity brokering virarem requisito, reavaliar Authorization Code Flow com tema customizado do Keycloak.

## Comandos Esperados

Atualize após o scaffold real existir:

- `docker compose up -d db`: sobe Postgres local.
- `docker compose up --build`: sobe API, frontend Vue, Postgres e Keycloak.
- `docker compose up -d --build api`: sobe API, Postgres e Keycloak em modo live por padrão.
- `FORTIDASHBOARD_MOCK_MODE=true docker compose up -d --build api`: sobe API com fixtures mockadas para desenvolvimento isolado do frontend.
- Portas locais podem ser sobrescritas com `FORTIDASHBOARD_API_PORT`, `FORTIDASHBOARD_WEB_PORT`, `FORTIDASHBOARD_KEYCLOAK_PORT` e `FORTIDASHBOARD_POSTGRES_PORT`.
- `cd apps/api && uv sync`: instala dependências Python.
- `cd apps/api && uv run uvicorn app.main:app --reload --port 8000`: roda a API.
- `cd apps/api && uv run pytest`: executa testes backend.
- `cd apps/api && uv run ruff check .`: roda lint backend.
- `cd apps/api && uv run alembic upgrade head`: aplica migrations.
- `cd apps/web && pnpm install`: instala dependências frontend.
- `cd apps/web && pnpm dev`: roda o frontend Vite.
- `cd apps/web && pnpm smoke:canvas`: valida o contrato mínimo de renderização do canvas.
- `cd apps/web && pnpm test`: executa testes frontend quando existirem.

Nota Docker: o serviço `web` usa `apps/web/Dockerfile` com `pnpm` pinado e volumes próprios para `node_modules`/store. Não monte `node_modules` do host no container; isso precisa continuar portátil entre Linux e Windows.

Nota Keycloak: mudanças em `infra/keycloak/realm-fortidashboard.json` só entram em um realm novo. Em ambiente dev com volume antigo, rode `docker compose down -v` antes de validar alteração de realm/service-account.

## Contratos e Mockups de Endpoints

### CSRF para formulários Vue

`GET /api/auth/csrf`

Response:

```json
{
  "csrfToken": "csrf_token_for_x_csrf_token_header"
}
```

A resposta define o cookie `fortidashboard_csrf` sem `HttpOnly`. Envie o mesmo valor no header `X-CSRF-Token` em todo método mutável (`POST`, `PUT`, `PATCH`, `DELETE`), incluindo auth, integrações e workspace. Falha de CSRF retorna `403`; excesso de tentativas de auth retorna `429`.

### Registrar usuário

`POST /api/auth/register`

Request:

```json
{
  "email": "analyst@example.com",
  "password": "correct-horse-battery-staple",
  "displayName": "SOC Analyst"
}
```

Response:

```json
{
  "user": {
    "id": "usr_01",
    "email": "analyst@example.com",
    "displayName": "SOC Analyst",
    "roles": ["analyst"]
  },
  "session": {
    "authenticated": true,
    "expiresAt": "2026-04-26T22:30:00.000Z"
  }
}
```

Não retornar tokens Keycloak. A resposta deve vir acompanhada de `Set-Cookie`.

### Login

`POST /api/auth/login`

Request:

```json
{
  "email": "analyst@example.com",
  "password": "correct-horse-battery-staple"
}
```

Response:

```json
{
  "user": {
    "id": "usr_01",
    "email": "analyst@example.com",
    "displayName": "SOC Analyst",
    "roles": ["analyst"]
  },
  "session": {
    "authenticated": true,
    "expiresAt": "2026-04-26T22:30:00.000Z"
  }
}
```

### Sessão atual

`GET /api/auth/me`

Response:

```json
{
  "authenticated": true,
  "user": {
    "id": "usr_01",
    "email": "analyst@example.com",
    "displayName": "SOC Analyst",
    "roles": ["analyst"]
  }
}
```

### Logout

`POST /api/auth/logout`

Response:

```json
{
  "authenticated": false
}
```

### Criar integração FortiGate

`POST /api/integrations/fortigate`

Request:

```json
{
  "name": "FortiGate Lab",
  "host": "https://fortigate.local",
  "apiKey": "fg_api_key_from_user",
  "verifyTls": false
}
```

Response:

```json
{
  "id": "int_fgt_01",
  "type": "fortigate",
  "name": "FortiGate Lab",
  "status": "connected",
  "capabilities": ["system", "interfaces", "policies", "threat_logs"],
  "lastCheckedAt": "2026-04-26T20:30:00.000Z"
}
```

API keys devem ser criptografadas em repouso e nunca retornadas.

O default do repositório é `FORTIDASHBOARD_MOCK_MODE=false`. Em modo live, a integração é persistida em Postgres na tabela `fortigate_integrations`, com `api_key_blob` criptografado. Use `FORTIDASHBOARD_MOCK_MODE=true` apenas de forma explícita para fixtures de frontend.

Em modo live, a integração pertence ao usuário autenticado pela sessão HTTP-only. A tabela `fortigate_integrations.owner_user_id` guarda o dono, e `GET /api/integrations` só lista integrações do usuário atual.

Antes de persistir em modo live, `POST /api/integrations/fortigate` executa um probe read-only. Falha de conexão retorna `400` e grava audit event `integration.fortigate.created` com `outcome: "failed"` sem persistir a API key.

### Testar conexão FortiGate

`POST /api/integrations/fortigate/test`

Request:

```json
{
  "host": "https://fortigate.local",
  "apiKey": "fg_api_key_from_user",
  "verifyTls": false
}
```

Response:

```json
{
  "ok": true,
  "status": "connected",
  "device": {
    "hostname": "FGT-VM",
    "model": "FortiGate-VM64",
    "version": "v7.4.x"
  }
}
```

Falhas controladas podem retornar HTTP 200 com `ok: false`, `status: "disconnected"` e `error.message`; o frontend deve tratar isso como falha, nunca como sucesso. API keys curtas ou inválidas no contrato retornam `422`.

### Health check persistido FortiGate

`POST /api/integrations/fortigate/:integrationId/health-check`

Response:

```json
{
  "id": "fgt_health_01",
  "integrationId": "int_fgt_01",
  "ok": true,
  "status": "connected",
  "device": {
    "hostname": "FGT-VM",
    "model": "FortiGate-VM64",
    "version": "v7.4.x"
  },
  "message": null,
  "latencyMs": 12,
  "checkedAt": "2026-04-27T20:30:00.000Z"
}
```

`GET /api/integrations/fortigate/:integrationId/health-checks?limit=20` retorna `{ "items": [...] }`. Em modo live, cada health check atualiza `fortigate_integrations.status`, `last_checked_at` e grava histórico em `fortigate_health_checks`.

### Listar integrações

`GET /api/integrations`

Response:

```json
{
  "items": [
    {
      "id": "int_fgt_01",
      "type": "fortigate",
      "name": "FortiGate Lab",
      "host": "https://fortigate.local",
      "status": "connected",
      "lastCheckedAt": "2026-04-26T20:30:00.000Z"
    }
  ]
}
```

Não retornar `apiKey`.

### Remover integração

`DELETE /api/integrations/int_fgt_01`

Response:

```json
{
  "deleted": true,
  "id": "int_fgt_01"
}
```

Exige sessão HTTP-only e `X-CSRF-Token`. Em modo live, remove apenas a integração salva no FortiDashboard, a API key criptografada e o histórico local de health checks daquele usuário. Sucesso ou falha gravam `integration.fortigate.deleted` no audit log. Não executa nenhuma alteração no FortiGate.

### Provar titularidade de domínio

`POST /api/tenants/domain-verifications`

Request:

```json
{
  "domain": "cliente.example.com"
}
```

Response:

```json
{
  "id": "domver_01",
  "domain": "cliente.example.com",
  "status": "pending",
  "dnsRecord": {
    "type": "TXT",
    "name": "_fortidashboard.cliente.example.com",
    "value": "fortidashboard-verification=nonce_abc123"
  },
  "expiresAt": "2026-04-27T20:30:00.000Z"
}
```

`POST /api/tenants/domain-verifications/domver_01/check`

Response:

```json
{
  "id": "domver_01",
  "domain": "cliente.example.com",
  "status": "verified",
  "verifiedAt": "2026-04-26T21:00:00.000Z"
}
```

### Auditoria

`GET /api/audit/events?limit=50`

Response:

```json
{
  "items": [
    {
      "id": "audit_01",
      "actor": { "id": "usr_01", "email": "analyst@example.com" },
      "action": "integration.fortigate.created",
      "outcome": "success",
      "ipAddress": "192.0.2.10",
      "userAgent": "Mozilla/5.0",
      "details": { "integrationId": "int_fgt_01" },
      "createdAt": "2026-04-26T21:10:00.000Z"
    }
  ]
}
```

Campos sensíveis em `details` são sempre saneados como `[REDACTED]` antes de persistir ou retornar: `apiKey`, `api_key`, `token`, `access_token`, `refresh_token`, `clientSecret`, `password`, `api_key_blob` e variações equivalentes.

No corte atual, o endpoint retorna eventos do usuário autenticado. Visão cross-user fica para RBAC/admin.

### Catálogo de widgets

`GET /api/widget-catalog?integrationType=fortigate`

Response:

```json
{
  "items": [
    {
      "id": "fortigate-system-status",
      "title": "System Status",
      "kind": "kpi",
      "source": "fortigate",
      "requiredCapabilities": ["system"],
      "defaultSize": { "w": 3, "h": 2 },
      "dataEndpoint": "/api/widgets/fortigate-system-status/data"
    },
    {
      "id": "fortigate-network-traffic",
      "title": "Network Traffic",
      "kind": "table",
      "source": "fortigate",
      "requiredCapabilities": ["interfaces"],
      "defaultSize": { "w": 5, "h": 4 },
      "dataEndpoint": "/api/widgets/fortigate-network-traffic/data"
    },
    {
      "id": "fortigate-kpi-sessions",
      "title": "Active Sessions",
      "kind": "kpi",
      "source": "fortigate",
      "requiredCapabilities": ["system"],
      "defaultSize": { "w": 3, "h": 2 },
      "dataEndpoint": "/api/widgets/fortigate-kpi-sessions/data"
    },
    {
      "id": "fortigate-firewall-policies",
      "title": "Firewall Policies",
      "kind": "table",
      "source": "fortigate",
      "requiredCapabilities": ["policies"],
      "defaultSize": { "w": 5, "h": 4 },
      "dataEndpoint": "/api/widgets/fortigate-firewall-policies/data"
    },
    {
      "id": "fortigate-top-threats",
      "title": "Top Threats",
      "kind": "table",
      "source": "fortigate",
      "requiredCapabilities": ["threat_logs"],
      "defaultSize": { "w": 5, "h": 4 },
      "dataEndpoint": "/api/widgets/fortigate-top-threats/data"
    }
  ]
}
```

Além dos campos acima, cada item pode informar `template`, `dataGroup` e `fieldBindings`. Esses metadados fazem a ponte Power BI-like entre o modelo de dados do provider e o template visual. O frontend deve tratar widgets como templates reutilizáveis que consomem campos normalizados, não como cards hardcoded.

Templates FortiGate adicionados para enriquecimento SOC:

- `fortigate-risk-posture`: `template: "risk-summary"`, usa `risk.score` e `risk.signals`.
- `fortigate-interface-health`: `template: "interface-health"`, usa `interfaces[]` e resumo de links.
- `fortigate-recent-events`: `template: "event-feed"`, usa eventos/threat logs normalizados.
- `fortigate-anomaly-highlights`: `template: "anomaly-list"`, usa sinais de CPU, memória e interfaces.

### Modelo de dados do provider FortiGate

`GET /api/providers/fortigate/data-fields`

Response resumido:

```json
{
  "provider": "fortigate",
  "groups": [
    {
      "id": "system",
      "name": "System Data",
      "fields": [
        {
          "id": "system.cpu",
          "label": "CPU Usage",
          "type": "number",
          "unit": "percent",
          "source": "fortigate-system-status",
          "recommendedVisuals": ["kpi", "gauge", "risk-summary"]
        }
      ]
    }
  ]
}
```

Grupos iniciais: `system`, `interfaces`, `policies`, `events` e `risk`. Esse endpoint é a base para o painel Data do build pane. No futuro, criar um widget customizado deve significar selecionar provider, grupo/campo e template visual, mantendo o FortiGate read-only.

### Dados normalizados de widget

`GET /api/widgets/:widgetId/data?integrationId=int_fgt_01`

Response:

```json
{
  "widgetId": "fortigate-system-status",
  "integrationId": "int_fgt_01",
  "refreshedAt": "2026-04-26T20:31:00.000Z",
  "status": "ready",
  "data": {
    "cpu": 12,
    "memory": 54,
    "sessions": 3812,
    "uptimeSeconds": 92420
  },
  "meta": {
    "source": "fortigate",
    "cacheTtlSeconds": 2,
    "refreshIntervalSeconds": 2
  }
}
```

### Workspace do dashboard

`GET /api/workspaces/:workspaceId`

Response:

```json
{
  "id": "ws_default",
  "name": "SOC Overview",
  "widgets": [
    {
      "instanceId": "w_01",
      "catalogId": "fortigate-system-status",
      "integrationId": "int_fgt_01",
      "layout": { "x": 0, "y": 0, "w": 3, "h": 2, "z": 10 }
    }
  ]
}
```

`PUT /api/workspaces/:workspaceId` salva `name`, lista de widgets e layout. A resposta mínima deve retornar `id`, `version` e `updatedAt`.

Em modo live, workspace é persistido em `workspace_specs` por `owner_user_id`; um usuário não deve ler ou sobrescrever o canvas de outro. Em mock mode, a fixture continua estável para desenvolvimento do frontend.

## Arquitetura Frontend

- Use Vue 3 apenas com Composition API e `<script setup>`.
- Pinia é a fonte única de verdade para `activeWidgets`, coordenadas `x/y`, tamanho, `zIndex` e estado do canvas.
- Tailwind CSS deve ser usado por classes utilitárias nos componentes.
- Motion for Vue controla drag-and-drop livre, transições e limites do canvas.
- O renderizador principal deve iterar `activeWidgets` e usar `<component :is="...">` para instanciar widgets.
- Widgets de visualização não sabem sua posição; eles ficam dentro de um `DraggableWidget` genérico.
- Componentes iniciais esperados: `WidgetHealth`, `WidgetThreats` e `WidgetNetwork`.
- A sidebar deve conter chat da IA e lista/catálogo de módulos disponíveis.

## Handoff de Widgets para o Lucas - Sprint Atual

O frontend pode trabalhar com widgets FortiGate sem depender do FortiGate real. Em `FORTIDASHBOARD_MOCK_MODE=true`, a API e as fixtures em `packages/contracts/fixtures` retornam payloads estáveis. Em modo live, os mesmos endpoints usam a integração persistida e o client FortiGate read-only.

Em modo live, dados de widget FortiGate usam cache curto em memória por processo, chaveado por `owner_user_id`, `integrationId` e `widgetId`. O backend informa `cacheTtlSeconds` e `refreshIntervalSeconds`, e o `DraggableWidget` deve usar esse intervalo para atualizar o card automaticamente. Widgets voláteis de sistema, sessões e rede usam 2s; threats usam 5s; policies usam 15s.

Widgets derivados do mesmo status de sistema, como `fortigate-system-status` e `fortigate-kpi-sessions`, compartilham o mesmo snapshot normalizado dentro do TTL para evitar números divergentes no canvas.

Fluxo recomendado no `apps/web`:

- Carregar opções com `GET /api/widget-catalog?integrationType=fortigate`.
- Para cada item do catálogo, usar `id`, `title`, `kind`, `defaultSize`, `requiredCapabilities` e `dataEndpoint`.
- Ao instanciar um widget no canvas, chamar `${dataEndpoint}?integrationId=<id-da-integracao>`.
- Em modo live, as chamadas a `/api/integrations*` e `/api/widgets/*/data` precisam enviar o cookie de sessão da API; o backend filtra por `owner_user_id`.
- Renderizar `status: "ready"` como dado normal, `status: "error"` como erro dentro do card, e estados de loading/empty no adapter HTTP.
- Não acoplar componente visual ao FortiGate: o componente recebe apenas o payload `data` normalizado.
- No frontend, `apps/web/src/services/widgetDataClient.ts` é o adapter HTTP dos widgets e deve continuar retornando `state: "ready"` ou `state: "error"` para o frame decidir loading/erro. O frame agenda o próximo fetch por `meta.refreshIntervalSeconds`.
- `defaultSize` do catálogo vem em unidades de grid. `apps/web/src/utils/widgetLayout.ts` converte essas unidades para pixels antes de renderizar ou adicionar widgets no canvas.

Widgets disponíveis nesta sprint:

| Widget ID | Tipo | Payload principal | Observação frontend |
| --- | --- | --- | --- |
| `fortigate-system-status` | `kpi` | `hostname`, `model`, `version`, `build`, `cpu`, `memory`, `sessions`, `uptimeSeconds` | Card de saúde geral do appliance |
| `fortigate-kpi-sessions` | `kpi` | `sessions` | KPI compacto para sessões ativas |
| `fortigate-network-traffic` | `table` | `interfaces[]` com `rxBytes`, `txBytes`, packets e `status` | Pode virar tabela ou gráfico por interface |
| `fortigate-firewall-policies` | `table` | `policies[]` | No lab atual pode vir lista vazia |
| `fortigate-top-threats` | `table` | `threats[]` ou `status: "error"` | O lab atual retorna `404`; renderizar erro contextual |
| `fortigate-risk-posture` | `summary` | `score`, `level`, `signals[]`, `summary` | Postura de risco derivada de CPU, memória, interfaces e políticas |
| `fortigate-interface-health` | `status-list` | `interfaces[]`, `summary` | Saúde operacional dos links e tráfego agregado |
| `fortigate-recent-events` | `feed` | `events[]`, `summary` | Feed simples para threat logs/eventos recentes |
| `fortigate-anomaly-highlights` | `feed` | `anomalies[]`, `summary` | Destaques de anomalias derivadas de métricas read-only |

Contrato comum de widget:

```json
{
  "widgetId": "fortigate-system-status",
  "integrationId": "int_fgt_01",
  "refreshedAt": "2026-04-26T23:45:00.000Z",
  "status": "ready",
  "data": {},
  "meta": {
    "source": "fortigate",
    "cacheTtlSeconds": 2,
    "refreshIntervalSeconds": 2
  }
}
```

Erro controlado:

```json
{
  "widgetId": "fortigate-top-threats",
  "integrationId": "int_fgt_01",
  "refreshedAt": "2026-04-26T23:45:00.000Z",
  "status": "error",
  "data": {},
  "meta": {
    "source": "fortigate",
    "cacheTtlSeconds": 5,
    "refreshIntervalSeconds": 5,
    "error": { "message": "FortiGate API request failed with HTTP 404" }
  }
}
```

## Timeline de Trabalho Paralelo

O frontend não deve esperar a integração FortiGate ficar pronta. A primeira fronteira compartilhada é o contrato estático: shapes de integração, catálogo, widget data, workspace, domínio verificado e audit log. Enquanto o backend implementa FastAPI e persistência, o Lucas pode evoluir `apps/web` usando mocks locais compatíveis com os exemplos deste arquivo.

| Marco | Backend/Felipe | Frontend/Lucas | Critério de desbloqueio |
| --- | --- | --- | --- |
| T-1 - Feedback incorporado | Converte feedback em requisitos de domínio, auditoria, menor privilégio e enriquecimento | Ajusta direção visual para produto SOC enterprise e SaaS | Backlog atualizado sem bloquear código em andamento |
| T0 - Contrato inicial | Define mockups de endpoints, IDs e schemas mínimos | Usa os mesmos payloads como fixtures locais | Frontend já consegue montar canvas com dados falsos |
| T1 - Scaffolds independentes | Cria `apps/api`, healthcheck, OpenAPI inicial e auth mocks | Cria `apps/web`, layout base, Pinia e canvas | Ambos rodam localmente sem depender um do outro |
| T2 - Front com mocks ricos | Publica JSON schemas/fixtures versionados, incluindo auth/session, domínio, audit log e widgets | Implementa login/register mockado, catálogo, chat, audit feed, estados de domínio e widgets estáticos | Lucas desenvolve UX completa sem Keycloak ou FortiGate real |
| T3 - Backend funcional fake/live | Implementa endpoints com mock mode, BFF auth, persistência de integração e audit events | Troca adapter mock por cliente HTTP mantendo stores | Integração acontece sem reescrever componentes |
| T4 - FortiGate read-only real | Implementa cliente FortiGate, normalizadores, health checks e cache curto | Consome API real, trata loading/erro/sem dados e conexão inválida | Dashboard salva layout e mostra dados reais |
| T5 - SaaS e hardening | Implementa prova DNS TXT, RBAC, SSO/IdP via Keycloak e auditoria consultável | Refina onboarding SaaS, tela de domínio, audit trail e polimento visual | Produto começa a responder riscos de phishing, supply-chain e insider |

Ponto de independência do frontend: ao final de T2, `apps/web` deve conseguir evoluir usando apenas fixtures/mockups. Ponto de backend funcional: ao final de T4, a API deve autenticar sessão, persistir integração FortiGate, consultar dados read-only e expor dados normalizados para widgets.

## Backlog Assíncrono

### Trilha Compartilhada - Contratos e Base

- [x] Criar estrutura raiz com `.gitignore`, `docker-compose.yml`, `.env.example` e `README.md`.
- [x] Criar `packages/contracts` com OpenAPI/JSON schemas exportáveis.
- [x] Criar fixtures em `packages/contracts/fixtures` para integração, catálogo, widget data e workspace.
- [x] Criar `packages/widget-catalog` com definição neutra dos widgets FortiGate.
- [ ] Adicionar fixtures de domínio pendente/verificado e audit events para desenvolvimento frontend.
- [ ] Registrar threat model inicial para phishing, supply-chain e insider antes do modo SaaS.
- [ ] Manter `AGENTS.md` como contrato vivo sempre que payloads ou responsabilidades mudarem.

### Trilha Backend - FastAPI, Dados e FortiGate

- [x] Scaffoldar `apps/api` com FastAPI, `pyproject.toml`, Ruff, Pytest e Alembic.
- [x] Dockerizar `apps/api` e adicionar serviço `api` ao Docker Compose.
- [x] Adicionar Postgres no Docker Compose e configurar variáveis via `.env.example`.
- [x] Implementar `GET /health` e documentação OpenAPI inicial.
- [x] Implementar endpoints acima em modo mock, usando fixtures compartilhadas.
- [x] Adicionar Keycloak ao Docker Compose com realm/client inicial para desenvolvimento.
- [x] Implementar client/provider para `POST /api/auth/register` usando Keycloak Admin API e sessão HTTP-only.
- [x] Implementar client/provider para `POST /api/auth/login` via token endpoint do Keycloak e sessão HTTP-only.
- [x] Normalizar erros de Keycloak/provider para responses JSON estáveis no BFF FastAPI.
- [x] Conceder `manage-users`/`view-users` ao service account `fortidashboard-bff` no realm dev do Keycloak.
- [x] Implementar `GET /api/auth/me` e `POST /api/auth/logout`.
- [x] Validar o fluxo live de auth contra Keycloak em Docker Compose com `FORTIDASHBOARD_MOCK_MODE=false`.
- [x] Persistir sessões server-side com tokens Keycloak criptografados ou referência segura.
- [x] Adicionar CSRF/rate limit/auditoria para endpoints de autenticação.
- [x] Implementar cadastro de integração FortiGate com `host`, `apiKey` e `verifyTls`.
- [x] Deixar `FORTIDASHBOARD_MOCK_MODE=false` como default do Docker/API; mocks são opt-in.
- [x] Validar tamanho mínimo da API key FortiGate antes de testar ou salvar integração.
- [x] Bloquear persistência de integração FortiGate live quando o probe read-only falhar.
- [x] Criptografar API keys em repouso e nunca retorná-las em responses.
- [x] Implementar cliente REST FortiGate em `apps/api/app/integrations/fortigate`.
- [x] Normalizar status do sistema, interfaces, políticas e threat logs.
- [x] Expor modelo Power BI-like de campos FortiGate em `GET /api/providers/fortigate/data-fields`.
- [x] Adicionar templates SOC de risco, saúde de interfaces, eventos recentes e anomalias ao catálogo FortiGate.
- [x] Ligar endpoints de widgets FortiGate a dados live normalizados em modo não-mock.
- [x] Escopar integrações FortiGate por usuário autenticado via `owner_user_id`.
- [x] Persistir integrações FortiGate por usuário autenticado via `fortigate_integrations.owner_user_id`.
- [x] Persistir health checks FortiGate em `fortigate_health_checks`.
- [x] Persistir workspace specs por usuário em `workspace_specs`.
- [x] Adicionar cache curto por widget para evitar excesso de chamadas ao FortiGate.
- [x] Compartilhar snapshot de status entre widgets FortiGate derivados do sistema.
- [x] Expor `refreshIntervalSeconds` e reduzir TTL de widgets voláteis para atualização quase em tempo real.
- [x] Implementar remoção local de integração via `DELETE /api/integrations/{integrationId}` com escopo por usuário, CSRF e audit log.
- [x] Implementar audit log para auth, integração e workspace, com endpoint `GET /api/audit/events`.
- [ ] Adicionar auditoria a rotas administrativas quando a superfície admin existir.
- [ ] Implementar prova de titularidade de domínio por DNS TXT antes de ativar tenant/domínio SaaS.
- [ ] Planejar SSO/IdP/LDAP via Keycloak sem expor tokens ao frontend.

Nota de progresso backend (2026-04-27): migrations adicionam `workspace_specs` e `fortigate_health_checks`. Workspace live agora faz round-trip no Postgres por usuário; health check salvo pode ser executado por integração persistida; widgets FortiGate têm cache curto; audit events são saneados antes de persistir e retornar. Review pré-merge adicionou escopo por usuário no audit feed, CSRF em mutáveis de integração/workspace e `404` para histórico de health check de integração inexistente.

Nota de realtime widgets (2026-04-28): `fortigate-system-status`, `fortigate-kpi-sessions` e `fortigate-network-traffic` atualizam a cada 2s no frontend via `meta.refreshIntervalSeconds`; `fortigate-top-threats` usa 5s e `fortigate-firewall-policies` usa 15s.

Nota de CRUD de integrações (2026-04-28): o frontend pode remover integrações conectadas pela sidebar. O backend apaga somente o registro local, a API key criptografada e health checks do usuário autenticado; o FortiGate não sofre mudanças de configuração.

Nota de modelo Power BI-like (2026-04-28): o FortiGate agora expõe um catálogo de campos por grupos (`system`, `interfaces`, `policies`, `events`, `risk`) e templates adicionais (`risk-posture`, `interface-health`, `recent-events`, `anomaly-highlights`). Isso prepara a futura criação de widgets customizados por seleção de campo + visual, sem abandonar os templates prontos.

Nota de validação FortiGate local (2026-04-26): host `192.0.2.118` responde em `443` e o API user `pingwin` autenticou com token regenerado. Validação read-only passou para status, performance e sessões, normalizando hostname, modelo, versão, build, CPU, memória e sessões sem registrar a API key no repositório.

Nota de validação de widgets live (2026-04-26): `fortigate-system-status`, `fortigate-network-traffic` e `fortigate-firewall-policies` retornaram payloads normalizados contra o FortiGate local. `fortigate-top-threats` retornou `status: error` controlado porque o endpoint de logs UTM/IPS respondeu `404` nesse lab.

### Trilha Frontend - Canvas e Mockups

- [x] Scaffoldar `apps/web` com Vue 3, Vite, Pinia, Tailwind, Motion for Vue e Lucide Vue.
- [x] Implementar telas Vue próprias de `login` e `register`, chamando `/api/auth/*`.
- [x] Centralizar CSRF/login/register/logout/me em `apps/web/src/services/authClient.ts`.
- [x] Confirmar sessão browser via `/api/auth/me` após login/register antes de marcar usuário autenticado.
- [x] Usar `/api/auth/me` para hidratar usuário/sessão no frontend.
- [x] Criar layout macro com sidebar fixa e canvas central.
- [x] Criar store Pinia `useDashboardStore` com fixtures de dois widgets.
- [x] Criar adapter de dados mockado consumindo `packages/contracts/fixtures`.
- [x] Criar `DraggableWidget` com Motion for Vue e persistência de posição no Pinia.
- [x] Criar cartões Fortinet com cabeçalho escuro, título e ação de fechar/excluir.
- [x] Criar `WidgetHealth`, `WidgetThreats` e `WidgetNetwork` com dados estáticos.
- [x] Criar `WidgetFirewallPolicies` para o widget `fortigate-firewall-policies`.
- [x] Implementar catálogo filtrado por integração conectada usando fixtures (Movido para o Build Pane direito estilo Power BI).
- [x] Implementar chat mockado que adiciona widget em posição livre no canvas (CoPilot na esquerda).
- [x] Implementar Redimensionamento Livre (Multi-eixo 8 direções) simulando experiência Power BI.
- [x] Implementar sistema de Theming (Theme Builder Modal) dinâmico via variáveis CSS do Tailwind v4.
- [x] Adicionar controle de Zoom livre (estilo Figma/Power BI) via scroll do mouse focado exclusivamente na workspace.
- [x] Preparar troca do adapter mock para HTTP sem alterar componentes de visualização.
- [x] Tratar `ok: false` de teste FortiGate como erro no painel de integrações.
- [x] Exibir identidade do FortiGate no widget de saúde para diferenciar dados live de mock.
- [x] Atualizar widgets automaticamente pelo intervalo retornado pela API.
- [x] Permitir remover integrações conectadas pela sidebar usando o endpoint `DELETE /api/integrations/{integrationId}`.
- [ ] Mostrar estados de loading, erro, sem dados e conexão inválida.
- [ ] Criar mocks visuais para domínio pendente/verificado e falha de verificação.
- [ ] Criar audit trail/activity feed para eventos sensíveis.
- [ ] Renderizar no frontend os novos templates de postura de risco, saúde de interfaces, eventos recentes e anomalias.
- [ ] Enriquecer dashboard com widgets de postura de risco, anomalias e investigação SOC.
- [ ] Refinar visual para experiência SaaS enterprise, não apenas protótipo técnico.

### Trilha de Integração e Qualidade

- [x] Validar que fixtures, schemas e responses FastAPI têm o mesmo shape.
- [x] Adicionar testes unitários para normalizadores FortiGate.
- [x] Adicionar testes unitários frontend para adapter de widgets, layout do canvas e renderizadores FortiGate.
- [x] Adicionar testes unitários frontend para CSRF, login/register e confirmação de sessão via `/auth/me`.
- [x] Adicionar testes backend para normalização de erros Keycloak e permissões do realm dev.
- [x] Adicionar testes para default live, rejeição de API key curta e `ok:false` no teste FortiGate.
- [x] Adicionar testes de contrato para payloads de API.
- [x] Adicionar smoke tests para conexão, catálogo e renderização do canvas.
- [x] Validar que ações destrutivas não entram no primeiro corte da integração FortiGate.
- [x] Testar remoção de integração com escopo por usuário, CSRF e audit log saneado.
- [x] Testar que audit logs não gravam segredos, API keys ou tokens.
- [x] Documentar setup local completo em `README.md`.
- [ ] Preparar PRs pequenos por trilha, com comandos executados e screenshots quando houver UI.

## Convenções de Código

Backend: use Python tipado, Pydantic para payloads, SQLAlchemy para modelos persistidos e Alembic para migrations. Use `snake_case` para módulos, variáveis e funções; `PascalCase` para modelos/classes.

Frontend: use Vue SFCs com `<script setup>`. Componentes em `PascalCase`, stores como `useDashboardStore`, arquivos Vue em `PascalCase.vue` e utilitários em `camelCase.ts`.

Contratos: toda mudança de endpoint precisa atualizar schema, mockup no `AGENTS.md` ou `docs/api`, e consumidor correspondente.

## Fluxo Git para Agents

- Sempre rode `git fetch origin` e confira a base antes de começar.
- Nunca trabalhe direto em `main` para feature nova. Crie branch com dono e escopo: `felipe/api-fortigate-client`, `lucas/web-canvas-base` ou `gemini/web-drag-widgets`.
- Antes de commitar, rode os checks relevantes da área alterada.
- Stage apenas arquivos do escopo da tarefa. Não inclua `.env`, segredos, dumps ou arquivos locais.
- Faça commits pequenos e imperativos, por exemplo `feat(api): add fortigate connection test` ou `feat(web): add draggable widget shell`.
- Publique com `git push -u origin <branch>`.
- Abra PR contra `main` ou avise o time com branch, commit e comandos rodados.
- Não use `git push --force` sem autorização explícita do Felipe.
- Se houver conflito em `AGENTS.md`, una as instruções em um documento só em vez de sobrescrever a seção de outro agent.

## Pull Requests

PRs devem explicar o que mudou, quais endpoints/contratos foram afetados, quais comandos foram executados e se há impacto visual para revisão do Lucas. Mudanças de backend que afetam payloads precisam incluir exemplo de request/response. Mudanças de frontend precisam incluir screenshot ou gravação curta quando alterarem a UI.
