# Integration-Scoped Executive SIEM Metrics Design

**Date:** 2026-05-19
**Scope:** Add integration/source scoping to the SIEM executive metrics endpoint
and the BFF SOC widget path so executive widgets can show the selected
provider/integration instead of global SIEM totals.

---

## Context

`siem_kowalski` now exposes `GET /metrics/executive` with widget-ready sections
for severity, recent incidents, top entities, SLA and MTTD/MTTR. The BFF routes
existing SIEM widgets through that aggregate. This is correct for the current
single-tenant MVP, but the aggregate is global inside SIEM.

Workspace widgets already carry an `integrationId`. The BFF validates that the
widget is bound to the current user's matching Penguin tool integration before
returning data. However, the validated `integrationId` is not passed down to
the SIEM metrics endpoint, so an executive template connected to one provider
can still show incidents produced by another provider.

This spec narrows the metrics by provider/integration while preserving the
global behavior for existing callers.

---

## Goals

- Allow executive SIEM metrics to be filtered by `integrationId`.
- Allow optional `providerType` filtering for cases where an incident has a
  provider source but no integration identifier.
- Preserve backward compatibility: calling `/metrics/executive` without filters
  returns the current global aggregate.
- Keep filtering in `siem_kowalski`; the BFF should not fetch all incidents and
  post-filter them.
- Avoid exposing secrets or cross-user integration metadata to the browser.
- Keep widget API shapes unchanged for existing Vue components.

---

## Non-Goals

- No multi-tenant authorization model inside `siem_kowalski`; BFF remains the
  user/session boundary.
- No new dashboard widget.
- No rollup table or background aggregation job in this phase.
- No changes to FortiGate/FortiWeb policy orchestration or SOAR execution.

---

## Endpoint Contract

Extend the SIEM endpoint:

```txt
GET /metrics/executive
  ?window=24h
  &limit=10
  &integrationId=int_fgt_01
  &providerType=fortigate
```

Query params:

| Param | Required | Meaning |
|-------|----------|---------|
| `window` | no | Existing metric window. Defaults to `24h`. |
| `limit` | no | Existing recent incident limit. Defaults to `10`. |
| `integrationId` | no | Restrict metrics to incidents/events tied to this integration. |
| `providerType` | no | Restrict metrics to a provider/source family such as `fortigate`, `fortiweb`, `xdr_rico`, `agent_private`, `manual` or `demo`. |

Response shape remains unchanged:

```json
{
  "window": "24h",
  "generatedAt": "2026-05-19T12:00:00.000Z",
  "scope": {
    "integrationId": "int_fgt_01",
    "providerType": "fortigate",
    "applied": true
  },
  "severity": { "items": [], "total": 0 },
  "recentIncidents": { "incidents": [], "count": 0 },
  "topEntities": { "entities": [] },
  "sla": { "breaches": [], "red": 0, "amber": 0, "open": 0 },
  "responseTimes": {
    "mttdAvgMs": null,
    "mttrAvgMs": null,
    "mttdMedianMs": null,
    "mttrMedianMs": null,
    "mttdSampleSize": 0,
    "mttrSampleSize": 0,
    "perIncident": []
  }
}
```

`scope` is additive. Existing widgets may ignore it. It is useful for logging,
debugging and future UI labels.

---

## Filtering Semantics

An incident matches `integrationId` when any of these fields equals the query
value:

- `incident.entities.integrationId`
- `incident.attributes.integrationId`
- `incident.origin.integrationId`
- any related event's `entities.integrationId`
- any related event's `attributes.integrationId`

An incident matches `providerType` when any of these values belongs to the
provider family:

- `incident.origin.kind`
- `incident.attributes.source`
- related event `source`
- related event `attributes.source`

Provider family matching is normalized:

| `providerType` | Matches |
|----------------|---------|
| `fortigate` | `fortigate`, `fortigate.syslog`, `fortigate.api` |
| `fortiweb` | `fortiweb`, `fortiweb.telemetry`, `fortiweb.api` |
| `xdr_rico` | `xdr_rico`, `xdr_rico.agent_private` |
| `agent_private` | `agent_private`, `xdr_rico.agent_private` |
| `manual` | `manual`, `manual.event` |
| `demo` | `demo`, `demo.replay`, `simulator` |

