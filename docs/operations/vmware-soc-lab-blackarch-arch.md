# VMware SOC Lab: FortiGate, FortiWeb, Attacker, Victim

This is the canonical VMware runbook for the local Penguard SOC lab.
Use it to rebuild the lab end to end without relying on synthetic replay.

The final traffic path is:

```txt
BlackArch attacker -> FortiGate -> FortiWeb -> Arch victim/origin
```

The final management path is separate:

```txt
Host Penguard/Docker -> FortiGate API
Host Penguard/Docker -> FortiWeb API/GUI
```

Penguard manages FortiGate lab policies directly through the governed
FortiGate API orchestration path. FortiManager is optional/future lab
infrastructure and is not required for this MVP topology. FortiAnalyzer is not
required for this lab.

## Network Names

Use simple VMware names and keep the traffic networks as LAN Segments.

| VMware network | Type | DHCP | Subnet | Purpose |
| --- | --- | --- | --- | --- |
| `MGMT_BRIDGED` | Bridged | Optional | Your physical LAN | Host, Penguard, FortiGate management, FortiWeb management |
| `ATTACK_NET` | LAN Segment | Off | `10.10.10.0/24` | BlackArch side of FortiGate |
| `WAF_FRONT` | LAN Segment | Off | `10.10.20.0/24` | FortiGate to FortiWeb public/VIP side |
| `WAF_BACK` | LAN Segment | Off | `10.10.40.0/24` | FortiWeb to victim/origin side |
| `NAT_UPDATES` | NAT | Optional | VMware NAT range | Optional package updates only |

Do not put attacker, FortiWeb front, and victim on one shared segment. That
creates bypass paths and weakens the demo.

## IP Plan

Use these lab IPs for isolated traffic networks. Management IPs are examples
because they depend on the bridged LAN DHCP/static range.

| Machine | Interface | VMware network | IP | Purpose |
| --- | --- | --- | --- | --- |
| Host | physical/Wi-Fi/Ethernet | `MGMT_BRIDGED` | `<HOST_MGMT_IP>` | Browser, Docker Compose, Penguard |
| FortiGate | `port1` | `MGMT_BRIDGED` | `<FGT_MGMT_IP>` | API and GUI management |
| FortiGate | `port2` | `ATTACK_NET` | `10.10.10.1/24` | Attacker gateway |
| FortiGate | `port3` | `WAF_FRONT` | `10.10.20.1/24` | WAF front gateway |
| FortiWeb | `port1` | `WAF_FRONT` | `10.10.20.29/24` | WAF data interface |
| FortiWeb | VIP | `WAF_FRONT` | `10.10.20.30/24` | Landing/WAF virtual IP |
| FortiWeb | `port2` | `MGMT_BRIDGED` | `<FWEB_MGMT_IP>` | GUI/API/SSH management |
| FortiWeb | `port3` | `WAF_BACK` | `10.10.40.1/24` | Origin-side interface |
| BlackArch attacker | lab NIC | `ATTACK_NET` | `10.10.10.10/24` | Scan/attack source |
| Arch victim/origin | lab NIC | `WAF_BACK` | `10.10.40.10/24` | Landing origin |

Example management assignment if your bridged LAN is `192.168.0.0/24`:

```txt
<FGT_MGMT_IP>  = 192.168.0.118
<FWEB_MGMT_IP> = 192.168.0.120
```

Do not copy those example addresses blindly. Use addresses that are free on the
actual bridged LAN.

## VM Adapter Mapping

### FortiGate VM

FortiGate trial exposes three usable interfaces. Keep it that way.

| VMware adapter | FortiOS interface | VMware network |
| --- | --- | --- |
| Network Adapter 1 | `port1` | `MGMT_BRIDGED` |
| Network Adapter 2 | `port2` | `ATTACK_NET` |
| Network Adapter 3 | `port3` | `WAF_FRONT` |

Rules:

- Do not design this lab around `port4`.
- Do not change licensed NIC MAC addresses after the trial/license is active.
- Take a snapshot before changing VMware adapters.

### FortiWeb VM

FortiWeb needs three interfaces for this no-bypass WAF design.

