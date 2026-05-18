import pytest
from fastapi.testclient import TestClient

from app.auth.errors import AuthProviderError
from app.auth.service import AuthService
from app.auth.session_store import InMemorySessionStore
from app.main import app
from app.routers import auth as auth_router


def csrf_headers(client: TestClient) -> dict[str, str]:
    response = client.get("/api/auth/csrf")
    return {"X-CSRF-Token": response.json()["csrfToken"]}


def test_register_sets_http_only_session_cookie_without_returning_tokens():
    client = TestClient(app)

    response = client.post(
        "/api/auth/register",
        headers=csrf_headers(client),
        json={
            "email": "analyst@example.com",
            "password": "correct-horse-battery-staple",
            "displayName": "SOC Analyst",
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "user": {
            "id": "usr_01",
            "email": "analyst@example.com",
            "displayName": "SOC Analyst",
            "roles": ["analyst"],
            "permissions": [],
            "isAdmin": False,
        },
        "session": {
            "authenticated": True,
            "expiresAt": "2026-04-26T22:30:00.000Z",
        },
    }
    assert "access_token" not in response.text
    assert "refresh_token" not in response.text

    set_cookie = response.headers["set-cookie"]
    assert "fortidashboard_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie


def test_login_sets_session_cookie_and_me_reads_contextual_browser_session():
    client = TestClient(app)

    login_response = client.post(
        "/api/auth/login",
        headers=csrf_headers(client),
        json={
            "email": "analyst@example.com",
            "password": "correct-horse-battery-staple",
        },
    )

    assert login_response.status_code == 200
    assert login_response.json()["session"]["authenticated"] is True
    assert "fortidashboard_session=" in login_response.headers["set-cookie"]

    me_response = client.get("/api/auth/me")

    assert me_response.status_code == 200
    assert me_response.json() == {
        "authenticated": True,
        "user": {
            "id": "usr_01",
            "email": "analyst@example.com",
            "displayName": "SOC Analyst",
            "roles": ["analyst"],
            "permissions": [],
            "isAdmin": False,
        },
    }


def test_me_without_session_reports_unauthenticated():
    client = TestClient(app)

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json() == {"authenticated": False, "user": None}


def test_logout_clears_http_only_session_cookie():
    client = TestClient(app)
    client.post(
        "/api/auth/login",
        headers=csrf_headers(client),
        json={
            "email": "analyst@example.com",
            "password": "correct-horse-battery-staple",
        },
    )

    logout_response = client.post("/api/auth/logout", headers=csrf_headers(client))

    assert logout_response.status_code == 200
    assert logout_response.json() == {"authenticated": False}
    set_cookie = logout_response.headers["set-cookie"]
    assert "fortidashboard_session=" in set_cookie
    assert "Max-Age=0" in set_cookie

    me_response = client.get("/api/auth/me")
    assert me_response.json() == {"authenticated": False, "user": None}


class FailingIdentityProvider:
    def register(self, *, email: str, password: str, display_name: str):
        raise AuthProviderError(status_code=409, detail="Email already registered")

    def login(self, *, email: str, password: str):
        raise AuthProviderError(status_code=401, detail="Invalid email or password")


@pytest.mark.parametrize(
    ("endpoint", "payload", "expected_status", "expected_detail"),
    [
        (
            "/api/auth/login",
            {"email": "analyst@example.com", "password": "wrong-password"},
            401,
            "Invalid email or password",
        ),
        (
            "/api/auth/register",
            {
                "email": "analyst@example.com",
                "password": "correct-horse-battery-staple",
                "displayName": "SOC Analyst",
            },
            409,
            "Email already registered",
        ),
    ],
)
def test_auth_routes_return_stable_provider_errors(
    endpoint,
    payload,
    expected_status,
    expected_detail,
):
    client = TestClient(app)
    service = AuthService(
        provider=FailingIdentityProvider(),
        session_store=InMemorySessionStore(),
    )
    app.dependency_overrides[auth_router.get_auth_service] = lambda: service

    try:
        response = client.post(endpoint, headers=csrf_headers(client), json=payload)
    finally:
        app.dependency_overrides.pop(auth_router.get_auth_service, None)

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
