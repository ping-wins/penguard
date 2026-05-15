# FortiWeb DoS Lab: Attacker → FortiWeb WAF → Victim

Runbook para adicionar FortiWeb à topologia VMware existente
(`vmware-soc-lab-blackarch-arch.md`) e validar detecção de DoS no FortiDashboard.

Pré-requisito: lab FortiGate + BlackArch + Arch Linux já configurado e
funcional conforme `vmware-soc-lab-blackarch-arch.md`.

Versão testada do FortiWeb: **8.0.5 trial**.

---

## Topologia final

```txt
Host machine (Docker Compose - FortiDashboard)
└── VMware
    ├── FortiGate VM
    │   ├── port2 → SOC_LAN  10.10.10.1/24   (BlackArch)
    │   ├── port3 → SOC_DMZ  10.10.20.1/24   (Arch victim)
    │   └── port4 → SOC_WAF  10.10.30.1/24   (FortiWeb)  ← NOVO
    ├── BlackArch VM          10.10.10.10     (atacante)
    ├── FortiWeb VM           10.10.30.10     (WAF)       ← NOVO
    └── Arch Linux victim VM  10.10.20.10     (vítima)

Fluxo de ataque:
  BlackArch → FortiGate → FortiWeb (WAF detecta DoS)
                                  ↓ reverse proxy
                              Arch victim :8080

Fluxo de telemetria:
  FortiWeb → HTTP POST → FortiDashboard /api/soc/ingest/fortiweb
           → siem_kowalski → incidente waf.dos
           → SSE → cockpit (widget + toast)
```

---

## 1. VMware: nova rede SOC_WAF

No VMware Virtual Network Editor:

| Network     | Type        | DHCP | Subnet         | Propósito           |
|-------------|-------------|------|----------------|---------------------|
| `SOC_WAF`   | LAN Segment | Off  | 10.10.30.0/24  | FortiWeb isolado    |

Não usar VMnet compartilhado com SOC_LAN ou SOC_DMZ.

---

## 2. FortiGate: adicionar port4 e políticas WAF

### 2.1 Tirar snapshot do FortiGate antes

No VMware, tirar snapshot da VM FortiGate antes de adicionar NIC.

### 2.2 Adicionar NIC ao FortiGate VM

No VMware VM Settings da FortiGate VM:
- Add → Network Adapter → LAN Segment `SOC_WAF`
- Manter MACs existentes intactos (licença vinculada ao MAC)

### 2.3 Configurar port4 no FortiGate CLI ou GUI

```
config system interface
    edit "port4"
        set alias "SOC_WAF"
        set ip 10.10.30.1 255.255.255.0
        set allowaccess ping https
        set role lan
    next
end
```

Verificar:

```bash
# FortiGate CLI
get system interface | grep -A5 port4
```

### 2.4 Políticas de tráfego

**Política 1 — BlackArch → FortiWeb (SOC_LAN → SOC_WAF):**

```
config firewall policy
    edit 0
        set name "LAN_to_WAF_allow_log"
        set srcintf "port2"
        set dstintf "port4"
        set srcaddr "all"
        set dstaddr "all"
        set action accept
        set schedule "always"
        set service "ALL"
        set logtraffic all
    next
end
```

**Política 2 — FortiWeb → Arch victim (SOC_WAF → SOC_DMZ):**

```
config firewall policy
    edit 0
        set name "WAF_to_DMZ_allow_log"
        set srcintf "port4"
        set dstintf "port3"
        set srcaddr "all"
        set dstaddr "all"
        set action accept
        set schedule "always"
        set service "ALL"
        set logtraffic all
    next
end
```

---

## 3. Arch Linux victim: subir serviço web

No Arch victim (10.10.20.10):

