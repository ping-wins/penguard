import pytest
from fastapi.testclient import TestClient

from app.auth import dependencies as auth_dependencies
from app.core.config import get_settings
from app.main import app
from app.routers import integrations, soc, soc_ingest
from app.routers.soc_ingest import BruteForceAggregator


class FakeSiemClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def request(
        self,
        method: str,
        path: str,
        *,
        json=None,
        params=None,
        headers=None,
        pass_through_statuses=None,
    ) -> dict:
        self.calls.append({"method": method, "path": path, "json": json})
        return {
            "id": f"evt_{len(self.calls):03d}",
            "eventType": (json or {}).get("eventType"),
        }


class FakeFortiWebTelemetryService:
    def __init__(self) -> None:
        self.recorded_events: list[dict] = []

    def verify_telemetry_token(self, *, integration_id: str, token: str) -> bool:
        return integration_id == "int_fweb_lab" and token == "native-token"

    def record_telemetry_event(
        self,
        *,
        integration_id: str,
        event_id: str | None,
        event_type: str,
        occurred_at: str,
    ) -> dict:
        event = {
            "integrationId": integration_id,
            "eventId": event_id,
            "eventType": event_type,
            "occurredAt": occurred_at,
        }
        self.recorded_events.append(event)
        return event


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setenv("FORTIDASHBOARD_SOC_INGEST_TOKEN", "test-secret-token")
    get_settings.cache_clear()
    fresh_aggregator = BruteForceAggregator(
        window_seconds=60.0,
        threshold=5,
        rate_limit_seconds=30.0,
    )
    app.dependency_overrides[soc_ingest.get_aggregator] = lambda: fresh_aggregator
    yield
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_missing_token_when_disabled_returns_503(monkeypatch):
    monkeypatch.delenv("FORTIDASHBOARD_SOC_INGEST_TOKEN", raising=False)
    get_settings.cache_clear()
    client = TestClient(app)

    response = client.post(
        "/api/soc/ingest/fortigate",
        json={"srcip": "203.0.113.7"},
    )

    assert response.status_code == 503
    assert "disabled" in response.json()["detail"].lower()


