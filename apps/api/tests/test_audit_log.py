from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.auth import dependencies as auth_dependencies
from app.auth.audit import InMemoryAuthAuditStore, sanitize_audit_details
from app.auth.token_cipher import TokenCipher
from app.db.base import Base
from app.integrations.fortigate.service import FortiGateIntegrationService
from app.integrations.fortigate.store import SqlAlchemyFortiGateIntegrationStore
from app.main import app
from app.routers import audit as audit_router
from app.routers import integrations as integrations_router
from app.routers import workspaces as workspaces_router
from app.workspaces.store import SqlAlchemyWorkspaceStore


def sqlite_engine():
    return create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def csrf_headers(client: TestClient) -> dict[str, str]:
    response = client.get("/api/auth/csrf")
    return {"X-CSRF-Token": response.json()["csrfToken"]}


def test_audit_details_redact_secret_fields_recursively():
    details = sanitize_audit_details(
        {
            "apiKey": "fg-secret",
            "api_key": "fg-secret",
            "token": "kc-secret",
            "access_token": "kc-secret",
            "refresh_token": "kc-secret",
            "clientSecret": "client-secret",
            "password": "user-secret",
            "nested": [{"api_key_blob": "encrypted-secret"}],
            "safe": "kept",
        }
    )

    assert details == {
        "apiKey": "[REDACTED]",
        "api_key": "[REDACTED]",
        "token": "[REDACTED]",
        "access_token": "[REDACTED]",
        "refresh_token": "[REDACTED]",
        "clientSecret": "[REDACTED]",
        "password": "[REDACTED]",
        "nested": [{"api_key_blob": "[REDACTED]"}],
        "safe": "kept",
    }
    assert "fg-secret" not in repr(details)
    assert "kc-secret" not in repr(details)


def test_integration_create_records_sanitized_audit_event():
    engine = sqlite_engine()
    Base.metadata.create_all(engine)
    service = FortiGateIntegrationService(
        store=SqlAlchemyFortiGateIntegrationStore(
            engine=engine,
            secret_cipher=TokenCipher.from_secret("test-secret"),
            id_factory=lambda: "int_fgt_audit",
        )
    )
    audit_store = InMemoryAuthAuditStore()
    app.dependency_overrides[integrations_router.get_fortigate_integration_service] = (
        lambda: service
    )
    app.dependency_overrides[auth_dependencies.get_auth_audit_store] = lambda: audit_store
    app.dependency_overrides[auth_dependencies.get_current_api_user] = lambda: {
        "id": "usr_owner",
        "email": "owner@example.com",
        "displayName": "Owner",
        "roles": ["analyst"],
    }
    client = TestClient(app)

    try:
        response = client.post(
            "/api/integrations/fortigate",
            headers=csrf_headers(client),
            json={
                "name": "FortiGate Lab",
                "host": "https://fortigate.local",
                "apiKey": "fg-secret",
                "verifyTls": False,
            },
        )
    finally:
        app.dependency_overrides.pop(
            integrations_router.get_fortigate_integration_service, None
        )
        app.dependency_overrides.pop(auth_dependencies.get_auth_audit_store, None)
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)

    assert response.status_code == 201
    assert [(event.action, event.outcome, event.user_id) for event in audit_store.events] == [
        ("integration.fortigate.created", "success", "usr_owner")
    ]
    assert audit_store.events[0].details == {
        "integrationId": "int_fgt_audit",
        "host": "https://fortigate.local/",
        "verifyTls": False,
    }
    assert "fg-secret" not in repr(audit_store.events)


