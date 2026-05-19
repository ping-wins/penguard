# FortiGate Brute Force Lab — Demo Guide

This guide walks a lab operator end-to-end through provoking a `repeated_failed_login`
incident from a Debian attacker VM and confirming the resulting alert in Penguard.
It assumes you own the FortiGate VM and the Debian VM (authorized lab use only).

Last updated: 2026-05-14.

## Topology

```
[Debian VM]──vmnet2 (LAN)──[FortiGate port2]──[FortiGate port1]──vmnet8 (WAN/NAT)──host
   192.168.50.10           192.168.50.1         192.168.23.x
```

Notes:

- The attacker must sit on a network segment where the FortiGate is the gateway.
  Two bridged VMs on the same `/24` stay on the L2 segment and the firewall never
  routes their packets — Forward Traffic logs stay empty. See AGENTS.md
  "Known Lab Setup Issues" for the full background.
- The brute force target must live on the **other side** of the FortiGate. Either
  the FortiGate itself (SSH on the LAN interface) or a host on the WAN.

## Phase 1 — FortiGate configuration

### 1.1 Read-only API user

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

Copy the generated key — you will paste it in the cockpit (phase 2).

### 1.2 LAN→WAN policy with traffic logging

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

Policies without `set logtraffic all` leave widgets empty even when packets are
crossing interfaces.

### 1.3 Login attempt audit

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

`local-traffic enable` + `event enable` is what makes SSH attempts against the
FortiGate itself show up in the event log.

## Phase 2 — Connect the integration in Penguard

In the cockpit: Sidebar → Integrations → Add → **FortiGate**.

| Field | Value |
| --- | --- |
| Name | `lab-fortigate` |
| Host | `192.168.50.1` (port2 IP) |
| API key | the key generated in 1.1 |
| Verify SSL | off (self-signed certificate) |

Save. The cockpit performs a read-only probe — if it passes, the integration
turns green. The `System Status` widget should show the real hostname and
firmware version. Empty values point to either the credential or the trusthost
CIDR not covering the BFF container.

## Phase 3 — Brute force from the Debian VM

### 3.1 Install hydra

```bash
sudo apt update && sudo apt install -y hydra
```

### 3.2 Small dictionaries

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

### 3.3 Run the attack

Against the FortiGate SSH admin interface:

```bash
hydra -L /tmp/users.txt -P /tmp/pass.txt -t 4 -f ssh://192.168.50.1
```

Flags:

- `-t 4` — four parallel threads.
- `-f` — stop on the first hit; here all attempts should fail and you want the
  full sweep, so the `-f` is purely defensive.

Alternative target on the WAN side (forces the LAN→WAN policy to log):

```bash
hydra -L /tmp/users.txt -P /tmp/pass.txt -t 4 ssh://192.168.23.5
```

The combined dictionary above produces 39 attempts (`3 users × 13 passwords`),
which is well above the `repeated_failed_login` detection threshold once the
backend aggregator collapses the events by source IP.

## Phase 4 — Ingest FortiGate events into the SIEM

The current FortiGate → SIEM ingest is manual (see AGENTS.md "Known Lab Setup
Issues"). Pick the FortiGate `integrationId` from the cockpit sidebar
(Integrations panel, expand the FortiGate card) and call:

```bash
curl -X POST "http://localhost:8000/api/soc/fortigate/INT_FGT_ID/ingest-events" \
  -H "Cookie: f_session=..." \
  -H "X-CSRF-Token: ..."
```

The response payload includes `rawEventCount` and `createdCount` (aggregated by
`(eventType, sourceIp)`). `apps/api/app/routers/integrations.py`
`_aggregate_fortigate_events()` is what makes `attributes.count` cross the
detection threshold — without it every raw event would land with `count=1` and
`repeated_failed_login` would never fire.

If you just want to validate the cockpit pipeline without depending on real
FortiGate traffic, use the **MVP Demo Replay** panel inside the cockpit
(`POST /api/soc/demo/replay`). It injects canonical port-scan / brute-force /
beacon events directly into `siem_kowalski`.

## Phase 5 — Verify in the dashboard

After the ingest call:

1. **Recent Incidents** widget shows a new `repeated_failed_login` incident
   within one poll cycle (≈5 s).
2. **Incidents by Severity** increments its `medium` or `high` bar.
3. **SLA Breach** widget stays green while the incident is fresh (< 15 min).
4. **Top Source IPs** (FortiGate) lists `192.168.50.10` (Debian) at the top
   with the denied/total counts.
5. The workspace header heat-strip surfaces the aggregated severity count.
6. KPI sparklines tick upward on the next poll.

## Phase 6 — Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `Recent Events` empty | Policy missing `logtraffic all` | Re-apply phase 1.2 |
| FortiGate widget shows "Connection invalid" | Wrong API key or `trusthost` CIDR does not cover the BFF | Verify the trusthost block accepts the API container IP |
| Hydra exits with `connect refused` | SSH disabled, or `allowaccess` does not include ssh | `set allowaccess ssh https` on the LAN interface |
| Attempts arrive, no incident appears | Aggregator did not reach the detection threshold | Increase the dictionary to produce ≥ 20 attempts |
| Bridged VM, FortiGate sees nothing | Classic L2 bypass on the same `/24` | Move Debian to a dedicated LAN segment with the FortiGate as default gateway |
| `denied_traffic_burst` expected, never fires | Per AGENTS.md the rule needs `attributes.count >= 20` on one event | The aggregator now handles this; confirm via the `soc_widget_data_*` log lines that the aggregated count is high enough |
| FortiGate boots with "File System Check Recommended" | Previous unsafe reboot | Run `execute disk list` then `execute disk scan <ref>` before recording any demo |

### Useful host-side logs

```bash
docker compose logs -f api | grep -E "fortigate|siem|soc_widget"
docker compose logs -f siem-kowalski | grep -E "detection|incident"
```

Expected patterns:

- `soc_widget_data_ready widget_id=fortigate-recent-events ...`
- `siem detection_fired rule=repeated_failed_login count=N source_ip=192.168.50.10`
- `soc_widget_data_ready widget_id=soc-recent-incidents incidents=1`

## Security reminders

- Brute force is destructive testing. Only run it against assets you control.
- Never push the generated API key or the lab passwords into the repository.
  `.env.local`, `penguard.keytab` and similar are intentionally gitignored.
- Trusthost CIDR on the FortiGate API user must remain narrow (`/24` of the BFF
  network at most). Loosening it removes the only network-level guard the
  read-only key has.
