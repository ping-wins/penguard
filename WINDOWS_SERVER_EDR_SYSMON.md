# Windows Server EDR + Sysmon Setup

Este runbook descreve as configuracoes necessarias em um Windows Server para
enviar telemetria de endpoint ao FortiDashboard e permitir enriquecimento de
IPs/dominios/URLs suspeitos com Threat Intel.

Status atual:

- `agent_private` ja envia `heartbeat`, `process.snapshot`,
  `connection.snapshot` e eventos do Windows Security Log.
- Sysmon deve ser instalado no Windows para gerar eventos ricos de rede e DNS.
- `agent_private sysmon` le eventos Sysmon `3` e `22` e os normaliza como
  `sysmon.network_connection` e `sysmon.dns_query`.
- `connection.snapshot` via `psutil` continua funcionando como fallback para
  IP/porta/processo quando Sysmon nao estiver disponivel.
- O BFF encaminha eventos Sysmon para o SIEM quando eles carregam
  `threatIntelVerdict` igual a `suspicious` ou `malicious`.
- O BFF consulta o provider de Threat Intel configurado, como VirusTotal,
  enriquece incidentes sob demanda e pode enriquecer eventos Sysmon antes de
  encaminhar ao SIEM.

## Objetivo

Permitir que o FortiDashboard veja:

- quais processos abriram conexoes de rede;
- quais IPs e portas foram acessados;
- quais dominios foram consultados por processo, quando Sysmon estiver ativo;
- quais destinos devem ser enriquecidos por Threat Intel;
- quais acessos devem gerar incidente `endpoint.suspicious_connection`.

O fluxo esperado e:

```txt
Windows Server -> Sysmon -> Windows Event Log
Windows Server -> agent_private -> apps/api -> xdr_rico
apps/api -> Threat Intel provider, quando houver chave configurada
apps/api -> siem_kowalski, quando o verdict for suspicious/malicious
```

## Pre-requisitos

No FortiDashboard:

- `api`, `xdr-rico` e `siem-kowalski` rodando.
- Endpoint enrollment criado no painel Endpoints.
- URL do BFF acessivel a partir do Windows Server, por exemplo
  `http://<fortidashboard-host>:8000`.

No Windows Server:

- Windows Server 2016 ou superior.
- PowerShell executado como Administrador para instalar o Sysmon.
- Permissao de saida HTTPS/HTTP ate o FortiDashboard BFF.
- Checkout do repositorio FortiDashboard, ou pacote do `agent_private`, no host.
- `uv` disponivel para executar `agent-private`.

Nunca cole tokens reais em arquivos versionados. O token de enrollment e
retornado uma unica vez e deve ser tratado como segredo.

## Instalar Sysmon

Baixe o Sysmon somente da pagina oficial da Microsoft Sysinternals:

```txt
https://learn.microsoft.com/en-us/sysinternals/downloads/sysmon
```

Extraia em um diretorio operacional, por exemplo:

```powershell
New-Item -ItemType Directory -Force C:\FortiDashboard\Sysmon
```

Copie `Sysmon64.exe` para esse diretorio e crie
`C:\FortiDashboard\Sysmon\sysmon-fortidashboard.xml` com uma configuracao
enxuta.

Configuracao inicial recomendada:

```xml
<Sysmon schemaversion="4.82">
  <HashAlgorithms>SHA256</HashAlgorithms>
  <DnsLookup>true</DnsLookup>
  <EventFiltering>
    <ProcessCreate onmatch="include">
      <Image condition="end with">powershell.exe</Image>
      <Image condition="end with">pwsh.exe</Image>
      <Image condition="end with">cmd.exe</Image>
      <Image condition="end with">wscript.exe</Image>
      <Image condition="end with">cscript.exe</Image>
      <Image condition="end with">mshta.exe</Image>
      <Image condition="end with">rundll32.exe</Image>
      <Image condition="end with">regsvr32.exe</Image>
      <Image condition="end with">curl.exe</Image>
      <Image condition="end with">certutil.exe</Image>
    </ProcessCreate>

    <NetworkConnect onmatch="include">
      <DestinationPort>80</DestinationPort>
      <DestinationPort>443</DestinationPort>
      <DestinationPort>8080</DestinationPort>
      <DestinationPort>8443</DestinationPort>
      <DestinationPort>53</DestinationPort>
    </NetworkConnect>

    <DnsQuery onmatch="exclude">
      <QueryName condition="end with">.local</QueryName>
      <QueryName condition="end with">.lan</QueryName>
      <QueryName condition="is">localhost</QueryName>
    </DnsQuery>
  </EventFiltering>
</Sysmon>
```

