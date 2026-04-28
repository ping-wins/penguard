from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.auth import dependencies as auth_dependencies
from app.auth.token_cipher import TokenCipher
from app.db.base import Base
from app.integrations.fortigate.service import FortiGateIntegrationService
from app.integrations.fortigate.store import SqlAlchemyFortiGateIntegrationStore
from app.main import app
from app.routers import integrations as integrations_router


def sqlite_engine():
    return create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def csrf_headers(client: TestClient) -> dict[str, str]:
    response = client.get("/api/auth/csrf")
    return {"X-CSRF-Token": response.json()["csrfToken"]}


class HealthyFortiGateClient:
    def get_system_status(self):
        return {
            "hostname": "FGT-VM",
            "model_name": "FortiGate-VM64",
            "version": "v7.4.3",
        }

    def get_performance_status(self):
        return {"cpu": {"idle": 91}, "mem": {"total": 100, "used": 45}}

    def get_resource_usage(self, *, resource: str | None = None):
        assert resource == "session"
        return {"session": [{"current": 128}]}


def test_fortigate_store_records_health_checks_without_exposing_secrets():
    engine = sqlite_engine()
    Base.metadata.create_all(engine)
    store = SqlAlchemyFortiGateIntegrationStore(
        engine=engine,
        secret_cipher=TokenCipher.from_secret("test-secret"),
        id_factory=lambda: "int_fgt_health",
        health_id_factory=lambda: "fgt_health_01",
    )
    store.create(
        owner_user_id="usr_owner",
        name="FortiGate Lab",
        host="https://fortigate.local/",
        api_key="secret-token",
        verify_tls=False,
    )

    recorded = store.record_health_check(
        owner_user_id="usr_owner",
        integration_id="int_fgt_health",
        ok=True,
        status="connected",
        device={"hostname": "FGT-VM", "model": "FortiGate-VM64", "version": "v7.4.3"},
        message=None,
        latency_ms=12,
        checked_at=datetime(2026, 4, 27, 20, 30, tzinfo=UTC),
    )

    assert recorded == {
        "id": "fgt_health_01",
        "integrationId": "int_fgt_health",
        "ok": True,
        "status": "connected",
        "device": {"hostname": "FGT-VM", "model": "FortiGate-VM64", "version": "v7.4.3"},
        "message": None,
        "latencyMs": 12,
        "checkedAt": "2026-04-27T20:30:00.000Z",
    }
    assert store.list_health_checks(owner_user_id="usr_owner", integration_id="int_fgt_health") == {
        "items": [recorded]
    }
    assert "secret-token" not in repr(recorded)


def test_fortigate_service_runs_saved_integration_health_check_and_persists_result():
    engine = sqlite_engine()
    Base.metadata.create_all(engine)
    store = SqlAlchemyFortiGateIntegrationStore(
        engine=engine,
        secret_cipher=TokenCipher.from_secret("test-secret"),
        id_factory=lambda: "int_fgt_health",
        health_id_factory=lambda: "fgt_health_01",
    )
    service = FortiGateIntegrationService(
        store=store,
        client_factory=lambda *, host, api_key, verify_tls: HealthyFortiGateClient(),
        clock=lambda: datetime(2026, 4, 27, 20, 31, tzinfo=UTC),
    )
    service.create(
        owner_user_id="usr_owner",
        name="FortiGate Lab",
        host="https://fortigate.local/",
        api_key="secret-token",
        verify_tls=False,
    )

    result = service.run_health_check(
        integration_id="int_fgt_health",
        owner_user_id="usr_owner",
    )

    assert result["ok"] is True
    assert result["status"] == "connected"
    assert result["device"]["hostname"] == "FGT-VM"
    assert store.list_health_checks(
        owner_user_id="usr_owner",
        integration_id="int_fgt_health",
    )["items"] == [result]


def test_health_checks_endpoint_returns_404_for_missing_integration():
    engine = sqlite_engine()
    Base.metadata.create_all(engine)
    service = FortiGateIntegrationService(
        store=SqlAlchemyFortiGateIntegrationStore(
            engine=engine,
            secret_cipher=TokenCipher.from_secret("test-secret"),
        ),
        client_factory=lambda *, host, api_key, verify_tls: HealthyFortiGateClient(),
    )
    app.dependency_overrides[integrations_router.get_fortigate_integration_service] = (
        lambda: service
    )
    app.dependency_overrides[auth_dependencies.get_current_api_user] = lambda: {
        "id": "usr_owner",
        "email": "owner@example.com",
        "displayName": "Owner",
        "roles": ["analyst"],
    }
    client = TestClient(app)

    try:
        response = client.get("/api/integrations/fortigate/int_missing/health-checks")
    finally:
        app.dependency_overrides.pop(
            integrations_router.get_fortigate_integration_service, None
        )
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)

    assert response.status_code == 404
