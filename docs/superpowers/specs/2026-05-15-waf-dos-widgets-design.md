# WAF DoS Widgets Design

**Date:** 2026-05-15
**Scope:** Three new dashboard widgets visualizing FortiWeb DoS events, with dual
data source (SIEM incidents or raw SecurityEvents), realtime SSE updates, and
integration into the existing widget canvas.

---

## Context

FortiWeb push telemetry already lands in Penguard via
`POST /api/soc/ingest/fortiweb`. The SIEM (`siem_kowalski`) classifies DoS
events as `waf.dos` and creates `fortiweb_dos_activity` incidents. No widget
exists yet to surface this data in the canvas. The lab topology
(`docs/operations/fortiweb-dos-lab.md`) sends HTTP flood traffic through
FortiWeb, generating `waf.dos` events that must be visible in real time.

---

## Widgets

Three widgets are added to the catalog. Each accepts a `source` query param
(`siem` | `raw`) on its data endpoint. Default is `siem`.

| Widget ID | Title | Kind | Default size |
|-----------|-------|------|--------------|
| `waf-dos-rate` | WAF DoS Rate | `line` | 6 × 4 |
| `waf-dos-top-ips` | WAF Top Attacking IPs | `table` | 5 × 4 |
| `waf-dos-feed` | WAF DoS Events | `feed` | 5 × 4 |

---

## API Endpoints

### GET /api/widgets/waf-dos-rate/data

Query params: `source=siem|raw` (default `siem`), `window=15m|1h|6h|24h` (default `1h`).

Response:

```json
{
  "buckets": [
    { "ts": "2026-05-15T10:00:00Z", "blocked": 142, "allowed": 3 },
    { "ts": "2026-05-15T10:01:00Z", "blocked": 891, "allowed": 0 }
  ],
  "window": "1h",
  "source": "siem"
}
```

Buckets are 1-minute intervals within the requested window. `blocked` counts
events/incidents with `action` in `{block, blocked, deny, dropped}`. `allowed`
counts the remainder. Empty window returns `buckets: []`.

### GET /api/widgets/waf-dos-top-ips/data

Query params: `source=siem|raw` (default `siem`), `limit=N` (default `10`),
`window=1h|6h|24h` (default `1h`).

Response:

```json
{
  "rows": [
    {
      "ip": "10.10.10.10",
      "count": 4823,
      "lastSeen": "2026-05-15T10:04:00Z",
      "blocked": true
    }
  ],
  "source": "siem"
}
```

Rows sorted by `count` descending. `blocked: true` when all observed actions
for that IP were block/deny.

### GET /api/widgets/waf-dos-feed/data

Query params: `source=siem|raw` (default `siem`), `limit=N` (default `20`).

Response:

```json
{
  "items": [
    {
      "id": "evt_abc123",
      "ts": "2026-05-15T10:04:12Z",
      "sourceIp": "10.10.10.10",
      "action": "block",
      "severity": "critical",
      "message": "HTTP flood detected",
      "policy": "lab-dos-policy"
    }
  ],
  "source": "siem"
}
```

Items ordered by `ts` descending.

---

## Source Mapping

| Source | Data pulled from | Filter |
|--------|-----------------|--------|
| `siem` | `siem_kowalski` incidents endpoint | `rule_id = fortiweb_dos_activity` |
| `raw` | SecurityEvent store in `siem_kowalski` | `event_type = waf.dos` |

Both sources are normalized by the API handler into the same response shapes
above. The widget components are unaware of the source — they only receive the
normalized payload.

---

## Architecture

```
widget_catalog_soc.json
  waf-dos-rate       dataEndpoint: /api/widgets/waf-dos-rate/data
  waf-dos-top-ips    dataEndpoint: /api/widgets/waf-dos-top-ips/data
  waf-dos-feed       dataEndpoint: /api/widgets/waf-dos-feed/data
          ↓
apps/api/app/routers/widgets.py
  get_waf_dos_rate()      → queries siem_kowalski client
  get_waf_dos_top_ips()   → queries siem_kowalski client
  get_waf_dos_feed()      → queries siem_kowalski client
  (source param selects incident vs. raw event path)
          ↓
apps/web/src/components/widgets/waf/
  WidgetWafDosRate.vue
  WidgetWafDosTopIps.vue
  WidgetWafDosFeed.vue
          ↓
apps/web/src/lib/widgetSeries.ts
  waf-dos-rate, waf-dos-top-ips, waf-dos-feed entries added
```

---

## Vue Components

All three components follow the existing widget pattern:
- Props: `widgetId: string`, `config: WidgetConfig`
- Use `useWidgetRealtimeStore` to receive SSE-pushed snapshots
- Call `dataEndpoint` with `source` as query param on mount and on SSE invalidation
- No internal polling

### WidgetWafDosRate

Stacked area chart. `blocked` series in red/danger color, `allowed` in muted
gray. X-axis: time labels. Y-axis: request count. Window selector (15m / 1h /
6h / 24h) rendered as tab strip above chart — changing window triggers
re-fetch with updated `window` param. Uses the chart library already present
in the project.

### WidgetWafDosTopIps

Table with columns: **IP** | **Requests** | **Last Seen** | **Status**.
Default sort: Requests descending. Rows where `blocked: true` render the IP
cell with a red/danger text class. Status column shows a badge: `Blocked`
(red) or `Allowed` (yellow).

### WidgetWafDosFeed

