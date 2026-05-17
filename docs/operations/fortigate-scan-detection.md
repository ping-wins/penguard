# FortiGate Scan Detection Operator Checklist

Use this path for real telemetry validation. Do not use synthetic replay or
seeded demo data for product/customer checks.

Build the VMware lab first:

- `docs/operations/vmware-soc-lab-blackarch-arch.md`

## Current Lab Target

In the current no-bypass WAF topology, the attacker-facing target is the
FortiWeb VIP:

```txt
BlackArch attacker 10.10.10.10
  -> FortiGate
  -> FortiWeb VIP 10.10.20.30
  -> FortiWeb
  -> victim/origin 10.10.40.10:8080
```

Scan `10.10.20.30`, not `10.10.40.10`. Direct attacker access to
`10.10.40.10:8080` should fail.

## Prerequisites

- FortiGate integration is connected in the cockpit and passes health checks.
- FortiGate syslog/log-forwarding ingestion is healthy.
- BlackArch route to `10.10.20.30` goes through `10.10.10.1`.
- The matching FortiGate policy logs traffic with `set logtraffic all`.
- For allow/log scan validation, a temporary FortiDashboard-owned policy allows
  `10.10.10.10 -> 10.10.20.30` with service `ALL`.
- FortiDashboard API can reach `siem_kowalski`.

## Validation Flow

1. In the cockpit, open Integrations and verify the FortiGate card is connected.
2. Confirm ingestion/log-forwarding health shows no last error.
3. Use FortiDashboard policy orchestration to create or verify a temporary
   allow/log policy for `10.10.10.10 -> 10.10.20.30`, service `ALL`.
4. From BlackArch, verify routing:

   ```bash
   ip route get 10.10.20.30
   ping -c 3 10.10.10.1
   curl -v http://10.10.20.30/
   ```

5. Run a controlled scan:

   ```bash
   sudo nmap -e <ATTACK_IFACE> -Pn -n -sS -T4 -p 1-2000 --max-retries 1 10.10.20.30
   ```

   If SYN scan is unavailable:

   ```bash
   nmap -Pn -n -sT -T4 -p 1-2000 --max-retries 1 10.10.20.30
   ```

6. Confirm FortiGate Forward Traffic logs show:
   - source `10.10.10.10`
   - destination `10.10.20.30`
   - matching temporary FortiDashboard-owned policy
   - `logtraffic all`
7. Watch FortiDashboard update through realtime delivery. Use manual/run-now
   ingestion only as a diagnostic fallback.
8. Open SOC Tickets and verify the `Possible port scan` ticket appears.
9. If containment is part of the test, approve the SOAR run, review the
   FortiGate policy change, and apply it from FortiDashboard.
10. Open Audit and confirm policy orchestration, ingestion, ticket, and approval
    actions were recorded.

## Expected Result

- Recent Incidents widget updates without browser refresh.
- SOC ticket appears without browser refresh.
- Playbook/containment suggestion points at source IP `10.10.10.10`.
- Any FortiGate block is applied only after explicit FortiDashboard approval.

## Cleanup

After the scan demo:

1. Disable or remove the temporary `service=ALL` scan-validation policy.
2. Keep the narrower WAF web policy for HTTP/HTTPS demos.
3. Confirm FortiDashboard policy inventory and FortiGate Forward Traffic logs
   reflect the cleanup.

## Troubleshooting

- No FortiGate raw logs: verify route to `10.10.20.30` and FortiGate policy
  order.
- Raw logs but no SIEM incident: verify accepted traffic from one source to at
  least 20 unique destination ports inside the detection window.
- Direct victim access works: victim is attached to the wrong VMware network or
  the attacker has an unintended route into `WAF_BACK`.
- AI actions fail: configure `FORTIDASHBOARD_AI_PROVIDER` and
  `FORTIDASHBOARD_AI_API_KEY`; scripted AI is lab-only.

## Lab-Only Tools

Synthetic replay and simulator helpers are quarantined for isolated development
labs. They are not the normal product validation path.
