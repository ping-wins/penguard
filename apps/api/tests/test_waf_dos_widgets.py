from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.routers import widgets as widgets_router


class FakeSiemClient:
    def __init__(self, incidents=None, events=None):
        self._incidents = incidents or []
        self._events = events or []
        self.calls: list[dict] = []

    def request(
        self, method, path, *, json=None, params=None, headers=None, pass_through_statuses=None
    ):
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
    fake = FakeSiemClient(
        incidents=[
            {
                "id": "inc_1",
                "ruleId": "fortiweb_dos_activity",
                "createdAt": _now_iso(),
                "severity": "critical",
                "entities": {},
                "attributes": {"action": "block"},
            },
            {
                "id": "inc_2",
                "ruleId": "fortiweb_dos_activity",
                "createdAt": _now_iso(),
                "severity": "critical",
                "entities": {},
                "attributes": {"action": "deny"},
            },
        ]
    )
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


def test_waf_dos_rate_siem_inferred_close_counts_as_allowed():
    fake = FakeSiemClient(
        incidents=[
            {
                "id": "inc_inferred",
                "ruleId": "fortiweb_dos_activity",
                "createdAt": _now_iso(),
                "severity": "critical",
                "entities": {"sourceIp": "10.10.10.10"},
                "attributes": {
                    "action": "close",
                    "ingestionMode": "fortigate_flow_inference",
                },
            },
        ]
    )
    app.dependency_overrides[widgets_router.get_siem_client] = lambda: fake
    client = TestClient(app)

    resp = client.get("/api/widgets/waf-dos-rate/data", params={"source": "siem", "window": "1h"})

    assert resp.status_code == 200
    buckets = resp.json()["data"]["buckets"]
    assert sum(b["blocked"] for b in buckets) == 0
    assert sum(b["allowed"] for b in buckets) == 1


def test_waf_dos_rate_raw_source_returns_buckets():
    fake = FakeSiemClient(
        events=[
            {
                "id": "evt_1",
                "eventType": "waf.dos",
                "occurredAt": _now_iso(),
                "severity": "critical",
                "entities": {"sourceIp": "10.10.10.10"},
                "attributes": {"action": "block"},
            },
        ]
    )
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
    fake = FakeSiemClient(
        incidents=[
            {
                "id": "inc_old",
                "ruleId": "fortiweb_dos_activity",
                "createdAt": old_ts,
                "severity": "critical",
                "entities": {},
                "attributes": {},
            },
        ]
    )
    app.dependency_overrides[widgets_router.get_siem_client] = lambda: fake
    client = TestClient(app)

    resp = client.get("/api/widgets/waf-dos-rate/data", params={"source": "siem", "window": "1h"})

    assert resp.status_code == 200
    assert resp.json()["data"]["buckets"] == []


def test_waf_dos_rate_ignores_non_fortiweb_incidents():
    fake = FakeSiemClient(
        incidents=[
            {
                "id": "inc_other",
                "ruleId": "fortigate_brute_force",
                "createdAt": _now_iso(),
                "severity": "high",
                "entities": {},
                "attributes": {},
            },
        ]
    )
    app.dependency_overrides[widgets_router.get_siem_client] = lambda: fake
    client = TestClient(app)

    resp = client.get("/api/widgets/waf-dos-rate/data", params={"source": "siem"})

    assert resp.status_code == 200
    assert resp.json()["data"]["buckets"] == []


# ── waf-dos-top-ips ───────────────────────────────────────────────────────────


def test_waf_dos_top_ips_siem_source_aggregates_by_ip():
    fake = FakeSiemClient(
        incidents=[
            {
                "id": "inc_1",
                "ruleId": "fortiweb_dos_activity",
                "createdAt": _now_iso(),
                "severity": "critical",
                "entities": {"sourceIp": "10.10.10.10"},
                "attributes": {"action": "block"},
            },
            {
                "id": "inc_2",
                "ruleId": "fortiweb_dos_activity",
                "createdAt": _now_iso(),
                "severity": "critical",
                "entities": {"sourceIp": "10.10.10.10"},
                "attributes": {"action": "deny"},
            },
            {
                "id": "inc_3",
                "ruleId": "fortiweb_dos_activity",
                "createdAt": _now_iso(),
                "severity": "high",
                "entities": {"sourceIp": "10.10.10.20"},
                "attributes": {"action": "close", "ingestionMode": "fortigate_flow_inference"},
            },
        ]
    )
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
    assert rows[1]["blocked"] is False