| VMware adapter | FortiWeb interface | VMware network |
| --- | --- | --- |
| Network Adapter 1 | `port1` | `WAF_FRONT` |
| Network Adapter 2 | `port2` | `MGMT_BRIDGED` |
| Network Adapter 3 | `port3` | `WAF_BACK` |

All FortiWeb virtual NICs must use the same VMware adapter type. If FortiWeb
boots with `Virtual machine need same type network cards`, power it off and make
all FortiWeb NICs the same type, preferably `vmxnet3`.

### BlackArch Attacker VM

| Adapter | VMware network | Required? | Purpose |
| --- | --- | --- | --- |
| Lab NIC | `ATTACK_NET` | Yes | Attack path |
| NAT NIC | `NAT_UPDATES` | Optional | Package updates |

If the VM has multiple NICs, verify the route before every test. Attack traffic
to `10.10.20.30` must go through `10.10.10.1`.

### Arch Victim VM

| Adapter | VMware network | Required? | Purpose |
| --- | --- | --- | --- |
| Lab NIC | `WAF_BACK` | Yes | Origin behind FortiWeb |
| NAT or bridged management NIC | `NAT_UPDATES` or `MGMT_BRIDGED` | Optional | Package updates/admin only |

The victim must not be attached to `ATTACK_NET` or `WAF_FRONT`.

### FortiManager VM (Optional/Deferred)

FortiManager is not part of the current critical path. The lab previously used
it as the policy manager, but FortiGate permanent trial limitations can prevent
FGFM registration with newer FortiManager builds because the trial VM may keep a
generic factory certificate and reject custom certificate imports.

For the MVP lab, manage policies directly from Penguard through the
FortiGate API. Reintroduce FortiManager only when a full evaluation/license path
or compatible version pair is available.

## Host: Penguard

Start the stack from the repository root:

```bash
docker compose config --quiet
docker compose up -d --build
```

The host must reach the management addresses:

```bash
ping <FGT_MGMT_IP>
ping <FWEB_MGMT_IP>
curl -k https://<FGT_MGMT_IP>/
curl -k https://<FWEB_MGMT_IP>/
```

## FortiGate Configuration

Configure FortiGate from the console or GUI.

### Interfaces

```txt
config system interface
  edit "port1"
    set mode dhcp
    set allowaccess ping https ssh
  next
  edit "port2"
    set ip 10.10.10.1 255.255.255.0
    set allowaccess ping
  next
  edit "port3"
    set ip 10.10.20.1 255.255.255.0
    set allowaccess ping
  next
end
```

If `port1` should be static instead of DHCP, set the static IP that belongs to
your bridged LAN.

Verify:

```txt
show system interface
get router info routing-table all
diagnose hardware deviceinfo nic
```

### Firewall Objects

```txt
config firewall address
  edit "PG_HOST_ATTACKER"
    set subnet 10.10.10.10 255.255.255.255
  next
  edit "PG_HOST_FORTIWEB_VIP"
    set subnet 10.10.20.30 255.255.255.255
  next
  edit "PG_NET_WAF_BACK"
    set subnet 10.10.40.0 255.255.255.0
  next
end
```

### Lab Policy For WAF Traffic

For the WAF landing demo, expose only HTTP/HTTPS to the FortiWeb VIP:

```txt
config firewall policy
  edit 0
    set name "PG_LAB_ALLOW_ATTACK_TO_WAF_WEB"
    set srcintf "port2"
    set dstintf "port3"
    set srcaddr "PG_HOST_ATTACKER"
    set dstaddr "PG_HOST_FORTIWEB_VIP"
    set action accept
    set schedule "always"
    set service "HTTP" "HTTPS"
    set logtraffic all
  next
end
```

For SIEM port-scan validation, use Penguard policy orchestration to create
a temporary allow/log policy to the FortiWeb VIP with service `ALL`, then remove
or disable it after the test.

```txt
srcintf: port2
dstintf: port3
srcaddr: 10.10.10.10
dstaddr: 10.10.20.30
service: ALL
action: ACCEPT
logtraffic: all
```

### Direct Origin Bypass Guard

The attacker should not reach `10.10.40.10` directly. FortiGate has no interface
on `WAF_BACK`, but a default route through `port1` could still create confusing
traffic. Add an explicit deny/log guard if the FortiGate has a general
`port2 -> port1` internet policy:

```txt
config firewall policy
  edit 0
    set name "PG_LAB_DENY_ATTACK_TO_WAF_BACK"
    set srcintf "port2"
    set dstintf "port1"
    set srcaddr "PG_HOST_ATTACKER"
    set dstaddr "PG_NET_WAF_BACK"
    set action deny
    set schedule "always"
    set service "ALL"
    set logtraffic all
  next
end
```

Place this deny above broad internet policies.

## FortiWeb Configuration

Configure FortiWeb from the console, then complete the WAF policy in the GUI if
preferred.

### Interfaces

```txt
config system interface
  edit "port1"
    set ip 10.10.20.29/24
    set allowaccess ping
    set status up
  next
  edit "port2"
    set mode dhcp
    set allowaccess ping ssh http https
    set status up
  next
  edit "port3"
    set ip 10.10.40.1/24
    set allowaccess ping
    set status up
  next
end
```

If DHCP on bridged `port2` is inconvenient, set a static `<FWEB_MGMT_IP>/24`.

Verify:

```txt
get system interface port1
get system interface port2
get system interface port3
```

### VIP, Server Pool, Vserver, Policy

FortiWeb expects the VIP in the vserver `vip-list` to reference a `system vip`
object.

```txt
config system vip
  edit "PG_VIP_LANDING"
    set interface "port1"
    set vip 10.10.20.30/24
  next
end

config server-policy server-pool
  edit "victim-pool"
    config pserver-list
      edit 1
        set ip 10.10.40.10
        set port 8080
      next
    end
  next
end

config server-policy vserver
  edit "lab-vserver"
    config vip-list
      edit 1
        set interface "port1"
        set status enable
        set use-interface-ip disable
        set vip "PG_VIP_LANDING"
      next
    end
  next
end

config server-policy policy
  edit "lab-waf-policy"
    set deployment-mode server-pool
    set vserver "lab-vserver"
    set service "HTTP"
    set replacemsg "Predefined"
    set server-pool "victim-pool"
  next
end
```

If FortiWeb says an attribute cannot be changed after policy creation, delete
the incomplete policy and recreate it with the final values.

## Arch Victim Configuration

Identify the lab NIC first:

```bash
ip -br a
```

Assign the origin address to the NIC attached to `WAF_BACK`:

```bash
sudo ip addr add 10.10.40.10/24 dev <VICTIM_WAF_BACK_IFACE>
sudo ip link set <VICTIM_WAF_BACK_IFACE> up
```

Start a minimal landing origin:

```bash
mkdir -p ~/victim-web
cd ~/victim-web
printf '<h1>hello</h1>\n' > index.html
python -m http.server 8080 --bind 10.10.40.10
```

Validation from the victim:

```bash
curl http://10.10.40.10:8080/
```

The victim does not need a default gateway for FortiWeb-to-origin HTTP because
FortiWeb `port3` and the victim are on the same subnet.

## BlackArch Attacker Configuration

Identify the lab NIC first:

```bash
ip -br a
```

Assign the attacker address and route:

```bash
sudo ip addr add 10.10.10.10/24 dev <ATTACK_IFACE>
sudo ip link set <ATTACK_IFACE> up
sudo ip route replace 10.10.20.0/24 via 10.10.10.1 dev <ATTACK_IFACE>
sudo ip route replace 10.10.40.0/24 via 10.10.10.1 dev <ATTACK_IFACE>
```

Install tools:

```bash
sudo pacman -Syu --needed nmap curl tcpdump apache-tools hping3
```

Validate the route:

```bash
ip route get 10.10.20.30
ping -c 3 10.10.10.1
curl -v http://10.10.20.30/
curl --max-time 5 http://10.10.40.10:8080/
```

Expected:

- `curl http://10.10.20.30/` returns the victim HTML through FortiWeb.
- Direct `curl http://10.10.40.10:8080/` fails.

## Penguard Policy Management

Penguard is the current policy manager for this lab. It talks directly to
FortiGate over the management network and may create or update only
Penguard-owned objects and policies after preflight, diff review, admin
confirmation and audit.

Use this path for:

- temporary allow/log scan-validation policies;
- logged WAF web policies owned by Penguard;
- approved temporary containment policies tied to SOC tickets.

