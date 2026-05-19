from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.auth import dependencies as auth_dependencies
from app.auth.audit import (
    AuditSiemForwarder,
    ForwardingAuthAuditStore,
    InMemoryAuthAuditStore,
    sanitize_audit_details,
)
from app.auth.token_cipher import TokenCipher
from app.db.base import Base
from app.integrations.fortigate.client import FortiGateApiError
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


class FakeSiemClient:
    def __init__(self):
        self.calls: list[dict] = []

    def request(
        self,
        method: str,
        path: str,
        *,
        json=None,
        params=None,
        headers=None,
        pass_through_statuses=None,
    ) -> dict:
        event = {"id": "evt_audit_01", **(json or {})}
        self.calls.append(
            {
                "method": method,
                "path": path,
                "json": json,
                "params": params,
                "headers": headers,
                "pass_through_statuses": pass_through_statuses,
            }
        )
        if path == "/events/ingest":
            return {
                "event": event,
                "incident": {
                    "id": "inc_audit_01",
                    "title": "Repeated failed Penguard logins",
                    "severity": "medium",
                    "triageLevel": "T2",
                    "ticketStatus": "new",
                    "createdAt": "2026-05-15T12:05:00.000Z",
                },
            }
        return event


class FailingSiemClient:
    def request(self, *args, **kwargs) -> dict:
        raise RuntimeError("siem unavailable")


class HealthyFortiGateClient:
    def __init__(self):
        self.syslog_setting = {
            "status": "disable",
            "server": "",
            "port": 514,
            "mode": "udp",
            "facility": "local7",
            "format": "default",
        }
        self.syslog_filter = {
            "severity": "information",
            "forward-traffic": "disable",
            "local-traffic": "disable",
            "multicast-traffic": "disable",
        }

    def get_system_status(self):
        return {
            "hostname": "FGT-VM",
            "model_name": "FortiGate-VM64",
            "version": "v7.4.3",
            "serial": "FGVMTEST",
        }

    def get_performance_status(self):
        return {"cpu": {"idle": 97}, "mem": {"total": 100, "used": 48}}

    def get_resource_usage(self, resource: str | None = None):
        assert resource == "session"
        return {"session": [{"current": 15}]}

    def get_syslog_setting(self, *, slot: int = 1):
        return dict(self.syslog_setting)

    def get_syslog_filter(self, *, slot: int = 1):
        return dict(self.syslog_filter)

    def update_syslog_setting(self, payload, *, slot: int = 1):
        self.syslog_setting.update(payload)
        return dict(payload)

    def update_syslog_filter(self, payload, *, slot: int = 1):
        self.syslog_filter.update(payload)
        return dict(payload)


def healthy_client_factory(*, host: str, api_key: str, verify_tls: bool):
    return HealthyFortiGateClient()


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


def test_audit_store_forwards_sanitized_platform_events_to_siem():
    primary = InMemoryAuthAuditStore()
    siem = FakeSiemClient()
    realtime_events: list[dict] = []
    store = ForwardingAuthAuditStore(
        primary=primary,
        forwarder=AuditSiemForwarder(
            siem_client=siem,
            realtime_publisher=realtime_events.append,
        ),
    )

    store.record(
        action="integration.fortigate.log_forwarding_applied",
        outcome="success",
        email="owner@example.com",
        user_id="usr_owner",
        client_ip="203.0.113.10",
        user_agent="pytest",
        details={
            "integrationId": "int_fgt_01",
            "apiKey": "fg-secret-token",
            "collectorHost": "192.0.2.50",
        },
    )

    assert primary.events[0].details["apiKey"] == "[REDACTED]"
    assert siem.calls == [
        {
            "method": "POST",
            "path": "/events/ingest",
            "json": {
                "source": "penguard.audit",
                "eventType": "platform.audit_action",
                "severity": "medium",
                "occurredAt": primary.events[0].created_at.isoformat(
                    timespec="milliseconds"
                ).replace("+00:00", "Z"),
                "entities": {
                    "actorUserId": "usr_owner",
                    "sourceIp": "203.0.113.10",
                    "user": "owner@example.com",
                },
                "attributes": {
                    "originKind": "penguard.audit",
                    "action": "integration.fortigate.log_forwarding_applied",
                    "outcome": "success",
                    "userAgent": "pytest",
                    "details": {
                        "integrationId": "int_fgt_01",
                        "apiKey": "[REDACTED]",
                        "collectorHost": "192.0.2.50",
                    },
                    "count": 1,
                },
            },
            "params": None,
            "headers": None,
            "pass_through_statuses": None,
        }
    ]
    assert realtime_events == [
        {
            "type": "audit.siem.event",
            "ownerUserId": "usr_owner",
            "eventId": "evt_audit_01",
            "receivedAt": primary.events[0].created_at.isoformat(
                timespec="milliseconds"
            ).replace("+00:00", "Z"),
            "ticket": {
                "id": "inc_audit_01",
                "title": "Repeated failed Penguard logins",
                "severity": "medium",
                "triageLevel": "T2",
                "ticketStatus": "new",
                "createdAt": "2026-05-15T12:05:00.000Z",
            },
        }
    ]
    assert "fg-secret-token" not in repr(siem.calls)


