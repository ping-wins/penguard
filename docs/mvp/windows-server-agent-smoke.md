# Windows Server Agent Smoke Path

Purpose: prove a VirtualBox Windows Server host can send real endpoint
telemetry into FortiDashboard through `agent_private`, `apps/api` and
`xdr_rico`.

## Preconditions

- FortiDashboard stack is running and `api`, `xdr-rico` and `siem-kowalski`
  are healthy.
- Windows Server VM can reach the host API, for example
  `http://192.168.56.1:8000` over the host-only adapter.
- An endpoint enrollment token was created through
  `POST /api/weapons/enrollments`. Treat the token as a secret; it is returned
  once and must not be committed or pasted into docs.
- The VM checkout is up to date with `origin/main`.

## Windows Commands

Run from `apps\agent_private` inside the Windows checkout:

```powershell
$env:AGENT_PRIVATE_API_URL = "http://192.168.56.1:8000"
$env:AGENT_PRIVATE_ENDPOINT_ID = "win-server-01"
$env:AGENT_PRIVATE_ENROLLMENT_TOKEN = "<returned-once-token>"

uv run agent-private heartbeat --post
uv run agent-private process-snapshot --post
uv run agent-private connection-snapshot --post
uv run agent-private windows-security --post --limit 50
```

## Expected Server Evidence

Container logs should show:

```txt
POST /api/weapons/endpoint-events HTTP/1.1" 200 OK
xdr_endpoint_event_ingested endpoint_id=win-server-01 event_type=heartbeat
xdr_endpoint_event_ingested endpoint_id=win-server-01 event_type=process.snapshot
xdr_endpoint_event_ingested endpoint_id=win-server-01 event_type=connection.snapshot
xdr_endpoint_event_ingested endpoint_id=win-server-01 event_type=auth.failed_login
```

The latest `connection.snapshot` must contain populated `localAddress`,
`status` and `pid` fields. A timeline full of `null` connection rows means the
Windows checkout is older than commit `ba0630a`.

## Cockpit Check

Open the **Endpoints** drawer in the sidebar. The Windows host should appear
with hostname, last-seen time, process count, connection count and a timeline
containing heartbeat, process, connection and Windows Security events. The
primary IP is the BFF-observed source address labeled **Observed via API**;
agent-reported interface IPs are shown separately and may include NAT adapter
addresses such as `10.0.2.15`.

Current verified lab result on 2026-05-12:

- Endpoint ID: `win-server-01`.
- Latest connection snapshot: `5150` populated connection rows.
- Windows Security events reached SIEM and generated `Repeated failed login`
  tickets.
