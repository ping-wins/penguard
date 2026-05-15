# Penguin Tools Realization Plan

This document tracks what is currently real, what is still demo/scripted, and
which real SOC use cases should drive the next Penguin tools implementation.

## Current Real Capabilities

- `siem_kowalski` ingests normalized security events, persists raw events and
  incidents, evaluates safe detection rules, creates timelines and exposes SOC
  tickets through `apps/api`.
- `xdr_rico` creates enrollment tokens, stores token hashes, persists endpoint
  inventory and timelines, accepts endpoint telemetry and correlates incidents
  by endpoint ID, IP, hostname and username.
- `soar_skipper` validates playbook graphs, simulates playbooks and runs
  dry-run workflows with approval gates for sensitive steps.
- `apps/api` owns BFF auth, CSRF, Keycloak session handling, Penguin tool
  integrations, SOC gateway routes and audit records for sensitive actions.
- `apps/web` has real SOC ticket panels, incident toasts, workspace sharing,
  presentation mode, provider rebind and Penguin widget/data-field plumbing.

## Demo Or Scripted Boundaries

- `/api/soc/demo/replay` is synthetic by design. It injects deterministic
  `source="demo.replay"` events so the MVP demo is reproducible.
- The default AI provider is `scripted`. Anthropic and OpenAI-compatible
  providers exist, but real AI requires explicit env configuration.
- `soar_skipper` runs are dry-run only. No FortiGate rule, Windows host,
  webhook, Slack, Teams or ticketing action is executed.
- `soar_skipper` playbooks and run history are persisted, but all action nodes
  still execute as dry-run/simulation boundaries.
- `agent_private simulate` and `scripts/seed_soc_demo.py` produce demo data.
- XDR widgets look empty until `agent_private`, the simulator or a real
  telemetry sender posts endpoint events.
- Kerberos/AD SSO has code and Keycloak realm support, but the full SPNEGO
  path must be verified in the Windows Server lab.

## Exit Criteria From Mockup

1. Preserve the current deterministic demo path, but label it as demo-only in
   UI, docs and logs.
2. Add an operator setup path for Windows Server AD SSO:
   AD DS/DNS, `fortidashboard.local`, SPN, keytab, Keycloak Kerberos provider,
   browser intranet/SPNEGO settings and callback URL verification.
3. Add a Windows-ready `agent_private` run mode with enrollment, heartbeat,
   process snapshot, connection snapshot and Windows event collection.
4. Persist `soar_skipper` playbooks and run history in SQL tables.
5. Add real but safe SOAR connector steps: case note, audit note, webhook
   dry-run, email/Teams notification dry-run and FortiGate policy
   orchestration through FortiDashboard approval gates.
6. Add scheduled/manual FortiGate event ingestion with aggregation, not only
   one-off manual forwarding.
7. Add UI labels that distinguish live provider data, seeded demo data and
   scripted AI output.
8. Add smoke tests for live-style flows that do not rely on `demo.replay`.

## Current Windows/AD First Cut

Implemented in the first Windows Server lab cut:

- `agent_private windows-security` reads Windows Security Log XML through
  `wevtutil` and normalizes event IDs `4625`, `4672` and `4663`.
- Failed logons are grouped by username and source IP before posting, so
  `attributes.count` can trigger the SIEM failed-login threshold.
- `xdr_rico` accepts `auth.failed_login`, `auth.privileged_logon` and
  `file.change` endpoint timeline events.
- The BFF forwards those endpoint events to `siem_kowalski` after successful
  XDR ingestion, preserving the XDR timeline item id in the SIEM attributes.
- `siem_kowalski` now has rules for repeated failed logins, privileged logon
  on unusual host and critical server file changes.

## Current SOAR Builder Foundation Cut

Implemented for the future n8n-like playbook builder:

- `soar_skipper` persists playbooks and playbook runs in SQL through
  `SOAR_SKIPPER_DATABASE_URL`.
- Docker Compose wires `soar_skipper` to the shared Postgres database and waits
  for the database health check before starting the service.
- `GET /node-types` exposes the allowed visual-builder node catalog with
  category, sensitivity, dry-run-only flag and config schema metadata.
- `GET /api/soc/playbook-node-types` proxies that catalog through the BFF so
  the browser never calls `soar_skipper` directly.
- Existing run behavior remains safe: runs are dry-run, sensitive nodes wait
  for approval, and FortiGate block nodes remain recommendations only.

Still pending for the full builder:

- Visual canvas/editor in `apps/web`.
- Node config forms generated from `configSchema`.
- Explicit draft/publish lifecycle and versioning.
- Real connector boundary implementations for notes, notifications and
  webhook dry-runs.

