from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.audit import InMemoryAuthAuditStore, SqlAlchemyAuthAuditStore
from app.auth.rate_limit import InMemoryRateLimiter
from app.db.base import Base
from app.db.models import AuthAuditEventModel
from app.main import app
from app.routers import auth as auth_router


def csrf_headers(client: TestClient) -> dict[str, str]:
    response = client.get("/api/auth/csrf")
    return {"X-CSRF-Token": response.json()["csrfToken"]}


def test_csrf_endpoint_issues_token_cookie_for_vue_forms():
    client = TestClient(app)

    response = client.get("/api/auth/csrf")

    assert response.status_code == 200
    csrf_token = response.json()["csrfToken"]
    assert len(csrf_token) >= 32

    set_cookie = response.headers["set-cookie"]
    assert "fortidashboard_csrf=" in set_cookie
    assert "HttpOnly" not in set_cookie
    assert "SameSite=lax" in set_cookie


def test_login_requires_matching_csrf_cookie_and_header():
    client = TestClient(app)

    missing_response = client.post(
        "/api/auth/login",
        json={
            "email": "analyst@example.com",
            "password": "correct-horse-battery-staple",
        },
    )

    assert missing_response.status_code == 403
    assert missing_response.json() == {"detail": "CSRF validation failed"}

    login_response = client.post(
        "/api/auth/login",
        headers=csrf_headers(client),
        json={
            "email": "analyst@example.com",
            "password": "correct-horse-battery-staple",
        },
    )

    assert login_response.status_code == 200


def test_login_rate_limit_returns_429_after_configured_attempts():
    client = TestClient(app)
    limiter = InMemoryRateLimiter(max_attempts=1, window_seconds=60)
    app.dependency_overrides[auth_router.get_auth_rate_limiter] = lambda: limiter

    try:
        first_response = client.post(
            "/api/auth/login",
            headers=csrf_headers(client),
            json={
                "email": "analyst@example.com",
                "password": "correct-horse-battery-staple",
            },
        )
        second_response = client.post(
            "/api/auth/login",
            headers=csrf_headers(client),
            json={
                "email": "analyst@example.com",
                "password": "correct-horse-battery-staple",
            },
        )
    finally:
        app.dependency_overrides.pop(auth_router.get_auth_rate_limiter, None)

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.json() == {"detail": "Too many authentication attempts"}


def test_auth_endpoints_record_audit_events_for_csrf_failure_and_login_success():
    client = TestClient(app)
    audit_store = InMemoryAuthAuditStore()
    app.dependency_overrides[auth_router.get_auth_audit_store] = lambda: audit_store

    try:
        csrf_failure_response = client.post(
            "/api/auth/login",
            json={
                "email": "analyst@example.com",
                "password": "correct-horse-battery-staple",
            },
        )
        login_response = client.post(
            "/api/auth/login",
            headers=csrf_headers(client),
            json={
                "email": "analyst@example.com",
                "password": "correct-horse-battery-staple",
            },
        )
    finally:
        app.dependency_overrides.pop(auth_router.get_auth_audit_store, None)

    assert csrf_failure_response.status_code == 403
    assert login_response.status_code == 200
    assert [(event.action, event.outcome, event.email) for event in audit_store.events] == [
        ("login", "csrf_failed", None),
        ("login", "success", "analyst@example.com"),
    ]


def test_sqlalchemy_auth_audit_store_persists_events():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    store = SqlAlchemyAuthAuditStore(engine=engine)

    store.record(
        action="login",
        outcome="success",
        email="analyst@example.com",
        user_id="usr_01",
        client_ip="testclient",
        user_agent="pytest",
    )

    with Session(engine) as db:
        row = db.execute(select(AuthAuditEventModel)).scalar_one()

    assert row.action == "login"
    assert row.outcome == "success"
    assert row.email == "analyst@example.com"
    assert row.user_id == "usr_01"
    assert row.client_ip == "testclient"
