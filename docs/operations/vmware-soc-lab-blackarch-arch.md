# VMware SOC lab: FortiGate + BlackArch + Arch victim

Use this lab when validating FortiDashboard with real FortiGate telemetry instead of synthetic replay.

The goal is to keep all attack/victim traffic inside VMware while FortiDashboard runs on the host with Docker Compose. The FortiGate VM stays in the middle so every BlackArch -> Arch Linux packet crosses FortiGate and can be logged/ingested.

## Machines

```txt
Host machine
├── Docker Compose FortiDashboard stack
│   ├── apps/web
│   ├── apps/api
│   ├── siem_kowalski
│   ├── soar_skipper
│   ├── xdr_rico
│   ├── postgres
│   ├── redis
│   └── keycloak
└── VMware
    ├── FortiGate VM
    ├── BlackArch VM          # attacker
    └── Arch Linux vanilla VM # victim
```

Pingwins services location:

- `siem_kowalski`, `soar_skipper` and `xdr_rico` run in Docker Compose with FortiDashboard.
- FortiGate, BlackArch and the Arch victim run in VMware.
- `agent_private` is optional and runs inside the Arch victim only if endpoint/XDR telemetry is being tested.

## VMware networks

Create two isolated LAN Segments for attack/victim traffic, plus normal VMware networks for administration and internet access.

```txt
NAT or Bridged      FortiGate management/API from the host
LAN Segment SOC_LAN 10.10.10.0/24   BlackArch attacker side
LAN Segment SOC_DMZ 10.10.20.0/24   Arch victim side
Host-only SSH_ADMIN optional SSH/admin access from host to Linux VMs
NAT                 optional internet access for BlackArch and Arch victim
```

Recommended VMware Virtual Network Editor settings:

| Network | Type | DHCP | Purpose |
| --- | --- | --- | --- |
| FortiGate management | NAT or Bridged | OK | Host reaches FortiGate API |
| `SOC_LAN` | LAN Segment | Off | BlackArch attacker network |
| `SOC_DMZ` | LAN Segment | Off | Victim network |
| `SSH_ADMIN` | Host-only | OK | Host SSH access to Linux VMs |
| Internet | NAT | OK | Package updates/internet for BlackArch and victim |

The important rule: `SOC_LAN` and `SOC_DMZ` are separate LAN Segments. Do not put BlackArch and the victim on the same segment, and do not use the SSH/NAT adapters for attack traffic.

## Network plan

```txt
Host Docker/FortiDashboard
localhost / host IP
        |
        | FortiGate API / management via NAT/Bridged adapter
        |
FortiGate port1
DHCP/static management IP reachable from host

FortiGate port2                 FortiGate port3
10.10.10.1/24                   10.10.20.1/24
        |                               |
        | LAN Segment SOC_LAN           | LAN Segment SOC_DMZ
        | 10.10.10.0/24                 | 10.10.20.0/24
        |                               |
BlackArch attacker              Arch Linux victim
10.10.10.10/24                  10.10.20.10/24
gw 10.10.10.1                   gw 10.10.20.1

BlackArch also has Host-only for SSH and NAT for internet.
Arch victim also has Host-only for SSH and NAT for internet.
Those extra adapters must not provide the default route used for the scan.
```

## VM adapter assignments

### FortiGate VM

Keep the existing licensed FortiGate VM. Do not migrate or convert it. Before changing NICs, take a VMware snapshot.

Adapters:

| FortiGate port | VMware network | IP | Purpose |
| --- | --- | --- | --- |
| port1 | NAT or Bridged | DHCP/static reachable from host | management/API from host |
| port2 | LAN Segment `SOC_LAN` | `10.10.10.1/24` | BlackArch side |
| port3 | LAN Segment `SOC_DMZ` | `10.10.20.1/24` | victim side |

Avoid changing the MAC address of an already-licensed NIC. Add new NICs instead of replacing existing ones whenever possible.

### BlackArch attacker VM

Adapters:

| Adapter | VMware network | IP | Gateway | Purpose |
| --- | --- | --- | --- | --- |
| eth0 | LAN Segment `SOC_LAN` | `10.10.10.10/24` | `10.10.10.1` | attack path |
| eth1 | Host-only `SSH_ADMIN` | DHCP or static | none | SSH from host |
| eth2 | NAT | DHCP | optional/default only for updates | internet/package updates |

For the actual nmap test, force traffic out `eth0` or verify the route to `10.10.20.10` goes through `10.10.10.1`.

Packages/tools:

