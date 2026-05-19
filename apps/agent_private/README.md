# agent_private

`agent_private` is the optional endpoint sensor for Penguard labs. It is
explicit and safe by default. The recommended Windows Server lab path is now a
daemon/service runtime managed by a local CLI; the TUI remains available for
troubleshooting and dry-run demos.

## Cockpit Onboarding

1. Open Penguard, go to **Endpoints**, and choose **Add Windows Agent**.
2. Enter a display name and optional hostname hint for the Windows host.
3. Generate the enrollment and copy only the one-time enrollment token.
4. Pair the agent from the repository root on the Windows host.
5. Install/start the Windows Scheduled Task daemon runtime, then check local
   daemon status with the CLI.
6. The cockpit moves the endpoint from pending to inventory after the first
   heartbeat.

PowerShell pairing shape:

```powershell
cd apps\agent_private
uv run agent-private pair "<token-returned-once>"
uv run agent-private task install
uv run agent-private task start
uv run agent-private status
```

`pair` discovers the Penguard API by sending a UDP broadcast on the VMware
management network. If broadcast is blocked, it automatically probes the likely
VMware host addresses on the VM network before failing. It saves the discovered
API URL, endpoint ID and enrollment token to the local config file, but prints
only a masked token summary.

For development or smoke tests without installing the Windows Service, run the
daemon in the foreground:

```powershell
uv run agent-private daemon
```

As soon as the daemon starts, it posts continuous telemetry to the SOC path:
heartbeat, process snapshots, connection snapshots and Windows Security Log
events. The foreground daemon also exposes a loopback-only control API on
`127.0.0.1:8765`. The local CLI uses that API for status and diagnostic
collection requests. The dashboard never connects inbound to the Windows host.

## Daemon, Task And Service CLI

```powershell
uv run agent-private task install
uv run agent-private task start
uv run agent-private task status
uv run agent-private task stop
uv run agent-private task uninstall

uv run agent-private service install
uv run agent-private service start
uv run agent-private service status
uv run agent-private service stop
uv run agent-private service uninstall

uv run agent-private status
uv run agent-private collect-now heartbeat
uv run agent-private collect-now processes
uv run agent-private collect-now connections
uv run agent-private collect-now windows-security
uv run agent-private collect-now all

uv run agent-private config show
uv run agent-private pair "<token-returned-once>"
uv run agent-private diagnostics --post
```

`task` is the recommended Windows Server lab runtime. It writes a runner script
under `%PROGRAMDATA%\agent_private`, registers `PenguardAgentDaemon` with
Windows Task Scheduler, runs the foreground daemon under `SYSTEM`, and redirects
stdout/stderr to `%PROGRAMDATA%\agent_private\logs\daemon-task.log`.

Task and service management commands publish a `health.signal` event to XDR
when local pairing config exists. Failed `install`, `start`, `stop`, `status` or
`uninstall` attempts attach an expanded diagnostics snapshot: service/task
registry state, Task Scheduler output, SCM events, Application events, recent
agent logs, Python/import checks, current process visibility and API reachability
probes. This is intended to make the endpoint timeline sufficient for remote
debugging without copying terminal output from the Windows VM.

Normal SOC telemetry does not depend on `collect-now`. After the Scheduled Task
or Windows Service starts, the daemon keeps posting on these default intervals:

- heartbeat every 30 seconds.
- connection snapshots every 60 seconds.
- Windows Security Log deltas every 60 seconds.
- process snapshots every 300 seconds.

`collect-now` remains available only as a local diagnostic/control command when
you need an immediate sample.

The Windows Service wrapper uses `pywin32` on Windows only. Linux CI and local
developer tests can import the service module safely, but service management
commands require Windows.

Use the manual diagnostics command whenever the agent is paired but a runtime
command did not capture enough context:

```powershell
uv run agent-private diagnostics --post --reason manual-check
```

The command posts the same diagnostics bundle to the endpoint timeline. Tokens
are masked/redacted before logs are printed or sent.

## VMware Discovery Network

For labs, put the Windows Server VM and the Penguard host on the same
VMware host-only or NAT management network. Keep this separate from the traffic
path used by FortiGate/FortiWeb/victim testing.

Recommended shape:

```txt
Windows Server VM
  NIC 1: VMware host-only/NAT management network -> Penguard API discovery
  NIC 2: lab traffic network, if needed

Penguard host
  Docker API port: 8000/tcp
  Agent discovery port: 8764/udp
```

The agent sends discovery broadcasts to the management network and builds the
API URL from the UDP response source IP. If broadcast fails, it tries the common
VMware host addresses for the VM subnet, such as `.1` and `.2`. Operators do not
pass API URLs or environment variables during normal lab setup. If VMware or the
host firewall blocks both paths, `agent-private pair --api-url
http://<host-ip>:8000 "<token>"` remains available as a manual diagnostic
fallback.

Remote dashboard orchestration is pull-based: the daemon polls the BFF for
typed XDR actions, executes only supported actions such as `collect_now` and
posts a result. It does not run arbitrary PowerShell from the dashboard.

## TUI Usage

