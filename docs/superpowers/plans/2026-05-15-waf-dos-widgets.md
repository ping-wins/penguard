# WAF DoS Widgets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three canvas widgets (`waf-dos-rate`, `waf-dos-top-ips`, `waf-dos-feed`) that visualize FortiWeb DoS events from either SIEM incidents or raw SecurityEvents, updating in realtime via SSE.

**Architecture:** WAF widgets use a dedicated code path in `widgets.py` (bypasses the penguin-tool integration check used by SIEM/SOAR/XDR widgets, since FortiWeb data arrives via push). A new `WAF_WIDGET_IDS` set routes to `_waf_widget_data()`. Each handler queries `siem_kowalski` — either the `/incidents` endpoint filtered by `ruleId=fortiweb_dos_activity` (source=siem) or `/events?eventType=waf.dos` (source=raw). Three Vue components follow the existing `WidgetShell` + CSS-bar pattern — no external chart library needed.

**Tech Stack:** FastAPI, Python 3.13, pytest, Vue 3 (Composition API), TypeScript, Vitest, Tailwind CSS, `WidgetShell` + existing composables.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `apps/api/app/routers/widgets.py` | modify | Add `WAF_WIDGET_IDS`, `source`/`window`/`limit` query params, `_waf_widget_data()`, three handler helpers |
| `apps/api/tests/test_waf_dos_widgets.py` | create | All backend widget tests |
| `packages/contracts/fixtures/widget_catalog_soc.json` | modify | +3 widget catalog entries |
| `apps/web/src/components/widgets/waf/WidgetWafDosRate.vue` | create | CSS bar chart: blocked req/s per minute bucket |
| `apps/web/src/components/widgets/waf/WidgetWafDosTopIps.vue` | create | Table: IP → count, blocked badge |
| `apps/web/src/components/widgets/waf/WidgetWafDosFeed.vue` | create | Feed: last N DoS events, severity badge |
| `apps/web/src/lib/widgetSeries.ts` | modify | +3 sampler entries |
| `apps/web/src/utils/widgetLayout.ts` | modify | +3 size constraint entries |
| `apps/web/src/components/canvas/DashboardCanvas.vue` | modify | Import + register 3 new components in `widgetMap` |
| `apps/web/tests/unit/widgetWafDos.test.ts` | create | Frontend widget tests |
| `docs/product/feature-map.md` | modify | Add WAF DoS widgets row |

---

## Task 1: Backend — WAF widget data helpers

**Files:**
- Modify: `apps/api/app/routers/widgets.py`

- [ ] **Step 1: Add `WAF_WIDGET_IDS` set and new query params**

Open `apps/api/app/routers/widgets.py`. Add after the `SOC_WIDGET_IDS` block:

```python
WAF_WIDGET_IDS = {
    "waf-dos-rate",
    "waf-dos-top-ips",
    "waf-dos-feed",
}
```

Update the `get_widget_data` signature to add three optional query params:

```python
@router.get("/widgets/{widget_id}/data")
def get_widget_data(
    widget_id: str,
    service: Annotated[FortiGateWidgetService, Depends(get_fortigate_widget_service)],
    penguin_service: Annotated[PenguinToolService, Depends(get_penguin_tool_integration_service)],
    siem_client: Annotated[SocWidgetClient, Depends(get_siem_client)],
    xdr_client: Annotated[SocWidgetClient, Depends(get_xdr_client)],
    soar_client: Annotated[SocWidgetClient, Depends(get_soar_client)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    integration_id: Annotated[str | None, Query(alias="integrationId")] = None,
    source: Annotated[str, Query()] = "siem",
    window: Annotated[str, Query()] = "1h",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
```

- [ ] **Step 2: Add WAF routing in `get_widget_data`**

Add the WAF branch before the SOC branch:

```python
    if widget_id in WAF_WIDGET_IDS:
        return _waf_widget_data(
            widget_id,
            source=source,
            window=window,
            limit=limit,
            siem_client=siem_client,
        )
    if widget_id in SOC_WIDGET_IDS:
```

- [ ] **Step 3: Add `_waf_widget_data` dispatcher**

Add after the `_soc_widget_data` function:

```python
def _waf_widget_data(
    widget_id: str,
    *,
    source: str,
    window: str,
    limit: int,
    siem_client: SocWidgetClient,
) -> dict[str, Any]:
    normalized_source = source if source in {"siem", "raw"} else "siem"
    match widget_id:
        case "waf-dos-rate":
            data = _waf_dos_rate(normalized_source, window=window, siem_client=siem_client)
        case "waf-dos-top-ips":
            data = _waf_dos_top_ips(normalized_source, window=window, limit=limit, siem_client=siem_client)
        case "waf-dos-feed":
            data = _waf_dos_feed(normalized_source, limit=limit, siem_client=siem_client)
        case _:
            raise HTTPException(status_code=404, detail="Widget data not found")
    logger.info(
        "waf_widget_data_ready widget_id=%s source=%s",
        widget_id,
        normalized_source,
    )
    return {
        "widgetId": widget_id,
        "status": "ready",
        "data": data,
        "meta": {
            "source": normalized_source,
            "cacheTtlSeconds": 5,
            "refreshIntervalSeconds": 5,
        },
    }
```

- [ ] **Step 4: Add `_window_seconds` helper**

```python
def _window_seconds(window: str) -> int:
    return {"15m": 900, "1h": 3600, "6h": 21600, "24h": 86400}.get(window, 3600)
```

- [ ] **Step 5: Add `_waf_dos_incidents` and `_waf_dos_events` helpers**

