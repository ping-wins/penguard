from fastapi.testclient import TestClient

from app.auth import dependencies as auth_dependencies
from app.main import app
from app.routers import integrations as integrations_router
from app.routers import widgets as widgets_router


class FakeSocClient:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []

    def request(
        self,
        method,
        path,
        *,
        json=None,
        params=None,
        headers=None,
        pass_through_statuses=None,
    ):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "json": json,
                "params": params,
                "headers": headers,
                "passThroughStatuses": pass_through_statuses,
            }
        )
        response = self.responses.get(path)
        if callable(response):
            return response(method=method, path=path, json=json, params=params)
        return response or {"items": []}


class FakeFortiGateWidgetService:
    def get_widget_data(self, widget_id, integration_id, *, owner_user_id):
        assert widget_id == "fortigate-recent-events"
        assert integration_id == "int_fgt_01"
        assert owner_user_id
        return {
            "data": {
                "events": [
                    {
                        "timestamp": "2026-05-08T12:00:00Z",
                        "severity": "medium",
                        "sourceIp": "192.0.2.10",
                        "destinationIp": "198.51.100.20",
                        "action": "deny",
                        "type": "traffic",
                        "subtype": "forward",
                        "message": "Denied connection",
                    }
                ]
            }
        }


class FakePenguinToolIntegrationService:
    def __init__(self, tool_type: str) -> None:
        self.tool_type = tool_type

    def get(self, *, integration_id: str, owner_user_id: str):
        assert owner_user_id
        if integration_id != "int_penguin_01":
            return None
        return {
            "id": "int_penguin_01",
            "type": self.tool_type,
            "name": self.tool_type,
            "status": "connected",
        }


def csrf_headers(client: TestClient) -> dict[str, str]:
    response = client.get("/api/auth/csrf")
    return {"X-CSRF-Token": response.json()["csrfToken"]}


def teardown_function():
    app.dependency_overrides.clear()


def test_soc_widget_catalog_returns_soc_widgets():
    client = TestClient(app)

    response = client.get("/api/widget-catalog", params={"integrationType": "soc"})

    assert response.status_code == 200
    assert {item["id"] for item in response.json()["items"]} >= {
        "soc-incidents-by-severity",
        "soc-recent-incidents",
        "soc-top-entities",
        "xdr-endpoint-health",
        "soar-active-playbook-runs",
    }