```bash
# Instalar nginx se não tiver
sudo pacman -Syu --needed nginx

# Criar página de lab
sudo mkdir -p /srv/http/lab
echo '<html><body><h1>Lab victim</h1></body></html>' | sudo tee /srv/http/lab/index.html

# Configurar nginx na porta 8080
sudo tee /etc/nginx/servers/lab.conf <<'EOF'
server {
    listen 8080;
    root /srv/http/lab;
    index index.html;

    location /demo/search {
        add_header Content-Type text/plain;
        return 200 "search: $arg_q\n";
    }

    location /api/contact {
        add_header Content-Type application/json;
        return 200 '{"status":"ok"}';
    }
}
EOF

sudo nginx -t && sudo systemctl enable --now nginx
```

Verificar localmente:

```bash
curl http://10.10.20.10:8080/
curl "http://10.10.20.10:8080/demo/search?q=test"
```

---

## 4. FortiWeb VM: setup inicial

### 4.1 Obter trial

- Baixar `.ova` do FortiWeb 8.0.5 trial em fortinet.com/trial
- Importar no VMware via File → Import OVF

### 4.2 Adapters da VM FortiWeb

| Adapter | VMware network  | IP           | Gateway      | Propósito              |
|---------|-----------------|--------------|--------------|------------------------|
| port1   | LAN Segment `SOC_WAF` | 10.10.30.10/24 | 10.10.30.1 | tráfego WAF + mgmt     |
| port2   | Host-only `SSH_ADMIN` | DHCP       | —            | acesso admin do host   |

### 4.3 Acesso inicial ao FortiWeb

FortiWeb boot padrão expõe GUI em `https://192.168.1.99` ou via console serial.

Via console VMware:
```
login: admin
password: (em branco no primeiro boot)
```

Configurar IP de management:
```
config system interface
    edit port1
        set ip 10.10.30.10/24
        set allowaccess https http ping ssh
    next
end
config router static
    edit 1
        set gateway 10.10.30.1
        set device port1
    next
end
```

Acessar GUI: `https://10.10.30.10` pelo host (via Host-only ou tunnel se necessário).

### 4.4 Licença trial

Na GUI: System → FortiGuard → License → Enter license key (trial key do email Fortinet).

---

## 5. FortiWeb: configurar reverse proxy e DoS policy

### 5.1 Server Pool (backend = Arch victim)

GUI: **Server Objects → Servers → Server Pool**

```
New Server Pool:
  Name: victim-pool
  Type: Reverse Proxy

  Add Server:
    IP: 10.10.20.10
    Port: 8080
    Status: Enable
```

### 5.2 Virtual Server (escuta o tráfego do atacante)

GUI: **Server Objects → Servers → Virtual Server**

```
New Virtual Server:
  Name: lab-vserver
  IP: 10.10.30.10
  Port: 80
  Status: Enable
```

### 5.3 Server Policy

GUI: **Policy → Server Policy**

```
New Server Policy:
  Name: lab-dos-policy
  Virtual Server: lab-vserver
  Server Pool: victim-pool
  HTTP Service: HTTP
  Enable: yes

  Web Protection Profile: (criar abaixo)
  DoS Protection: (criar abaixo)
```

### 5.4 DoS Protection Policy

GUI: **DoS Protection → Application → HTTP Flood Prevention**

```
New HTTP Flood Prevention:
  Name: lab-dos-flood
  Status: Enable

  HTTP Request Flood:
    Real Browser Enforcement: Enable
    Threshold (req/s per source IP): 50
    Action: Alert & Deny
    Severity: Critical

  HTTP Request Rate Limit:
    Limit (req/s per URL): 100
    Action: Alert & Deny

  Slow HTTP Attack:
    Status: Enable
    Action: Alert & Deny
```

GUI: **DoS Protection → Network → Network DoS Policy**

```
New Network DoS Policy:
  Name: lab-dos-network
  SYN Flood: Enable  (threshold: 200/s)
  Action: Drop
```

Associar ao Server Policy:
```
Server Policy lab-dos-policy:
  DoS Protection: lab-dos-flood
```

### 5.5 Web Protection Profile

GUI: **Policy → Web Protection Profile**