```python
from datetime import UTC, datetime, timedelta

def _waf_dos_incidents(siem_client: SocWidgetClient, *, since: datetime) -> list[dict[str, Any]]:
    raw = _items(siem_client.request("GET", "/incidents", params={"limit": 500}))
    return [
        inc for inc in raw
        if inc.get("ruleId") == "fortiweb_dos_activity"
        and _parse_dt(inc.get("createdAt")) >= since
    ]


def _waf_dos_events(siem_client: SocWidgetClient, *, since: datetime, limit: int) -> list[dict[str, Any]]:
    raw = _items(
        siem_client.request(
            "GET",
            "/events",
            params={"eventType": "waf.dos", "limit": limit},
        )
    )
    return [e for e in raw if _parse_dt(e.get("occurredAt")) >= since]


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=UTC)
```

- [ ] **Step 6: Add `_waf_dos_rate` helper**

```python
def _waf_dos_rate(
    source: str,
    *,
    window: str,
    siem_client: SocWidgetClient,
) -> dict[str, Any]:
    seconds = _window_seconds(window)
    since = datetime.now(UTC) - timedelta(seconds=seconds)

    if source == "raw":
        records = _waf_dos_events(siem_client, since=since, limit=500)
        ts_key = "occurredAt"
        action_key = "attributes"
        def is_blocked(r: dict[str, Any]) -> bool:
            attrs = r.get("attributes") or {}
            return str(attrs.get("action", "")).lower() in {"block", "blocked", "deny", "dropped"}
    else:
        records = _waf_dos_incidents(siem_client, since=since)
        ts_key = "createdAt"
        def is_blocked(r: dict[str, Any]) -> bool:  # noqa: E301
            return True  # incidents are always triggered by blocked/detected events

    buckets: dict[str, dict[str, int]] = {}
    for record in records:
        dt = _parse_dt(record.get(ts_key))
        bucket_key = dt.strftime("%Y-%m-%dT%H:%M:00Z")
        if bucket_key not in buckets:
            buckets[bucket_key] = {"blocked": 0, "allowed": 0}
        if is_blocked(record):
            buckets[bucket_key]["blocked"] += 1
        else:
            buckets[bucket_key]["allowed"] += 1

    sorted_buckets = [
        {"ts": k, "blocked": v["blocked"], "allowed": v["allowed"]}
        for k, v in sorted(buckets.items())
    ]
    return {"buckets": sorted_buckets, "window": window, "source": source}
```

- [ ] **Step 7: Add `_waf_dos_top_ips` helper**

```python
def _waf_dos_top_ips(
    source: str,
    *,
    window: str,
    limit: int,
    siem_client: SocWidgetClient,
) -> dict[str, Any]:
    seconds = _window_seconds(window)
    since = datetime.now(UTC) - timedelta(seconds=seconds)

    if source == "raw":
        records = _waf_dos_events(siem_client, since=since, limit=500)
        def get_ip(r: dict[str, Any]) -> str:
            return str(r.get("entities", {}).get("sourceIp") or "")
        def get_ts(r: dict[str, Any]) -> str:
            return str(r.get("occurredAt") or "")
        def get_blocked(r: dict[str, Any]) -> bool:
            attrs = r.get("attributes") or {}
            return str(attrs.get("action", "")).lower() in {"block", "blocked", "deny", "dropped"}
    else:
        records = _waf_dos_incidents(siem_client, since=since)
        def get_ip(r: dict[str, Any]) -> str:  # noqa: E301
            return str(r.get("entities", {}).get("sourceIp") or "")
        def get_ts(r: dict[str, Any]) -> str:  # noqa: E301
            return str(r.get("createdAt") or "")
        def get_blocked(_r: dict[str, Any]) -> bool:  # noqa: E301
            return True

    ip_data: dict[str, dict[str, Any]] = {}
    for record in records:
        ip = get_ip(record)
        if not ip:
            continue
        if ip not in ip_data:
            ip_data[ip] = {"count": 0, "lastSeen": "", "blocked": get_blocked(record)}
        ip_data[ip]["count"] += 1
        ts = get_ts(record)
        if ts > ip_data[ip]["lastSeen"]:
            ip_data[ip]["lastSeen"] = ts

    rows = [
        {"ip": ip, "count": v["count"], "lastSeen": v["lastSeen"], "blocked": v["blocked"]}
        for ip, v in ip_data.items()
    ]
    rows.sort(key=lambda r: r["count"], reverse=True)
    return {"rows": rows[:limit], "source": source}
```

- [ ] **Step 8: Add `_waf_dos_feed` helper**

```python
def _waf_dos_feed(
    source: str,
    *,
    limit: int,
    siem_client: SocWidgetClient,
) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(hours=24)

    if source == "raw":
        records = _waf_dos_events(siem_client, since=since, limit=limit)
        items_out = [
            {
                "id": r.get("id") or "",
                "ts": r.get("occurredAt") or "",
                "sourceIp": r.get("entities", {}).get("sourceIp") or "",
                "action": r.get("attributes", {}).get("action") or "",
                "severity": r.get("severity") or "medium",
                "message": r.get("message") or "DoS event",
                "policy": r.get("attributes", {}).get("policy") or "",
            }
            for r in records
        ]
    else:
        records = _waf_dos_incidents(siem_client, since=since)
        records.sort(key=lambda r: r.get("createdAt") or "", reverse=True)
        items_out = [
            {
                "id": r.get("id") or "",
                "ts": r.get("createdAt") or "",
                "sourceIp": r.get("entities", {}).get("sourceIp") or "",
                "action": "block",
                "severity": r.get("severity") or "critical",
                "message": r.get("summary") or r.get("title") or "DoS activity detected",
                "policy": r.get("attributes", {}).get("policy") or "",
            }
            for r in records[:limit]
        ]
    return {"items": items_out, "source": source}
```

---

## Task 2: Backend tests

**Files:**
- Create: `apps/api/tests/test_waf_dos_widgets.py`

- [ ] **Step 1: Write test file**

