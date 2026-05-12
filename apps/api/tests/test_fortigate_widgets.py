from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.auth import dependencies as auth_dependencies
from app.main import app
from app.routers import widgets as widgets_router


class FakeFortiGateConnectionStore:
    def get_connection(self, integration_id: str, *, owner_user_id: str):
        assert integration_id == "int_fgt_live"
        assert owner_user_id == "usr_owner"
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
            "cpu": {"idle": 8},
            "mem": {"used": 1843, "total": 2048},
            "uptime": "1 days, 1 hours, 40 minutes, 20 seconds",
        }

    def get_resource_usage(self, *, resource: str | None = None):
        assert resource == "session"
        return {"session": [{"current": 42}]}

    def get_web_ui_state(self):
        return {
            "snapshot_utc_time": 1777477582000,
            "utc_last_reboot": 1777470648000,
        }

    def get_interface_status(self):
        return {
            "port1": {
                "id": "port1",
                "name": "port1",
                "ip": "192.0.2.118",
                "link": True,
                "rx_bytes": 8304525,
                "tx_bytes": 6185442,
                "rx_packets": 35655,
                "tx_packets": 26875,
            },
            "port2": {
                "id": "port2",
                "name": "port2",
                "ip": "10.0.0.1",
                "link": False,
                "rx_bytes": 0,
                "tx_bytes": 0,
                "rx_packets": 0,
                "tx_packets": 0,
            },
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
        owner_user_id="usr_owner",
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
            "cpu": 92,
            "memory": 90,
            "sessions": 42,
            "uptimeSeconds": 92420,
        },
        "meta": {
            "source": "fortigate",
            "cacheTtlSeconds": 2,
            "refreshIntervalSeconds": 2,
        },
    }


def test_fortigate_widget_service_caches_payloads_inside_realtime_ttl():
    from app.integrations.fortigate.widgets import FortiGateWidgetDataService

    current_time = datetime(2026, 4, 26, 23, 45, tzinfo=UTC)
    factory_calls = 0

    def clock():
        return current_time

    def cached_client_factory(*, host: str, api_key: str, verify_tls: bool):
        nonlocal factory_calls
        factory_calls += 1
        return FakeFortiGateClient()

    service = FortiGateWidgetDataService(
        store=FakeFortiGateConnectionStore(),
        client_factory=cached_client_factory,
        clock=clock,
    )

    first = service.get_widget_data(
        "fortigate-system-status",
        integration_id="int_fgt_live",
        owner_user_id="usr_owner",
    )
    current_time = datetime(2026, 4, 26, 23, 45, 1, tzinfo=UTC)
    second = service.get_widget_data(
        "fortigate-system-status",
        integration_id="int_fgt_live",
        owner_user_id="usr_owner",
    )
    current_time = datetime(2026, 4, 26, 23, 45, 3, tzinfo=UTC)
    third = service.get_widget_data(
        "fortigate-system-status",
        integration_id="int_fgt_live",
        owner_user_id="usr_owner",
    )

    assert second == first
    assert third["refreshedAt"] == "2026-04-26T23:45:03.000Z"
    assert factory_calls == 2


def test_system_status_and_session_kpi_share_system_snapshot_inside_short_ttl():
    from app.integrations.fortigate.widgets import FortiGateWidgetDataService

    session_counts = iter([42, 43])

    class ChangingSessionClient(FakeFortiGateClient):
        def get_resource_usage(self, *, resource: str | None = None):
            assert resource == "session"
            return {"session": [{"current": next(session_counts)}]}

    service = FortiGateWidgetDataService(
        store=FakeFortiGateConnectionStore(),
        client_factory=lambda *, host, api_key, verify_tls: ChangingSessionClient(),
        clock=lambda: datetime(2026, 4, 26, 23, 45, tzinfo=UTC),
    )

    system_status = service.get_widget_data(
        "fortigate-system-status",
        integration_id="int_fgt_live",
        owner_user_id="usr_owner",
    )
    sessions_kpi = service.get_widget_data(
        "fortigate-kpi-sessions",
        integration_id="int_fgt_live",
        owner_user_id="usr_owner",
    )

    assert system_status["data"]["sessions"] == 42
    assert sessions_kpi["data"]["sessions"] == 42