```
New Profile:
  Name: lab-waf-profile
  Signature Protection: Enable (default ruleset)
  HTTP Protocol Constraints: Enable
```

Associar ao Server Policy:
```
Server Policy lab-dos-policy:
  Web Protection Profile: lab-waf-profile
```

---

## 6. FortiWeb: configurar log push para FortiDashboard

FortiWeb suporta envio de attack logs via Syslog ou HTTP trigger.
Usar **Trigger (HTTP)** para enviar ao endpoint de ingestão.

### 6.1 Obter token de ingestão

No host, verificar `.env` do FortiDashboard:

```bash
grep SOC_INGEST_TOKEN apps/api/.env
```

Se vazio, gerar:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Adicionar ao `.env`:
```
SOC_INGEST_TOKEN=<token_gerado>
```

Reiniciar API:
```bash
docker compose up -d --build api
```

### 6.2 Descobrir IP do host acessível pela SOC_WAF

O FortiWeb (10.10.30.10) precisa alcançar o FortiDashboard API no host.
Verificar IP do host na rede SOC_WAF ou usar Host-only:

```bash
# No host PowerShell
ipconfig | Select-String "VMware\|10\.10\."
```

IP do host na SOC_WAF tipicamente: **10.10.30.1** (gateway FortiGate port4 não é o host direto).

Alternativa: usar Host-only VMnet IP do host (ex: 192.168.100.1) se FortiWeb tiver adapter Host-only.

Se não há rota direta, adicionar adapter Host-only ao FortiWeb port2 conforme seção 4.2 e usar esse IP.

### 6.3 Configurar Trigger no FortiWeb

GUI: **Log & Report → Log Policy → Trigger**

```
New Trigger:
  Name: fortidashboard-push
  Type: HTTP

  URL: http://<HOST_IP>:8000/api/soc/ingest/fortiweb
  Method: POST
  Content-Type: application/json

  HTTP Headers:
    Authorization: Bearer <SOC_INGEST_TOKEN>
    X-FortiDashboard-Integration-Id: fortiweb-lab
```

### 6.4 Associar Trigger ao Log Policy

GUI: **Log & Report → Log Policy**

```
Attack Log Policy:
  Trigger: fortidashboard-push
  Severity: Information and above
  Enable: yes
```

Associar ao Server Policy:
```
Server Policy lab-dos-policy:
  Log Policy: (política acima)
```

### 6.5 Testar push manualmente

No FortiWeb CLI:
```
execute log-trigger test fortidashboard-push
```

Verificar no host:
```bash
docker compose logs api --tail=20 | grep fortiweb
```

Deve aparecer: `soc.fortiweb_events.ingested`.

---

## 7. BlackArch: ferramentas de ataque

No BlackArch (10.10.10.10):

```bash
# Instalar ferramentas de HTTP flood
sudo pacman -Syu --needed apache-tools hping3

# Verificar rota ao FortiWeb
ip route get 10.10.30.10
# deve mostrar via 10.10.10.1 (FortiGate)

ping -c 3 10.10.30.10
```

---

## 8. Fluxo de validação

### 8.1 Verificar conectividade antes do ataque

```bash
# BlackArch → FortiWeb virtual server
curl http://10.10.30.10/
# esperado: página do Arch victim via FortiWeb
```

### 8.2 Watch nos logs do FortiDashboard

No host, antes de atacar:
```bash
docker compose logs -f api siem_kowalski
```

### 8.3 Executar HTTP flood controlado

No BlackArch:

```bash
# HTTP flood com ab (Apache Bench) — 500 requests, 50 concorrentes
ab -n 500 -c 50 http://10.10.30.10/

# Ou com hey — 20 segundos, 50 workers
hey -z 20s -c 50 http://10.10.30.10/

# Ou hping3 SYN flood (L4) — 30 segundos
sudo hping3 -S --flood -p 80 --count 10000 10.10.30.10
```