```python
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.auth import dependencies as auth_dependencies
from app.main import app
from app.routers import widgets as widgets_router


class FakeSiemClient:
    def __init__(self, incidents=None, events=None):
        self._incidents = incidents or []
        self._events = events or []
        self.calls: list[dict] = []

    def request(self, method, path, *, json=None, params=None, headers=None, pass_through_statuses=None):
        self.calls.append({"method": method, "path": path, "params": params})
        if path == "/incidents":
            return {"items": self._incidents}
        if path == "/events":
            et = (params or {}).get("eventType")
            filtered = [e for e in self._events if not et or e.get("eventType") == et]
            return {"items": filtered}
        return {"items": []}


def _now_iso():
    return datetime.now(UTC).isoformat()


def _ago_iso(seconds):
    return (datetime.now(UTC) - timedelta(seconds=seconds)).isoformat()


def teardown_function():
    app.dependency_overrides.clear()


# ── waf-dos-rate ─────────────────────────────────────────────────────────────

def test_waf_dos_rate_siem_source_returns_buckets():
    fake = FakeSiemClient(incidents=[
        {"id": "inc_1", "ruleId": "fortiweb_dos_activity", "createdAt": _now_iso(), "severity": "critical", "entities": {}, "attributes": {}},
        {"id": "inc_2", "ruleId": "fortiweb_dos_activity", "createdAt": _now_iso(), "severity": "critical", "entities": {}, "attributes": {}},
    ])
    app.dependency_overrides[widgets_router.get_siem_client] = lambda: fake
    client = TestClient(app)

    resp = client.get("/api/widgets/waf-dos-rate/data", params={"source": "siem", "window": "1h"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["window"] == "1h"
    assert body["data"]["source"] == "siem"
    assert len(body["data"]["buckets"]) >= 1
    total_blocked = sum(b["blocked"] for b in body["data"]["buckets"])
    assert total_blocked == 2


def test_waf_dos_rate_raw_source_returns_buckets():
    fake = FakeSiemClient(events=[
        {"id": "evt_1", "eventType": "waf.dos", "occurredAt": _now_iso(), "severity": "critical", "entities": {"sourceIp": "10.10.10.10"}, "attributes": {"action": "block"}},
    ])
    app.dependency_overrides[widgets_router.get_siem_client] = lambda: fake
    client = TestClient(app)

    resp = client.get("/api/widgets/waf-dos-rate/data", params={"source": "raw", "window": "1h"})

    assert resp.status_code == 200
    assert resp.json()["data"]["source"] == "raw"
    total_blocked = sum(b["blocked"] for b in resp.json()["data"]["buckets"])
    assert total_blocked == 1


def test_waf_dos_rate_empty_returns_empty_buckets():
    fake = FakeSiemClient()
    app.dependency_overrides[widgets_router.get_siem_client] = lambda: fake
    client = TestClient(app)

    resp = client.get("/api/widgets/waf-dos-rate/data", params={"source": "siem"})

    assert resp.status_code == 200
    assert resp.json()["data"]["buckets"] == []


def test_waf_dos_rate_window_param_excludes_old_events():
    old_ts = _ago_iso(7200)  # 2h ago — outside 1h window
    fake = FakeSiemClient(incidents=[
        {"id": "inc_old", "ruleId": "fortiweb_dos_activity", "createdAt": old_ts, "severity": "critical", "entities": {}, "attributes": {}},
    ])
    app.dependency_overrides[widgets_router.get_siem_client] = lambda: fake
    client = TestClient(app)

    resp = client.get("/api/widgets/waf-dos-rate/data", params={"source": "siem", "window": "1h"})

    assert resp.status_code == 200
    assert resp.json()["data"]["buckets"] == []


def test_waf_dos_rate_ignores_non_fortiweb_incidents():
    fake = FakeSiemClient(incidents=[
        {"id": "inc_other", "ruleId": "fortigate_brute_force", "createdAt": _now_iso(), "severity": "high", "entities": {}, "attributes": {}},
    ])
    app.dependency_overrides[widgets_router.get_siem_client] = lambda: fake
    client = TestClient(app)

    resp = client.get("/api/widgets/waf-dos-rate/data", params={"source": "siem"})

    assert resp.status_code == 200
    assert resp.json()["data"]["buckets"] == []


# ── waf-dos-top-ips ───────────────────────────────────────────────────────────

def test_waf_dos_top_ips_siem_source_aggregates_by_ip():
    fake = FakeSiemClient(incidents=[
        {"id": "inc_1", "ruleId": "fortiweb_dos_activity", "createdAt": _now_iso(), "severity": "critical", "entities": {"sourceIp": "10.10.10.10"}, "attributes": {}},
        {"id": "inc_2", "ruleId": "fortiweb_dos_activity", "createdAt": _now_iso(), "severity": "critical", "entities": {"sourceIp": "10.10.10.10"}, "attributes": {}},
        {"id": "inc_3", "ruleId": "fortiweb_dos_activity", "createdAt": _now_iso(), "severity": "high", "entities": {"sourceIp": "10.10.10.20"}, "attributes": {}},
    ])
    app.dependency_overrides[widgets_router.get_siem_client] = lambda: fake
    client = TestClient(app)

    resp = client.get("/api/widgets/waf-dos-top-ips/data", params={"source": "siem"})

    assert resp.status_code == 200
    rows = resp.json()["data"]["rows"]
    assert rows[0]["ip"] == "10.10.10.10"
    assert rows[0]["count"] == 2
    assert rows[0]["blocked"] is True
    assert rows[1]["ip"] == "10.10.10.20"
    assert rows[1]["count"] == 1


def test_waf_dos_top_ips_raw_source_aggregates_by_ip():
    fake = FakeSiemClient(events=[
        {"id": "evt_1", "eventType": "waf.dos", "occurredAt": _now_iso(), "severity": "critical", "entities": {"sourceIp": "10.10.10.10"}, "attributes": {"action": "block"}},
        {"id": "evt_2", "eventType": "waf.dos", "occurredAt": _now_iso(), "severity": "critical", "entities": {"sourceIp": "10.10.10.10"}, "attributes": {"action": "deny"}},
        {"id": "evt_3", "eventType": "waf.dos", "occurredAt": _now_iso(), "severity": "medium", "entities": {"sourceIp": "10.10.10.30"}, "attributes": {"action": "allow"}},
    ])
    app.dependency_overrides[widgets_router.get_siem_client] = lambda: fake
    client = TestClient(app)

    resp = client.get("/api/widgets/waf-dos-top-ips/data", params={"source": "raw"})

    assert resp.status_code == 200
    rows = resp.json()["data"]["rows"]
    assert rows[0]["ip"] == "10.10.10.10"
    assert rows[0]["blocked"] is True
    assert rows[1]["ip"] == "10.10.10.30"
    assert rows[1]["blocked"] is False


def test_waf_dos_top_ips_respects_limit():
    incidents = [
        {"id": f"inc_{i}", "ruleId": "fortiweb_dos_activity", "createdAt": _now_iso(), "severity": "critical", "entities": {"sourceIp": f"10.0.0.{i}"}, "attributes": {}}
        for i in range(20)
    ]
    fake = FakeSiemClient(incidents=incidents)
    app.dependency_overrides[widgets_router.get_siem_client] = lambda: fake
    client = TestClient(app)

    resp = client.get("/api/widgets/waf-dos-top-ips/data", params={"source": "siem", "limit": "5"})

    assert resp.status_code == 200
    assert len(resp.json()["data"]["rows"]) == 5


# ── waf-dos-feed ──────────────────────────────────────────────────────────────

def test_waf_dos_feed_siem_source_returns_items_desc():
    ts1 = _ago_iso(300)
    ts2 = _ago_iso(100)
    fake = FakeSiemClient(incidents=[
        {"id": "inc_old", "ruleId": "fortiweb_dos_activity", "createdAt": ts1, "severity": "critical", "summary": "DoS 1", "entities": {"sourceIp": "10.10.10.10"}, "attributes": {}},
        {"id": "inc_new", "ruleId": "fortiweb_dos_activity", "createdAt": ts2, "severity": "critical", "summary": "DoS 2", "entities": {"sourceIp": "10.10.10.10"}, "attributes": {}},
    ])
    app.dependency_overrides[widgets_router.get_siem_client] = lambda: fake
    client = TestClient(app)

    resp = client.get("/api/widgets/waf-dos-feed/data", params={"source": "siem"})

    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 2
    assert items[0]["id"] == "inc_new"
    assert items[0]["action"] == "block"
    assert items[0]["message"] == "DoS 2"


def test_waf_dos_feed_raw_source_returns_items():
    fake = FakeSiemClient(events=[
        {"id": "evt_1", "eventType": "waf.dos", "occurredAt": _now_iso(), "severity": "critical", "message": "HTTP flood", "entities": {"sourceIp": "10.10.10.10"}, "attributes": {"action": "block", "policy": "lab-dos"}},
    ])
    app.dependency_overrides[widgets_router.get_siem_client] = lambda: fake
    client = TestClient(app)

    resp = client.get("/api/widgets/waf-dos-feed/data", params={"source": "raw"})

    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert items[0]["message"] == "HTTP flood"
    assert items[0]["action"] == "block"
    assert items[0]["policy"] == "lab-dos"


def test_waf_dos_feed_respects_limit():
    events = [
        {"id": f"evt_{i}", "eventType": "waf.dos", "occurredAt": _now_iso(), "severity": "critical", "entities": {"sourceIp": "10.10.10.10"}, "attributes": {"action": "block"}}
        for i in range(30)
    ]
    fake = FakeSiemClient(events=events)
    app.dependency_overrides[widgets_router.get_siem_client] = lambda: fake
    client = TestClient(app)

    resp = client.get("/api/widgets/waf-dos-feed/data", params={"source": "raw", "limit": "5"})

    assert resp.status_code == 200
    assert len(resp.json()["data"]["items"]) == 5


# ── routing ───────────────────────────────────────────────────────────────────

def test_waf_widget_does_not_require_integration_id():
    fake = FakeSiemClient()
    app.dependency_overrides[widgets_router.get_siem_client] = lambda: fake
    client = TestClient(app)

    resp = client.get("/api/widgets/waf-dos-feed/data")

    assert resp.status_code == 200


def test_waf_widget_invalid_source_falls_back_to_siem():
    fake = FakeSiemClient()
    app.dependency_overrides[widgets_router.get_siem_client] = lambda: fake
    client = TestClient(app)

    resp = client.get("/api/widgets/waf-dos-rate/data", params={"source": "banana"})

    assert resp.status_code == 200
    assert resp.json()["meta"]["source"] == "siem"
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd apps/api && uv run pytest tests/test_waf_dos_widgets.py -v
```

