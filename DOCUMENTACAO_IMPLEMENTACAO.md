# Documentacao de implementacao da solucao Penguard

Data de referencia: 2026-05-23.

Este documento descreve como reproduzir o ambiente Penguard, subir a solucao
em Docker e executar os testes principais da ferramenta. Ele foi escrito para
um laboratorio ou avaliacao tecnica. Valores reais de IP, hostnames, chaves de
API, tokens e senhas devem ficar somente no `.env` local ou no cofre da equipe.

## 1. Visao geral da solucao

Penguard e um cockpit modular de NG-SOC. O primeiro provedor real e o
FortiGate; as capacidades de SIEM, SOAR e XDR/EDR usadas no MVP sao servicos
internos identificados como SOC-lite:

| Componente | Funcao |
| --- | --- |
| `apps/web` | Cockpit Vue 3 para workspace, widgets, integracoes, tickets, endpoints e playbooks. |
| `apps/api` | BFF FastAPI, autenticacao, sessoes, auditoria, integracoes e gateway para servicos internos. |
| `apps/siem_kowalski` | SIEM-lite para eventos, deteccoes, incidentes e timelines. |
| `apps/soar_skipper` | SOAR-lite para playbooks, simulacao, aprovacao e historico de execucao. |
| `apps/xdr_rico` | XDR/EDR-lite para inventario de endpoints, heartbeat, timelines e correlacao. |
| `apps/agent_private` | Sensor opcional de endpoint para enviar telemetria real ao XDR. |
| `FortiGate` | Provedor real de firewall, inventario, widgets, syslog e orquestracao governada. |

Fluxo esperado:

```txt
Browser -> apps/api -> FortiGate
Browser -> apps/api -> siem_kowalski | soar_skipper | xdr_rico
FortiGate -> syslog UDP collector em apps/api -> siem_kowalski
agent_private -> apps/api -> xdr_rico
```

O deploy MVP e single-tenant por stack: um cliente ou laboratorio executa sua
propria instancia com Postgres, Redis, Keycloak, BFF e servicos SOC-lite.

## 2. Pre-requisitos

Obrigatorios:

- Git.
- Docker Engine ou Docker Desktop com Docker Compose v2.
- Acesso de rede do host para as portas locais usadas pelo Compose.

Recomendados para desenvolvimento e testes locais:

- Python 3.12+.
- `uv` para os servicos Python.
- Node.js e `pnpm` para o frontend quando rodar fora do container.
- `curl` e `jq` para validacoes por terminal.

Portas padrao:

| Porta | Servico |
| --- | --- |
| `5173/tcp` | Cockpit web |
| `8000/tcp` | API/BFF |
| `8080/tcp` | Keycloak |
| `5432/tcp` | Postgres |
| `6379/tcp` | Redis |
| `8011/tcp` | `siem_kowalski` |
| `8012/tcp` | `soar_skipper` |
| `8013/tcp` | `xdr_rico` |
| `5514/udp` | Coletor syslog FortiGate |
| `8764/udp` | Descoberta de agentes XDR |

Se alguma porta ja estiver ocupada, altere no `.env`, por exemplo:

```bash
PENGUARD_WEB_PORT=5174 PENGUARD_API_PORT=8001 docker compose up -d --build
```

## 3. Preparacao do ambiente

Clone o repositorio e entre na raiz:

```bash
git clone <URL_DO_REPOSITORIO>
cd fortidashboard
```

Gere o `.env` com segredos fortes. O arquivo `.env` nao deve ser commitado.

Linux, macOS ou WSL:

```bash
./scripts/bootstrap-secrets.sh
```

Windows PowerShell:

```powershell
.\scripts\bootstrap-secrets.ps1
```

Revise o `.env` gerado antes de subir o stack. Ajustes comuns:

- `PENGUARD_FORTIGATE_SYSLOG_COLLECTOR_PUBLIC_HOST`: IP que o FortiGate usa
  para enviar syslog ao host Penguard.