def test_workspace_update_records_audit_event_without_widget_secrets():
    engine = sqlite_engine()
    Base.metadata.create_all(engine)
    workspace_store = SqlAlchemyWorkspaceStore(engine=engine)
    audit_store = InMemoryAuthAuditStore()
    app.dependency_overrides[workspaces_router.get_workspace_store] = lambda: workspace_store
    app.dependency_overrides[auth_dependencies.get_auth_audit_store] = lambda: audit_store
    app.dependency_overrides[auth_dependencies.get_current_api_user] = lambda: {
        "id": "usr_owner",
        "email": "owner@example.com",
        "displayName": "Owner",
        "roles": ["analyst"],
    }
    client = TestClient(app)

    try:
        response = client.put(
            "/api/workspaces/ws_default",
            headers=csrf_headers(client),
            json={
                "name": "SOC Overview",
                "widgets": [
                    {
                        "instanceId": "w_01",
                        "catalogId": "fortigate-system-status",
                        "integrationId": "int_fgt_01",
                        "layout": {"x": 0, "y": 0, "w": 3, "h": 2, "z": 10},
                        "apiKey": "must-not-log",
                    }
                ],
            },
        )
    finally:
        app.dependency_overrides.pop(workspaces_router.get_workspace_store, None)
        app.dependency_overrides.pop(auth_dependencies.get_auth_audit_store, None)
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)

    assert response.status_code == 200
    assert [(event.action, event.outcome, event.user_id) for event in audit_store.events] == [
        ("workspace.updated", "success", "usr_owner")
    ]
    assert audit_store.events[0].details["workspaceId"] == "ws_default"
    assert audit_store.events[0].details["widgetCount"] == 1
    assert "must-not-log" not in repr(audit_store.events)


def test_audit_events_endpoint_returns_sanitized_events_for_authenticated_user():
    audit_store = InMemoryAuthAuditStore()
    audit_store.record(
        action="integration.fortigate.created",
        outcome="success",
        email="owner@example.com",
        user_id="usr_owner",
        client_ip="testclient",
        user_agent="pytest",
        details={"integrationId": "int_fgt_01", "apiKey": "must-not-leak"},
    )
    app.dependency_overrides[audit_router.get_auth_audit_store] = lambda: audit_store
    app.dependency_overrides[auth_dependencies.get_current_api_user] = lambda: {
        "id": "usr_owner",
        "email": "owner@example.com",
        "displayName": "Owner",
        "roles": ["analyst"],
    }
    client = TestClient(app)

    try:
        response = client.get("/api/audit/events", params={"limit": 50})
    finally:
        app.dependency_overrides.pop(audit_router.get_auth_audit_store, None)
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)

    assert response.status_code == 200
    assert response.json()["items"] == [
        {
            "id": "audit_memory_1",
            "actor": {"id": "usr_owner", "email": "owner@example.com"},
            "action": "integration.fortigate.created",
            "outcome": "success",
            "ipAddress": "testclient",
            "userAgent": "pytest",
            "details": {"integrationId": "int_fgt_01", "apiKey": "[REDACTED]"},
            "createdAt": response.json()["items"][0]["createdAt"],
        }
    ]
    assert "must-not-leak" not in response.text


def test_audit_events_endpoint_scopes_events_to_authenticated_user():
    audit_store = InMemoryAuthAuditStore()
    audit_store.record(
        action="integration.fortigate.created",
        outcome="success",
        email="owner@example.com",
        user_id="usr_owner",
        details={"integrationId": "int_fgt_owner"},
    )
    audit_store.record(
        action="workspace.updated",
        outcome="success",
        email="other@example.com",
        user_id="usr_other",
        details={"workspaceId": "ws_other"},
    )
    app.dependency_overrides[audit_router.get_auth_audit_store] = lambda: audit_store
    app.dependency_overrides[auth_dependencies.get_current_api_user] = lambda: {
        "id": "usr_owner",
        "email": "owner@example.com",
        "displayName": "Owner",
        "roles": ["analyst"],
    }
    client = TestClient(app)

    try:
        response = client.get("/api/audit/events")
    finally:
        app.dependency_overrides.pop(audit_router.get_auth_audit_store, None)
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)

    assert response.status_code == 200
    assert [item["actor"]["id"] for item in response.json()["items"]] == ["usr_owner"]