Instale:

```powershell
Set-Location C:\FortiDashboard\Sysmon
.\Sysmon64.exe -accepteula -i .\sysmon-fortidashboard.xml
```

Atualizar configuracao depois:

```powershell
.\Sysmon64.exe -c .\sysmon-fortidashboard.xml
```

Remover em laboratorio, se necessario:

```powershell
.\Sysmon64.exe -u
```

## Eventos Sysmon usados

O FortiDashboard deve consumir principalmente:

| Sysmon Event ID | Uso |
| --- | --- |
| `1` | Processo criado, linha de comando e hash SHA256. |
| `3` | Conexao de rede com processo, IP/porta de origem e destino. |
| `22` | Consulta DNS com processo e dominio consultado. |

Evento `3` e desabilitado por padrao no Sysmon se nao houver configuracao de
`NetworkConnect`. Evento `22` exige Windows 8.1/Server 2012 R2 ou superior.

## Validar eventos no Windows

Confirmar que o log existe:

```powershell
Get-WinEvent -ListLog Microsoft-Windows-Sysmon/Operational
```

Gerar uma conexao de teste:

```powershell
Invoke-WebRequest https://example.com -UseBasicParsing
```

Ver ultimos eventos de conexao e DNS:

```powershell
Get-WinEvent -LogName Microsoft-Windows-Sysmon/Operational -MaxEvents 20 |
  Where-Object { $_.Id -in 3, 22 } |
  Select-Object TimeCreated, Id, ProviderName, Message
```

Se nao aparecerem eventos `3`, revise a configuracao `NetworkConnect`.
Se nao aparecerem eventos `22`, revise a versao do Windows e a configuracao
`DnsQuery`.

## Configurar retencao do Event Log

Aumente o tamanho do log Sysmon para reduzir perda de eventos em hosts ativos:

```powershell
wevtutil sl Microsoft-Windows-Sysmon/Operational /ms:67108864
```

Valor acima: 64 MiB. Ajuste conforme volume do servidor.

## Permissoes para leitura

Instalar ou atualizar Sysmon exige Administrador.

Para leitura pelo `agent_private`, use uma destas abordagens:

- executar o agente em terminal elevado durante laboratorio;
- adicionar a conta operacional ao grupo local `Event Log Readers`;
- rodar futuramente por Scheduled Task explicita com uma conta de servico
  autorizada.

Adicionar conta ao grupo:

```powershell
Add-LocalGroupMember -Group "Event Log Readers" -Member "<DOMAIN\user>"
```

Nao instale persistencia escondida. Para MVP, o fluxo preferido continua sendo
TUI ou foreground headless. Execucao em background deve ser uma Scheduled Task
explicita e auditavel.

## Configurar agent_private

No painel Endpoints do FortiDashboard:

1. Clique em adicionar endpoint Windows.
2. Gere o enrollment.
3. Copie o comando PowerShell retornado.
4. Execute no Windows Server a partir do checkout do repositorio.

Formato do comando:

```powershell
cd apps\agent_private
$env:AGENT_PRIVATE_API_URL = "http://<fortidashboard-host>:8000"
$env:AGENT_PRIVATE_ENDPOINT_ID = "<enrollment-id>"
$env:AGENT_PRIVATE_ENROLLMENT_TOKEN = "<token-returned-once>"
uv run agent-private run
```

Coleta Sysmon one-shot:

```powershell
uv run agent-private sysmon --limit 50
uv run agent-private sysmon --limit 50 --post
```

Para modo headless em laboratorio:

```powershell
cd apps\agent_private
$env:AGENT_PRIVATE_API_URL = "http://<fortidashboard-host>:8000"
$env:AGENT_PRIVATE_ENDPOINT_ID = "<enrollment-id>"
$env:AGENT_PRIVATE_ENROLLMENT_TOKEN = "<token-returned-once>"

uv run agent-private run-headless `
  --heartbeat-interval 30 `
  --connection-interval 60 `
  --process-interval 300 `
  --windows-security-interval 60 `
  --sysmon-interval 60
