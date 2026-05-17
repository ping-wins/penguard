from fastapi.testclient import TestClient

from app.auth import dependencies as auth_dependencies
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