When both filters are provided, both must match. If a filter is provided and no
incident matches, the endpoint returns empty metric sections with HTTP 200.

Invalid `providerType` values return HTTP 422 from FastAPI validation. Unknown
but syntactically valid `integrationId` values return empty metrics, not 404,
because SIEM does not own integration authorization.

---

## SIEM Implementation

Add a narrow filtering layer before metric aggregation:

```python
def _filter_incidents_for_scope(
    incidents: list[Incident],
    *,
    integration_id: str | None,
    provider_type: ExecutiveProviderType | None,
) -> list[Incident]:
    ...
```

The response-time calculation already loads related events by `eventIds`. Reuse
that event lookup for filtering instead of querying event rows repeatedly per
incident. The implementation should:

1. Collect all event IDs from candidate incidents.
2. Load related events once with `store.list_events_by_ids()`.
3. Build `events_by_id`.
4. Filter incidents using incident fields and related events.
5. Pass the filtered incident list and `events_by_id` into the existing metrics
   calculations.

This keeps current behavior for unscoped calls and avoids an N+1 event lookup.

---

## BFF Routing

Update `_siem_executive_metrics()` in `apps/api/app/routers/widgets.py` to pass
the widget's validated `integrationId`:

```python
def _siem_executive_metrics(
    siem_client: SocWidgetClient,
    *,
    integration_id: str | None,
) -> dict[str, Any]:
    return siem_client.request(
        "GET",
        "/metrics/executive",
        params={
            "window": "24h",
            "limit": 10,
            "integrationId": integration_id,
        },
    )
```

For SIEM Penguin widgets, the BFF already validates the integration belongs to
the current user and has type `siem_kowalski`. That validation remains the
authorization boundary.

Future provider-specific SOC widgets can pass `providerType` too, but this spec
does not require UI changes for provider selection.

---

## Data Quality Requirements

Event ingestion should continue to include `integrationId` when available.
Agents implementing this spec should inspect FortiGate, FortiWeb and endpoint
ingestion paths and add tests where an event-to-incident path lacks
`integrationId`.

Do not fabricate an integration ID. If an event genuinely has no integration,
it remains visible in global metrics and in `providerType`-scoped metrics when
the source family matches.

---

## Logging

SIEM logs should include scope without secrets:

```txt
siem_executive_metrics window=24h integration_id=int_fgt_01 provider_type=fortigate severity_total=3 sla_red=1 sla_amber=0
```

If `integrationId` ever contains a value that looks secret-like, it is still an
internal ID and safe to log. Do not log API keys, tokens or full raw event
payloads.

---

## Testing

Add SIEM tests:

- Unscoped `/metrics/executive` keeps returning all incidents.
- `integrationId=int_fgt_a` includes only incidents whose incident or related
  event contains that integration ID.
- Filtering can match related events even if the incident payload itself lacks
  `attributes.integrationId`.
- `providerType=fortigate` includes FortiGate incidents and excludes FortiWeb,
  manual and demo incidents.
- Combined `integrationId` + `providerType` requires both matches.
- Unknown integration ID returns empty sections and HTTP 200.

Add BFF tests:

- SIEM widgets pass their validated `integrationId` to `/metrics/executive`.
- Wrong integration type still returns 404 and does not call SIEM.
- Missing `integrationId` still returns 422.

Optional contract tests:

- FortiGate/FortiWeb ingestion-created incidents preserve enough integration
  metadata to match scoped executive metrics.

---

## Acceptance Criteria

- Existing unscoped executive metrics tests still pass.
- Scoped SIEM metrics return only the requested integration/source family.
- Existing widget payload shapes do not change.
- Existing Vue widgets require no prop or rendering changes.
- `git diff --check`, SIEM tests and API widget tests pass.

---

## Open Follow-Ups

- Add rollup tables once incident/event volume makes request-time aggregation
  expensive.
- Add per-severity SLA thresholds after scoped metrics are stable.
- Surface the active metric scope in the executive widget shell or detail modal
  if analysts need visible assurance about what source is being shown.