**Limites de segurança:**
- Atacar apenas `10.10.30.10` (FortiWeb lab)
- Duração máxima: 30 segundos por teste
- Não rodar contra IPs fora da sub-rede lab
- Parar imediatamente se a VM do host ficar sem recursos

### 8.4 Verificar logs no FortiWeb

GUI FortiWeb: **Log & Report → Attack Log**

Esperado:
- Entries com `subtype: dos` ou `main_type: DoS`
- `src: 10.10.10.10`
- `action: block` ou `deny`
- Trigger disparado (ícone na entrada de log)

### 8.5 Verificar ingestão no FortiDashboard

```bash
docker compose logs api --tail=50 | grep -E "fortiweb|ingest"
```

Esperado:
```
soc.fortiweb_events.ingested received=1 emitted=1
```

### 8.6 Verificar incidente no SIEM

```bash
docker compose exec siem_kowalski python -c "
from app.store import get_store
store = get_store()
incidents = store.list_incidents()
for i in incidents[-3:]:
    print(i.id, i.title, i.severity)
"
```

Esperado: incidente `fortiweb_dos_activity` com severity `critical`.

### 8.7 Verificar no cockpit

No browser do host, abrir FortiDashboard:

1. **Tickets panel** — ticket gerado com título "FortiWeb DoS activity detected"
2. **Recent Incidents widget** — entrada com severity crítica e source `fortiweb`
3. **Toast de incidente** — aparece em tempo real via SSE sem refresh

---

## 9. Resultado esperado no dashboard

| Onde | O que ver |
|------|-----------|
| SOC Tickets | Ticket "FortiWeb DoS activity detected", severity critical, source IP 10.10.10.10 |
| Recent Incidents widget | Entrada com ícone critical, label `waf.dos` |
| Incident toast | Notificação em tempo real no cockpit |
| AI Cockpit (se configurado) | Sugestão de bloqueio do IP atacante via SOAR |

---

## 10. Troubleshooting

### FortiWeb não alcança FortiDashboard API

```bash
# No FortiWeb CLI
execute ping <HOST_IP>
execute traceroute <HOST_IP>
```

Se sem rota: adicionar adapter Host-only ao FortiWeb e usar esse IP no trigger.

### Log push disparando mas FortiDashboard não recebe

Verificar token:
```bash
curl -X POST http://localhost:8000/api/soc/ingest/fortiweb \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"type":"attack","subtype":"dos","src":"10.10.10.10","msg":"HTTP flood detected","action":"block"}'
```

Esperado: `{"received":1,"emitted":1}`

### FortiWeb bloqueia mas não gera log

Verificar no Server Policy:
- Log Policy está associada
- Attack Log Level está em `Information` ou mais baixo
- Trigger está habilitado

### Incidente não aparece no SIEM

Verificar classificação do evento:
```bash
docker compose exec api python -c "
from app.routers.soc_ingest import _classify_fortiweb_event
print(_classify_fortiweb_event({'subtype':'dos','src':'10.10.10.10','action':'block'}))
"
```

Deve retornar `waf.dos`.

---

## 11. Safety boundaries

- Atacar apenas IPs dentro de `10.10.10.0/24`, `10.10.20.0/24`, `10.10.30.0/24`
- Não rodar flood aberto sem limite de tempo ou contagem
- FortiWeb policy writes devem ser documentadas antes de uso em produção
- SOAR actions permanecem dry-run durante validação de lab
- Não expor a porta 8000 (FortiDashboard API) fora da rede local

## Referências

- Runbook base: `docs/operations/vmware-soc-lab-blackarch-arch.md`
- FortiWeb lab existente: `docs/operations/fortiweb-landing-waf-lab.md`
- FortiWeb logging docs: https://docs.fortinet.com/document/fortiweb/7.4.7/administration-guide/303842/logging
- FortiWeb attack log reference: https://docs.fortinet.com/document/fortiweb/7.0.3/log-message-reference/445549/attack
- Plano de implementação: `docs/superpowers/plans/2026-05-15-fortiweb-waf-marketplace-landing-lab.md`