def test_soc_incidents_by_severity_widget_aggregates_incidents():
    client = TestClient(app)
    fake_siem = FakeSocClient(
        {
            "/incidents": {
                "items": [
                    {"id": "inc_01", "severity": "high", "entities": {"sourceIp": "192.0.2.10"}},
                    {"id": "inc_02", "severity": "high", "entities": {"sourceIp": "192.0.2.10"}},
                    {"id": "inc_03", "severity": "medium", "entities": {"hostname": "host-01"}},
                ]
            }
        }
    )
    app.dependency_overrides[widgets_router.get_siem_client] = lambda: fake_siem
    app.dependency_overrides[widgets_router.get_penguin_tool_integration_service] = (
        lambda: FakePenguinToolIntegrationService("siem_kowalski")
    )

    response = client.get(
        "/api/widgets/soc-incidents-by-severity/data",
        params={"integrationId": "int_penguin_01"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "items": [
            {"severity": "high", "count": 2},
            {"severity": "medium", "count": 1},
        ],
        "total": 3,
    }


def test_xdr_endpoint_health_widget_aggregates_endpoint_health():
    client = TestClient(app)
    fake_xdr = FakeSocClient(
        {
            "/endpoints": {
                "items": [
                    {"id": "end_01", "health": "healthy"},
                    {"id": "end_02", "health": "warning"},
                    {"id": "end_03", "health": "warning"},
                ]
            }
        }
    )
    app.dependency_overrides[widgets_router.get_xdr_client] = lambda: fake_xdr
    app.dependency_overrides[widgets_router.get_penguin_tool_integration_service] = (
        lambda: FakePenguinToolIntegrationService("xdr_rico")
    )

    response = client.get(
        "/api/widgets/xdr-endpoint-health/data",
        params={"integrationId": "int_penguin_01"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["summary"] == {"healthy": 1, "warning": 2}
    assert response.json()["data"]["total"] == 3


def test_soar_active_playbook_runs_widget_filters_completed_runs():
    client = TestClient(app)
    fake_soar = FakeSocClient(
        {
            "/playbook-runs": {
                "items": [
                    {"id": "run_01", "status": "waiting_approval"},
                    {"id": "run_02", "status": "completed"},
                ]
            }
        }
    )
    app.dependency_overrides[widgets_router.get_soar_client] = lambda: fake_soar
    app.dependency_overrides[widgets_router.get_penguin_tool_integration_service] = (
        lambda: FakePenguinToolIntegrationService("soar_skipper")
    )

    response = client.get(
        "/api/widgets/soar-active-playbook-runs/data",
        params={"integrationId": "int_penguin_01"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "runs": [{"id": "run_01", "status": "waiting_approval"}],
        "count": 1,
    }


def test_soc_widget_logs_empty_payload_for_first_setup(caplog):
    client = TestClient(app)
    fake_siem = FakeSocClient({"/incidents": {"items": []}})
    caplog.set_level("INFO", logger="uvicorn.error")
    app.dependency_overrides[widgets_router.get_siem_client] = lambda: fake_siem
    app.dependency_overrides[widgets_router.get_penguin_tool_integration_service] = (
        lambda: FakePenguinToolIntegrationService("siem_kowalski")
    )

    response = client.get(
        "/api/widgets/soc-top-entities/data",
        params={"integrationId": "int_penguin_01"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"entities": []}
    assert (
        "soc_widget_data_empty widget_id=soc-top-entities "
        "integration_id=int_penguin_01 source=siem_kowalski summary=entities=0"
    ) in caplog.text
    assert "hint=seed_demo_data_or_ingest_events" in caplog.text


def test_soc_widget_requires_matching_penguin_integration():
    client = TestClient(app)
    fake_siem = FakeSocClient({"/incidents": {"items": []}})
    app.dependency_overrides[widgets_router.get_siem_client] = lambda: fake_siem
    app.dependency_overrides[widgets_router.get_penguin_tool_integration_service] = (
        lambda: FakePenguinToolIntegrationService("xdr_rico")
    )

    missing_id = client.get("/api/widgets/soc-incidents-by-severity/data")
    wrong_type = client.get(
        "/api/widgets/soc-incidents-by-severity/data",
        params={"integrationId": "int_penguin_01"},
    )

    assert missing_id.status_code == 422
    assert wrong_type.status_code == 404
    assert fake_siem.calls == []


def test_ingest_fortigate_events_posts_normalized_events_to_siem():
    client = TestClient(app)
    fake_siem = FakeSocClient(
        {
            "/events": lambda **kwargs: {
                "id": f"evt_{len(fake_siem.calls)}",
                "eventType": kwargs["json"]["eventType"],
            }
        }
    )
    app.dependency_overrides[integrations_router.get_fortigate_widget_service] = (
        lambda: FakeFortiGateWidgetService()
    )
    app.dependency_overrides[integrations_router.get_siem_client] = lambda: fake_siem

    response = client.post(
        "/api/soc/fortigate/int_fgt_01/ingest-events",
        headers=csrf_headers(client),
    )
    audit = auth_dependencies.get_auth_audit_store().list_events(
        action="soc.fortigate_events.ingested"
    )

    assert response.status_code == 200
    assert response.json()["createdCount"] == 1
    assert fake_siem.calls[0]["json"]["eventType"] == "network.deny"
    assert fake_siem.calls[0]["json"]["entities"]["integrationId"] == "int_fgt_01"
    assert audit["items"][0]["details"]["count"] == 1
