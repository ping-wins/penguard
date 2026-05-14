# agent_private

`agent_private` is the optional endpoint sensor for FortiDashboard labs. It is
explicit, foreground-only and safe by default. The recommended onboarding flow
starts in the FortiDashboard Endpoints panel; the TUI and CLI commands remain
available for tests, scripts and dry-run demos.

## Cockpit Onboarding

1. Open FortiDashboard, go to **Endpoints**, and choose **Add Windows Agent**.
2. Enter a display name and optional hostname hint for the Windows host.
3. Generate the enrollment and copy the one-time PowerShell command.
4. Run the command from the repository root on the Windows host.
5. The command opens the `agent_private` TUI with the enrollment values already
   loaded. Review the setup and press **Start agent**.
6. Keep the terminal open. The cockpit moves the endpoint from pending to
   inventory after the first heartbeat.

PowerShell command shape:

```powershell
cd apps\agent_private; $env:AGENT_PRIVATE_API_URL="http://<fortidashboard-host>:8000"; $env:AGENT_PRIVATE_ENDPOINT_ID="<enrollment-id>"; $env:AGENT_PRIVATE_ENROLLMENT_TOKEN="<token-returned-once>"; uv run agent-private run
```

To include Windows Security events, set the Windows Security interval in the TUI
to a positive number before starting the agent. `0` disables collection.

Stop the foreground agent with the **Stop agent** button or close the TUI with
`Ctrl+C`. Windows Scheduled Task installation is planned as the next cut after
the foreground loop is stable.

## TUI Usage

```bash
cd apps/agent_private
uv run agent-private
```

The TUI lets the operator set the FortiDashboard API URL, endpoint ID,
enrollment token and loop intervals, save a local config, start/stop the
foreground agent loop, or send one-off heartbeat, process snapshot, connection
snapshot and demo telemetry. The enrollment token is masked in the UI log and is
sent only as `Authorization: Bearer ...`.

Navigation:

- Use `Tab` / `Shift+Tab` to move between fields and buttons.
- Press `Enter` to activate the focused button.
- Use `Ctrl+V` to paste into the focused field. On Windows, the TUI falls back
  to the system clipboard when the terminal does not emit a paste event.
- Use the mouse wheel to scroll when the terminal is short.
- Shortcuts: `s` saves, `r` starts the agent loop, `x` stops it, `h` sends a
  heartbeat, `d` sends demo telemetry and `q` quits.

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

## Windows Security Log Collection

On Windows Server labs, `agent_private` can read recent Security Log records
through `wevtutil`, normalize them, and optionally post them through the BFF.

```powershell
$env:AGENT_PRIVATE_API_URL = "http://localhost:8000"
$env:AGENT_PRIVATE_ENDPOINT_ID = "win-dc01"
$env:AGENT_PRIVATE_ENROLLMENT_TOKEN = "<token-returned-once>"

uv run agent-private windows-security --limit 50
uv run agent-private windows-security --limit 50 --post
```

Supported Windows events:

- `4625` failed logons are grouped by user and source IP into
  `auth.failed_login` events with `attributes.count`.
- `4672` special-privilege logons become `auth.privileged_logon`. Pass
  `--allowed-admin-host WIN-SOC-DC01` to mark other hosts as unusual.
- `4663` object access events become `file.change`. Pass
  `--critical-path C:\Sensitive` to flag important paths.

Windows audit policy must emit the target events before the command can collect
them. For file changes, enable object access auditing and configure auditing on
the directory being tested.

## CLI Posting Telemetry

Create an enrollment token through the FortiDashboard BFF, then send telemetry to the browser-facing API. The BFF forwards the enrollment token to `xdr_rico`; the agent does not need a browser session.

```bash
export AGENT_PRIVATE_API_URL=http://localhost:8000
export AGENT_PRIVATE_ENDPOINT_ID=demo-endpoint-01
export AGENT_PRIVATE_ENROLLMENT_TOKEN=<token-returned-once>

uv run agent-private heartbeat --post
```

Interactive foreground loop:

```bash
uv run agent-private run
```

Headless foreground loop for scripts/tests:

```bash
uv run agent-private run-headless
uv run agent-private run-headless --heartbeat-interval 30 --connection-interval 60 --process-interval 300
uv run agent-private run-headless --windows-security-interval 60
```

Windows PowerShell:

```powershell
$env:AGENT_PRIVATE_API_URL = "http://localhost:8000"
$env:AGENT_PRIVATE_ENDPOINT_ID = "demo-endpoint-01"
$env:AGENT_PRIVATE_ENROLLMENT_TOKEN = "<token-returned-once>"

uv run agent-private heartbeat --post
uv run agent-private run
```

## Safety Notes

- No daemon install, privilege escalation or remote command execution.
- Saved TUI config stores the enrollment token in the user's local config file; Linux files are written with `0600`. Use lab-scoped tokens and clear the config after demos.
- Enrollment tokens are sent only as `Authorization: Bearer ...`.
- The interactive `run` command masks the enrollment token in the TUI log.
- The `run-headless` command logs event status but never prints the enrollment token.
- Process and connection snapshots may include usernames, process names and remote IPs; use only in authorized labs.
- Keep dry-run mode for demos unless the SOC stack is running and the token is scoped to the lab endpoint.