Expected: most tests fail with `404` or `NameError` — handlers not yet wired.

- [ ] **Step 3: Implement all handler code from Task 1**

Follow Task 1 steps 1–8 exactly.

- [ ] **Step 4: Run tests — expect all pass**

```bash
cd apps/api && uv run pytest tests/test_waf_dos_widgets.py -v
```

Expected: all 14 tests PASS.

- [ ] **Step 5: Run full API test suite**

```bash
cd apps/api && uv run pytest -q
```

Expected: no regressions.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/routers/widgets.py apps/api/tests/test_waf_dos_widgets.py
git commit -m "feat(widgets): add WAF DoS rate, top-IPs, feed widget endpoints"
```

---

## Task 3: Widget catalog entries

**Files:**
- Modify: `packages/contracts/fixtures/widget_catalog_soc.json`

- [ ] **Step 1: Add three entries to the `items` array**

Append inside the `"items"` array at the end, before the closing `]`:

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

- [ ] **Step 2: Verify JSON is valid**

```bash
python -c "import json; json.load(open('packages/contracts/fixtures/widget_catalog_soc.json'))"
```

Expected: no output (silent success).

- [ ] **Step 3: Commit**

```bash
git add packages/contracts/fixtures/widget_catalog_soc.json
git commit -m "feat(catalog): add waf-dos-rate, waf-dos-top-ips, waf-dos-feed entries"
```

---

## Task 4: `WidgetWafDosRate.vue`

**Files:**
- Create: `apps/web/src/components/widgets/waf/WidgetWafDosRate.vue`

- [ ] **Step 1: Create the component**

```vue
<script setup lang="ts">
import { computed, ref } from 'vue'
import { Activity } from 'lucide-vue-next'
import WidgetShell from '../shell/WidgetShell.vue'
import WidgetEmptyState from '../shell/WidgetEmptyState.vue'

