from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import dependencies as auth_dependencies
from app.db.base import Base
from app.main import app
from app.routers import integrations_v2


def _client() -> TestClient:
    return TestClient(app)


def _csrf_headers(client: TestClient) -> dict[str, str]:
    response = client.get("/api/auth/csrf")
    return {"X-CSRF-Token": response.json()["csrfToken"]}


def _admin_user() -> dict:
    return {"id": "usr_admin", "email": "admin@example.com", "roles": ["admin"]}


def test_catalog_requires_auth() -> None:
    response = _client().get("/api/integrations/catalog")
    assert response.status_code in (401, 403)


def test_connect_test_validates_required_auth(monkeypatch) -> None:
    client = _client()
    app.dependency_overrides[auth_dependencies.get_current_api_user] = _admin_user
    monkeypatch.setattr(
        integrations_v2,
        "_catalog_entry",
        lambda _addon_id: {
            "addonId": "fortiweb-core",
            "name": "FortiWeb Core",
            "providerType": "fortiweb",
            "versions": ["8.0.5"],
            "authFields": [
                {"id": "host", "label": "URL", "type": "url", "required": True}
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
            "/api/integrations/connect/test",
            json={
                "addonId": "fortiweb-core",
                "version": "8.0.5",
                "name": "WAF",
                "auth": {},
            },
            headers=_csrf_headers(client),
        )
    finally:
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)

    assert response.status_code == 422
    assert "host" in response.text


def test_connect_returns_per_destination_wiring(monkeypatch) -> None:
    client = _client()
    session_factory = _session_factory()
    registry = _FakeRegistry()
    fortiweb = _FakeFortiWebService()
    app.dependency_overrides[auth_dependencies.get_current_api_user] = _admin_user
    app.dependency_overrides[integrations_v2.get_fortiweb_integration_service] = (
        lambda: fortiweb
    )
    monkeypatch.setattr(integrations_v2, "SessionLocal", session_factory)
    monkeypatch.setattr(integrations_v2, "get_connector_registry", lambda: registry)
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
            headers=_csrf_headers(client),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["wiring"]["soar"]["ok"] is True
        integration_id = body["integration"]["id"]

        actions = client.get(f"/api/integrations/{integration_id}/soar-actions")
    finally:
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)
        app.dependency_overrides.pop(
            integrations_v2.get_fortiweb_integration_service,
            None,
        )

    assert actions.status_code == 200
    assert any(action["id"] == "block_source_ip" for action in actions.json()["items"])


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


class _FakeFortiWebService:
    def create(self, **kwargs) -> dict:
        return {
            "id": "int_fweb_01",
            "type": "fortiweb",
            "name": kwargs["name"],
            "host": kwargs["host"],
            "status": "connected",
        }


def _session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)
