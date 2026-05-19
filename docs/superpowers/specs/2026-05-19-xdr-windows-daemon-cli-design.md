# XDR Windows Daemon And CLI Design

## Problem

`agent_private` currently proves endpoint telemetry, but the operator path is
still centered on a TUI/foreground terminal. That is brittle for the lab Windows
Server 2022 Desktop Experience host: PowerShell paste/focus behavior is awkward,
the terminal must stay open, and the dashboard cannot clearly show that a
background endpoint sensor is installed and manageable.

FortiDashboard needs the Windows endpoint sensor to behave like an XDR agent:
an explicit background process that sends telemetry, receives tightly scoped
remote actions from the dashboard, and can be managed locally without using the
TUI as the runtime.

## Goals

- Turn `agent_private` into a Windows daemon model suitable for the lab host.
- Keep the existing telemetry builders and `run-headless` scheduling logic as
  the reusable runtime core.
- Add a local CLI that controls the daemon: install, start, stop, status,
  config and immediate collection.
- Add the XDR-side action queue needed for dashboard orchestration.
- Keep all remote actions typed, small, auditable and safe by default.
- Preserve the TUI only as a troubleshooting/debug path.

## Non-Goals

- No arbitrary remote PowerShell or shell execution from FortiDashboard.
- No stealth persistence, credential harvesting, hidden privilege escalation or
  destructive endpoint response.
- No MSI/EXE packaging, code signing or auto-update in this cut.
- No full endpoint isolation response in this cut. The first remote action is
  telemetry collection on demand.

## Architecture

```txt
FortiDashboard Vue
  -> apps/api BFF
    -> xdr_rico endpoint inventory, action queue and action results

Windows Server 2022
  agent_private Windows Service
    -> sends telemetry to apps/api /api/weapons/endpoint-events
    -> polls apps/api for queued endpoint actions
    -> posts action results back through apps/api
    -> exposes local control API on 127.0.0.1 for the CLI only

  agent-private CLI
    -> controls Windows Service through SCM for install/start/stop
    -> asks daemon local control API for status and collect-now
```

The dashboard never connects inbound to the Windows host. All dashboard-driven
orchestration is outbound from the agent by polling for queued XDR actions.

## Agent Runtime

`agent_private` gains a daemon layer above the existing runner:

- `agent-private daemon` runs the daemon loop in the foreground for development
  and tests.
- `agent-private service install|start|stop|status|uninstall` manages the real
  Windows Service on Windows.
- `agent-private status` queries the local daemon control API.
- `agent-private collect-now <kind>` asks the local daemon to collect and post a
  telemetry batch immediately.
- `agent-private config show|set` reads and updates the local config file used
  by the daemon.

The Windows Service implementation uses `pywin32` when running on Windows. The
module must import safely on Linux CI/test hosts; Windows-only imports stay
inside service code paths.

## Local CLI To Daemon Contract

The daemon exposes a loopback-only control API:

```txt
GET  http://127.0.0.1:<port>/status
POST http://127.0.0.1:<port>/collect-now
POST http://127.0.0.1:<port>/stop
```

The API returns JSON only and never includes enrollment tokens. The first cut
binds to `127.0.0.1` and uses a configurable local port. A later hardening cut
can replace this with Windows Named Pipes.

## XDR Remote Action Contract

`xdr_rico` stores endpoint actions:

```txt
POST /endpoints/{endpoint_id}/actions
POST /endpoints/{endpoint_id}/actions/claim
POST /endpoints/{endpoint_id}/actions/{action_id}/result
GET  /endpoints/{endpoint_id}/actions
```

Action fields:

- `id`
- `endpointId`
- `kind`
- `status`: `queued`, `claimed`, `completed`, `failed`
- `parameters`
- `createdAt`
- `claimedAt`
- `completedAt`
- `result`

Allowed first-cut action kinds:

- `collect_now`: ask the daemon to post heartbeat/process/connection/security
  telemetry now.
- `run_diagnostic`: ask the daemon to report agent configuration and collector
  availability.

The agent authenticates action claim/result requests with the same enrollment
bearer token used for telemetry. Once an enrollment token has claimed an
endpoint, it cannot claim or complete actions for another endpoint.

## BFF Contract

`apps/api` mirrors the XDR action endpoints under `/api/weapons/...`:

```txt
POST /api/weapons/endpoints/{endpoint_id}/actions
POST /api/weapons/endpoints/{endpoint_id}/actions/claim
POST /api/weapons/endpoints/{endpoint_id}/actions/{action_id}/result
GET  /api/weapons/endpoints/{endpoint_id}/actions
```

Dashboard/user-created actions require BFF auth and CSRF for mutations, and are
audited. Agent claim/result endpoints require enrollment bearer auth and do not
require a browser session.

## UX Direction

The Endpoints panel should move away from "open TUI and keep terminal alive" to
an installed-agent flow:

1. Generate enrollment.
2. Copy a PowerShell install command.
3. Run the command on Windows Server.
4. Dashboard shows pending -> online.
5. Endpoint detail shows daemon status, collector status, last action and action
   history.
6. Analyst can request safe typed actions such as collect telemetry now.

## Safety Rules

- No remote arbitrary command execution.
- No remote PowerShell text execution.
- No secrets in logs, status payloads, action results or audit details.
- All dashboard-created actions are audited.
- Agent-side action handling must reject unknown action kinds.
- Remote actions are pull-based from the agent; no inbound host exposure.

## Implementation Phases

1. **Daemon/CLI foundation:** local daemon, local control API, Windows Service
   wrapper and CLI commands.
2. **XDR action queue:** persist actions, claim queued actions and post results.
3. **BFF action gateway:** expose action endpoints with browser auth/audit for
   analysts and bearer auth for agents.
4. **Agent remote action polling:** daemon polls for queued actions and executes
   `collect_now`.
5. **Dashboard UX:** installation command, daemon status and action history in
   the endpoint panel.
6. **Hardening:** Named Pipe transport, Windows Event Log, package/installer,
   service account choice and richer collector health.

## Testing Strategy

- Unit-test local control API status and collect-now without starting a real
  Windows Service.
- Unit-test CLI command routing and token redaction.
- Unit-test Windows Service command guards on non-Windows hosts.
- Unit-test XDR action queue lifecycle: create, claim, complete, invalid token
  and endpoint mismatch.
- Unit-test BFF forwarding/audit for action creation and bearer pass-through for
  claim/result.
- Keep existing agent and XDR telemetry tests green.

## Self-Review

- The design keeps the user's core requirement: a daemon-like Windows process
  plus CLI control.
- The service path is explicit and reversible.
- The dashboard orchestration path is pull-based and does not expose the host.
- The first implementation slice stays narrow enough to ship without packaging
  or arbitrary command execution.
