# Realtime Telemetry Flow

This document describes the implemented realtime contract between FortiGate,
`apps/api`, `siem_kowalski` and the Vue cockpit.

## Current Shape

```txt
FortiGate
  -> UDP syslog :5514
  -> apps/api FortiGateSyslogForwarder
  -> siem_kowalski POST /events/ingest
  -> apps/api RealtimeBroker
  -> Browser GET /api/events/stream
  -> Pinia stores
  -> tickets, incident toasts and workspace widgets
```

The browser uses Server-Sent Events (SSE), not WebSocket. The flow is
server-to-browser only: provider telemetry arrives at the backend and the
backend pushes typed events to the authenticated user.

## Backend Components

| Component | Responsibility |
| --- | --- |
| `apps/api/app/integrations/fortigate/syslog.py` | Parses FortiGate syslog datagrams, normalizes them into SIEM events and posts them to `siem_kowalski`. |
| `apps/api/app/main.py` | Starts the UDP syslog collector and publishes `fortigate.syslog.event` SSE payloads after SIEM ingestion. |
| `apps/api/app/realtime.py` | In-memory owner-scoped SSE broker. |
| `apps/api/app/routers/realtime.py` | Exposes `GET /api/events/stream` as `text/event-stream`. |
| `apps/api/app/auth/audit.py` | Optionally forwards sanitized audit events into SIEM and publishes `audit.siem.event`. |
| `apps/siem_kowalski/app/main.py` | Ingests events, applies detections and returns both stored event and optional incident. |

## SSE Endpoint

```txt
GET /api/events/stream
```

Authentication uses the normal BFF session. The Vue client opens the stream with
`withCredentials: true`, so Keycloak tokens and FortiGate API keys never reach
the browser.

Stream behavior:

- On connect, the API emits a `connected` event for the current user.
- Events are delivered only to subscribers whose `ownerUserId` matches the
  published event.
- Keep-alives are sent as SSE comments every 25 seconds when no event is
  available.
- Each subscriber queue is bounded to 100 events. A full queue is treated as a
  stale subscriber and is removed.

## Event Types

### `connected`

Emitted once after the stream opens.

```json
{
  "type": "connected",
  "ownerUserId": "user-id"
}
```

### `fortigate.syslog.event`

Emitted when the API receives and forwards a FortiGate syslog datagram.

```json
{
  "type": "fortigate.syslog.event",
  "ownerUserId": "user-id",
  "integrationId": "int_fgt_...",
  "eventId": "evt_...",
  "receivedAt": "2026-05-15T12:00:00.000Z",
  "ticket": {
    "id": "inc_...",
    "title": "Repeated failed login",
    "severity": "high",
    "triageLevel": "T1",
    "ticketStatus": "new",
    "createdAt": "2026-05-15T12:00:00.000Z"
  },
  "widgets": [
    {
      "widgetId": "fortigate-system-status",
      "integrationId": "int_fgt_...",
      "refreshedAt": "2026-05-15T12:00:00.000Z",
      "status": "ready",
      "data": {},
      "meta": {
        "source": "fortigate",
        "cacheTtlSeconds": 2,
        "refreshIntervalSeconds": 2
      }
    }
  ]
}
```

Fields:

- `ticket` is present only when SIEM detection created an incident.
- `widgets` contains event-triggered widget snapshots. Today this includes
  `fortigate-system-status`.
- Widget snapshots are throttled in the backend per
  `(ownerUserId, integrationId)` to avoid turning high-volume syslog into
  repeated FortiGate API calls.

### `fortigate.ingestion.events`

Emitted by the manual/scheduled FortiGate event-ingestion fallback path, not by
the native UDP syslog path.

```json
{
  "type": "fortigate.ingestion.events",
  "ownerUserId": "user-id",
  "integrationId": "int_fgt_...",
  "eventIds": ["evt_..."],
  "receivedAt": "2026-05-15T12:00:00.000Z",
  "refresh": ["widgets", "tickets"],
  "trigger": "manual"
}
```

This path is kept for diagnostics and fallback behavior. It should not become
the normal dashboard refresh mechanism.

### `audit.siem.event`

