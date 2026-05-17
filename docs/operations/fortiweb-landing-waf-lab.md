# FortiWeb Landing WAF Lab

This runbook is the FortiWeb-specific checklist for the VMware SOC lab. Build
the base topology first:

- `docs/operations/vmware-soc-lab-blackarch-arch.md`

Tested FortiWeb version: 8.0.5 trial.

## Topology

FortiWeb is a reverse proxy for the landing page. It is not an SSH gateway and
it is not the default router for the whole lab.

```txt
BlackArch attacker 10.10.10.10
  -> FortiGate port2 10.10.10.1
  -> FortiGate port3 10.10.20.1
  -> FortiWeb VIP 10.10.20.30:80
  -> FortiWeb port3 10.10.40.1
  -> Arch victim/origin 10.10.40.10:8080
```

Management stays out of the attack path:

```txt
Host FortiDashboard/Docker
  -> FortiWeb port2 <FWEB_MGMT_IP> on bridged management
```

## Landing Page Requirements

- Landing source code lives outside this repository.
- Origin listens on `10.10.40.10:8080`.
- Attacker-facing URL is `http://10.10.20.30/`.
- Direct attacker access to `10.10.40.10:8080` must fail.
- FortiGate logs attacker traffic to `10.10.20.30`.
- FortiWeb logs WAF traffic/attacks and pushes telemetry to FortiDashboard when
  the FortiWeb add-on/provider path is enabled.
- The origin should expose:
  - `GET /`
  - `GET /demo/search?q=...`
  - `POST /api/contact`
- The origin must not contain real customer data or real credentials.

## FortiWeb Objects

Use these object names so screenshots, docs, and FortiDashboard fields line up:

```txt
system vip:             FD_VIP_LANDING -> 10.10.20.30/24 on port1
server-policy vserver:  lab-vserver
server pool:            victim-pool -> 10.10.40.10:8080
server policy:          lab-waf-policy
```

Minimal CLI shape:

```txt
config system vip
  edit "FD_VIP_LANDING"
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
        set vip "FD_VIP_LANDING"
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

## Validation

From BlackArch:

```bash
curl -v http://10.10.20.30/
curl --max-time 5 http://10.10.40.10:8080/
```

Expected:

- First command returns the landing page through FortiWeb.
- Second command fails; the attacker cannot reach the origin directly.

## Demo Attack Inputs

Use only against this lab-owned target:

```bash
curl "http://10.10.20.30/demo/search?q=%27%20OR%201%3D1--"
curl "http://10.10.20.30/.env"
ab -n 500 -c 50 "http://10.10.20.30/"
```

Keep DoS/flood tests bounded. Do not run open-ended flood traffic.

## Expected Dashboard Result

- FortiWeb records attack or traffic logs.
- FortiDashboard receives FortiWeb telemetry when the FortiWeb provider path is
  configured.
- `siem_kowalski` creates a WAF incident.
- The dashboard shows an incident toast, recent incident, and ticket without a
  browser refresh.
- SOAR proposes response actions from inside FortiDashboard; live actions still
  require explicit approval.