- `PENGUARD_API_PORT` e `PENGUARD_WEB_PORT`: portas locais da API e do web.
- `MARKETPLACE_GH_TOKEN`: token somente leitura se for testar registry privado
  de add-ons.
- `PENGUARD_AI_PROVIDER`, `PENGUARD_AI_API_KEY`, `PENGUARD_AI_MODEL` e
  `PENGUARD_AI_BASE_URL`: somente se for testar IA real.

Modo mock existe apenas para desenvolvimento tecnico. Para validar o produto,
mantenha `PENGUARD_MOCK_MODE=false` e use FortiGate/syslog/endpoint reais.

## 4. Subida do stack

Valide o Compose:

```bash
docker compose config --quiet
```

Suba todos os servicos:

```bash
docker compose up -d --build
```

Confira o estado:

```bash
docker compose ps
```

Sincronize o secret do client Keycloak com o valor do `.env` depois do primeiro
`up`. Isto evita erro `invalid_client` no login/register.

Linux, macOS ou WSL:

```bash
./scripts/sync-keycloak-client-secret.sh
```

Windows PowerShell:

```powershell
.\scripts\sync-keycloak-client-secret.ps1
```

URLs locais:

| URL | Uso |
| --- | --- |
| `http://localhost:5173` | Cockpit Penguard |
| `http://localhost:8000/health` | Health da API |
| `http://localhost:8000/docs` | OpenAPI da API |
| `http://localhost:8080` | Console Keycloak |
| `http://localhost:8011/health` | Health do SIEM-lite |
| `http://localhost:8012/health` | Health do SOAR-lite |
| `http://localhost:8013/health` | Health do XDR-lite |

Checks rapidos:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/ai/status
curl http://localhost:8000/api/soc/ingest/health
curl http://localhost:8011/health
curl http://localhost:8012/health
curl http://localhost:8013/health
```

Resultado esperado para a API:

```json
{"status":"ok","service":"penguard-api"}
```

## 5. Primeiro acesso no cockpit

1. Acesse `http://localhost:5173`.
2. Crie o primeiro usuario pela tela de cadastro do Penguard.
3. Entre com o usuario criado.
4. Abra o drawer de integracoes e confirme que o cockpit consegue conversar
   com o BFF.
5. Abra Settings/Profile para conferir a sessao BFF.

O navegador nunca recebe access token, refresh token ou client secret do
Keycloak. A sessao do cockpit usa cookie HTTP-only e CSRF nas rotas mutantes.

## 6. Reproducao com FortiGate real

Para validar a ferramenta como produto, use FortiGate real ou VM de laboratorio.
Nao use replay sintetico como criterio principal.

Pre-requisitos no laboratorio:

- Host Penguard consegue acessar o IP de gerenciamento do FortiGate.
- FortiGate possui API key com permissoes compativeis com leitura, health,
  inventario e as acoes governadas que serao testadas.
- FortiGate consegue enviar syslog UDP para
  `PENGUARD_FORTIGATE_SYSLOG_COLLECTOR_PUBLIC_HOST:PENGUARD_FORTIGATE_SYSLOG_COLLECTOR_PORT`.
- O Compose esta com `PENGUARD_ENABLE_LAB_DEMO_TOOLS=false` para validacao
  normal de produto.

Fluxo recomendado no cockpit:

1. Abra Integrations.
2. Conecte FortiGate com URL/IP e API key.
3. Execute o teste/probe antes de salvar.
4. Salve a integracao.
5. Execute Health check.
6. Abra o status de log forwarding/syslog.
7. Aplique configuracao segura/aditiva de log forwarding somente se o cockpit
   mostrar o diff/resumo e um usuario permitido confirmar.
8. Verifique se o coletor recebeu eventos.
9. Abra SOC Tickets/Incidents e confirme criacao de eventos/incidentes a partir
   de syslog real.
10. Abra Audit e confirme registro de integracao, health check, ingestao e
    qualquer acao sensivel.