def test_audit_store_maps_failed_login_to_siem_failed_login_event():
    primary = InMemoryAuthAuditStore()
    siem = FakeSiemClient()
    store = ForwardingAuthAuditStore(
        primary=primary,
        forwarder=AuditSiemForwarder(siem_client=siem),
    )

    store.record(
        action="login",
        outcome="invalid_credentials",
        email="analyst@example.com",
        client_ip="198.51.100.20",
        user_agent="pytest",
    )

    forwarded = siem.calls[0]["json"]
    assert forwarded["source"] == "penguard.audit"
    assert forwarded["eventType"] == "auth.failed_login"
    assert forwarded["severity"] == "medium"
    assert forwarded["entities"] == {
        "sourceIp": "198.51.100.20",
        "user": "analyst@example.com",
    }
    assert forwarded["attributes"]["action"] == "login"
    assert forwarded["attributes"]["outcome"] == "invalid_credentials"
    assert forwarded["attributes"]["count"] == 1


def test_audit_siem_forwarding_failure_does_not_drop_primary_audit_record():
    primary = InMemoryAuthAuditStore()
    store = ForwardingAuthAuditStore(
        primary=primary,
        forwarder=AuditSiemForwarder(siem_client=FailingSiemClient()),
    )

    store.record(
        action="workspace.updated",
        outcome="success",
        user_id="usr_owner",
        details={"workspaceId": "ws_01"},
    )

    assert primary.list_events()["items"][0]["action"] == "workspace.updated"


def test_integration_create_records_sanitized_audit_event():
    engine = sqlite_engine()
    Base.metadata.create_all(engine)
    service = FortiGateIntegrationService(
        store=SqlAlchemyFortiGateIntegrationStore(
            engine=engine,
            secret_cipher=TokenCipher.from_secret("test-secret"),
            id_factory=lambda: "int_fgt_audit",
        ),
        client_factory=healthy_client_factory,
    )
    audit_store = InMemoryAuthAuditStore()
    app.dependency_overrides[integrations_router.get_fortigate_integration_service] = lambda: (
        service
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
                "apiKey": "fg-secret-token-123",
                "verifyTls": False,
            },
        )
    finally:
        app.dependency_overrides.pop(integrations_router.get_fortigate_integration_service, None)
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
        "logForwardingConfigured": True,
        "logForwardingChanged": True,
    }
    assert "fg-secret-token-123" not in repr(audit_store.events)