Do not require FortiManager for the MVP validation flow. Keep any FortiManager
VM powered off unless you are explicitly testing a licensed/compatible
FortiManager path.

## Penguard Connector Setup

In the cockpit:

1. Connect FortiGate using `<FGT_MGMT_IP>`.
2. Verify FortiGate syslog/log-forwarding health.
3. Connect FortiWeb using `<FWEB_MGMT_IP>` when the add-on/provider is enabled.
4. Keep FortiGate and FortiWeb telemetry direct to Penguard/SIEM.
5. Use Penguard policy orchestration for temporary lab policies and
   approved containment.

FortiWeb WAF policy remains direct FortiWeb configuration in this lab.
FortiManager should not be treated as the FortiWeb WAF configuration manager or
as a required FortiGate policy manager for MVP validation.

## End-to-End Validation

### 1. WAF Path

From BlackArch:

```bash
ip route get 10.10.20.30
curl -v http://10.10.20.30/
```

Expected path:

```txt
10.10.10.10 -> 10.10.10.1 -> 10.10.20.30 -> 10.10.40.10:8080
```

### 2. No Direct Origin Bypass

From BlackArch:

```bash
curl --max-time 5 http://10.10.40.10:8080/
```

Expected: connection failure or timeout.

### 3. FortiGate SIEM Port Scan

Temporarily apply an allow/log policy to the FortiWeb VIP through
Penguard policy orchestration, then run:

```bash
sudo nmap -e <ATTACK_IFACE> -Pn -n -sS -T4 -p 1-2000 --max-retries 1 10.10.20.30
```

Expected:

- FortiGate Forward Traffic logs from `10.10.10.10` to `10.10.20.30`.
- Penguard receives syslog in real time.
- SIEM creates a `Possible port scan` incident without browser refresh.
- SOAR can suggest a FortiGate temporary block, but live apply requires a
  Penguard approval/review flow.

### 4. FortiWeb DoS/WAF Test

Use only short, lab-owned tests:

```bash
ab -n 500 -c 50 http://10.10.20.30/
```

Expected:

- FortiWeb attack/traffic logs.
- Penguard WAF/SIEM widgets update through realtime delivery.
- Recent incidents and tickets update without `F5`.

### 5. Penguard Policy Management

In Penguard:

1. Open the FortiGate integration policy workflow.
2. Confirm preflight reads interfaces, address objects, services and current
   policy order.
3. Review the diff for any `PG_` object or policy change.
4. Apply only after an admin explicitly confirms.
5. Confirm the audit drawer records the policy request, diff summary, FortiGate
   response and rollback/cleanup guidance.

## Troubleshooting

### FortiWeb Returns Empty Reply

Check from FortiWeb:

```txt
execute ping 10.10.40.10
```

If it fails, the victim is probably not on `WAF_BACK` or does not have
`10.10.40.10/24` assigned.

### Direct Origin Is Reachable From Attacker

Check that:

- Victim is not connected to `ATTACK_NET`.
- Victim is not connected to `WAF_FRONT`.
- Attacker has no bridged route into `WAF_BACK`.
- FortiGate has an explicit deny/log guard for `10.10.40.0/24` if it has a
  broad internet policy from `port2` to `port1`.

### No FortiGate Logs

Check that:

- `ip route get 10.10.20.30` on BlackArch uses `10.10.10.1`.
- FortiGate policy is `port2 -> port3`.
- The matching policy has `logtraffic all`.
- Penguard ingestion/log-forwarding health is green.

### Penguard Policy Orchestration Fails

Check:

```txt
execute ping <HOST_MGMT_IP>
show firewall policy
show firewall address
```

Then confirm the FortiGate API token is valid, trusted hosts include the
Penguard API host, and the requested change touches only `PG_` lab-owned
objects or policies.

## Safety Rules

- Attack only `10.10.20.30` for WAF/DoS demonstrations.
- Use `10.10.20.30`, not `10.10.40.10`, as the attacker-facing landing target.
- Keep flood tests short and bounded.
- Do not expose Penguard API to the internet.
- Do not run scans against the physical LAN.
- Use Penguard governed policy orchestration for real FortiGate policy
  changes.
