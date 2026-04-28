import json

import httpx
import pytest

from app.auth.errors import AuthProviderError
from app.auth.keycloak import KeycloakClient


def test_login_uses_keycloak_password_grant_without_exposing_tokens_to_browser_layer():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/realms/fortidashboard/protocol/openid-connect/token"
        form = dict(item.split("=") for item in request.content.decode().split("&"))
        assert form["grant_type"] == "password"
        assert form["client_id"] == "fortidashboard-bff"
        assert form["client_secret"] == "dev-client-secret"
        assert form["username"] == "analyst%40example.com"
        assert form["password"] == "correct-horse-battery-staple"
        return httpx.Response(
            200,
            json={
                "access_token": "keycloak-access-token",
                "refresh_token": "keycloak-refresh-token",
                "expires_in": 300,
            },
        )

    client = KeycloakClient(
        base_url="http://keycloak.local",
        realm="fortidashboard",
        client_id="fortidashboard-bff",
        client_secret="dev-client-secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    tokens = client.login(
        email="analyst@example.com",
        password="correct-horse-battery-staple",
    )

    assert len(requests) == 1
    assert tokens.access_token == "keycloak-access-token"
    assert tokens.refresh_token == "keycloak-refresh-token"
    assert tokens.expires_in == 300


def test_create_user_uses_service_account_and_keycloak_admin_api():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/realms/fortidashboard/protocol/openid-connect/token":
            form = dict(item.split("=") for item in request.content.decode().split("&"))
            assert form["grant_type"] == "client_credentials"
            return httpx.Response(200, json={"access_token": "admin-token", "expires_in": 300})

        assert request.url.path == "/admin/realms/fortidashboard/users"
        assert request.headers["authorization"] == "Bearer admin-token"
        payload = json.loads(request.content)
        assert payload["username"] == "analyst@example.com"
        assert payload["email"] == "analyst@example.com"
        assert payload["enabled"] is True
        assert payload["emailVerified"] is True
        assert payload["requiredActions"] == []
        assert payload["firstName"] == "SOC"
        assert payload["lastName"] == "Analyst"
        assert payload["credentials"] == [
            {
                "type": "password",
                "value": "correct-horse-battery-staple",
                "temporary": False,
            }
        ]
        return httpx.Response(
            201,
            headers={"Location": "http://keycloak.local/admin/realms/fortidashboard/users/usr_01"},
        )

    client = KeycloakClient(
        base_url="http://keycloak.local",
        realm="fortidashboard",
        client_id="fortidashboard-bff",
        client_secret="dev-client-secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    user = client.create_user(
        email="analyst@example.com",
        password="correct-horse-battery-staple",
        display_name="SOC Analyst",
    )

    assert [request.url.path for request in requests] == [
        "/realms/fortidashboard/protocol/openid-connect/token",
        "/admin/realms/fortidashboard/users",
    ]
    assert user.id == "usr_01"
    assert user.email == "analyst@example.com"
    assert user.display_name == "SOC Analyst"


def test_login_maps_keycloak_invalid_credentials_to_auth_error():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/realms/fortidashboard/protocol/openid-connect/token"
        return httpx.Response(
            401,
            json={
                "error": "invalid_grant",
                "error_description": "Invalid user credentials",
            },
        )

    client = KeycloakClient(
        base_url="http://keycloak.local",
        realm="fortidashboard",
        client_id="fortidashboard-bff",
        client_secret="dev-client-secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(AuthProviderError) as exc:
        client.login(email="analyst@example.com", password="wrong-password")

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid email or password"


def test_create_user_maps_keycloak_conflict_to_duplicate_user_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/realms/fortidashboard/protocol/openid-connect/token":
            return httpx.Response(200, json={"access_token": "admin-token", "expires_in": 300})
        return httpx.Response(409, json={"errorMessage": "User exists with same username"})

    client = KeycloakClient(
        base_url="http://keycloak.local",
        realm="fortidashboard",
        client_id="fortidashboard-bff",
        client_secret="dev-client-secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(AuthProviderError) as exc:
        client.create_user(
            email="analyst@example.com",
            password="correct-horse-battery-staple",
            display_name="SOC Analyst",
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == "Email already registered"


def test_create_user_maps_admin_api_transport_failure_to_provider_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/realms/fortidashboard/protocol/openid-connect/token":
            return httpx.Response(200, json={"access_token": "admin-token", "expires_in": 300})
        raise httpx.ConnectError("connection failed", request=request)

    client = KeycloakClient(
        base_url="http://keycloak.local",
        realm="fortidashboard",
        client_id="fortidashboard-bff",
        client_secret="dev-client-secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(AuthProviderError) as exc:
        client.create_user(
            email="analyst@example.com",
            password="correct-horse-battery-staple",
            display_name="SOC Analyst",
        )

    assert exc.value.status_code == 503
    assert exc.value.detail == "Identity provider unavailable"


def test_get_userinfo_maps_transport_failure_to_provider_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    client = KeycloakClient(
        base_url="http://keycloak.local",
        realm="fortidashboard",
        client_id="fortidashboard-bff",
        client_secret="dev-client-secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(AuthProviderError) as exc:
        client.get_userinfo(access_token="access-token")

    assert exc.value.status_code == 503
    assert exc.value.detail == "Identity provider unavailable"