def test_integration_create_failure_records_sanitized_audit_event():
    engine = sqlite_engine()
    Base.metadata.create_all(engine)

    class FailingFortiGateClient:
        def get_system_status(self):
            raise FortiGateApiError("FortiGate API request failed")

        def get_performance_status(self):
            return {}

        def get_resource_usage(self, resource: str | None = None):
            return {}

    store = SqlAlchemyFortiGateIntegrationStore(
        engine=engine,
        secret_cipher=TokenCipher.from_secret("test-secret"),
        id_factory=lambda: "int_fgt_failed_audit",
    )
    service = FortiGateIntegrationService(
        store=store,
        client_factory=lambda *, host, api_key, verify_tls: FailingFortiGateClient(),
    )
    audit_store = InMemoryAuthAuditStore()
    app.dependency_overrides[integrations_router.get_fortigate_integration_service] = lambda: (
        service
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
                "name": "Broken FortiGate",
                "host": "https://fortigate.invalid",
                "apiKey": "fg-secret-token-123",
                "verifyTls": False,
            },
        )
    finally:
        app.dependency_overrides.pop(integrations_router.get_fortigate_integration_service, None)
        app.dependency_overrides.pop(auth_dependencies.get_auth_audit_store, None)
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)

    assert response.status_code == 400
    assert response.json() == {"detail": "FortiGate API request failed"}
    assert audit_store.events[0].action == "integration.fortigate.created"
    assert audit_store.events[0].outcome == "failed"
    assert audit_store.events[0].details == {
        "host": "https://fortigate.invalid/",
        "verifyTls": False,
        "error": "FortiGate API request failed",
    }
    assert store.list_public(owner_user_id="usr_owner") == {"items": []}
    assert "fg-secret-token-123" not in repr(audit_store.events)


def test_integration_delete_records_sanitized_audit_event():
    engine = sqlite_engine()
    Base.metadata.create_all(engine)
    service = FortiGateIntegrationService(
        store=SqlAlchemyFortiGateIntegrationStore(
            engine=engine,
            secret_cipher=TokenCipher.from_secret("test-secret"),
            id_factory=lambda: "int_fgt_delete_audit",
        ),
        client_factory=healthy_client_factory,
    )
    audit_store = InMemoryAuthAuditStore()
    app.dependency_overrides[integrations_router.get_fortigate_integration_service] = lambda: (
        service
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
        create_response = client.post(
            "/api/integrations/fortigate",
            headers=csrf_headers(client),
            json={
                "name": "FortiGate Lab",
                "host": "https://fortigate.local",
                "apiKey": "fg-secret-token-123",
                "verifyTls": False,
            },
        )
        delete_response = client.delete(
            "/api/integrations/int_fgt_delete_audit",
            headers=csrf_headers(client),
        )
    finally:
        app.dependency_overrides.pop(integrations_router.get_fortigate_integration_service, None)
        app.dependency_overrides.pop(auth_dependencies.get_auth_audit_store, None)
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)

    assert create_response.status_code == 201
    assert delete_response.status_code == 200
    assert [(event.action, event.outcome, event.user_id) for event in audit_store.events] == [
        ("integration.fortigate.created", "success", "usr_owner"),
        ("integration.fortigate.deleted", "success", "usr_owner"),
    ]
    assert audit_store.events[1].details == {"integrationId": "int_fgt_delete_audit"}
    assert "fg-secret-token-123" not in repr(audit_store.events)


def test_integration_delete_failure_records_audit_event():
    engine = sqlite_engine()
    Base.metadata.create_all(engine)
    service = FortiGateIntegrationService(
        store=SqlAlchemyFortiGateIntegrationStore(
            engine=engine,
            secret_cipher=TokenCipher.from_secret("test-secret"),
            id_factory=lambda: "int_fgt_other_user",
        ),
        client_factory=healthy_client_factory,
    )
    audit_store = InMemoryAuthAuditStore()
    app.dependency_overrides[integrations_router.get_fortigate_integration_service] = lambda: (
        service
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
        create_response = client.post(
            "/api/integrations/fortigate",
            headers=csrf_headers(client),
            json={
                "name": "FortiGate Lab",
                "host": "https://fortigate.local",
                "apiKey": "fg-secret-token-123",
                "verifyTls": False,
            },
        )
        app.dependency_overrides[auth_dependencies.get_current_api_user] = lambda: {
            "id": "usr_other",
            "email": "other@example.com",
            "displayName": "Other",
            "roles": ["analyst"],
        }
        delete_response = client.delete(
            "/api/integrations/int_fgt_other_user",
            headers=csrf_headers(client),
        )
    finally:
        app.dependency_overrides.pop(integrations_router.get_fortigate_integration_service, None)
        app.dependency_overrides.pop(auth_dependencies.get_auth_audit_store, None)
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)

    assert create_response.status_code == 201
    assert delete_response.status_code == 404
    assert [(event.action, event.outcome, event.user_id) for event in audit_store.events] == [
        ("integration.fortigate.created", "success", "usr_owner"),
        ("integration.fortigate.deleted", "failed", "usr_other"),
    ]
    assert audit_store.events[1].details == {
        "integrationId": "int_fgt_other_user",
        "error": "Integration not found",
    }
    assert "fg-secret-token-123" not in repr(audit_store.events)


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


