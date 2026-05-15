from datetime import datetime

from fastapi.testclient import TestClient

from app.auth import dependencies as auth_dependencies
from app.auth.audit import InMemoryAuthAuditStore
from app.integrations.fortigate.store import InMemoryFortiGateIngestionStore
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


class FailingFortiGateWidgetService:
    def get_widget_data(self, widget_id, integration_id, *, owner_user_id):
        raise RuntimeError("FortiGate logs unavailable")


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
    integrations_router.get_fortigate_ingestion_store.cache_clear()


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
        "soar-playbook-run-history",
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
    app.dependency_overrides[widgets_router.get_penguin_tool_integration_service] = lambda: (
        FakePenguinToolIntegrationService("siem_kowalski")
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
    app.dependency_overrides[widgets_router.get_penguin_tool_integration_service] = lambda: (
        FakePenguinToolIntegrationService("xdr_rico")
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
    app.dependency_overrides[widgets_router.get_penguin_tool_integration_service] = lambda: (
        FakePenguinToolIntegrationService("soar_skipper")
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


def test_soar_playbook_run_history_widget_returns_all_runs_and_summary():
    client = TestClient(app)
    fake_soar = FakeSocClient(
        {
            "/playbook-runs": {
                "items": [
                    {
                        "id": "run_01",
                        "incidentId": "inc_01",
                        "playbookId": "pb_block",
                        "status": "waiting_approval",
                    },
                    {
                        "id": "run_02",
                        "incidentId": "inc_01",
                        "playbookId": "pb_notes",
                        "status": "completed",
                    },
                    {
                        "id": "run_03",
                        "incidentId": "inc_02",
                        "playbookId": "pb_notify",
                        "status": "failed",
                    },
                ]
            }
        }
    )
    app.dependency_overrides[widgets_router.get_soar_client] = lambda: fake_soar
    app.dependency_overrides[widgets_router.get_penguin_tool_integration_service] = lambda: (
        FakePenguinToolIntegrationService("soar_skipper")
    )

    response = client.get(
        "/api/widgets/soar-playbook-run-history/data",
        params={"integrationId": "int_penguin_01"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "runs": [
            {
                "id": "run_01",
                "incidentId": "inc_01",
                "playbookId": "pb_block",
                "status": "waiting_approval",
            },
            {
                "id": "run_02",
                "incidentId": "inc_01",
                "playbookId": "pb_notes",
                "status": "completed",
            },
            {
                "id": "run_03",
                "incidentId": "inc_02",
                "playbookId": "pb_notify",
                "status": "failed",
            },
        ],
        "count": 3,
        "summary": {
            "active": 1,
            "completed": 1,
            "failed": 1,
            "running": 0,
            "waitingApproval": 1,
        },
    }


def test_soc_widget_logs_empty_payload_for_first_setup(caplog):
    client = TestClient(app)
    fake_siem = FakeSocClient({"/incidents": {"items": []}})
    caplog.set_level("INFO", logger="uvicorn.error")
    app.dependency_overrides[widgets_router.get_siem_client] = lambda: fake_siem
    app.dependency_overrides[widgets_router.get_penguin_tool_integration_service] = lambda: (
        FakePenguinToolIntegrationService("siem_kowalski")
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
    app.dependency_overrides[widgets_router.get_penguin_tool_integration_service] = lambda: (
        FakePenguinToolIntegrationService("xdr_rico")
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
                "id": f"evt_{len(fake_siem.calls) - 1}",
                "eventType": kwargs["json"]["eventType"],
            }
        }
    )
    app.dependency_overrides[integrations_router.get_fortigate_widget_service] = lambda: (
        FakeFortiGateWidgetService()
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


def test_fortigate_ingestion_status_can_be_configured_and_updated_by_run_now():
    client = TestClient(app)
    fake_siem = FakeSocClient(
        {
            "/events": lambda **kwargs: {
                "id": f"evt_{len(fake_siem.calls) - 1}",
                "eventType": kwargs["json"]["eventType"],
            }
        }
    )
    app.dependency_overrides[integrations_router.get_fortigate_widget_service] = lambda: (
        FakeFortiGateWidgetService()
    )
    app.dependency_overrides[integrations_router.get_siem_client] = lambda: fake_siem

    configured = client.put(
        "/api/soc/fortigate/int_fgt_01/ingestion-status",
        headers=csrf_headers(client),
        json={"enabled": True, "intervalSeconds": 30},
    )
    run_now = client.post(
        "/api/soc/fortigate/int_fgt_01/ingest-events",
        headers=csrf_headers(client),
    )
    current = client.get("/api/soc/fortigate/int_fgt_01/ingestion-status")

    assert configured.status_code == 200
    assert configured.json()["enabled"] is True
    assert configured.json()["intervalSeconds"] == 30
    assert run_now.status_code == 200
    assert run_now.json()["createdCount"] == 1
    assert run_now.json()["ingestion"]["status"] == "success"
    assert run_now.json()["ingestion"]["lastRawEventCount"] == 1
    assert run_now.json()["ingestion"]["lastCreatedCount"] == 1
    assert run_now.json()["ingestion"]["lastEventIds"] == ["evt_0"]
    assert current.status_code == 200
    assert current.json()["enabled"] is True
    assert current.json()["status"] == "success"
    assert current.json()["lastEventIds"] == ["evt_0"]


def test_fortigate_ingestion_status_records_failed_run_without_leaking_secrets():
    client = TestClient(app)
    app.dependency_overrides[integrations_router.get_fortigate_widget_service] = lambda: (
        FailingFortiGateWidgetService()
    )

    response = client.post(
        "/api/soc/fortigate/int_fgt_01/ingest-events",
        headers=csrf_headers(client),
    )
    current = client.get("/api/soc/fortigate/int_fgt_01/ingestion-status")
    audit = auth_dependencies.get_auth_audit_store().list_events(
        action="soc.fortigate_events.ingested"
    )

    assert response.status_code == 502
    assert current.json()["status"] == "failed"
    assert current.json()["lastError"] == "FortiGate logs unavailable"
    assert audit["items"][0]["outcome"] == "failure"
    assert "api" not in str(audit["items"][0]["details"]).lower()


def test_scheduled_fortigate_ingestion_runs_due_enabled_integrations(monkeypatch):
    fake_siem = FakeSocClient(
        {
            "/events": lambda **kwargs: {
                "id": f"evt_{len(fake_siem.calls) - 1}",
                "eventType": kwargs["json"]["eventType"],
            }
        }
    )
    ingestion_store = InMemoryFortiGateIngestionStore(
        default_ingestion_interval_seconds=30,
        id_factory=lambda: "fgt_ingest_due_01",
    )
    audit_store = InMemoryAuthAuditStore()
    ingestion_store.upsert_ingestion_status(
        owner_user_id="usr_owner",
        integration_id="int_fgt_01",
        enabled=True,
        interval_seconds=30,
        updated_at=datetime.fromisoformat("2026-05-13T18:00:00+00:00"),
    )
    monkeypatch.setattr(
        integrations_router,
        "get_fortigate_ingestion_store",
        lambda: ingestion_store,
    )
    monkeypatch.setattr(
        integrations_router,
        "get_fortigate_widget_service",
        lambda: FakeFortiGateWidgetService(),
    )
    monkeypatch.setattr(integrations_router, "get_siem_client", lambda: fake_siem)
    monkeypatch.setattr(integrations_router, "get_auth_audit_store", lambda: audit_store)

    results = integrations_router.run_due_fortigate_ingestions_once()
    current = ingestion_store.get_ingestion_status(
        owner_user_id="usr_owner",
        integration_id="int_fgt_01",
    )
    audit = audit_store.list_events(action="soc.fortigate_events.auto_ingested")

    assert results[0]["createdCount"] == 1
    assert current["status"] == "success"
    assert current["lastRunTrigger"] == "scheduled"
    assert audit["items"][0]["outcome"] == "success"
    assert audit["items"][0]["details"]["trigger"] == "scheduled"