```bash
sudo pacman -Syu --needed nmap curl tcpdump openbsd-netcat
```

### Arch Linux victim VM

Adapters:

| Adapter | VMware network | IP | Gateway | Purpose |
| --- | --- | --- | --- | --- |
| eth0 | LAN Segment `SOC_DMZ` | `10.10.20.10/24` | `10.10.20.1` | victim path |
| eth1 | Host-only `SSH_ADMIN` | DHCP or static | none | SSH from host |
| eth2 | NAT | DHCP | optional/default only for updates | internet/package updates |

The victim must answer on `10.10.20.10` for the lab. SSH/NAT adapters are only for convenience.

Packages/services:

```bash
sudo pacman -Syu --needed openssh nginx python
sudo systemctl enable --now sshd nginx
```

Optional test web service:

```bash
mkdir -p ~/victim-web
cd ~/victim-web
python -m http.server 8080
```

## Arch static IP examples

Use whatever network manager the VM already uses. These examples are for quick lab setup.

Because BlackArch and the victim also have NAT adapters, keep these lab interfaces explicit. If NAT becomes the default route for internet updates, add a specific route so traffic to the opposite lab subnet still goes through FortiGate.

### systemd-networkd: BlackArch attacker

`/etc/systemd/network/20-eth0.network`:

```ini
[Match]
Name=eth0

[Network]
Address=10.10.10.10/24
DNS=1.1.1.1

[Route]
Destination=10.10.20.0/24
Gateway=10.10.10.1
```

Enable:

```bash
sudo systemctl enable --now systemd-networkd systemd-resolved
ip addr show eth0
ip route
```

### systemd-networkd: Arch victim

`/etc/systemd/network/20-eth0.network`:

```ini
[Match]
Name=eth0

[Network]
Address=10.10.20.10/24
DNS=1.1.1.1

[Route]
Destination=10.10.10.0/24
Gateway=10.10.20.1
```

Enable:

```bash
sudo systemctl enable --now systemd-networkd systemd-resolved
ip addr show eth0
ip route
```

If the interface name is not `eth0`, replace it with the actual name from `ip link`.

## FortiGate minimum configuration

Configure the interfaces from the FortiGate GUI or CLI.

Interface intent:

```txt
port1: SOC_MGMT 10.10.99.1/24, allow HTTPS/SSH/PING from host
port2: SOC_LAN  10.10.10.1/24, allow PING for testing
port3: SOC_DMZ  10.10.20.1/24, allow PING for testing
```

For port1, use the actual management IP assigned by NAT/Bridged. The older `10.10.99.1` management example only applies if you intentionally create a dedicated management VMnet.

First validation policy should generate deny logs because the current SIEM rule is easiest to trigger from `network.deny` bursts.

Create a policy:

```txt
name: SOC_LAN_to_DMZ_deny_log
srcintf: port2
dstintf: port3
srcaddr: all or 10.10.10.0/24
dstaddr: all or 10.10.20.10
service: ALL
action: DENY
logtraffic: all
```

The exact GUI labels vary by FortiOS version. The key requirement is that blocked traffic from BlackArch to the Arch victim appears in Forward Traffic logs.

After deny-based validation works, a more realistic allow-logged policy can be tested:

```txt
name: SOC_LAN_to_DMZ_allow_log
srcintf: port2
dstintf: port3
srcaddr: all or 10.10.10.0/24
dstaddr: all or 10.10.20.10
service: ALL
action: ACCEPT
logtraffic: all
```

The current SOC detection is more reliable with deny logs. Allow-log scan detection should be improved later by counting unique destination ports.

## FortiDashboard integration

FortiDashboard runs on the host through Docker Compose.

The host must reach FortiGate management/API:

```bash
ping <FORTIGATE_PORT1_MGMT_IP>
curl -k https://<FORTIGATE_PORT1_MGMT_IP>/
```

In the cockpit:

1. Open FortiDashboard in the host browser.
2. Connect FortiGate using `https://<FORTIGATE_PORT1_MGMT_IP>` or the configured management URL.
3. Confirm the read-only FortiGate health check passes.
4. Keep the FortiGate integration card open for ingestion status.

## First validation flow

### 1. Verify routing

From BlackArch:

```bash
ip addr
ip route
ip route get 10.10.20.10
ping -c 3 10.10.10.1
```

`ip route get 10.10.20.10` must show the `SOC_LAN` interface and gateway `10.10.10.1`, not the NAT or host-only SSH adapter.

From Arch victim:

```bash
ip addr
ip route
ip route get 10.10.10.10
ping -c 3 10.10.20.1
```

`ip route get 10.10.10.10` must show the `SOC_DMZ` interface and gateway `10.10.20.1`.

If the FortiGate policy is deny, BlackArch may not be able to ping `10.10.20.10`. That is okay for the first deny-log test.

### 2. Watch FortiGate logs

In FortiGate GUI:

```txt
Log & Report -> Forward Traffic
filter source IP: 10.10.10.10
```

Keep this open while running the scan.

### 3. Run a controlled port scan

From BlackArch:

```bash
sudo nmap -Pn -n -sS -T4 -p 1-2000 --max-retries 1 10.10.20.10
```

If multiple adapters make routing ambiguous, force the `SOC_LAN` interface:

```bash
sudo nmap -e <SOC_LAN_IFACE> -Pn -n -sS -T4 -p 1-2000 --max-retries 1 10.10.20.10
```

If SYN scan is unavailable:

```bash
nmap -Pn -n -sT -T4 -p 1-2000 --max-retries 1 10.10.20.10
```

Expected FortiGate result:

- 20+ Forward Traffic entries.
- source IP `10.10.10.10`.
- destination IP `10.10.20.10`.
- action `deny`, `blocked` or equivalent.
- policy is the LAN-to-DMZ deny/log policy.

### 4. Ingest in FortiDashboard

In FortiDashboard:

1. Open Integrations.
2. On the FortiGate card, run event ingestion manually.
3. Confirm `rawEventCount > 0`.
4. Confirm `createdCount >= 1`.
5. Confirm `lastError` is empty.

Current aggregation behavior:

```txt
FortiGate raw logs grouped by (eventType, sourceIp)
20+ deny logs from 10.10.10.10 -> one SIEM event with attributes.count >= 20
```

### 5. Confirm SOC ticket

In FortiDashboard:

1. Open SOC Tickets.
2. Find the new ticket/incident.
3. Confirm source IP is `10.10.10.10`.
4. Confirm destination IP is `10.10.20.10` or the DMZ target.
5. Open Audit drawer and confirm `soc.fortigate_events.ingested`.

## Optional XDR/endpoint step

Only add this after FortiGate ingestion works.

Purpose:

- Register the Arch victim as an endpoint.
- Let `xdr_rico` show endpoint inventory/timeline.
- Correlate SIEM tickets with endpoint context.

Flow:

1. In FortiDashboard, create an endpoint enrollment for the Arch victim.
2. Install/run `agent_private` on the Arch victim using the generated API URL, endpoint ID and token.
3. Ensure the victim can reach the FortiDashboard API. Prefer routing through FortiGate rather than adding a bypass NIC.
4. Confirm the endpoint appears online in the cockpit.
5. Re-run the scan and confirm related incidents/endpoint context.

If the victim cannot reach the host API through FortiGate, add a temporary policy:

```txt
srcintf: port3
srcaddr: 10.10.20.10
dstintf: port1
dstaddr: 10.10.99.100
service: API port or HTTPS
action: ACCEPT
logtraffic: all
```

## Troubleshooting checklist

### No FortiGate Forward Traffic logs

Root cause is likely VMware network topology or FortiGate policy.

Check:

- BlackArch is on SOC_LAN only.
- Arch victim is on SOC_DMZ only.
- Their gateways point to FortiGate port2/port3.
- They are not both attached to the same VMnet/bridged network.
- The FortiGate policy matches port2 -> port3 traffic.
- The policy has logging enabled.

### FortiGate logs exist, but FortiDashboard rawEventCount is zero

Root cause is likely FortiGate integration/event fetch.

Check:

- Host can reach `https://10.10.99.1`.
- FortiGate API key/user is valid and read-only.
- FortiGate integration health check passes.
- The logs are recent enough for the widget/event fetch.

### rawEventCount is positive, but no SOC ticket

Root cause is likely event shape or SIEM rule threshold.

Check:

- Logs are deny/block actions.
- At least 20 deny logs came from the same source IP.
- Ingestion reports `createdCount >= 1`.
- `siem_kowalski` service is healthy.

### Ticket exists, but no endpoint context

Expected until `agent_private` is running on the Arch victim and the endpoint has sent heartbeat/telemetry.

## Safety boundaries

- Keep this lab isolated from production networks.
- Scan only the Arch victim IP/range assigned to this lab.
- Do not run broad scans against the physical LAN or internet.
- Keep FortiGate access read-only from FortiDashboard.
- SOAR actions remain dry-run for MVP validation.