const props = defineProps<{
  data: any
  instanceId: string
  integrationId: string
  catalogId: string
}>()

type Bucket = { ts: string; blocked: number; allowed: number }

const selectedWindow = ref('1h')
const windows = ['15m', '1h', '6h', '24h']

const buckets = computed<Bucket[]>(() =>
  Array.isArray(props.data?.buckets) ? props.data.buckets : []
)

const maxVal = computed(() =>
  buckets.value.reduce((m, b) => Math.max(m, b.blocked + b.allowed), 0)
)

const totalBlocked = computed(() => buckets.value.reduce((s, b) => s + b.blocked, 0))
const totalAllowed = computed(() => buckets.value.reduce((s, b) => s + b.allowed, 0))
const source = computed(() => props.data?.source ?? 'siem')

function barHeightPct(val: number): string {
  if (maxVal.value === 0) return '0%'
  return `${Math.max(4, (val / maxVal.value) * 100)}%`
}

function formatTs(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ts
  }
}
</script>

<template>
  <WidgetShell
    :widget-id="catalogId"
    title="WAF DoS Rate"
    subtitle="HTTP flood req/min"
    :icon="Activity"
    source="fortiweb"
  >
    <template #glance>
      <div class="mb-2 flex items-center justify-between gap-2">
        <div class="flex gap-1">
          <button
            v-for="w in windows"
            :key="w"
            type="button"
            class="rounded px-1.5 py-0.5 text-[10px] font-medium transition-colors"
            :class="selectedWindow === w
              ? 'bg-theme-primary/20 text-theme-primary'
              : 'text-theme-text-muted hover:text-theme-text'"
            @click.stop="selectedWindow = w"
          >
            {{ w }}
          </button>
        </div>
        <span class="text-[10px] text-theme-text-muted">{{ source }}</span>
      </div>

      <div v-if="buckets.length === 0">
        <WidgetEmptyState message="No DoS events in window." />
      </div>
      <div v-else class="flex min-h-0 flex-1 items-end gap-px overflow-hidden">
        <div
          v-for="bucket in buckets"
          :key="bucket.ts"
          class="group relative flex min-w-0 flex-1 flex-col items-center justify-end"
          :title="`${formatTs(bucket.ts)}\nBlocked: ${bucket.blocked}\nAllowed: ${bucket.allowed}`"
        >
          <div class="w-full rounded-t-sm bg-red-500/70" :style="{ height: barHeightPct(bucket.blocked) }" />
          <div
            v-if="bucket.allowed > 0"
            class="w-full bg-theme-text/20"
            :style="{ height: barHeightPct(bucket.allowed) }"
          />
        </div>
      </div>

      <div class="mt-2 flex justify-between text-[10px] text-theme-text-muted">
        <span class="flex items-center gap-1">
          <span class="h-2 w-2 rounded-sm bg-red-500/70" /> Blocked {{ totalBlocked }}
        </span>
        <span class="flex items-center gap-1">
          <span class="h-2 w-2 rounded-sm bg-theme-text/20" /> Allowed {{ totalAllowed }}
        </span>
      </div>
    </template>

    <template #detail>
      <div class="flex flex-col gap-3">
        <div class="text-xs font-semibold uppercase tracking-wide text-theme-text-muted">
          Minute-by-minute breakdown
        </div>
        <div v-if="buckets.length === 0" class="text-xs text-theme-text-muted">No data.</div>
        <div v-else class="max-h-64 overflow-y-auto no-scrollbar">
          <table class="w-full text-xs">
            <thead>
              <tr class="text-[10px] uppercase tracking-wide text-theme-text-muted">
                <th class="py-1 text-left">Time</th>
                <th class="py-1 text-right">Blocked</th>
                <th class="py-1 text-right">Allowed</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="b in buckets"
                :key="b.ts"
                class="border-t border-theme-border/30"
              >
                <td class="py-0.5 font-mono text-theme-text-muted">{{ formatTs(b.ts) }}</td>
                <td class="py-0.5 text-right font-semibold text-red-400">{{ b.blocked }}</td>
                <td class="py-0.5 text-right text-theme-text-muted">{{ b.allowed }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </WidgetShell>
</template>
```

---

## Task 5: `WidgetWafDosTopIps.vue`

**Files:**
- Create: `apps/web/src/components/widgets/waf/WidgetWafDosTopIps.vue`

- [ ] **Step 1: Create the component**

```vue
<script setup lang="ts">
import { computed } from 'vue'
import { ShieldAlert } from 'lucide-vue-next'
import WidgetShell from '../shell/WidgetShell.vue'
import WidgetEmptyState from '../shell/WidgetEmptyState.vue'

const props = defineProps<{
  data: any
  instanceId: string
  integrationId: string
  catalogId: string
}>()

type IpRow = { ip: string; count: number; lastSeen: string; blocked: boolean }

const rows = computed<IpRow[]>(() =>
  Array.isArray(props.data?.rows) ? props.data.rows : []
)

const maxCount = computed(() => rows.value.reduce((m, r) => Math.max(m, r.count), 0))
const source = computed(() => props.data?.source ?? 'siem')

function barWidthPct(count: number): string {
  if (maxCount.value === 0) return '0%'
  return `${Math.max(4, (count / maxCount.value) * 100)}%`
}

function formatTs(ts: string): string {
  if (!ts) return '—'
  try {
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ts
  }
}
</script>

<template>
  <WidgetShell
    :widget-id="catalogId"
    title="WAF Top Attacking IPs"
    subtitle="Highest request count"
    :icon="ShieldAlert"
    source="fortiweb"
  >
    <template #glance>
      <div class="mb-1 flex justify-end text-[10px] text-theme-text-muted">{{ source }}</div>
      <div v-if="rows.length === 0">
        <WidgetEmptyState message="No attacking IPs detected." />
      </div>
      <div v-else class="flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto no-scrollbar">
        <div
          v-for="row in rows.slice(0, 8)"
          :key="row.ip"
          class="flex flex-col gap-0.5"
        >
          <div class="flex items-center justify-between gap-2 text-xs">
            <span
              class="font-mono truncate"
              :class="row.blocked ? 'text-red-400' : 'text-theme-text'"
            >{{ row.ip }}</span>
            <span class="shrink-0 tabular-nums text-theme-text-muted">{{ row.count }}</span>
          </div>
          <div class="h-1.5 overflow-hidden rounded-sm bg-theme-text/5">
            <div
              class="h-full rounded-sm"
              :class="row.blocked ? 'bg-red-500/60' : 'bg-amber-400/60'"
              :style="{ width: barWidthPct(row.count) }"
            />
          </div>
        </div>
      </div>
    </template>

    <template #detail>
      <div class="flex flex-col gap-3">
        <div class="text-xs font-semibold uppercase tracking-wide text-theme-text-muted">All IPs</div>
        <div v-if="rows.length === 0" class="text-xs text-theme-text-muted">No data.</div>
        <div v-else class="max-h-64 overflow-y-auto no-scrollbar">
          <table class="w-full text-xs">
            <thead>
              <tr class="text-[10px] uppercase tracking-wide text-theme-text-muted">
                <th class="py-1 text-left">IP</th>
                <th class="py-1 text-right">Requests</th>
                <th class="py-1 text-right">Last Seen</th>
                <th class="py-1 text-right">Status</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in rows"
                :key="row.ip"
                class="border-t border-theme-border/30"
              >
                <td class="py-0.5 font-mono" :class="row.blocked ? 'text-red-400' : 'text-theme-text'">{{ row.ip }}</td>
                <td class="py-0.5 text-right tabular-nums">{{ row.count }}</td>
                <td class="py-0.5 text-right text-theme-text-muted">{{ formatTs(row.lastSeen) }}</td>
                <td class="py-0.5 text-right">
                  <span
                    class="rounded px-1 py-0.5 text-[10px] font-medium"
                    :class="row.blocked
                      ? 'bg-red-500/20 text-red-300'
                      : 'bg-amber-500/20 text-amber-300'"
                  >
                    {{ row.blocked ? 'Blocked' : 'Allowed' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </WidgetShell>
</template>
```

---

## Task 6: `WidgetWafDosFeed.vue`

**Files:**
- Create: `apps/web/src/components/widgets/waf/WidgetWafDosFeed.vue`

- [ ] **Step 1: Create the component**

```vue
<script setup lang="ts">
import { computed } from 'vue'
import { Waves } from 'lucide-vue-next'
import WidgetShell from '../shell/WidgetShell.vue'
import WidgetEmptyState from '../shell/WidgetEmptyState.vue'

const props = defineProps<{
  data: any
  instanceId: string
  integrationId: string
  catalogId: string
}>()

type FeedItem = {
  id: string
  ts: string
  sourceIp: string
  action: string
  severity: string
  message: string
  policy: string
}

const items = computed<FeedItem[]>(() =>
  Array.isArray(props.data?.items) ? props.data.items : []
)

const source = computed(() => props.data?.source ?? 'siem')

function severityClass(severity: string): string {
  switch (severity.toLowerCase()) {
    case 'critical': return 'bg-red-500/20 text-red-300 border-red-500/30'
    case 'high': return 'bg-orange-500/20 text-orange-300 border-orange-500/30'
    case 'medium': return 'bg-amber-500/20 text-amber-300 border-amber-500/30'
    default: return 'bg-theme-text/10 text-theme-text-muted border-theme-border'
  }
}

function formatTs(ts: string): string {
  if (!ts) return '—'
  try {
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return ts
  }
}
</script>

<template>
  <WidgetShell
    :widget-id="catalogId"
    title="WAF DoS Events"
    subtitle="Live event feed"
    :icon="Waves"
    source="fortiweb"
  >
    <template #glance>
      <div class="mb-1 flex items-center justify-between text-[10px] text-theme-text-muted">
        <span>{{ items.length }} events</span>
        <span>{{ source }}</span>
      </div>
      <div v-if="items.length === 0">
        <WidgetEmptyState message="No DoS events." />
      </div>
      <div v-else class="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto no-scrollbar">
        <div
          v-for="item in items.slice(0, 10)"
          :key="item.id"
          class="rounded border border-theme-border/30 bg-theme-text/5 px-2 py-1.5 text-xs"
        >
          <div class="flex items-center justify-between gap-2">
            <span
              class="rounded border px-1 py-0.5 text-[10px] font-medium uppercase"
              :class="severityClass(item.severity)"
            >{{ item.severity }}</span>
            <span class="font-mono text-[10px] text-theme-text-muted">{{ formatTs(item.ts) }}</span>
          </div>
          <div class="mt-1 truncate text-theme-text">{{ item.message }}</div>
          <div class="mt-0.5 flex gap-2 text-[10px] text-theme-text-muted">
            <span class="font-mono">{{ item.sourceIp || '—' }}</span>
            <span v-if="item.action" class="uppercase">{{ item.action }}</span>
            <span v-if="item.policy" class="truncate">{{ item.policy }}</span>
          </div>
        </div>
      </div>
    </template>

    <template #detail>
      <div class="flex flex-col gap-2">
        <div class="text-xs font-semibold uppercase tracking-wide text-theme-text-muted">All events</div>
        <div v-if="items.length === 0" class="text-xs text-theme-text-muted">No data.</div>
        <div v-else class="max-h-80 overflow-y-auto no-scrollbar space-y-1">
          <div
            v-for="item in items"
            :key="item.id"
            class="rounded border border-theme-border/30 bg-theme-text/5 px-2 py-1.5 text-xs"
          >
            <div class="flex items-center justify-between gap-2">
              <span class="rounded border px-1 py-0.5 text-[10px] font-medium uppercase" :class="severityClass(item.severity)">{{ item.severity }}</span>
              <span class="font-mono text-[10px] text-theme-text-muted">{{ formatTs(item.ts) }}</span>
            </div>
            <div class="mt-1 text-theme-text">{{ item.message }}</div>
            <div class="mt-0.5 flex gap-2 text-[10px] text-theme-text-muted">
              <span class="font-mono">{{ item.sourceIp || '—' }}</span>
              <span v-if="item.action" class="uppercase">{{ item.action }}</span>
              <span v-if="item.policy">{{ item.policy }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>
  </WidgetShell>
</template>
```

---

## Task 7: Wire components into `DashboardCanvas` and supporting files

**Files:**
- Modify: `apps/web/src/components/canvas/DashboardCanvas.vue`
- Modify: `apps/web/src/lib/widgetSeries.ts`
- Modify: `apps/web/src/utils/widgetLayout.ts`

- [ ] **Step 1: Add imports to `DashboardCanvas.vue`**

After the last `import Widget…` line (currently `import WidgetFortigateTopSourceIps`), add:

```ts
import WidgetWafDosRate from '../widgets/waf/WidgetWafDosRate.vue'
import WidgetWafDosTopIps from '../widgets/waf/WidgetWafDosTopIps.vue'
import WidgetWafDosFeed from '../widgets/waf/WidgetWafDosFeed.vue'
```

- [ ] **Step 2: Register in `widgetMap`**

In the `widgetMap` object, after the `'fortigate-top-source-ips'` entry add:

```ts
  'waf-dos-rate': WidgetWafDosRate,
  'waf-dos-top-ips': WidgetWafDosTopIps,
  'waf-dos-feed': WidgetWafDosFeed,
```

- [ ] **Step 3: Add samplers to `widgetSeries.ts`**

In `SAMPLERS`, add after the `'soar-playbook-run-history'` entry:

```ts
  'waf-dos-rate': (data) => {
    const buckets = items(data, 'buckets')
    const blocked = buckets.reduce((s, b) => {
      if (!b || typeof b !== 'object') return s
      return s + num((b as Record<string, unknown>).blocked)
    }, 0)
    const allowed = buckets.reduce((s, b) => {
      if (!b || typeof b !== 'object') return s
      return s + num((b as Record<string, unknown>).allowed)
    }, 0)
    return { blocked, allowed, total: blocked + allowed }
  },
  'waf-dos-top-ips': (data) => ({
    topCount: num((data as any)?.rows?.[0]?.count ?? 0),
    uniqueIps: items(data, 'rows').length,
  }),
  'waf-dos-feed': (data) => ({
    events: items(data, 'items').length,
  }),
```

- [ ] **Step 4: Add size constraints to `widgetLayout.ts`**

In `WIDGET_SIZE_CONSTRAINTS`, add:

```ts
  'waf-dos-rate': { minW: 480, minH: 300, maxW: 980, maxH: 680 },
  'waf-dos-top-ips': { minW: 420, minH: 300, maxW: 880, maxH: 700 },
  'waf-dos-feed': { minW: 400, minH: 320, maxW: 840, maxH: 700 },
```

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/canvas/DashboardCanvas.vue \
        apps/web/src/lib/widgetSeries.ts \
        apps/web/src/utils/widgetLayout.ts \
        apps/web/src/components/widgets/waf/
git commit -m "feat(web): add WidgetWafDosRate, WidgetWafDosTopIps, WidgetWafDosFeed components"
```

---

## Task 8: Frontend tests

**Files:**
- Create: `apps/web/tests/unit/widgetWafDos.test.ts`

- [ ] **Step 1: Write test file**

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import WidgetWafDosRate from '../../src/components/widgets/waf/WidgetWafDosRate.vue'
import WidgetWafDosTopIps from '../../src/components/widgets/waf/WidgetWafDosTopIps.vue'
import WidgetWafDosFeed from '../../src/components/widgets/waf/WidgetWafDosFeed.vue'

const DEFAULT_PROPS = {
  instanceId: 'w_test_01',
  integrationId: 'int_waf_01',
  catalogId: 'waf-dos-rate',
}

function makeBuckets(n: number) {
  return Array.from({ length: n }, (_, i) => ({
    ts: new Date(Date.now() - i * 60000).toISOString(),
    blocked: 100 + i * 10,
    allowed: 0,
  }))
}

describe('WidgetWafDosRate', () => {
  it('renders without error when data is empty', () => {
    const wrapper = mount(WidgetWafDosRate, {
      global: { plugins: [createTestingPinia()] },
      props: { ...DEFAULT_PROPS, data: { buckets: [], source: 'siem' } },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders bar for each bucket', () => {
    const wrapper = mount(WidgetWafDosRate, {
      global: { plugins: [createTestingPinia()] },
      props: { ...DEFAULT_PROPS, data: { buckets: makeBuckets(5), source: 'siem' } },
    })
    const bars = wrapper.findAll('[title*="Blocked"]')
    expect(bars.length).toBeGreaterThan(0)
  })

  it('shows source label', () => {
    const wrapper = mount(WidgetWafDosRate, {
      global: { plugins: [createTestingPinia()] },
      props: { ...DEFAULT_PROPS, data: { buckets: [], source: 'raw' } },
    })
    expect(wrapper.text()).toContain('raw')
  })
})

describe('WidgetWafDosTopIps', () => {
  const rows = [
    { ip: '10.10.10.10', count: 500, lastSeen: new Date().toISOString(), blocked: true },
    { ip: '10.10.10.20', count: 100, lastSeen: new Date().toISOString(), blocked: false },
  ]

  it('renders rows', () => {
    const wrapper = mount(WidgetWafDosTopIps, {
      global: { plugins: [createTestingPinia()] },
      props: { ...DEFAULT_PROPS, catalogId: 'waf-dos-top-ips', data: { rows, source: 'siem' } },
    })
    expect(wrapper.text()).toContain('10.10.10.10')
    expect(wrapper.text()).toContain('10.10.10.20')
  })

  it('blocked row has red text class', () => {
    const wrapper = mount(WidgetWafDosTopIps, {
      global: { plugins: [createTestingPinia()] },
      props: { ...DEFAULT_PROPS, catalogId: 'waf-dos-top-ips', data: { rows, source: 'siem' } },
    })
    const redEl = wrapper.find('.text-red-400')
    expect(redEl.exists()).toBe(true)
    expect(redEl.text()).toContain('10.10.10.10')
  })

  it('shows Blocked badge for blocked row', () => {
    const wrapper = mount(WidgetWafDosTopIps, {
      global: { plugins: [createTestingPinia()] },
      props: { ...DEFAULT_PROPS, catalogId: 'waf-dos-top-ips', data: { rows, source: 'siem' } },
    })
    expect(wrapper.text()).toContain('Blocked')
  })

  it('renders empty state when no rows', () => {
    const wrapper = mount(WidgetWafDosTopIps, {
      global: { plugins: [createTestingPinia()] },
      props: { ...DEFAULT_PROPS, catalogId: 'waf-dos-top-ips', data: { rows: [], source: 'siem' } },
    })
    expect(wrapper.text()).toContain('No attacking IPs')
  })
})

describe('WidgetWafDosFeed', () => {
  const feedItems = [
    { id: 'evt_1', ts: new Date().toISOString(), sourceIp: '10.10.10.10', action: 'block', severity: 'critical', message: 'HTTP flood detected', policy: 'lab-dos' },
    { id: 'evt_2', ts: new Date().toISOString(), sourceIp: '10.10.10.10', action: 'block', severity: 'high', message: 'SYN flood', policy: '' },
  ]

  it('renders feed items', () => {
    const wrapper = mount(WidgetWafDosFeed, {
      global: { plugins: [createTestingPinia()] },
      props: { ...DEFAULT_PROPS, catalogId: 'waf-dos-feed', data: { items: feedItems, source: 'siem' } },
    })
    expect(wrapper.text()).toContain('HTTP flood detected')
    expect(wrapper.text()).toContain('SYN flood')
  })

  it('critical severity badge has red class', () => {
    const wrapper = mount(WidgetWafDosFeed, {
      global: { plugins: [createTestingPinia()] },
      props: { ...DEFAULT_PROPS, catalogId: 'waf-dos-feed', data: { items: feedItems, source: 'siem' } },
    })
    const badge = wrapper.find('.bg-red-500\\/20')
    expect(badge.exists()).toBe(true)
  })

  it('high severity badge has orange class', () => {
    const wrapper = mount(WidgetWafDosFeed, {
      global: { plugins: [createTestingPinia()] },
      props: { ...DEFAULT_PROPS, catalogId: 'waf-dos-feed', data: { items: feedItems, source: 'siem' } },
    })
    const badge = wrapper.find('.bg-orange-500\\/20')
    expect(badge.exists()).toBe(true)
  })

  it('renders empty state when no items', () => {
    const wrapper = mount(WidgetWafDosFeed, {
      global: { plugins: [createTestingPinia()] },
      props: { ...DEFAULT_PROPS, catalogId: 'waf-dos-feed', data: { items: [], source: 'raw' } },
    })
    expect(wrapper.text()).toContain('No DoS events')
  })
})
```

- [ ] **Step 2: Run frontend tests**

```bash
cd apps/web && pnpm test -- tests/unit/widgetWafDos.test.ts --runInBand
```

Expected: all tests PASS.

- [ ] **Step 3: Run full frontend test suite**

```bash
cd apps/web && pnpm test -- --runInBand
```

Expected: no regressions.

- [ ] **Step 4: Commit**

```bash
git add apps/web/tests/unit/widgetWafDos.test.ts
git commit -m "test(web): add WAF DoS widget unit tests"
```

---

## Task 9: Feature map update and final commit

**Files:**
- Modify: `docs/product/feature-map.md`

- [ ] **Step 1: Add feature row**

In `docs/product/feature-map.md`, add to the Widgets section (or after the last widget row):

```
| Widgets | FortiWeb WAF DoS visualization (rate, top IPs, feed) | `apps/api` + `apps/web` | beta | yes | FortiWeb lab + `/api/soc/ingest/fortiweb` push | `apps/api/app/routers/widgets.py`, `apps/web/src/components/widgets/waf/` | `cd apps/api && uv run pytest -q tests/test_waf_dos_widgets.py && cd ../web && pnpm test -- tests/unit/widgetWafDos.test.ts --runInBand` |
```

- [ ] **Step 2: Push everything**

```bash
git add docs/product/feature-map.md
git commit -m "docs(product): add WAF DoS widgets to feature map"
git push origin main
```

- [ ] **Step 3: Final verification — run both test suites**

```bash
cd apps/api && uv run pytest -q tests/test_waf_dos_widgets.py && cd ../web && pnpm test -- tests/unit/widgetWafDos.test.ts --runInBand
```

Expected: all pass, no errors.
