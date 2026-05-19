# Lab de Brute Force FortiGate — Guia de Demo

Este guia leva o operador de lab ponta a ponta: provocar um incidente
`repeated_failed_login` a partir de uma VM Debian atacante e confirmar o
alerta resultante nos widgets do Penguard. Assume que você é dono
da VM FortiGate e da VM Debian (uso autorizado de laboratório).

Última atualização: 2026-05-14.

## Topologia

```
[VM Debian]──vmnet2 (LAN)──[FortiGate port2]──[FortiGate port1]──vmnet8 (WAN/NAT)──host
   192.168.50.10            192.168.50.1         192.168.23.x
```

Observações:

- A VM atacante precisa estar em um segmento de rede onde o FortiGate é o
  gateway padrão. Duas VMs bridged no mesmo `/24` ficam no segmento L2 e
  o firewall nunca roteia os pacotes — logs de Forward Traffic ficam
  vazios. Veja AGENTS.md "Known Lab Setup Issues" para o contexto
  completo.
- O alvo do brute force precisa estar do **outro lado** do FortiGate. Ou
  o próprio FortiGate (SSH na interface LAN) ou um host na WAN.

## Fase 1 — Configurar o FortiGate

### 1.1 Usuário de API read-only

```text
config system accprofile
    edit "fdashboard_ro"
        set system read
        set fwgrp read
        set logrpt read
    next
end

config system api-user
    edit "fdashboard"
        set accprofile "fdashboard_ro"
        set vdom "root"
        config trusthost
            edit 1
                set ipv4-trusthost 192.168.50.0 255.255.255.0
            next
        end
    next
end

execute api-user generate-key fdashboard
```

Copie a chave gerada — você vai colá-la no cockpit (fase 2).

### 1.2 Política LAN→WAN com log de tráfego

```text
config firewall policy
    edit 0
        set name "LAN_TO_WAN_DEMO"
        set srcintf "port2"
        set dstintf "port1"
        set srcaddr "all"
        set dstaddr "all"
        set action accept
        set schedule "always"
        set service "ALL"
        set logtraffic all
        set logtraffic-start enable
    next
end
```

Políticas sem `set logtraffic all` deixam os widgets vazios mesmo quando
pacotes estão cruzando as interfaces.

### 1.3 Auditoria de tentativas de login

```text
config system global
    set admin-lockout-threshold 5
    set admin-lockout-duration 60
end

config log memory setting
    set status enable
end

config log memory filter
    set forward-traffic enable
    set local-traffic enable
    set event enable
    set system-config enable
    set anomaly enable
end
```

`local-traffic enable` + `event enable` é o que faz tentativas SSH contra
o próprio FortiGate aparecerem no event log.

## Fase 2 — Conectar a integração no Penguard

No cockpit: Sidebar → Integrations → Add → **FortiGate**.

| Campo | Valor |
| --- | --- |
| Name | `lab-fortigate` |
| Host | `192.168.50.1` (IP da port2) |
| API key | a chave gerada em 1.1 |
| Verify SSL | desligado (certificado self-signed) |

Salve. O cockpit executa um probe read-only — se passar, a integração
fica verde. O widget `System Status` deve mostrar o hostname e a versão
de firmware reais. Valores vazios apontam para problema na credencial
ou no CIDR do `trusthost` não cobrindo o container do BFF.

## Fase 3 — Brute force a partir da VM Debian

### 3.1 Instalar o hydra

```bash
sudo apt update && sudo apt install -y hydra
```

### 3.2 Dicionários pequenos

```bash
cat > /tmp/users.txt <<'EOF'
admin
root
fortigate
EOF

cat > /tmp/pass.txt <<'EOF'
admin
password
123456
fortinet
P@ssw0rd
toor
letmein
admin123
qwerty
abc123
fortinet123
admin1
admin@123
EOF
```

### 3.3 Disparar o ataque

Contra o SSH admin do FortiGate:

```bash
hydra -L /tmp/users.txt -P /tmp/pass.txt -t 4 -f ssh://192.168.50.1
```

Flags:

- `-t 4` — quatro threads paralelas.
- `-f` — para no primeiro hit. Aqui todas as tentativas devem falhar e
  você quer o sweep inteiro, então o `-f` é puramente defensivo.

Alvo alternativo na WAN (força a política LAN→WAN a logar):

```bash
hydra -L /tmp/users.txt -P /tmp/pass.txt -t 4 ssh://192.168.23.5
```

