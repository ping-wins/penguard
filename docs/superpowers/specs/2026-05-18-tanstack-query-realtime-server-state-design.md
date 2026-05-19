# TanStack Query Realtime Server-State Design

## Problem

Penguard currently receives live FortiGate telemetry through UDP syslog, but
the cockpit still behaves like a fetch-on-demand dashboard. Widgets hydrate from
`/api/widgets/*/data`, the backend publishes narrow SSE events, and several
widgets only update after a manual page refresh or an ad hoc widget reload.

This keeps bringing back the same product issue: live telemetry exists in the
backend, but the Vue cockpit does not have a single authoritative server-state
cache that realtime events can update.

## Decision

Use TanStack Query for Vue as the frontend server-state cache and keep Pinia for
local cockpit/UI state.

- Pinia owns UI state: canvas layout, selected integration, drawers, filters,
  theme, local builder state and non-server interaction state.
- TanStack Query owns server state: widget payloads, SOC tickets, SIEM events,
  incidents, endpoint data and integration status snapshots.
- A single SSE bridge updates TanStack Query cache entries from backend domain
  events with `queryClient.setQueryData`.
- Normal SOC telemetry refresh must not use polling, hidden timers or
  `refetchInterval`.

The Context7-checked TanStack Query API supports the required model: `useQuery`
for initial fetch and cache ownership, `queryKey` for identity, `staleTime` for
freshness semantics, `refetchInterval` only when polling is explicitly desired,
and immutable `setQueryData` updates when realtime events already contain the
new data.

## Non-Negotiables

- No hidden widget polling loops for SOC/FortiGate/FortiWeb telemetry.
- No `refetchInterval` for telemetry widgets or tickets.
- No page refresh requirement to see new tickets, WAF DoS activity or top
  attacking IPs.
- Manual refresh buttons may call `refetch()` explicitly.
- One reconnect resync is allowed after SSE recovers from an error.
- Existing FortiGate API pull ingestion remains diagnostic/fallback only and
  must not be the normal live dashboard path.

## Target Flow

```txt
FortiGate UDP syslog
-> apps/api UDP collector
-> siem_kowalski /events/ingest
-> event and optional incident response
-> apps/api realtime broker
-> /api/events/stream SSE domain event
-> Vue realtime query bridge
-> TanStack Query cache upsert
-> widgets and SOC panels re-render from cache
```

## Backend Realtime Contract

The backend must publish domain events, not vague refresh hints.

### `soc.event.created`

Emitted whenever syslog forwarding creates a SIEM event.

```json
{
  "type": "soc.event.created",
  "ownerUserId": "user-id",
  "integrationId": "int_fgt_x",
  "event": {
    "id": "evt_x",
    "eventType": "network.event",
    "severity": "medium",
    "occurredAt": "2026-05-18T03:30:00Z",
    "entities": {},
    "attributes": {}
  },
  "receivedAt": "2026-05-18T03:30:00.000Z"
}
```

### `soc.incident.created`

Emitted when SIEM creates an incident/ticket. It includes the full ticket-shaped
incident payload so the frontend does not need to immediately refetch.

```json
{
  "type": "soc.incident.created",
  "ownerUserId": "user-id",
  "integrationId": "int_fgt_x",
  "event": {},
  "ticket": {},
  "receivedAt": "2026-05-18T03:30:00.000Z"
}
```

### Compatibility

The legacy `fortigate.syslog.event` SSE type can stay temporarily, but new code
must consume the domain events above. During migration the backend may include
`refresh: ["widgets", "tickets"]` for old components, but that is a bridge, not
the final update model.

## Frontend Query Keys

Use stable query key helpers so every component and realtime updater addresses
the same cache entries.

```ts
widgetDataKey(widgetId, params)
socTicketsKey(filters)
socIncidentsKey(filters)
socEventsKey(filters)
```

Widget keys must include the same request parameters that change the response:
`widgetId`, `integrationId`, `source`, `window`, `limit` and field bindings once
those are query-backed.

## Frontend Realtime Bridge

Create one bridge owned by app startup, not by every widget instance.

Responsibilities:

- Open `/api/events/stream` once.
- Parse typed realtime events.
- Upsert tickets into all active ticket/incident query caches.
- Upsert SIEM events into active event caches.
- Apply widget-specific reducers for known realtime-compatible widgets.
- Invalidate once on SSE reconnect if the connection had been broken.
- Never start an interval.

Initial implementation should support:

- `soc-recent-incidents`
- `soc-incidents-by-severity`
- `waf-dos-rate`
- `waf-dos-top-ips`
- `waf-dos-feed`
- SOC tickets panel store/query

## WAF DoS Semantics

DoS observed through FortiGate flow inference is not automatically blocked.

Widget classification rules:

- Blocked: `action` in `block`, `blocked`, `deny`, `dropped`.
- Observed/allowed: `action` in `close`, `accept`, `allow`, `allowed`,
  `timeout`, `client-rst`, `server-rst`, or `ingestionMode` equals
  `fortigate_flow_inference`.

The UI can still show severity as critical, but it must not claim traffic was
blocked unless the event action says so.

## Testing Requirements

Backend tests:

- Syslog forwarding emits `soc.event.created`.
- Syslog forwarding emits `soc.incident.created` with a ticket when SIEM creates
  an incident.
- WAF DoS inferred incidents keep action `close` and do not masquerade as block.

Frontend tests:

- TanStack Query plugin is installed.
- Realtime bridge updates widget query cache using SSE event data.
- Realtime bridge updates ticket cache without calling widget endpoints.
- WAF DoS widget data treats `action=close` as observed/allowed.
- No telemetry path test should use `refetchInterval`.

## Rollout

1. Add TanStack Query dependency and app plugin.
2. Add typed query key helpers.
3. Add backend SSE domain events for SIEM event/incident creation.
4. Add frontend realtime query bridge.
5. Convert WAF/SOC widgets to read through query cache.
6. Remove old per-widget realtime reload behavior after coverage is in place.
7. Keep manual refresh as explicit user action.

## Out Of Scope

- Replacing SSE with WebSocket.
- Moving realtime broker out of process.
- Full migration of every non-SOC settings/integration screen to TanStack Query.
- Removing FortiGate pull ingestion fallback endpoints.