def test_fortiweb_native_ingest_uses_integration_token_without_global_env(monkeypatch):
    monkeypatch.delenv("FORTIDASHBOARD_SOC_INGEST_TOKEN", raising=False)
    get_settings.cache_clear()
    fake_siem = FakeSiemClient()
    fake_fortiweb = FakeFortiWebTelemetryService()
    app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem
    app.dependency_overrides[integrations.get_fortiweb_integration_service] = (
        lambda: fake_fortiweb
    )
    client = TestClient(app)

    response = client.post(
        "/api/soc/ingest/fortiweb/int_fweb_lab",
        headers={"Authorization": "Bearer native-token"},
        json={
            "type": "attack",
            "subtype": "dos",
            "src": "10.10.10.10",
            "dst": "10.10.20.30",
            "msg": "HTTP flood detected",
            "action": "block",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "received": 1,
        "emitted": 1,
        "integrationId": "int_fweb_lab",
    }
    assert fake_siem.calls[0]["json"]["eventType"] == "waf.dos"
    assert fake_siem.calls[0]["json"]["entities"]["integrationId"] == "int_fweb_lab"
    assert fake_fortiweb.recorded_events[0]["eventType"] == "waf.dos"


def test_invalid_token_returns_401():
    client = TestClient(app)

    response = client.post(
        "/api/soc/ingest/fortigate",
        headers={"Authorization": "Bearer wrong"},
        json={"srcip": "203.0.113.7"},
    )

    assert response.status_code == 401


def test_below_threshold_throttles_emission():
    fake_siem = FakeSiemClient()
    app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem
    client = TestClient(app)

    for _ in range(4):
        response = client.post(
            "/api/soc/ingest/fortigate",
            headers={"Authorization": "Bearer test-secret-token"},
            json={
                "logid": "0100040704",
                "type": "event",
                "subtype": "system",
                "action": "login",
                "status": "failed",
                "level": "warning",
                "srcip": "203.0.113.99",
                "user": "admin",
                "msg": "Admin login failed",
                "eventtime": 1700000000,
            },
        )
        assert response.status_code == 200

    assert fake_siem.calls == []
    body = response.json()
    assert body["received"] == 1
    assert body["emitted"] == 0
    assert body["throttled"] == 1


def test_threshold_crossing_emits_aggregated_event():
    fake_siem = FakeSiemClient()
    app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem
    client = TestClient(app)

    last_response = None
    for _ in range(5):
        last_response = client.post(
            "/api/soc/ingest/fortigate",
            headers={"Authorization": "Bearer test-secret-token"},
            json={
                "logid": "0100040704",
                "type": "event",
                "subtype": "system",
                "action": "login",
                "status": "failed",
                "srcip": "203.0.113.99",
                "user": "admin",
                "msg": "Admin login failed via port2",
            },
        )

    assert last_response is not None
    assert last_response.status_code == 200
    assert len(fake_siem.calls) == 1
    forwarded = fake_siem.calls[0]["json"]
    assert forwarded["eventType"] == "auth.failed_login"
    assert forwarded["entities"]["sourceIp"] == "203.0.113.99"
    assert forwarded["attributes"]["count"] == 5
    assert "admin" in forwarded["attributes"]["users"]
    assert forwarded["attributes"]["ingestionMode"] == "push"


def test_classifies_traffic_deny_as_network_deny():
    fake_siem = FakeSiemClient()
    app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem
    client = TestClient(app)

    for _ in range(5):
        client.post(
            "/api/soc/ingest/fortigate",
            headers={"Authorization": "Bearer test-secret-token"},
            json={
                "type": "traffic",
                "action": "deny",
                "srcip": "198.51.100.50",
                "dstip": "10.0.0.5",
                "level": "warning",
            },
        )

    assert fake_siem.calls
    forwarded = fake_siem.calls[0]["json"]
    assert forwarded["eventType"] == "network.deny"
    assert forwarded["entities"]["destinationIp"] == "10.0.0.5"


def test_accepts_batch_payload_and_aggregates_within_call():
    fake_siem = FakeSiemClient()
    app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem
    client = TestClient(app)

    response = client.post(
        "/api/soc/ingest/fortigate",
        headers={"Authorization": "Bearer test-secret-token"},
        json=[
            {
                "logid": "0100040704",
                "subtype": "user",
                "action": "login",
                "status": "failed",
                "srcip": "203.0.113.77",
                "user": "root",
                "msg": "User login fail",
            }
            for _ in range(5)
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["received"] == 5
    assert body["emitted"] == 1
    assert body["throttled"] == 4


def test_integration_id_header_propagates_to_event():
    fake_siem = FakeSiemClient()
    app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem
    client = TestClient(app)

    for _ in range(5):
        client.post(
            "/api/soc/ingest/fortigate",
            headers={
                "Authorization": "Bearer test-secret-token",
                "X-FortiDashboard-Integration-Id": "int_fgt_lab01",
            },
            json={
                "logid": "0100040704",
                "subtype": "system",
                "action": "login",
                "status": "failed",
                "srcip": "203.0.113.99",
                "user": "admin",
                "msg": "Admin login failed",
            },
        )

    forwarded = fake_siem.calls[0]["json"]
    assert forwarded["entities"]["integrationId"] == "int_fgt_lab01"


def test_audit_log_records_ingestion_summary():
    fake_siem = FakeSiemClient()
    app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem
    client = TestClient(app)

    for _ in range(5):
        client.post(
            "/api/soc/ingest/fortigate",
            headers={"Authorization": "Bearer test-secret-token"},
            json={
                "logid": "0100040704",
                "subtype": "system",
                "action": "login",
                "status": "failed",
                "srcip": "203.0.113.99",
                "user": "admin",
                "msg": "Admin login failed",
            },
        )

    audit = auth_dependencies.get_auth_audit_store().list_events(
        action="soc.ingest.fortigate"
    )
    assert audit["items"]
    last = audit["items"][-1]
    assert last["details"]["service"] == "siem_kowalski"
    assert last["details"]["received"] >= 1


def test_health_endpoint_reports_enabled_state():
    client = TestClient(app)

    response = client.get("/api/soc/ingest/health")

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["threshold"] == 5


def test_fortiweb_attack_log_emits_waf_attack():
    fake_siem = FakeSiemClient()
    app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem
    client = TestClient(app)

    response = client.post(
        "/api/soc/ingest/fortiweb",
        headers={
            "Authorization": "Bearer test-secret-token",
            "X-FortiDashboard-Integration-Id": "int_fweb_landing",
        },
        json={
            "type": "attack",
            "subtype": "signature",
            "src": "203.0.113.50",
            "dst": "198.51.100.10",
            "host": "landing.example.test",
            "method": "GET",
            "url": "/demo/search?q=' OR 1=1--",
            "action": "block",
            "severity": "high",
            "msg": "SQL Injection Detected",
            "policy": "landing-waf-policy",
            "eventtime": "2026-05-15T12:00:00Z",
        },
    )

    assert response.status_code == 200
    assert response.json()["emitted"] == 1
    forwarded = fake_siem.calls[0]["json"]
    assert forwarded["eventType"] == "waf.attack"
    assert forwarded["severity"] == "high"
    assert forwarded["entities"]["sourceIp"] == "203.0.113.50"
    assert forwarded["entities"]["destinationIp"] == "198.51.100.10"
    assert forwarded["entities"]["httpHost"] == "landing.example.test"
    assert forwarded["entities"]["integrationId"] == "int_fweb_landing"
    assert forwarded["attributes"]["action"] == "block"
    assert forwarded["attributes"]["policy"] == "landing-waf-policy"


def test_fortiweb_dos_log_emits_waf_dos():
    fake_siem = FakeSiemClient()
    app.dependency_overrides[soc.get_siem_client] = lambda: fake_siem
    client = TestClient(app)

    response = client.post(
        "/api/soc/ingest/fortiweb",
        headers={"Authorization": "Bearer test-secret-token"},
        json={
            "type": "attack",
            "subtype": "dos",
            "src": "203.0.113.60",
            "host": "landing.example.test",
            "action": "block",
            "severity": "critical",
            "msg": "HTTP Flood detected",
            "count": 250,
        },
    )

    assert response.status_code == 200
    forwarded = fake_siem.calls[0]["json"]
    assert forwarded["eventType"] == "waf.dos"
    assert forwarded["severity"] == "critical"
    assert forwarded["attributes"]["count"] == 250