```bash
cd apps/agent_private
uv run agent-private
```

The TUI lets the operator set the Penguard API URL, endpoint ID,
enrollment token and loop intervals, save a local config, start/stop the
foreground agent loop, or send one-off heartbeat, process snapshot, connection
snapshot and demo telemetry. It is a troubleshooting surface, not the preferred
Windows Server runtime. The enrollment token is masked in the UI log and is sent
only as `Authorization: Bearer ...`.

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
- Windows: `%PROGRAMDATA%\agent_private\config.json`, so the Windows Service
  and the administrator shell read the same agent configuration.

## CLI Dry-Run Usage

```bash
cd apps/agent_private
uv run agent-private tui
uv run agent-private identity
uv run agent-private heartbeat --endpoint-id demo-endpoint-01
uv run agent-private process-snapshot --endpoint-id demo-endpoint-01
uv run agent-private connection-snapshot --endpoint-id demo-endpoint-01
uv run agent-private sysmon --endpoint-id demo-endpoint-01
uv run agent-private simulate --endpoint-id demo-endpoint-01
```

## Sysmon Network And DNS Collection

On Windows Server labs with Microsoft Sysinternals Sysmon installed,
`agent_private` can read recent Sysmon Operational Log records through
`wevtutil`, normalize network and DNS activity, and optionally post them
through the BFF.

```powershell
$env:AGENT_PRIVATE_API_URL = "http://localhost:8000"
$env:AGENT_PRIVATE_ENDPOINT_ID = "win-dc01"
$env:AGENT_PRIVATE_ENROLLMENT_TOKEN = "<token-returned-once>"

uv run agent-private sysmon --limit 50
uv run agent-private sysmon --limit 50 --post
```

Supported Sysmon events:

- `3` network connections become `sysmon.network_connection` with process,
  destination IP/port and optional destination hostname.
- `22` DNS queries become `sysmon.dns_query` with process, query name and
  resolved results.

These events include minimized IoC fields for later Threat Intel enrichment.
They do not capture full URLs, request headers, cookies or page content.
When a later enrichment step marks an event with `threatIntelVerdict` equal to
`suspicious` or `malicious`, the BFF can forward it to the SIEM as
`endpoint.suspicious_connection`.

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

The daemon stores a Windows Security cursor in the local state file and forwards
only new records after the first daemon interval. This avoids turning old
Security Log backlog into fake incidents when the agent starts.

The BFF forwards endpoint telemetry to `siem_kowalski` when it can become a SOC
incident:

- `auth.failed_login` can trigger brute-force incidents when the grouped count
  reaches the SIEM threshold.
- `auth.privileged_logon` triggers when the host is outside the configured
  admin-host baseline.
- `file.change` triggers when the object path matches a configured critical
  path.
- `connection.snapshot` triggers when an established connection is marked
  suspicious, including high-risk remote ports such as `4444` or `31337`.

Optional baselines can be persisted once and will be used by the daemon on the
next start:

```powershell
uv run agent-private config set --allowed-admin-host WIN-SOC-DC01
uv run agent-private config set --critical-path C:\Sensitive
uv run agent-private task stop
uv run agent-private task start
```

## CLI Posting Telemetry

Create an enrollment token through the Penguard BFF, then send telemetry to the browser-facing API. The BFF forwards the enrollment token to `xdr_rico`; the agent does not need a browser session.

```bash
export AGENT_PRIVATE_API_URL=http://localhost:8000
export AGENT_PRIVATE_ENDPOINT_ID=demo-endpoint-01
export AGENT_PRIVATE_ENROLLMENT_TOKEN=<token-returned-once>

uv run agent-private heartbeat --post
```

Interactive troubleshooting loop:

```bash
uv run agent-private run
```

Headless foreground loop for scripts/tests:

```bash
uv run agent-private run-headless
uv run agent-private run-headless --heartbeat-interval 30 --connection-interval 60 --process-interval 300
uv run agent-private run-headless --windows-security-interval 60
uv run agent-private run-headless --sysmon-interval 60
```

Windows PowerShell:

```powershell
$env:AGENT_PRIVATE_API_URL = "http://localhost:8000"
$env:AGENT_PRIVATE_ENDPOINT_ID = "demo-endpoint-01"
$env:AGENT_PRIVATE_ENROLLMENT_TOKEN = "<token-returned-once>"

uv run agent-private heartbeat --post
uv run agent-private daemon
```

## Safety Notes

- No hidden install, privilege escalation or arbitrary remote command execution.
- Saved TUI config stores the enrollment token in the user's local config file; Linux files are written with `0600`. Use lab-scoped tokens and clear the config after demos.
- Enrollment tokens are sent only as `Authorization: Bearer ...`.
- The interactive `run` command masks the enrollment token in the TUI log.
- The `run-headless` command logs event status but never prints the enrollment token.
- The daemon status and action result payloads never include the enrollment token.
- Supported remote actions are typed and bounded; unknown actions fail closed.
- Process and connection snapshots may include usernames, process names and remote IPs; use only in authorized labs.
- Keep dry-run mode for demos unless the SOC stack is running and the token is scoped to the lab endpoint.
