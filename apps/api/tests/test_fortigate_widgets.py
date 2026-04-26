from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.routers import widgets as widgets_router


class FakeFortiGateConnectionStore:
    def get_connection(self, integration_id: str):
        assert integration_id == "int_fgt_live"
        return {
            "id": "int_fgt_live",
            "host": "https://fortigate.local/",
            "api_key": "secret-token",
            "verify_tls": False,
        }


class FakeFortiGateClient:
    def get_system_status(self):
        return {
            "hostname": "FGT-VM",
            "model_name": "FortiGate",
            "version": "v7.6.6",
            "build": 3652,
            "serial": "FGVMTEST",
        }

    def get_performance_status(self):
        return {
            "cpu": {"idle": 88},
            "mem": {"used": 1024, "total": 2048},
        }

    def get_resource_usage(self, *, resource: str | None = None):
        assert resource == "session"
        return {"session": [{"current": 42}]}

    def get_interface_status(self):
        return {
            "port1": {
                "id": "port1",
                "name": "port1",
                "ip": "192.168.0.118",
                "link": True,
                "rx_bytes": 8304525,
                "tx_bytes": 6185442,
                "rx_packets": 35655,
                "tx_packets": 26875,
            }
        }

    def get_policies(self):
        return [
            {
                "policyid": 1,
                "name": "LAN to WAN",
                "status": "enable",
                "action": "accept",
                "srcintf": [{"name": "lan"}],
                "dstintf": [{"name": "wan"}],
                "service": [{"name": "HTTPS"}],
                "schedule": "always",
            }
        ]

    def get_threat_logs(self, *, limit: int = 25):
        assert limit == 25
        return [
            {
                "itime": 1777234800,
                "type": "utm",
                "subtype": "ips",
                "severity": "high",
                "srcip": "10.0.0.10",
                "dstip": "203.0.113.10",
                "action": "blocked",
                "msg": "IPS signature matched",
            }
        ]


def fake_client_factory(*, host: str, api_key: str, verify_tls: bool):
    assert host == "https://fortigate.local/"
    assert api_key == "secret-token"
    assert verify_tls is False
    return FakeFortiGateClient()


def test_fortigate_widget_service_returns_live_system_status_payload():
    from app.integrations.fortigate.widgets import FortiGateWidgetDataService

    service = FortiGateWidgetDataService(
        store=FakeFortiGateConnectionStore(),
        client_factory=fake_client_factory,
        clock=lambda: datetime(2026, 4, 26, 23, 45, tzinfo=UTC),
    )

    assert service.get_widget_data(
        "fortigate-system-status",
        integration_id="int_fgt_live",
    ) == {
        "widgetId": "fortigate-system-status",
        "integrationId": "int_fgt_live",
        "refreshedAt": "2026-04-26T23:45:00.000Z",
        "status": "ready",
        "data": {
            "hostname": "FGT-VM",
            "model": "FortiGate",
            "version": "v7.6.6",
            "serial": "FGVMTEST",
            "build": 3652,
            "cpu": 12,
            "memory": 50,
            "sessions": 42,
            "uptimeSeconds": None,
        },
        "meta": {"source": "fortigate", "cacheTtlSeconds": 30},
    }


def test_fortigate_widget_service_returns_interfaces_policies_and_threats():
    from app.integrations.fortigate.widgets import FortiGateWidgetDataService

    service = FortiGateWidgetDataService(
        store=FakeFortiGateConnectionStore(),
        client_factory=fake_client_factory,
        clock=lambda: datetime(2026, 4, 26, 23, 45, tzinfo=UTC),
    )

    interfaces = service.get_widget_data("fortigate-network-traffic", "int_fgt_live")
    policies = service.get_widget_data("fortigate-firewall-policies", "int_fgt_live")
    threats = service.get_widget_data("fortigate-top-threats", "int_fgt_live")

    assert interfaces["data"]["interfaces"] == [
        {
            "id": "port1",
            "name": "port1",
            "alias": "",
            "status": "up",
            "ip": "192.168.0.118",
            "role": "unknown",
            "type": "unknown",
            "rxBytes": 8304525,
            "txBytes": 6185442,
            "rxPackets": 35655,
            "txPackets": 26875,
        }
    ]
    assert policies["data"]["policies"][0]["name"] == "LAN to WAN"
    assert threats["data"]["threats"][0]["severity"] == "high"


def test_fortigate_widget_service_returns_error_payload_when_fortigate_endpoint_fails():
    from app.integrations.fortigate.client import FortiGateApiError
    from app.integrations.fortigate.widgets import FortiGateWidgetDataService

    class FailingThreatClient(FakeFortiGateClient):
        def get_threat_logs(self, *, limit: int = 25):
            raise FortiGateApiError("FortiGate API request failed with HTTP 404")

    service = FortiGateWidgetDataService(
        store=FakeFortiGateConnectionStore(),
        client_factory=lambda *, host, api_key, verify_tls: FailingThreatClient(),
        clock=lambda: datetime(2026, 4, 26, 23, 45, tzinfo=UTC),
    )

    assert service.get_widget_data("fortigate-top-threats", "int_fgt_live") == {
        "widgetId": "fortigate-top-threats",
        "integrationId": "int_fgt_live",
        "refreshedAt": "2026-04-26T23:45:00.000Z",
        "status": "error",
        "data": {},
        "meta": {
            "source": "fortigate",
            "cacheTtlSeconds": 30,
            "error": {"message": "FortiGate API request failed with HTTP 404"},
        },
    }


def test_live_widget_endpoint_uses_service_dependency_override():
    from app.integrations.fortigate.widgets import FortiGateWidgetDataService

    service = FortiGateWidgetDataService(
        store=FakeFortiGateConnectionStore(),
        client_factory=fake_client_factory,
        clock=lambda: datetime(2026, 4, 26, 23, 45, tzinfo=UTC),
    )
    app.dependency_overrides[widgets_router.get_fortigate_widget_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.get(
            "/api/widgets/fortigate-system-status/data",
            params={"integrationId": "int_fgt_live"},
        )
    finally:
        app.dependency_overrides.pop(widgets_router.get_fortigate_widget_service, None)

    assert response.status_code == 200
    assert response.json()["data"]["sessions"] == 42
