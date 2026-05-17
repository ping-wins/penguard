# FortiWeb DoS Lab: Attacker -> FortiGate -> FortiWeb -> Victim

Runbook para validar DoS/WAF com telemetria real no FortiDashboard usando o
laboratorio VMware canonical:

- `docs/operations/vmware-soc-lab-blackarch-arch.md`

Versao testada do FortiWeb: **8.0.5 trial**.

## Topologia

```txt
BlackArch attacker 10.10.10.10
  -> FortiGate port2 10.10.10.1
  -> FortiGate port3 10.10.20.1
  -> FortiWeb VIP 10.10.20.30:80
  -> FortiWeb port3 10.10.40.1
  -> Arch victim/origin 10.10.40.10:8080
```

Gestao fica fora do caminho de ataque:

```txt
Host FortiDashboard/Docker
  -> FortiGate port1 <FGT_MGMT_IP> bridged
  -> FortiWeb port2 <FWEB_MGMT_IP> bridged
```

Regras do lab:

- O alvo WAF do atacante e `10.10.20.30`, nao `10.10.40.10`.
- A victim/origin fica apenas na rede `WAF_BACK`.
- `curl http://10.10.40.10:8080/` a partir do atacante deve falhar.
- FortiWeb protege HTTP/HTTPS. SSH e GUI usam gestao bridged, nao WAF.
- FortiGate registra o caminho attacker -> FortiWeb.

## Pre-requisitos

1. FortiDashboard stack rodando no host.
2. FortiGate conectado no FortiDashboard e com syslog/log-forwarding saudavel.
3. FortiWeb configurado com:
   - `FD_VIP_LANDING` em `10.10.20.30/24` na `port1`.
   - `victim-pool` apontando para `10.10.40.10:8080`.
   - `lab-vserver` usando `FD_VIP_LANDING`.
   - `lab-waf-policy` usando `victim-pool`.
4. Victim servindo landing em `10.10.40.10:8080`.
5. BlackArch com rota para `10.10.20.0/24` via `10.10.10.1`.

## FortiGate Policy Para DoS/WAF

Para a demo WAF, permita e logue HTTP/HTTPS do atacante para o VIP:

```txt
config firewall address
  edit "FD_HOST_ATTACKER"
    set subnet 10.10.10.10 255.255.255.255
  next
  edit "FD_HOST_FORTIWEB_VIP"
    set subnet 10.10.20.30 255.255.255.255
  next
end

config firewall policy
  edit 0
    set name "FD_LAB_ALLOW_ATTACK_TO_WAF_WEB"
    set srcintf "port2"
    set dstintf "port3"
    set srcaddr "FD_HOST_ATTACKER"
    set dstaddr "FD_HOST_FORTIWEB_VIP"
    set action accept
    set schedule "always"
    set service "HTTP" "HTTPS"
    set logtraffic all
  next
end
```

Para validacao de port-scan SIEM, use uma policy temporaria `ALL` para o mesmo
VIP criada pela orquestracao de policies do FortiDashboard e remova/desabilite
depois.

## Victim: Landing Simples

Na victim:

```bash
ip -br a
sudo ip addr add 10.10.40.10/24 dev <VICTIM_WAF_BACK_IFACE>
sudo ip link set <VICTIM_WAF_BACK_IFACE> up

mkdir -p ~/victim-web
cd ~/victim-web
printf '<h1>hello</h1>\n' > index.html
python -m http.server 8080 --bind 10.10.40.10
```

## FortiWeb: Objetos Minimos

Use o runbook base para configurar as interfaces. O resumo dos objetos:

```txt
system vip:             FD_VIP_LANDING -> 10.10.20.30/24 on port1
server-policy vserver:  lab-vserver
server pool:            victim-pool -> 10.10.40.10:8080
server policy:          lab-waf-policy
```

O `server-policy policy` precisa ter `set replacemsg "Predefined"`, porque
FortiWeb pode recusar `next` quando `replacemsg` fica vazio.

## FortiWeb: Log Push Para FortiDashboard

