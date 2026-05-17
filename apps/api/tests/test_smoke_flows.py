from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import dependencies as auth_dependencies
from app.db.base import Base
from app.main import app
from app.routers import integrations_v2

client = TestClient(app)


def csrf_headers() -> dict[str, str]:
    response = client.get("/api/auth/csrf")
    return {"X-CSRF-Token": response.json()["csrfToken"]}


def test_smoke_connection_catalog_and_widget_payloads():
    connection = client.post(
        "/api/integrations/fortigate/test",
        headers=csrf_headers(),
        json={
            "host": "https://fortigate.local",
            "apiKey": "fg_api_key_from_user",
            "verifyTls": False,
        },
    )
    catalog = client.get("/api/widget-catalog", params={"integrationType": "fortigate"})
    widget = client.get(
        "/api/widgets/fortigate-system-status/data",
        params={"integrationId": "int_fgt_01"},
    )

    assert connection.status_code == 200
    assert connection.json()["status"] == "connected"
    assert catalog.status_code == 200
    assert len(catalog.json()["items"]) >= 5
    assert widget.status_code == 200
    assert widget.json()["status"] == "ready"


def test_smoke_workspace_payload_has_canvas_render_contract():
    workspace = client.get("/api/workspaces/ws_default")
    catalog = client.get("/api/widget-catalog", params={"integrationType": "fortigate"})

    assert workspace.status_code == 200
    widget = workspace.json()["widgets"][0]
    catalog_ids = {item["id"] for item in catalog.json()["items"]}

    assert widget["catalogId"] in catalog_ids
    assert widget["integrationId"]
    assert widget["layout"].keys() >= {"x", "y", "w", "h", "z"}


def test_smoke_connect_wizard_creates_listing_and_soar_actions(monkeypatch):
    session_factory = _session_factory()
    service = _StatefulFortiWebService()
    app.dependency_overrides[auth_dependencies.get_current_api_user] = _admin_user
    app.dependency_overrides[integrations_v2.get_fortiweb_integration_service] = (
        lambda: service
    )
    monkeypatch.setattr(integrations_v2, "SessionLocal", session_factory)
    monkeypatch.setattr(integrations_v2, "get_connector_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(
        integrations_v2,
        "_catalog_entry",
        lambda _addon_id: {
            "addonId": "fortiweb-core",
            "name": "FortiWeb Core",
            "providerType": "fortiweb",
            "versions": ["8.0.5"],
            "authFields": [
                {"id": "host", "label": "URL", "type": "url", "required": True},
                {
                    "id": "apiKey",
                    "label": "API Key",
                    "type": "secret",
                    "required": True,
                },
                {"id": "verifyTls", "label": "Verify TLS", "type": "boolean"},
            ],
            "capabilities": {
                "logSource": True,
                "playbookTarget": True,
                "managed": True,
            },
        },
    )
    try:
        response = client.post(
            "/api/integrations/connect",
            headers=csrf_headers(),
            json={
                "addonId": "fortiweb-core",
                "version": "8.0.5",
                "name": "WAF",
                "auth": {
                    "host": "https://fw.local",
                    "apiKey": "0123456789abcdef",
                    "verifyTls": False,
                },
                "wire": {"siem": True, "soar": True},
            },
        )
        assert response.status_code == 200
        integration_id = response.json()["integration"]["id"]

        listing = client.get("/api/integrations")
        soar = client.get(f"/api/integrations/{integration_id}/soar-actions")
    finally:
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)
        app.dependency_overrides.pop(
            integrations_v2.get_fortiweb_integration_service,
            None,
        )

    assert listing.status_code == 200
    assert any(item["id"] == integration_id for item in listing.json()["items"])
    assert soar.status_code == 200
    assert any(action["id"] == "block_source_ip" for action in soar.json()["items"])


def _admin_user() -> dict:
    return {"id": "usr_admin", "email": "admin@example.com", "roles": ["admin"]}


class _FakeConnector:
    def health_check(self) -> dict:
        return {
            "ok": True,
            "status": "connected",
            "device": {"hostname": "FWB"},
        }

    def list_playbook_actions(self) -> list[dict]:
        return [
            {
                "id": "block_source_ip",
                "label": "Block source IP on FortiWeb",
                "paramsSchema": {"sourceIp": {"type": "string", "required": True}},
            }
        ]


class _FakeRegistry:
    def get(self, *args, **kwargs):
        return _FakeConnector()


class _StatefulFortiWebService:
    def __init__(self) -> None:
        self._items: list[dict] = []

    def create(self, **kwargs) -> dict:
        item = {
            "id": "int_fweb_smoke_01",
            "type": "fortiweb",
            "name": kwargs["name"],
            "host": kwargs["host"],
            "status": "connected",
        }
        self._items.append(item)
        return item

    def list(self, *, owner_user_id: str) -> dict:
        _ = owner_user_id
        return {"items": list(self._items)}


def _session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)
