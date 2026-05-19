# Como usar Threat Intel no Penguard

Este guia descreve o que precisa estar configurado para usar o enriquecimento
de incidentes com Threat Intel e para transformar telemetria Sysmon suspeita em
incidentes SOC.

## O que foi implementado

- O BFF extrai indicadores de incidentes existentes: IPs, dominios e URLs.
- URLs sao sanitizadas para `scheme://host[:port]`, sem path, query string ou
  fragmento.
- O provider inicial e VirusTotal API v3.
- Resultados sao normalizados para `clean`, `unknown`, `suspicious` ou
  `malicious`.
- O enriquecimento manual fica no drawer de Tickets SOC.
- Eventos Sysmon `3` e `22` enviados pelo `agent_private` podem ser
  enriquecidos antes de serem persistidos no XDR.
- Se o verdict Sysmon for `suspicious` ou `malicious`, o BFF cria evento SIEM
  `endpoint.suspicious_connection`.
- Toda chamada manual de enriquecimento de incidente gera evento de auditoria.

## Configurar o provider

Edite o `.env` local ou o segredo equivalente do deploy:

```env
PENGUARD_THREAT_INTEL_PROVIDER=virustotal
PENGUARD_THREAT_INTEL_CACHE_TTL_SECONDS=3600
PENGUARD_VIRUSTOTAL_API_KEY=<sua-chave>
PENGUARD_VIRUSTOTAL_BASE_URL=https://www.virustotal.com
```

Nao versionar chave real. A chave deve ficar apenas em `.env`, secret manager
ou variavel de ambiente do ambiente.

Depois de alterar variaveis da API em Docker:

```bash
docker compose up -d --build api
```

Sem `PENGUARD_VIRUSTOTAL_API_KEY`, o recurso continua disponivel na UI,
mas retorna `providerConfigured=false` e nao faz chamada externa.

## Preparar telemetria Windows

Para ver sites/destinos suspeitos acessados pelo Windows Server:

1. Instale Sysmon no Windows.
2. Habilite eventos `NetworkConnect` e `DnsQuery`.
3. Enrole o host no Penguard pelo painel Endpoints.
4. Rode o `agent_private` com Sysmon:

```powershell
uv run agent-private run-headless `
  --heartbeat-interval 30 `
  --connection-interval 60 `
  --process-interval 300 `
  --windows-security-interval 60 `
  --sysmon-interval 60
```

O runbook completo fica em `WINDOWS_SERVER_EDR_SYSMON.md`.

## Usar no cockpit

1. Abra Tickets SOC.
2. Abra um incidente.
3. Clique em `Threat Intel` -> `Enriquecer`.
4. Revise a contagem de indicadores maliciosos, suspeitos, limpos e
   desconhecidos.
5. Verifique os indicadores sinalizados e o link de referencia do provider.

O enriquecimento adiciona uma nota de triagem no incidente. Ele nao bloqueia IP,
nao altera FortiGate e nao executa playbook automaticamente.

## Validar

Backend:

```bash
cd apps/api
UV_CACHE_DIR=/home/guest/penguard/.uv-cache \
RUFF_CACHE_DIR=/home/guest/penguard/.ruff-cache \
uv run pytest tests/test_threat_intel.py tests/test_soc_gateway.py -q
```

Endpoint manual:

```bash
POST /api/soc/incidents/{incidentId}/threat-intel/enrich
```

Fluxo Sysmon:

```powershell
uv run agent-private sysmon --post --limit 50
```

Depois confira:

- endpoint timeline no XDR;
- incidente `endpoint.suspicious_connection` no SIEM, quando o verdict for
  `suspicious` ou `malicious`;
- auditoria `soc.incident.threat_intel_enriched` para enriquecimento manual.

## Privacidade e limites

- Nao envie URL completa por padrao.
- Nao envie payload bruto inteiro do endpoint ao provider externo.
- Nao inclua tokens, cookies, headers, credenciais ou query strings.
- Respeite quota e termos do provider configurado.
- Resultados de Threat Intel sao contexto de triagem, nao autorizacao automatica
  de bloqueio.

Referencias oficiais:

- VirusTotal API v3 Overview: https://docs.virustotal.com/reference/overview
- VirusTotal IP report: https://docs.virustotal.com/reference/ip-info
- VirusTotal URL identifiers: https://docs.virustotal.com/reference/url