Scrollable list of event cards. Each card shows: severity badge (critical=red,
high=orange, medium=yellow) · timestamp · source IP · action chip · message
text · policy name. No pagination — renders up to `limit` items. Card layout
matches existing `WidgetSoarPlaybookRunHistory` card style for consistency.

---

## SSE Integration

No server-side changes required. The existing `useWidgetRealtimeStore` already
invalidates widget snapshots when a realtime event arrives. The three new
widget IDs (`waf-dos-rate`, `waf-dos-top-ips`, `waf-dos-feed`) are registered
in the store on component mount. When FortiWeb pushes a `waf.dos` event that
propagates through SIEM and SSE, the store invalidates those widgets and each
component re-fetches its `dataEndpoint`.

---

## widgetSeries.ts

Three sampler entries added:

```ts
'waf-dos-rate': (data) => ({
  blocked: num((data as any)?.buckets?.reduce(...) ?? 0),
}),
'waf-dos-top-ips': (data) => ({
  topCount: num((data as any)?.rows?.[0]?.count ?? 0),
}),
'waf-dos-feed': (data) => ({
  events: num((data as any)?.items?.length ?? 0),
}),
```

Exact sampler shape finalized during implementation once component data flow
is confirmed.

---

## Widget Catalog Entries

Three entries appended to `packages/contracts/fixtures/widget_catalog_soc.json`:

```json
{
  "id": "waf-dos-rate",
  "title": "WAF DoS Rate",
  "kind": "line",
  "source": "fortiweb",
  "requiredCapabilities": ["incidents"],
  "defaultSize": { "w": 6, "h": 4 },
  "dataEndpoint": "/api/widgets/waf-dos-rate/data",
  "template": "line-chart",
  "dataGroup": "waf",
  "fieldBindings": {
    "series": "buckets",
    "x": "ts",
    "y": ["blocked", "allowed"]
  }
},
{
  "id": "waf-dos-top-ips",
  "title": "WAF Top Attacking IPs",
  "kind": "table",
  "source": "fortiweb",
  "requiredCapabilities": ["incidents"],
  "defaultSize": { "w": 5, "h": 4 },
  "dataEndpoint": "/api/widgets/waf-dos-top-ips/data",
  "template": "entity-table",
  "dataGroup": "waf",
  "fieldBindings": {
    "rows": "rows"
  }
},
{
  "id": "waf-dos-feed",
  "title": "WAF DoS Events",
  "kind": "feed",
  "source": "fortiweb",
  "requiredCapabilities": ["incidents"],
  "defaultSize": { "w": 5, "h": 4 },
  "dataEndpoint": "/api/widgets/waf-dos-feed/data",
  "template": "incident-feed",
  "dataGroup": "waf",
  "fieldBindings": {
    "items": "items"
  }
}
```

---

## Tests

### Backend — `apps/api/tests/test_waf_dos_widgets.py`

| Test | What it validates |
|------|------------------|
| `test_dos_rate_siem_source` | SIEM incidents → correct buckets per minute |
| `test_dos_rate_raw_source` | Raw SecurityEvents → same bucket shape |
| `test_dos_top_ips_siem` | sourceIp aggregation from incidents |
| `test_dos_top_ips_raw` | sourceIp aggregation from raw events |
| `test_dos_feed_siem` | items ordered desc, correct shape |
| `test_dos_feed_raw` | same via raw events |
| `test_dos_rate_window_param` | `window=15m` filters to correct time range |
| `test_dos_rate_empty` | no events → `buckets: []`, no 500 |

### Frontend — `apps/web/tests/unit/widgetWafDos.test.ts`

| Test | What it validates |
|------|------------------|
| `renders rate chart with mocked buckets` | WidgetWafDosRate mounts without error |
| `source=raw passes param in URL` | dataEndpoint called with `?source=raw` |
| `re-fetches on SSE waf.dos snapshot` | store invalidation triggers fetch |
| `blocked row has danger class` | WidgetWafDosTopIps row styling |
| `severity badge color` | WidgetWafDosFeed critical → red badge class |

---

## Feature Map Update

`docs/product/feature-map.md` — add row:

| Area | Feature | Owner | Status | Customer-visible? | Lab dependency |
|------|---------|-------|--------|-------------------|----------------|
| Widgets | FortiWeb WAF DoS visualization (rate, top IPs, feed) | `apps/api` + `apps/web` | planned | yes | FortiWeb lab + `/api/soc/ingest/fortiweb` push |

---

## Files Changed

| File | Action |
|------|--------|
| `packages/contracts/fixtures/widget_catalog_soc.json` | +3 widget entries |
| `apps/api/app/routers/widgets.py` | +3 GET handlers |
| `apps/web/src/components/widgets/waf/WidgetWafDosRate.vue` | create |
| `apps/web/src/components/widgets/waf/WidgetWafDosTopIps.vue` | create |
| `apps/web/src/components/widgets/waf/WidgetWafDosFeed.vue` | create |
| `apps/web/src/lib/widgetSeries.ts` | +3 sampler entries |
| `apps/api/tests/test_waf_dos_widgets.py` | create |
| `apps/web/tests/unit/widgetWafDos.test.ts` | create |
| `docs/product/feature-map.md` | +1 row |

---

## Out of Scope

- FortiWeb policy writes from the dashboard
- Historical event retention beyond what SIEM already stores
- Multi-tenant isolation (single lab tenant assumed)
- Pagination on the feed widget
- Custom alert thresholds configurable from UI
