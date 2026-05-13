# MVP Demo Walkthrough

This is the exact click-by-click script for the MVP demo video. The flow uses
the synthetic `POST /api/soc/demo/replay` event burst so the recording is
reproducible without depending on a live FortiGate scan (see
`AGENTS.md → Known Lab Setup Issues`).

The total demo runs in **2-3 minutes** including the AI containment walkthrough.

## Prerequisites

- `docker compose up --build` brings up `api`, `web`, `siem-kowalski`,
  `soar-skipper`, `xdr-rico`, `db`, `redis`, `keycloak`.
- Web served at `http://localhost:5173` (or `http://fortidashboard.local:5173`
  if the Kerberos lab is configured).
- A signed-in analyst user. Use `analyst@example.com` /
  `correct-horse-battery-staple` (realm seed) for the recording. The Keycloak
  Kerberos federation provider should be disabled before recording so the
  registration screen is fast (see Known Lab Setup Issues).
- (Optional) Real AI provider:

  ```yaml
  # docker-compose.yml (api service env)
  FORTIDASHBOARD_AI_PROVIDER: anthropic
  FORTIDASHBOARD_AI_API_KEY: sk-ant-...
  FORTIDASHBOARD_AI_MODEL: claude-3-5-haiku-latest
  ```

  Default is the deterministic `scripted` adapter — the demo always works
  offline.

## Reset state before recording

1. Stop the stack: `docker compose down -v` (drops volumes for a clean slate).
2. Bring it back: `docker compose up -d --build`.
3. Wait for `GET /health` on the API to return 200.
4. Open the cockpit and log in as the analyst.

## Recorded sequence

| Step | Action | What the camera shows |
|------|--------|------------------------|
| 1 | Sidebar (left rail) → `FolderTree` "Workspaces" tab | Workspace list, MVP demo panel, no tickets yet |
| 2 | Click the yellow **Replay** button under "MVP demo", then pick **Cadeia completa / Full chain** in the popover (chips for `Port scan`, `Brute force SSH`, `Beacon C2 do endpoint` let you replay one attack at a time when re-recording a specific phase) | Success toast: `Demo injetado (3 eventos, run demo_…, ataques: Cadeia completa)` |
| 3 | Bottom-right corner | Toast pops up: "New incident · T1 · Inbound port scan from 203.0.113.77" |
| 4 | Sidebar → `Ticket` icon to open **SOC Tickets** | Three lanes (T1/T2/T3) populate; the port scan sits in T1 with status `new`. Seeded replay data is badged as `Seeded demo` instead of looking live |
| 5 | Click the T1 ticket | Detail drawer opens with summary, entities, timeline |
| 6 | Sidebar → `Endpoints` icon, select the demo endpoint | Endpoint detail shows timeline plus **Related incidents**, proving XDR/endpoint context links back to the SIEM ticket |
| 7 | Return to **SOC Tickets** → inside "AI assistant" click **Analyze** | Risk score, suggested triage, IoCs and next steps appear with a `Scripted AI` badge when the offline provider is used. The cockpit records `aiAnalysisId` on the ticket |
| 8 | Click **Apply** next to "Suggested: T1 · investigating" | Ticket status flips to `investigating` and the timeline gets a "Status changed" entry |
| 9 | Click **Suggest containment** | Numbered draft plan: block IP / notify SOC / collect endpoint telemetry, each with `requires approval` flag |
| 10 | Click **Draft playbook** | A second green block renders the new `pb_ai_…` playbook plus its dry-run simulation steps |
| 11 | Click **Apply (dry-run)**, then click **Approve** if the banner says approval is paused | Banner appears: "Threat contained". If the run paused at approval, the approval button clears the gate and the linked ticket transitions to `contained` |
| 12 | Sidebar → `History` (Audit Trail) | The full chain shows up: `soc.demo.replay → soc.incident.analyzed → soc.incident.containment_suggested → soc.ticket.playbook_drafted → soc.ticket.contained` plus `soc.playbook_run.approved` if an approval gate was cleared |
| 13 | Sidebar → Workspaces → **Export** | Manifest JSON downloads — show the audit trail bundling so the exec sees how everything ties together |

## Failure handling on camera

If a step misbehaves on the recording, fall back to the synthetic event POST
directly so the analyst doesn't have to re-run docker compose. The reset is a
single call:

```powershell
$cookie = "fortidashboard_session=COOKIE"
$csrf = (curl.exe -s -H "Cookie: $cookie" http://localhost:8000/api/auth/csrf | ConvertFrom-Json).csrfToken
curl.exe -X POST -H "Cookie: $cookie" -H "X-CSRF-Token: $csrf" `
  http://localhost:8000/api/soc/demo/replay
# Or pick a subset to replay only one attack at a time:
curl.exe -X POST -H "Cookie: $cookie" -H "X-CSRF-Token: $csrf" `
  -H "Content-Type: application/json" `
  --data '{\"attackTypes\":[\"port_scan\"]}' `
  http://localhost:8000/api/soc/demo/replay
```

Allowed `attackTypes` values: `port_scan`, `brute_force`, `c2_beacon`. Omit the
field (or pass an empty list) to inject the full canonical chain.

The `demoRunId` lets you correlate the next set of tickets with the retake.

## What stays out of the recording

- Real FortiGate ingestion (the aggregator works, but the lab topology issues
  noted in `AGENTS.md` make scan-driven incidents unreliable on camera).
- Live AI providers without an API key — the scripted adapter is deterministic
  and faster, perfect for a recording.
- Soar_skipper non-dry-run execution. Soar lite always replies `dry_run=True`
  for the MVP; the AI must never bypass that.

## After the recording

- Stop the stack: `docker compose down`.
- Save the manifest export under `docs/mvp/recordings/<date>/manifest.json` so
  the exec can reproduce the dashboard in their own account.
- Update `AGENTS.md → Backlog → MVP Demo (cross-cutting)` if you re-shoot.
