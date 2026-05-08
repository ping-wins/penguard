# agent_private

`agent_private` is the optional endpoint sensor for FortiDashboard labs. It is explicit, foreground-only and safe by default. The recommended operator flow is the TUI; CLI commands remain available for tests, scripts and dry-run demos.

## TUI Usage

```bash
cd apps/agent_private
uv run agent-private
```

The TUI lets the operator set the FortiDashboard API URL, endpoint ID and enrollment token, save a local config, then send heartbeat, process snapshot, connection snapshot or demo telemetry. The enrollment token is masked in the UI log and is sent only as `Authorization: Bearer ...`.

Local config path:

- Linux: `$XDG_CONFIG_HOME/agent_private/config.json` or `~/.config/agent_private/config.json`.
- Windows: `%APPDATA%\agent_private\config.json`.

## CLI Dry-Run Usage

```bash
cd apps/agent_private
uv run agent-private tui
uv run agent-private identity
uv run agent-private heartbeat --endpoint-id demo-endpoint-01
uv run agent-private process-snapshot --endpoint-id demo-endpoint-01
uv run agent-private connection-snapshot --endpoint-id demo-endpoint-01
uv run agent-private simulate --endpoint-id demo-endpoint-01
```

## CLI Posting Telemetry

Create an enrollment token through the FortiDashboard BFF, then send telemetry to the browser-facing API. The BFF forwards the enrollment token to `xdr_rico`; the agent does not need a browser session.

```bash
export AGENT_PRIVATE_API_URL=http://localhost:8000
export AGENT_PRIVATE_ENDPOINT_ID=demo-endpoint-01
export AGENT_PRIVATE_ENROLLMENT_TOKEN=<token-returned-once>

uv run agent-private heartbeat --post
```

Windows PowerShell:

```powershell
$env:AGENT_PRIVATE_API_URL = "http://localhost:8000"
$env:AGENT_PRIVATE_ENDPOINT_ID = "demo-endpoint-01"
$env:AGENT_PRIVATE_ENROLLMENT_TOKEN = "<token-returned-once>"

uv run agent-private heartbeat --post
```

## Safety Notes

- No persistence, daemon install, privilege escalation or remote command execution.
- Saved TUI config stores the enrollment token in the user's local config file; Linux files are written with `0600`. Use lab-scoped tokens and clear the config after demos.
- Enrollment tokens are sent only as `Authorization: Bearer ...`.
- Process and connection snapshots may include usernames, process names and remote IPs; use only in authorized labs.
- Keep dry-run mode for demos unless the SOC stack is running and the token is scoped to the lab endpoint.