Emitted when a sanitized BFF audit event is forwarded into SIEM.

```json
{
  "type": "audit.siem.event",
  "ownerUserId": "user-id",
  "eventId": "evt_...",
  "receivedAt": "2026-05-15T12:00:00.000Z",
  "ticket": null
}
```

If SIEM creates an incident from the audit event, `ticket` contains the
incident/ticket payload and the frontend can update ticket surfaces without a
manual refresh.

## Frontend Components

| Component | Responsibility |
| --- | --- |
| `apps/web/src/stores/useRealtimeStore.ts` | Owns the singleton `EventSource`, parses typed SSE events and fan-outs to subscribers. |
| `apps/web/src/stores/useTicketsStore.ts` | Bootstraps tickets once, then upserts `event.ticket` from realtime events. |
| `apps/web/src/stores/useIncidentToastsStore.ts` | Shows new incident toasts from realtime ticket payloads. |
| `apps/web/src/stores/useWidgetRealtimeStore.ts` | Stores latest widget snapshots by `widgetId + integrationId`. |
| `apps/web/src/components/canvas/DraggableWidget.vue` | Applies matching widget snapshots and hydrates duplicate widgets from shared Pinia state. |

`DraggableWidget` does not run a hidden `refreshIntervalSeconds` polling loop.
It fetches widget data on mount, rebind or navigation hydration, then relies on
SSE snapshots for provider-triggered updates.

## FortiGate Metric Semantics

FortiGate CPU, memory, sessions and uptime are not pushed by FortiGate as a
native metric stream. Penguard currently treats FortiGate syslog as the
provider trigger:

1. A syslog event arrives.
2. The API forwards it to SIEM.
3. The API records ingestion health.
4. The API fetches a throttled FortiGate widget snapshot.
5. The API publishes the snapshot in `widgets[]`.
6. Vue applies that snapshot to every matching widget instance.

This means:

- No browser-side polling is required for the dashboard widget refresh.
- If FortiGate sends no syslog events, FortiGate metric widgets will not receive
  new pushed snapshots.
- Multiple duplicate widgets share the same latest snapshot through
  `useWidgetRealtimeStore`.
- Manual/scheduled ingestion remains a fallback and diagnostic path.

## Security Boundaries

- SSE events are owner-scoped by `ownerUserId`.
- Browser auth stays BFF-based through HTTP-only session cookies.
- FortiGate API keys are encrypted at rest and are never sent through SSE.
- Audit details are sanitized before SIEM forwarding.
- SSE does not authorize or execute FortiGate policy changes. Live FortiGate
  writes must use separate CSRF-protected, admin-gated policy orchestration APIs
  with preflight, diff/summary, explicit approval and audit.

## Operational Notes

- The API container exposes UDP `5514` by default for FortiGate syslog.
- `PENGUARD_FORTIGATE_SYSLOG_COLLECTOR_HOST` and
  `PENGUARD_FORTIGATE_SYSLOG_COLLECTOR_PORT` configure the collector
  bind address.
- `PENGUARD_FORTIGATE_SYSLOG_COLLECTOR_PUBLIC_HOST` is used when showing
  operators the collector address to configure on FortiGate.
- The old scheduler settings still exist for fallback ingestion, but the
  dashboard should not depend on them for normal realtime UX.

## Verification

```bash
cd apps/api && uv run pytest -q tests/test_fortigate_syslog_ingestion.py
cd apps/api && uv run pytest -q tests/test_realtime_widget_push.py
cd apps/api && uv run pytest -q tests/test_audit_log.py
cd apps/web && pnpm test -- tests/unit/draggableWidget.test.ts tests/unit/ticketsRealtimeStore.test.ts
```

Runtime checks:

```bash
docker compose ps api web siem-kowalski
docker compose logs --tail=120 api
docker compose logs --tail=120 siem-kowalski
```

Expected signs:

- `GET /api/events/stream` returns `200 OK`.
- API logs show `soc_service_request service=siem_kowalski method=POST path=/events/ingest`.
- SIEM logs show `siem_event_ingested`.
- New incidents appear in the cockpit without a browser refresh when detections
  create a ticket.