Endpoint util para acompanhar ingestao de uma integracao FortiGate:

```txt
GET /api/soc/fortigate/{integrationId}/ingestion-status
```

Use o OpenAPI em `http://localhost:8000/docs` para testar endpoints
autenticados quando precisar validar payloads manualmente.

## 7. Validacao de deteccao de scan no laboratorio

O runbook detalhado esta em:

```txt
docs/operations/fortigate-scan-detection.md
```

Topologia de referencia:

```txt
BlackArch attacker -> FortiGate -> FortiWeb VIP -> FortiWeb -> Arch origin
```

Resumo do teste:

1. Conecte o FortiGate no cockpit e confirme health/log forwarding.
2. Use a orquestracao do Penguard para criar ou verificar uma politica
   temporaria, logada e de propriedade Penguard para o caminho de teste.
3. A partir da maquina atacante, confirme rota ate o alvo.
4. Execute scan controlado contra o VIP FortiWeb, nao contra o origin direto.
5. Verifique logs Forward Traffic no FortiGate.
6. Confirme que o Penguard recebe evento realtime e cria ticket de possivel
   port scan.
7. Se testar contencao, aprove manualmente o fluxo SOAR e revise o diff antes
   de aplicar qualquer mudanca real.
8. Remova ou desative a politica temporaria apos o teste.

Exemplo de scan controlado:

```bash
sudo nmap -e <ATTACK_IFACE> -Pn -n -sS -T4 -p 1-2000 --max-retries 1 <FORTIWEB_VIP>
```

Resultado esperado:

- Widget de incidentes atualiza sem refresh manual do navegador.
- Ticket `Possible port scan` aparece no SOC.
- Auditoria registra ingestao, ticket, aprovacao e mudanca de politica quando
  houver contencao.
- Nenhuma acao destrutiva ou silenciosa e aplicada automaticamente.

## 8. Reproducao com endpoint XDR

O endpoint opcional `agent_private` envia heartbeat, processos, conexoes e
eventos Windows Security/Sysmon ao Penguard.

Crie um token de enrollment pelo cockpit ou pelo script:

```bash
PENGUARD_LOGIN_EMAIL=<email> \
PENGUARD_LOGIN_PASSWORD=<senha> \
  scripts/create-xdr-enrollment.sh --display-name "Windows Server Lab"
```

No host Windows ou Linux do agente:

```bash
cd apps/agent_private
uv sync
uv run agent-private pair <TOKEN_DE_ENROLLMENT> --api-url http://<HOST_PENGUARD>:8000
uv run agent-private run
```

Para smoke test headless:

```bash
uv run agent-private run-headless \
  --api-url http://<HOST_PENGUARD>:8000 \
  --endpoint-id win-server-01 \
  --enrollment-token <TOKEN_DE_ENROLLMENT> \
  --once
```

No cockpit, abra Endpoints e valide:

- endpoint aparece com last seen recente;
- timeline contem heartbeat/processos/conexoes;
- eventos correlacionados aparecem no contexto de incidentes quando aplicavel.

Runbook complementar:

```txt
docs/mvp/windows-server-agent-smoke.md
```

## 9. Testes automatizados

Use estes comandos antes de handoff ou PR.

Validacao geral:

```bash
git diff --check
docker compose config --quiet
```

API:

```bash
cd apps/api
uv sync
uv run ruff check .
uv run pytest -q
```

Frontend:

```bash
cd apps/web
pnpm install
pnpm test
pnpm build
pnpm smoke:canvas
```

Servicos SOC-lite:

```bash
cd apps/siem_kowalski
uv run ruff check .
uv run pytest -q
```

```bash
cd apps/soar_skipper
uv run ruff check .
uv run pytest -q
```

```bash
cd apps/xdr_rico
uv run ruff check .
uv run pytest -q
```

Agente:

```bash
cd apps/agent_private
uv run pytest -q
```

## 10. Criterios de aceite do ambiente

Considere o ambiente reproduzido quando:

- `docker compose ps` mostra API, web, db, redis, keycloak, SIEM, SOAR e XDR
  saudaveis.
- `curl http://localhost:8000/health` retorna `status=ok`.
- Cockpit abre em `http://localhost:5173`.
- Cadastro/login funcionam via BFF.
- FortiGate conectado passa probe/health check.
- Syslog real do FortiGate chega ao coletor UDP e aparece na saude de ingestao.
- SIEM cria incidente/ticket a partir de telemetria real.
- Acoes sensiveis exigem usuario permitido, confirmacao explicita e auditoria.
- `agent_private`, quando usado, aparece no cockpit como endpoint com timeline.
- Testes automatizados relevantes passam no escopo alterado.

## 11. Troubleshooting

### API nao sobe por segredo inseguro

Execute `./scripts/bootstrap-secrets.sh` ou `.\scripts\bootstrap-secrets.ps1`.
A API recusa defaults perigosos quando `PENGUARD_MOCK_MODE=false`.

### Login falha com `invalid_client`

Sincronize o client secret:

```bash
./scripts/sync-keycloak-client-secret.sh
```

ou no Windows:

```powershell
.\scripts\sync-keycloak-client-secret.ps1
```

### Keycloak ficou com realm antigo

Em laboratorio descartavel, recrie os volumes:

```bash
docker compose down -v
docker compose up -d --build
```

Isto apaga dados locais. Nao use em ambiente com dados que precisam ser
preservados.

### FortiGate nao envia logs

Verifique:

- `PENGUARD_FORTIGATE_SYSLOG_COLLECTOR_PUBLIC_HOST` e porta UDP `5514`;
- rota do FortiGate ate o host;
- regra FortiGate com `logtraffic all`;
- firewall local do host permitindo UDP;
- status em `/api/soc/fortigate/{integrationId}/ingestion-status`.

### Ha logs brutos, mas nao ha incidente

Confirme se o padrao de evento dispara a regra SIEM. Para port scan, o teste
deve gerar conexoes de uma mesma origem para varias portas dentro da janela de
deteccao.

### Frontend nao atualiza tickets/widgets

Verifique o stream realtime:

```txt
GET /api/events/stream
```

Confira tambem logs dos containers:

```bash
docker compose logs -f api siem-kowalski web
```

## 12. Implantacao com TLS

Para ambiente com hostname publico ou laboratorio com reverse proxy, use o
overlay de producao:

```bash
export PENGUARD_PUBLIC_HOSTNAME=forti.example.com
export CADDY_TLS_MODE=
export CADDY_ADMIN_EMAIL=ops@example.com

docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Rotas esperadas:

| Rota | Destino |
| --- | --- |
| `https://<host>/` | Cockpit Vue |
| `https://<host>/api/*` | BFF FastAPI |
| `https://<host>/auth/*` | Keycloak |

Para laboratorio sem dominio publico, `CADDY_TLS_MODE=internal` usa certificado
interno do Caddy.

## 13. Limites de seguranca

- Nao commitar `.env`, keytabs, certificados privados, tokens, senhas ou IPs de
  laboratorio que identifiquem cliente.
- Acoes de FortiGate devem passar pelo BFF, com RBAC, preflight, diff/resumo,
  aprovacao explicita e auditoria.
- Playbooks gerados por IA sao rascunhos ate revisao humana.
- Replay sintetico e simuladores sao lab-only e nao substituem validacao com
  FortiGate/syslog/endpoint reais.
- Nao aplicar mudancas destrutivas, silenciosas ou automaticas no FortiGate.

## 14. Referencias internas

- `README.md`
- `AGENTS.md`
- `docs/operations/README.md`
- `docs/operations/vmware-soc-lab-blackarch-arch.md`
- `docs/operations/fortigate-scan-detection.md`
- `docs/mvp/windows-server-agent-smoke.md`
- `docs/architecture/realtime-telemetry-flow.md`
- `docs/architecture/threat-model.md`