```

O argumento `--sysmon-interval` ativa a leitura recorrente do log
`Microsoft-Windows-Sysmon/Operational`.

## Windows Security Log opcional

Para complementar rede/DNS com autenticacao e arquivos:

```powershell
uv run agent-private windows-security --limit 50
uv run agent-private windows-security --limit 50 --post
```

Eventos ja normalizados:

- `4625`: logon falhou, vira `auth.failed_login`.
- `4672`: logon com privilegios especiais, vira `auth.privileged_logon`.
- `4663`: acesso a objeto auditado, vira `file.change`.

Para `4663`, habilite auditoria de Object Access e configure auditoria na pasta
testada. Nao monitore diretorios grandes sem filtro.

## Como o Threat Intel deve usar os dados

Configure no `.env` do FortiDashboard:

```env
FORTIDASHBOARD_THREAT_INTEL_PROVIDER=virustotal
FORTIDASHBOARD_THREAT_INTEL_CACHE_TTL_SECONDS=3600
FORTIDASHBOARD_VIRUSTOTAL_API_KEY=<sua-chave>
FORTIDASHBOARD_VIRUSTOTAL_BASE_URL=https://www.virustotal.com
```

Depois de editar variaveis da API em Docker, reconstrua o container:

```bash
docker compose up -d --build api
```

O enriquecimento deve consultar somente IoCs minimizados:

- IP remoto;
- dominio consultado;
- URL sanitizada no formato `scheme://host`, sem path, query string ou fragmento.

Nao envie URL completa por padrao. Paths e query strings podem conter tokens,
nomes de arquivos, parametros internos ou dados pessoais.

Mapeamento esperado:

| Origem | IoC extraido | Uso |
| --- | --- | --- |
| Sysmon Event `3` | Destination IP, Destination Port, Image | reputacao IP + processo responsavel |
| Sysmon Event `22` | QueryName, Image | reputacao dominio + processo responsavel |
| `connection.snapshot` fallback | remoteAddress.ip, remoteAddress.port, pid | reputacao IP quando Sysmon nao estiver disponivel |

Se Threat Intel retornar `malicious` ou `suspicious`, o BFF grava o verdict no
evento XDR como `threatIntelVerdict` e cria evento SIEM
`endpoint.suspicious_connection` com:

- `endpointId`;
- `hostname`;
- `username`, quando disponivel;
- `sourceIp`;
- `destinationIp`;
- `domain`;
- `processName` ou `image`;
- `threatIntelVerdict`;
- `threatIntelProvider`;
- `xdrTimelineItemId`.

## Validacao no FortiDashboard

Depois de iniciar o agente:

1. Abra o painel Endpoints.
2. Confirme que o Windows Server aparece online.
3. Confira heartbeat, processos e conexoes na timeline.
4. Gere uma conexao de teste:

   ```powershell
   Invoke-WebRequest https://example.com -UseBasicParsing
   ```

5. Confirme no Windows que Sysmon gerou eventos `3` e `22`.
6. Rode `uv run agent-private sysmon --post --limit 50` ou inicie o loop com
   `--sysmon-interval 60` e confirme que os dominios/IPs aparecem na timeline
   do endpoint.
7. Enriqueca o incidente ou IoC no FortiDashboard e verifique o verdict.

## Troubleshooting

Sysmon nao instala:

- confirme PowerShell como Administrador;
- confirme que `Sysmon64.exe` veio da Microsoft Sysinternals;
- rode `.\Sysmon64.exe -s` para validar schema suportado.

Sem eventos `3`:

- confira se `NetworkConnect` existe no XML;
- gere trafego novo depois da instalacao;
- rode `.\Sysmon64.exe -c` para ver a configuracao ativa.

Sem eventos `22`:

- confirme versao do Windows;
- confira filtro `DnsQuery`;
- teste resolucao DNS com `Resolve-DnsName example.com`.

Endpoint nao aparece no FortiDashboard:

- confira `AGENT_PRIVATE_API_URL`;
- confira conectividade de rede ate `/health`;
- confirme que o token de enrollment nao foi trocado ou expirado;
- confira logs do `api` e do `xdr-rico`.

Eventos chegam no XDR, mas nao viram incidente:

- incidentes so devem ser criados quando houver evidencia suspeita;
- confirme se a conexao foi marcada como suspeita ou enriquecida como
  `suspicious`/`malicious`;
- confira se `siem-kowalski` esta saudavel.

## Seguranca e privacidade

- Nao capture URL completa por padrao.
- Nao envie payload bruto inteiro do endpoint para providers externos.
- Nao colete conteudo de pagina, cookies, headers ou credenciais.
- Nao aprove bloqueio automatico por IA ou Threat Intel.
- Qualquer acao de bloqueio deve passar por RBAC, aprovacao explicita,
  preflight, diff/summary, rollback guidance e auditoria.
- Use somente tokens de enrollment de laboratorio durante testes.