def test_waf_dos_top_ips_raw_source_aggregates_by_ip():
    fake = FakeSiemClient(
        events=[
            {
                "id": "evt_1",
                "eventType": "waf.dos",
                "occurredAt": _now_iso(),
                "severity": "critical",
                "entities": {"sourceIp": "10.10.10.10"},
                "attributes": {"action": "block"},
            },
            {
                "id": "evt_2",
                "eventType": "waf.dos",
                "occurredAt": _now_iso(),
                "severity": "critical",
                "entities": {"sourceIp": "10.10.10.10"},
                "attributes": {"action": "deny"},
            },
            {
                "id": "evt_3",
                "eventType": "waf.dos",
                "occurredAt": _now_iso(),
                "severity": "medium",
                "entities": {"sourceIp": "10.10.10.30"},
                "attributes": {"action": "allow"},
            },
        ]
    )
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
        {
            "id": f"inc_{i}",
            "ruleId": "fortiweb_dos_activity",
            "createdAt": _now_iso(),
            "severity": "critical",
            "entities": {"sourceIp": f"10.0.0.{i}"},
            "attributes": {},
        }
        for i in range(20)
    ]
    fake = FakeSiemClient(incidents=incidents)
    app.dependency_overrides[widgets_router.get_siem_client] = lambda: fake
    client = TestClient(app)

    resp = client.get("/api/widgets/waf-dos-top-ips/data", params={"source": "siem", "limit": "5"})

    assert resp.status_code == 200
    assert len(resp.json()["data"]["rows"]) == 5


def test_waf_dos_top_ips_window_param_excludes_old_events():
    old_ts = _ago_iso(7200)  # 2h ago — outside 1h window
    fake = FakeSiemClient(
        incidents=[
            {
                "id": "inc_old",
                "ruleId": "fortiweb_dos_activity",
                "createdAt": old_ts,
                "severity": "critical",
                "entities": {"sourceIp": "10.10.10.10"},
                "attributes": {},
            },
        ]
    )
    app.dependency_overrides[widgets_router.get_siem_client] = lambda: fake
    client = TestClient(app)

    resp = client.get(
        "/api/widgets/waf-dos-top-ips/data", params={"source": "siem", "window": "1h"}
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["rows"] == []


# ── waf-dos-feed ──────────────────────────────────────────────────────────────


def test_waf_dos_feed_siem_source_returns_items_desc():
    ts1 = _ago_iso(300)
    ts2 = _ago_iso(100)
    fake = FakeSiemClient(
        incidents=[
            {
                "id": "inc_old",
                "ruleId": "fortiweb_dos_activity",
                "createdAt": ts1,
                "severity": "critical",
                "summary": "DoS 1",
                "entities": {"sourceIp": "10.10.10.10"},
                "attributes": {"action": "block"},
            },
            {
                "id": "inc_new",
                "ruleId": "fortiweb_dos_activity",
                "createdAt": ts2,
                "severity": "critical",
                "summary": "DoS 2",
                "entities": {"sourceIp": "10.10.10.10"},
                "attributes": {"action": "close", "ingestionMode": "fortigate_flow_inference"},
            },
        ]
    )
    app.dependency_overrides[widgets_router.get_siem_client] = lambda: fake
    client = TestClient(app)

    resp = client.get("/api/widgets/waf-dos-feed/data", params={"source": "siem"})

    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 2
    assert items[0]["id"] == "inc_new"
    assert items[0]["action"] == "close"
    assert items[0]["message"] == "DoS 2"


def test_waf_dos_feed_raw_source_returns_items():
    fake = FakeSiemClient(
        events=[
            {
                "id": "evt_1",
                "eventType": "waf.dos",
                "occurredAt": _now_iso(),
                "severity": "critical",
                "message": "HTTP flood",
                "entities": {"sourceIp": "10.10.10.10"},
                "attributes": {"action": "block", "policy": "lab-dos"},
            },
        ]
    )
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
        {
            "id": f"evt_{i}",
            "eventType": "waf.dos",
            "occurredAt": _now_iso(),
            "severity": "critical",
            "entities": {"sourceIp": "10.10.10.10"},
            "attributes": {"action": "block"},
        }
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


def test_waf_widget_unknown_id_returns_404():
    fake = FakeSiemClient()
    app.dependency_overrides[widgets_router.get_siem_client] = lambda: fake
    client = TestClient(app)

    resp = client.get("/api/widgets/waf-dos-unknown/data")

    # waf-dos-unknown is not in WAF_WIDGET_IDS so falls through to integrationId check
    assert resp.status_code == 422


def test_waf_dos_top_ips_blocked_updates_on_any_blocked_hit():
    fake = FakeSiemClient(
        events=[
            # first hit for this IP has action=allow
            {
                "id": "evt_1",
                "eventType": "waf.dos",
                "occurredAt": _now_iso(),
                "severity": "medium",
                "entities": {"sourceIp": "10.10.10.10"},
                "attributes": {"action": "allow"},
            },
            # second hit is blocked — should flip blocked=True
            {
                "id": "evt_2",
                "eventType": "waf.dos",
                "occurredAt": _now_iso(),
                "severity": "critical",
                "entities": {"sourceIp": "10.10.10.10"},
                "attributes": {"action": "block"},
            },
        ]
    )
    app.dependency_overrides[widgets_router.get_siem_client] = lambda: fake
    client = TestClient(app)

    resp = client.get("/api/widgets/waf-dos-top-ips/data", params={"source": "raw"})

    assert resp.status_code == 200
    rows = resp.json()["data"]["rows"]
    assert rows[0]["ip"] == "10.10.10.10"
    assert rows[0]["count"] == 2
    assert rows[0]["blocked"] is True
