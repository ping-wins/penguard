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
| 2 | Click the yellow **Replay** button under "MVP demo" | Success toast: `Incidente demo injetado (3 eventos, run demo_…)` |
| 3 | Bottom-right corner | Toast pops up: "New incident · T1 · Inbound port scan from 203.0.113.77" |
| 4 | Sidebar → `Ticket` icon to open **SOC Tickets** | Three lanes (T1/T2/T3) populate; the port scan sits in T1 with status `new` |
| 5 | Click the T1 ticket | Detail drawer opens with summary, entities, timeline |
| 6 | Inside the drawer → "AI assistant" block → click **Analyze** | Risk score, suggested triage, IoCs and next steps appear. The cockpit silently records `aiAnalysisId` on the ticket |
| 7 | Click **Apply** next to "Suggested: T1 · investigating" | Ticket status flips to `investigating` and the timeline gets a "Status changed" entry |
| 8 | Click **Suggest containment** | Numbered draft plan: block IP / notify SOC / collect endpoint telemetry, each with `requires approval` flag |
| 9 | Click **Draft playbook** | A second green block renders the new `pb_ai_…` playbook plus its dry-run simulation steps |
| 10 | Click **Apply (dry-run)** | Banner appears: "Threat contained" (or "Containment paused at approval gate" if the AI marked a step sensitive). The lane card updates to `contained` |
| 11 | Sidebar → `History` (Audit Trail) | The full chain shows up: `soc.demo.replay → soc.incident.analyzed → soc.incident.containment_suggested → soc.ticket.playbook_drafted → soc.ticket.contained` |
| 12 | Sidebar → Workspaces → **Export** | Manifest JSON downloads — show the audit trail bundling so the exec sees how everything ties together |

## Failure handling on camera

If a step misbehaves on the recording, fall back to the synthetic event POST
directly so the analyst doesn't have to re-run docker compose. The reset is a
single call:

```powershell
$cookie = "fortidashboard_session=COOKIE"
$csrf = (curl.exe -s -H "Cookie: $cookie" http://localhost:8000/api/auth/csrf | ConvertFrom-Json).csrfToken
curl.exe -X POST -H "Cookie: $cookie" -H "X-CSRF-Token: $csrf" `
  http://localhost:8000/api/soc/demo/replay
```

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
