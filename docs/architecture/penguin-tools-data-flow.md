# Penguard and Penguin Tools Data Flow

Penguard is the browser-facing cockpit and BFF. The Penguin tools are internal SOC-lite services behind `apps/api`; the browser must never call them directly.

Current implementation status:

- `apps/api` exposes auth, FortiGate integration, workspace, widgets and audit APIs.
- `apps/api` now exposes first-cut SOC gateway routes for SIEM events/incidents, SOAR playbooks/runs and XDR endpoints/timeline.
- `siem_kowalski` exposes health checks plus persisted event and incident endpoints in Docker Compose.
- `xdr_rico` exposes health checks plus persisted endpoint inventory, enrollment token hashes and timeline endpoints in Docker Compose.
- `soar_skipper` exposes health checks plus persisted playbook, run and node catalog endpoints in Docker Compose.
- `agent_private` is a TUI/CLI endpoint sensor package, not a deployed service.
- SOC event, incident, endpoint, playbook and playbook-run examples live in `packages/contracts/fixtures`.
- Runtime SOC routes are intentionally first-cut behind the BFF; `siem_kowalski`, `xdr_rico` and `soar_skipper` now persist core records, while service auth hardening is still future work.

## Runtime Topology

```txt
Browser
  -> apps/api
       -> Keycloak for identity
       -> Postgres for sessions, FortiGate integrations, workspace and audit state
       -> FortiGate provider for live telemetry and governed policy orchestration
       -> siem_kowalski for SOC events and incidents
       -> soar_skipper for playbooks, simulation and dry-run runs
       -> xdr_rico for endpoint inventory and endpoint timelines

agent_private
  -> apps/api or xdr_rico enrollment/telemetry endpoint
```

Docker Compose currently resolves internal services by these names:

```txt
http://siem-kowalski:8000
http://soar-skipper:8000
http://xdr-rico:8000
redis://redis:6379/0
```

`apps/api` owns the external contract and should normalize Penguin service failures into stable API errors. Frontend code should keep using `/api/...` paths with browser credentials and CSRF for mutating calls.

## Data Boundaries

`apps/api` remains responsible for:

- Browser session authentication and CSRF.
- Product RBAC and admin checks.
- Audit logging for sensitive reads and all state-changing actions.
- Secret handling and encrypted storage.
- FortiGate telemetry reads and governed policy orchestration calls.
- Mapping user-facing API errors from internal service errors.

`siem_kowalski` owns:

- Normalized security event ingestion.
- Detection rule execution.
- Incident creation, status and timelines.
- Correlation by IP, hostname, username, integration ID and endpoint ID.

`soar_skipper` owns:

- Playbook graph validation.
- Simulation.
- Dry-run playbook runs and step state.
- Approval state for sensitive steps.

`xdr_rico` owns:

- Endpoint enrollment state.
- Endpoint inventory and heartbeat.
- Endpoint event ingestion.
- Endpoint timelines and correlation context.

`agent_private` owns:

- Host identity collection.
- Lightweight telemetry collection.
- Windows Security Log collection for lab events `4625`, `4672` and `4663`.
- Retry/backoff when offline.
- Simulator mode for demos.

## Main Flows

### FortiGate Telemetry to SOC Events

```txt
Browser -> GET /api/widgets/{widgetId}/data
apps/api -> FortiGate monitor/log endpoints and approved policy orchestration
apps/api -> normalized widget response

Current first-cut SOC flow:
apps/api -> POST /events to siem_kowalski
siem_kowalski -> incident generation and timeline updates
```

FortiGate integration secrets stay in `apps/api` storage and are never sent to Penguin services unless a future contract explicitly requires a scoped, non-secret provider reference.

### Event Ingestion and Incidents

External contract through `apps/api`:

```txt
POST /api/soc/events
GET  /api/soc/events
GET  /api/soc/incidents
GET  /api/soc/incidents/{incidentId}
PATCH /api/soc/incidents/{incidentId}
```

Example event payload:

```json
{
  "source": "fortigate",
  "eventType": "network.deny",
  "severity": "medium",
  "occurredAt": "2026-05-08T12:00:00.000Z",
  "entities": {
    "sourceIp": "192.0.2.10",
    "destinationIp": "198.51.100.20"
  },
  "attributes": {
    "policyId": "12",
    "action": "deny",
    "count": 25
  }
}
```

### Playbook Simulation and Runs

External contract through `apps/api`:

```txt
GET  /api/soc/playbook-node-types
GET  /api/soc/playbooks
POST /api/soc/playbooks
POST /api/soc/playbooks/{playbookId}/simulate
POST /api/soc/incidents/{incidentId}/playbooks/{playbookId}/run
GET  /api/soc/playbook-runs/{runId}
```

`soar_skipper` persists playbooks and run history in SQL through
`SOAR_SKIPPER_DATABASE_URL`. The browser-facing node catalog comes from
`/api/soc/playbook-node-types`; each node advertises category, sensitivity,
dry-run-only status and config schema metadata for the future n8n-like builder.

All playbooks start disabled or draft until validated and activated by an
authorized human. Sensitive FortiGate response nodes may become live only after
approval and must call Penguard-owned policy orchestration APIs. They must
not bypass the BFF, RBAC, preflight, diff/summary or audit path.

### Endpoint Telemetry

External contract through `apps/api`:

```txt
GET  /api/weapons/endpoints
GET  /api/weapons/endpoints/{endpointId}
GET  /api/weapons/endpoints/{endpointId}/timeline
POST /api/weapons/endpoint-events
POST /api/weapons/enrollments
```

In the current cut, endpoint enrollment tokens authenticate telemetry submission and are stored hashed inside `xdr_rico`. They are returned only at creation time. Production hardening should make them one-time bootstrap tokens or short-lived credentials with rotation.

Windows/AD endpoint events follow this extra hop:

```txt
agent_private windows-security -> POST /api/weapons/endpoint-events
apps/api -> xdr_rico endpoint timeline
apps/api -> siem_kowalski security event
siem_kowalski -> incident rules for auth/file events
```

The gateway currently forwards `auth.failed_login`, `auth.privileged_logon`
and `file.change` endpoint events to the SIEM only after XDR ingestion
succeeds. The SIEM event keeps `xdrTimelineItemId` in attributes so tickets can
be correlated back to endpoint context.

## Review Checklist

- [ ] Browser calls only `apps/api`, never direct Penguin service URLs.
- [ ] Internal service failures are mapped to stable `/api/...` errors.
- [ ] FortiGate writes are limited to governed policy orchestration through
  `apps/api`.
- [ ] Secrets, API keys and enrollment tokens are not present in SOC payloads.
- [ ] Mutating SOC APIs write audit events.
- [ ] Endpoint examples use documentation-safe IP ranges and no personal identifiers.
- [ ] This document is updated when persistence, retries or service auth hardening land.
