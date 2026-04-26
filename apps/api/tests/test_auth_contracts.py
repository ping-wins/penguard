from fastapi.testclient import TestClient

from app.main import app


def test_register_sets_http_only_session_cookie_without_returning_tokens():
    client = TestClient(app)

    response = client.post(
        "/api/auth/register",
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
        json={
            "email": "analyst@example.com",
            "password": "correct-horse-battery-staple",
        },
    )

    logout_response = client.post("/api/auth/logout")

    assert logout_response.status_code == 200
    assert logout_response.json() == {"authenticated": False}
    set_cookie = logout_response.headers["set-cookie"]
    assert "fortidashboard_session=" in set_cookie
    assert "Max-Age=0" in set_cookie

    me_response = client.get("/api/auth/me")
    assert me_response.json() == {"authenticated": False, "user": None}
