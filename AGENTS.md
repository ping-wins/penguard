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
- Frontend deve chamar `GET /api/auth/csrf` antes de `login`, `register` ou `logout` e enviar o valor em `X-CSRF-Token`.

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
- `docker compose up -d --build api`: sobe API, Postgres e Keycloak em modo mock por padrão.
- `FORTIDASHBOARD_MOCK_MODE=false docker compose up -d --build api`: sobe API usando Keycloak live e sessões persistidas no Postgres.
- `cd apps/api && uv sync`: instala dependências Python.
- `cd apps/api && uv run uvicorn app.main:app --reload --port 8000`: roda a API.
- `cd apps/api && uv run pytest`: executa testes backend.
- `cd apps/api && uv run ruff check .`: roda lint backend.
- `cd apps/api && uv run alembic upgrade head`: aplica migrations.
- `cd apps/web && pnpm install`: instala dependências frontend.
- `cd apps/web && pnpm dev`: roda o frontend Vite.
- `cd apps/web && pnpm test`: executa testes frontend quando existirem.

## Contratos e Mockups de Endpoints

### CSRF para formulários Vue

`GET /api/auth/csrf`

Response:

```json
{
  "csrfToken": "csrf_token_for_x_csrf_token_header"
}
```

A resposta define o cookie `fortidashboard_csrf` sem `HttpOnly`. Envie o mesmo valor no header `X-CSRF-Token` em `POST /api/auth/register`, `POST /api/auth/login` e `POST /api/auth/logout`. Falha de CSRF retorna `403`; excesso de tentativas de auth retorna `429`.

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

Em `FORTIDASHBOARD_MOCK_MODE=true`, a API mantém respostas fixture para desenvolvimento do frontend. Em `FORTIDASHBOARD_MOCK_MODE=false`, a integração é persistida em Postgres na tabela `fortigate_integrations`, com `api_key_blob` criptografado.

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
      "target": { "type": "integration", "id": "int_fgt_01" },
      "risk": "medium",
      "ipAddress": "192.0.2.10",
      "createdAt": "2026-04-26T21:10:00.000Z"
    }
  ]
}
```

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
    "cacheTtlSeconds": 30
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

## Arquitetura Frontend

- Use Vue 3 apenas com Composition API e `<script setup>`.
- Pinia é a fonte única de verdade para `activeWidgets`, coordenadas `x/y`, tamanho, `zIndex` e estado do canvas.
- Tailwind CSS deve ser usado por classes utilitárias nos componentes.
- Motion for Vue controla drag-and-drop livre, transições e limites do canvas.
- O renderizador principal deve iterar `activeWidgets` e usar `<component :is="...">` para instanciar widgets.
- Widgets de visualização não sabem sua posição; eles ficam dentro de um `DraggableWidget` genérico.
- Componentes iniciais esperados: `WidgetHealth`, `WidgetThreats` e `WidgetNetwork`.
- A sidebar deve conter chat da IA e lista/catálogo de módulos disponíveis.

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
- [x] Implementar `GET /api/auth/me` e `POST /api/auth/logout`.
- [x] Validar o fluxo live de auth contra Keycloak em Docker Compose com `FORTIDASHBOARD_MOCK_MODE=false`.
- [x] Persistir sessões server-side com tokens Keycloak criptografados ou referência segura.
- [x] Adicionar CSRF/rate limit/auditoria para endpoints de autenticação.
- [x] Implementar cadastro de integração FortiGate com `host`, `apiKey` e `verifyTls`.
- [x] Criptografar API keys em repouso e nunca retorná-las em responses.
- [x] Implementar cliente REST FortiGate em `apps/api/app/integrations/fortigate`.
- [x] Normalizar status do sistema, interfaces, políticas e threat logs.
- [ ] Persistir integrações, health checks e workspace specs.
- [ ] Adicionar cache curto por widget para evitar excesso de chamadas ao FortiGate.
- [ ] Implementar audit log para ações sensíveis de auth, integração, workspace e administração.
- [ ] Implementar prova de titularidade de domínio por DNS TXT antes de ativar tenant/domínio SaaS.
- [ ] Planejar SSO/IdP/LDAP via Keycloak sem expor tokens ao frontend.

Nota de validação FortiGate local (2026-04-26): host `192.168.0.118` responde em `443` e o API user `pingwin` autenticou com token regenerado. Validação read-only passou para status, performance e sessões, normalizando hostname, modelo, versão, build, CPU, memória e sessões sem registrar a API key no repositório.

### Trilha Frontend - Canvas e Mockups

- [x] Scaffoldar `apps/web` com Vue 3, Vite, Pinia, Tailwind, Motion for Vue e Lucide Vue.
- [ ] Implementar telas Vue próprias de `login` e `register`, chamando `/api/auth/*`.
- [ ] Usar `/api/auth/me` para hidratar usuário/sessão no frontend.
- [x] Criar layout macro com sidebar fixa e canvas central.
- [x] Criar store Pinia `useDashboardStore` com fixtures de dois widgets.
- [x] Criar adapter de dados mockado consumindo `packages/contracts/fixtures`.
- [x] Criar `DraggableWidget` com Motion for Vue e persistência de posição no Pinia.
- [x] Criar cartões Fortinet com cabeçalho escuro, título e ação de fechar/excluir.
- [x] Criar `WidgetHealth`, `WidgetThreats` e `WidgetNetwork` com dados estáticos.
- [x] Implementar catálogo filtrado por integração conectada usando fixtures (Movido para o Build Pane direito estilo Power BI).
- [x] Implementar chat mockado que adiciona widget em posição livre no canvas (CoPilot na esquerda).
- [x] Implementar Redimensionamento Livre (Multi-eixo 8 direções) simulando experiência Power BI.
- [ ] Preparar troca do adapter mock para HTTP sem alterar componentes de visualização.
- [ ] Mostrar estados de loading, erro, sem dados e conexão inválida.
- [ ] Criar mocks visuais para domínio pendente/verificado e falha de verificação.
- [ ] Criar audit trail/activity feed para eventos sensíveis.
- [ ] Enriquecer dashboard com widgets de postura de risco, anomalias e investigação SOC.
- [ ] Refinar visual para experiência SaaS enterprise, não apenas protótipo técnico.

### Trilha de Integração e Qualidade

- [x] Validar que fixtures, schemas e responses FastAPI têm o mesmo shape.
- [ ] Adicionar testes unitários para normalizadores FortiGate.
- [x] Adicionar testes de contrato para payloads de API.
- [ ] Adicionar smoke tests para conexão, catálogo e renderização do canvas.
- [ ] Validar que ações destrutivas não entram no primeiro corte da integração FortiGate.
- [ ] Testar que audit logs não gravam segredos, API keys ou tokens.
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