def test_admin_audit_events_requires_admin_role():
    audit_store = InMemoryAuthAuditStore()
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
        response = client.get("/api/admin/audit/events")
    finally:
        app.dependency_overrides.pop(audit_router.get_auth_audit_store, None)
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)

    assert response.status_code == 403
    assert response.json() == {"detail": "Administrator role required"}


def test_admin_audit_events_returns_cross_user_events_and_records_read_event():
    audit_store = InMemoryAuthAuditStore()
    audit_store.record(
        action="integration.fortigate.created",
        outcome="success",
        email="owner@example.com",
        user_id="usr_owner",
        details={"integrationId": "int_fgt_owner", "apiKey": "must-not-leak"},
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
        "id": "usr_admin",
        "email": "admin@example.com",
        "displayName": "SOC Admin",
        "roles": ["admin"],
    }
    client = TestClient(app)

    try:
        response = client.get("/api/admin/audit/events", params={"limit": 50})
    finally:
        app.dependency_overrides.pop(audit_router.get_auth_audit_store, None)
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)

    assert response.status_code == 200
    payload = response.json()
    assert {item["actor"]["id"] for item in payload["items"]} == {"usr_owner", "usr_other"}
    assert "must-not-leak" not in response.text
    owner_event = next(item for item in payload["items"] if item["actor"]["id"] == "usr_owner")
    assert owner_event["details"]["apiKey"] == "[REDACTED]"
    assert audit_store.events[-1].action == "audit.events.viewed"
    assert audit_store.events[-1].outcome == "success"
    assert audit_store.events[-1].user_id == "usr_admin"
    assert audit_store.events[-1].details == {
        "scope": "admin",
        "limit": 50,
        "actorUserId": None,
        "action": None,
        "outcome": None,
    }


def test_admin_audit_events_filters_by_actor_action_and_outcome():
    audit_store = InMemoryAuthAuditStore()
    audit_store.record(
        action="login",
        outcome="success",
        email="owner@example.com",
        user_id="usr_owner",
        details={},
    )
    audit_store.record(
        action="login",
        outcome="failed",
        email="other@example.com",
        user_id="usr_other",
        details={"reason": "invalid_password"},
    )
    audit_store.record(
        action="workspace.updated",
        outcome="failed",
        email="other@example.com",
        user_id="usr_other",
        details={"workspaceId": "ws_other"},
    )
    app.dependency_overrides[audit_router.get_auth_audit_store] = lambda: audit_store
    app.dependency_overrides[auth_dependencies.get_current_api_user] = lambda: {
        "id": "usr_admin",
        "email": "admin@example.com",
        "displayName": "SOC Admin",
        "roles": ["admin"],
    }
    client = TestClient(app)

    try:
        response = client.get(
            "/api/admin/audit/events",
            params={
                "actorUserId": "usr_other",
                "action": "login",
                "outcome": "failed",
            },
        )
    finally:
        app.dependency_overrides.pop(audit_router.get_auth_audit_store, None)
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)

    assert response.status_code == 200
    assert [
        (item["actor"]["id"], item["action"], item["outcome"]) for item in response.json()["items"]
    ] == [("usr_other", "login", "failed")]
    assert audit_store.events[-1].details == {
        "scope": "admin",
        "limit": 50,
        "actorUserId": "usr_other",
        "action": "login",
        "outcome": "failed",
    }
