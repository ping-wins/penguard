# FortiGate scan detection operator checklist

Use this path for real telemetry validation. Do not use synthetic replay or seeded demo data for product/customer checks.

For the current VMware lab layout with FortiGate + BlackArch attacker + Arch Linux victim, follow `docs/operations/vmware-soc-lab-blackarch-arch.md` first, then use this checklist during the actual scan validation.

## Prerequisites

- FortiGate integration is connected in the cockpit and passes the health check.
- The scanned traffic crosses FortiGate interfaces. Same-L2 bridged hosts on one subnet may never produce Forward Traffic logs.
- The matching FortiGate policy logs accepted/denied traffic with `set logtraffic all`.
- FortiDashboard API can reach `siem_kowalski` and the FortiGate provider.
- For endpoint correlation, enroll a host from the cockpit and run `agent_private run-headless` with the issued token.

## Validation flow

1. In the cockpit, open Integrations and verify the FortiGate card is connected.
2. Confirm the ingestion status shows no last error.
3. Generate routed scan traffic from a lab workstation through the FortiGate path.
4. If the lab path is not already logged, use FortiDashboard policy
   orchestration to create or verify a log-enabled deny/log or allow/log policy.
5. Click the FortiGate ingestion run-now control, or enable scheduled ingestion and wait for the next successful poll.
6. Confirm the ingestion card reports raw events and created SIEM events.
7. Open SOC Tickets and verify a new ticket appears from live FortiGate telemetry.
8. Open the audit drawer and confirm policy orchestration, ingestion and ticket
   actions were recorded.

## Troubleshooting

- No raw events: verify the traffic crossed FortiGate interfaces and check FortiGate Forward Traffic logs directly.
- Raw events but no SIEM incident: verify at least 20 denies from the same source were ingested so `denied_traffic_burst` can fire after aggregation.
- Endpoint context missing: create a cockpit enrollment, start `agent_private`, and wait for the first heartbeat.
- AI actions fail: configure `FORTIDASHBOARD_AI_PROVIDER` plus `FORTIDASHBOARD_AI_API_KEY`. The scripted provider is lab-only and requires `FORTIDASHBOARD_ENABLE_LAB_DEMO_TOOLS=true`.

## Lab-only tools

Synthetic replay and simulator helpers are quarantined for isolated development labs. They are not registered in the normal API runtime. If a developer intentionally needs them, start the API with `FORTIDASHBOARD_ENABLE_LAB_DEMO_TOOLS=true` and keep generated data labeled as demo/lab-only.