O dicionário combinado acima produz 39 tentativas (`3 usuários × 13
senhas`), bem acima do threshold da detecção `repeated_failed_login`
depois que o agregador do backend colapsa os eventos por source IP.

## Fase 4 — Ingerir eventos do FortiGate no SIEM

A ingestão FortiGate → SIEM é manual hoje (veja AGENTS.md "Known Lab
Setup Issues"). Pegue o `integrationId` do FortiGate na sidebar
(painel Integrations, expanda o card FortiGate) e chame:

```bash
curl -X POST "http://localhost:8000/api/soc/fortigate/INT_FGT_ID/ingest-events" \
  -H "Cookie: f_session=..." \
  -H "X-CSRF-Token: ..."
```

O payload de resposta inclui `rawEventCount` e `createdCount` (agregados
por `(eventType, sourceIp)`). O
`apps/api/app/routers/integrations.py` `_aggregate_fortigate_events()` é
o que faz `attributes.count` cruzar o threshold de detecção — sem ele
cada evento cru iria com `count=1` e `repeated_failed_login` nunca
dispararia.

Se você quer apenas validar a pipeline do cockpit sem depender de
tráfego real do FortiGate, use o painel **MVP Demo Replay** dentro do
cockpit (`POST /api/soc/demo/replay`). Ele injeta eventos canônicos de
port-scan / brute-force / beacon diretamente no `siem_kowalski`.

## Fase 5 — Verificar no dashboard

Depois da chamada de ingest:

1. O widget **Recent Incidents** mostra um novo incidente
   `repeated_failed_login` dentro de um ciclo de poll (≈5 s).
2. O widget **Incidents by Severity** incrementa a barra `medium` ou
   `high`.
3. O widget **SLA Breach** continua verde enquanto o incidente está
   fresco (< 15 min).
4. O widget **Top Source IPs** (FortiGate) lista `192.168.50.10` (Debian)
   no topo com os counts denied/total.
5. O heat-strip no header do workspace mostra a soma agregada de
   severidade.
6. As sparklines dos KPIs sobem no poll seguinte.

## Fase 6 — Troubleshooting

| Sintoma | Causa provável | Fix |
| --- | --- | --- |
| `Recent Events` vazio | Política sem `logtraffic all` | Refaz a fase 1.2 |
| Widget FortiGate mostra "Connection invalid" | API key errada ou CIDR do `trusthost` não cobre o BFF | Verifica que o trusthost aceita o IP do container API |
| Hydra falha imediato com `connect refused` | SSH desligado ou `allowaccess` sem ssh | `set allowaccess ssh https` na interface LAN |
| Tentativas chegam, incidente não aparece | Agregador não atingiu o threshold da detecção | Aumenta o dicionário pra produzir ≥ 20 tentativas |
| VM bridged, FortiGate não vê nada | Bypass L2 clássico no mesmo `/24` | Move o Debian pra um segmento LAN dedicado com o FortiGate como gateway padrão |
| `denied_traffic_burst` esperado, nunca dispara | Per AGENTS.md a regra precisa `attributes.count >= 20` num evento só | O agregador já resolve; confirma pelas linhas de log `soc_widget_data_*` que o count agregado tá alto o suficiente |
| FortiGate sobe com aviso "File System Check Recommended" | Reboot inseguro anterior | Roda `execute disk list` e depois `execute disk scan <ref>` antes de gravar qualquer demo |

### Logs úteis no host

```bash
docker compose logs -f api | grep -E "fortigate|siem|soc_widget"
docker compose logs -f siem-kowalski | grep -E "detection|incident"
```

Padrões esperados:

- `soc_widget_data_ready widget_id=fortigate-recent-events ...`
- `siem detection_fired rule=repeated_failed_login count=N source_ip=192.168.50.10`
- `soc_widget_data_ready widget_id=soc-recent-incidents incidents=1`

## Lembretes de segurança

- Brute force é teste destrutivo. Só rode contra ativos que você
  controla.
- Nunca commite a API key gerada nem as senhas do lab no repositório.
  `.env.local`, `penguard.keytab` e similares estão no gitignore
  de propósito.
- O CIDR do `trusthost` no usuário de API do FortiGate precisa
  permanecer estreito (`/24` da rede do BFF no máximo). Afrouxar isso
  remove a única guarda de rede que a key read-only tem.