Still requiring manual Windows Server validation:

- Confirm `wevtutil qe Security ...` can read the lab events with the chosen
  operator account.
- Confirm AD audit policy emits `4625` and `4672` in the expected fields.
- Confirm object access audit policy emits `4663` for the demo directory.
- Confirm the browser/API address used by the VM reaches `apps/api` over the
  chosen VirtualBox adapter.

## Real Use Cases To Build

### Use Case 1: Windows AD Failed Login Burst

Goal: prove `siem_kowalski` can detect identity attacks.

Flow:

```txt
Windows Server security event -> agent_private -> xdr_rico
xdr_rico normalized auth event -> siem_kowalski
siem_kowalski repeated_failed_login rule -> SOC ticket T2/T1
apps/web ticket drawer -> AI summary -> soar_skipper notification dry-run
audit log records ingest, ticket update, AI suggestion and playbook run
```

Required work:

- Add Windows event collection for failed logons.
- Normalize event IDs into `auth.failed_login`.
- Correlate username and host against endpoint inventory.
- Add a ticket filter for identity-related incidents.

### Use Case 2: FortiGate Denied Traffic Burst

Goal: prove FortiGate telemetry becomes a SIEM incident without synthetic
events.

Flow:

```txt
FortiGate traffic logs -> apps/api FortiGate ingest
apps/api aggregation by source/destination -> siem_kowalski network.deny
denied_traffic_burst rule -> ticket T1
soar_skipper requests approved FortiDashboard policy orchestration
```

Required work:

- Add FortiGate policy orchestration with RBAC, preflight, diff/summary,
  explicit approval and audit.
- Add repeatable manual and scheduled ingestion controls.
- Surface the source integration and log window in the ticket timeline.
- Show the approved FortiGate action and FortiGate response in the incident
  timeline.

### Use Case 3: Suspicious Endpoint Process And Connection

Goal: prove `xdr_rico` adds endpoint context to a network incident.

Flow:

```txt
agent_private process/network snapshot -> xdr_rico endpoint timeline
Suspicious process or connection event -> siem_kowalski
siem_kowalski suspicious_endpoint_connection rule -> ticket
apps/api endpoint-context route -> related endpoint panel/widget
```

Required work:

- Add Windows process and connection snapshot scheduling.
- Add suspicious process heuristics with allowlists and false-positive notes.
- Add endpoint detail panel with timeline and related incidents.

### Use Case 4: Domain Admin Logon On Unusual Host

Goal: demonstrate insider-threat and privilege visibility without destructive
response.

Flow:

```txt
Windows logon event -> xdr_rico identity/host context
siem_kowalski privileged_logon_unusual_host rule -> ticket
soar_skipper case-note + notify dry-run
audit trail shows who reviewed and changed ticket status
```

Required work:

- Add identity/role metadata input for privileged users.
- Add baseline or static allowed-host list for the lab.
- Add rule explaining why the host was unusual.

### Use Case 5: Critical File Change On Server

Goal: use `agent_private` file monitoring for a simple EDR-lite story.

Flow:

```txt
watchdog file change event -> xdr_rico timeline
siem_kowalski file.change critical_path rule -> ticket
apps/web endpoint timeline + SOC ticket correlation
```

Required work:

- Add optional `watchdog` directory monitoring.
- Make watched paths explicit and visible in the agent TUI.
- Never monitor secrets by default.

## Windows Server Lab Notes

- Keep all AD lab values, keytabs, hostnames and IPs out of committed secrets.
- Browser-facing SSO URLs may use `fortidashboard.local` because the Kerberos
  service principal is host-sensitive.
- The API container must still use `http://keycloak:8080` for
  `FORTIDASHBOARD_KEYCLOAK_BASE_URL`.
- Verify SSO in this order: DNS resolution, SPN/keytab, Keycloak provider,
  `/api/auth/sso/kerberos/init` redirect, callback state, BFF session cookie.

## Acceptance Tests Needed

- Windows Server SSO smoke: init redirect -> Keycloak -> callback -> BFF
  session.
- Agent enrollment smoke: create token -> enroll Windows host -> heartbeat
  visible in `xdr_rico`. Verified on 2026-05-12; operator steps live in
  `docs/mvp/windows-server-agent-smoke.md`.
- Windows failed-login smoke: failed logon -> normalized event -> incident ->
  ticket.
- Endpoint correlation smoke: endpoint telemetry and incident entities resolve
  to the same endpoint.
- SOAR dry-run smoke: ticket -> AI/scripted draft -> playbook simulation ->
  approval gate -> audit events.