Quando o caminho FortiWeb provider/add-on estiver habilitado, configure o push
para o endpoint de ingestao do FortiDashboard. O FortiWeb deve usar a rede de
gestao bridged (`port2`) para alcancar o host.

Endpoint:

```txt
POST http://<HOST_MGMT_IP>:8000/api/soc/ingest/fortiweb
Authorization: Bearer <SOC_INGEST_TOKEN>
X-FortiDashboard-Integration-Id: fortiweb-lab
Content-Type: application/json
```

No host:

```bash
docker compose logs -f api siem_kowalski
```

Teste manual do endpoint, sem FortiWeb:

```bash
curl -X POST http://localhost:8000/api/soc/ingest/fortiweb \
  -H "Authorization: Bearer <SOC_INGEST_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"type":"attack","subtype":"dos","src":"10.10.10.10","msg":"HTTP flood detected","action":"block"}'
```

Esperado:

```txt
{"received":1,"emitted":1}
```

## BlackArch: Validar Rota

```bash
ip -br a
sudo ip addr add 10.10.10.10/24 dev <ATTACK_IFACE>
sudo ip link set <ATTACK_IFACE> up
sudo ip route replace 10.10.20.0/24 via 10.10.10.1 dev <ATTACK_IFACE>

ip route get 10.10.20.30
ping -c 3 10.10.10.1
curl -v http://10.10.20.30/
curl --max-time 5 http://10.10.40.10:8080/
```

Esperado:

- `curl http://10.10.20.30/` retorna HTML via FortiWeb.
- `curl http://10.10.40.10:8080/` falha.

## Executar DoS Controlado

Instalar ferramentas:

```bash
sudo pacman -Syu --needed apache-tools hping3
```

Executar apenas contra o VIP do FortiWeb:

```bash
ab -n 500 -c 50 http://10.10.20.30/
```

Opcional, se `hey` estiver instalado:

```bash
hey -z 20s -c 50 http://10.10.20.30/
```

Opcional L4, com muito cuidado:

```bash
sudo hping3 -S --flood -p 80 --count 10000 10.10.20.30
```

Limites:

- Alvo unico: `10.10.20.30`.
- Duracao maxima: 30 segundos por teste.
- Nunca atacar a LAN fisica, internet ou `10.10.40.10` direto.

## Resultado Esperado

| Onde | O que ver |
| --- | --- |
| FortiGate Forward Traffic | Logs de `10.10.10.10` para `10.10.20.30` |
| FortiWeb Attack/Traffic Log | Evento DoS/WAF para origem `10.10.10.10` |
| API logs | `soc.fortiweb_events.ingested` quando push estiver configurado |
| SIEM | Incidente `waf.dos` ou equivalente |
| Cockpit | Recent incidents/tickets atualizam via realtime sem refresh |

## Troubleshooting

### `curl http://10.10.20.30/` retorna `Empty reply from server`

No FortiWeb:

```txt
execute ping 10.10.40.10
show server-policy server-pool victim-pool
show server-policy vserver lab-vserver
show server-policy policy lab-waf-policy
```

Se o ping falhar, a victim provavelmente nao esta na `WAF_BACK` ou nao recebeu
`10.10.40.10/24`.

### Atacante alcanca `10.10.40.10:8080`

Verifique se a victim nao esta conectada em `ATTACK_NET`, `WAF_FRONT` ou na
mesma rede bridged do atacante. O unico caminho de aplicacao deve ser pelo VIP
`10.10.20.30`.

### Dashboard nao recebe evento FortiWeb

```bash
docker compose logs api --tail=80 | grep -i fortiweb
docker compose logs siem_kowalski --tail=80
```

Verifique token, URL do trigger e conectividade do FortiWeb `port2` ate
`<HOST_MGMT_IP>:8000`.

## Safety Boundaries

- Atacar apenas `10.10.20.30`.
- Nao usar flood sem limite de tempo ou contagem.
- Nao expor o endpoint `:8000` do FortiDashboard para fora da rede local.
- Live response continua exigindo aprovacao explicita no FortiDashboard.