def test_fortigate_widget_service_returns_interfaces_policies_and_threats():
    from app.integrations.fortigate.widgets import FortiGateWidgetDataService

    service = FortiGateWidgetDataService(
        store=FakeFortiGateConnectionStore(),
        client_factory=fake_client_factory,
        clock=lambda: datetime(2026, 4, 26, 23, 45, tzinfo=UTC),
    )

    interfaces = service.get_widget_data(
        "fortigate-network-traffic", "int_fgt_live", owner_user_id="usr_owner"
    )
    policies = service.get_widget_data(
        "fortigate-firewall-policies", "int_fgt_live", owner_user_id="usr_owner"
    )
    threats = service.get_widget_data(
        "fortigate-top-threats", "int_fgt_live", owner_user_id="usr_owner"
    )

    assert interfaces["data"]["interfaces"] == [
        {
            "id": "port1",
            "name": "port1",
            "alias": "",
            "status": "up",
            "ip": "192.0.2.118",
            "role": "unknown",
            "type": "unknown",
            "rxBytes": 8304525,
            "txBytes": 6185442,
            "rxPackets": 35655,
            "txPackets": 26875,
        },
        {
            "id": "port2",
            "name": "port2",
            "alias": "",
            "status": "down",
            "ip": "10.0.0.1",
            "role": "unknown",
            "type": "unknown",
            "rxBytes": 0,
            "txBytes": 0,
            "rxPackets": 0,
            "txPackets": 0,
        },
    ]
    assert policies["data"]["policies"][0]["name"] == "LAN to WAN"
    assert threats["data"]["threats"][0]["severity"] == "high"


def test_fortigate_widget_service_returns_soc_enrichment_payloads():
    from app.integrations.fortigate.widgets import FortiGateWidgetDataService

    service = FortiGateWidgetDataService(
        store=FakeFortiGateConnectionStore(),
        client_factory=fake_client_factory,
        clock=lambda: datetime(2026, 4, 26, 23, 45, tzinfo=UTC),
    )

    risk = service.get_widget_data(
        "fortigate-risk-posture", "int_fgt_live", owner_user_id="usr_owner"
    )
    interface_health = service.get_widget_data(
        "fortigate-interface-health", "int_fgt_live", owner_user_id="usr_owner"
    )
    recent_events = service.get_widget_data(
        "fortigate-recent-events", "int_fgt_live", owner_user_id="usr_owner"
    )
    anomalies = service.get_widget_data(
        "fortigate-anomaly-highlights", "int_fgt_live", owner_user_id="usr_owner"
    )

    assert risk["data"] == {
        "score": 54,
        "level": "high",
        "signals": [
            {
                "id": "system.cpu",
                "label": "High CPU usage",
                "severity": "critical",
                "value": 92,
                "unit": "percent",
                "description": "FortiGate CPU usage is above 85%.",
            },
            {
                "id": "system.memory",
                "label": "High memory usage",
                "severity": "critical",
                "value": 90,
                "unit": "percent",
                "description": "FortiGate memory usage is above 85%.",
            },
            {
                "id": "interfaces.down",
                "label": "Interfaces down",
                "severity": "warning",
                "value": 1,
                "unit": "count",
                "description": "One or more FortiGate interfaces report link down.",
            },
            {
                "id": "policies.enabled",
                "label": "Firewall policies enabled",
                "severity": "healthy",
                "value": 1,
                "unit": "count",
                "description": "Observed firewall policies are enabled.",
            },
        ],
        "summary": {"critical": 2, "warning": 1, "healthy": 1},
    }
    assert interface_health["data"]["summary"] == {
        "total": 2,
        "up": 1,
        "down": 1,
        "totalRxBytes": 8304525,
        "totalTxBytes": 6185442,
    }
    assert recent_events["data"]["summary"] == {
        "total": 1,
        "blocked": 1,
        "highSeverity": 1,
    }
    assert anomalies["data"]["anomalies"] == [
        {
            "id": "cpu-critical",
            "title": "CPU pressure above normal SOC threshold",
            "severity": "critical",
            "metric": "system.cpu",
            "value": 92,
            "unit": "percent",
            "description": "Sustained CPU pressure can delay inspection and logging.",
        },
        {
            "id": "memory-critical",
            "title": "Memory pressure above normal SOC threshold",
            "severity": "critical",
            "metric": "system.memory",
            "value": 90,
            "unit": "percent",
            "description": "High memory usage can indicate overloaded inspection or logging.",
        },
        {
            "id": "interfaces-down",
            "title": "Interface link down",
            "severity": "warning",
            "metric": "interfaces.down",
            "value": 1,
            "unit": "count",
            "description": "One or more FortiGate interfaces are not passing traffic.",
        },
    ]


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

    assert service.get_widget_data(
        "fortigate-top-threats", "int_fgt_live", owner_user_id="usr_owner"
    ) == {
        "widgetId": "fortigate-top-threats",
        "integrationId": "int_fgt_live",
        "refreshedAt": "2026-04-26T23:45:00.000Z",
        "status": "error",
        "data": {},
        "meta": {
            "source": "fortigate",
            "cacheTtlSeconds": 5,
            "refreshIntervalSeconds": 5,
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
    app.dependency_overrides[auth_dependencies.get_current_api_user] = lambda: {
        "id": "usr_owner",
        "email": "owner@example.com",
        "displayName": "Owner",
        "roles": ["analyst"],
    }
    client = TestClient(app)

    try:
        response = client.get(
            "/api/widgets/fortigate-system-status/data",
            params={"integrationId": "int_fgt_live"},
        )
    finally:
        app.dependency_overrides.pop(widgets_router.get_fortigate_widget_service, None)
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)

    assert response.status_code == 200
    assert response.json()["data"]["sessions"] == 42
