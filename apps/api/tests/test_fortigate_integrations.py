from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import dependencies as auth_dependencies
from app.auth.token_cipher import TokenCipher
from app.db.base import Base
from app.db.models import FortiGateIntegrationModel
from app.integrations.fortigate.service import FortiGateIntegrationService
from app.integrations.fortigate.store import SqlAlchemyFortiGateIntegrationStore
from app.main import app
from app.routers import integrations as integrations_router


def csrf_headers(client: TestClient) -> dict[str, str]:
    response = client.get("/api/auth/csrf")
    return {"X-CSRF-Token": response.json()["csrfToken"]}


def test_fortigate_integration_store_encrypts_api_key_and_returns_public_payload():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    store = SqlAlchemyFortiGateIntegrationStore(
        engine=engine,
        secret_cipher=TokenCipher.from_secret("test-secret"),
        id_factory=lambda: "int_fgt_test",
    )

    created = store.create(
        owner_user_id="usr_owner",
        name="FortiGate Lab",
        host="https://fortigate.local/",
        api_key="fg_api_key_from_user",
        verify_tls=False,
    )

    with Session(engine) as db:
        row = db.execute(select(FortiGateIntegrationModel)).scalar_one()

    assert created["id"] == "int_fgt_test"
    assert created["type"] == "fortigate"
    assert created["name"] == "FortiGate Lab"
    assert created["status"] == "connected"
    assert created["capabilities"] == ["system", "interfaces", "policies", "threat_logs"]
    assert "apiKey" not in created
    assert row.owner_user_id == "usr_owner"
    assert row.api_key_blob != ""
    assert "fg_api_key_from_user" not in row.api_key_blob
    assert store.get_api_key("int_fgt_test", owner_user_id="usr_owner") == "fg_api_key_from_user"

    listed = store.list_public(owner_user_id="usr_owner")

    assert listed == {
        "items": [
            {
                "id": "int_fgt_test",
                "type": "fortigate",
                "name": "FortiGate Lab",
                "host": "https://fortigate.local/",
                "status": "connected",
                "lastCheckedAt": created["lastCheckedAt"],
            }
        ]
    }
    assert "apiKey" not in listed["items"][0]


def test_fortigate_integration_store_scopes_rows_by_owner_user_id():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    ids = iter(["int_fgt_owner_a", "int_fgt_owner_b"])
    store = SqlAlchemyFortiGateIntegrationStore(
        engine=engine,
        secret_cipher=TokenCipher.from_secret("test-secret"),
        id_factory=lambda: next(ids),
    )

    store.create(
        owner_user_id="usr_a",
        name="Owner A FortiGate",
        host="https://fortigate-a.local/",
        api_key="owner-a-token",
        verify_tls=False,
    )
    store.create(
        owner_user_id="usr_b",
        name="Owner B FortiGate",
        host="https://fortigate-b.local/",
        api_key="owner-b-token",
        verify_tls=False,
    )

    assert [item["id"] for item in store.list_public(owner_user_id="usr_a")["items"]] == [
        "int_fgt_owner_a"
    ]
    assert store.get_connection("int_fgt_owner_b", owner_user_id="usr_a") is None
    assert store.get_connection("int_fgt_owner_a", owner_user_id="usr_a") == {
        "id": "int_fgt_owner_a",
        "host": "https://fortigate-a.local/",
        "api_key": "owner-a-token",
        "verify_tls": False,
    }


def test_fortigate_integration_service_can_use_persistent_store():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    service = FortiGateIntegrationService(
        store=SqlAlchemyFortiGateIntegrationStore(
            engine=engine,
            secret_cipher=TokenCipher.from_secret("test-secret"),
            id_factory=lambda: "int_fgt_service",
        )
    )

    created = service.create(
        owner_user_id="usr_owner",
        name="FortiGate Lab",
        host="https://fortigate.local/",
        api_key="fg_api_key_from_user",
        verify_tls=False,
    )
    listed = service.list(owner_user_id="usr_owner")

    assert created["id"] == "int_fgt_service"
    assert listed["items"][0]["id"] == "int_fgt_service"


def test_fortigate_integration_service_tests_connection_with_live_client():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    class FakeClient:
        def get_system_status(self):
            return {
                "hostname": "FGT-VM",
                "model_name": "FortiGate-VM64",
                "version": "v7.4.3",
            }

        def get_performance_status(self):
            return {
                "cpu": {"idle": 97},
                "mem": {"total": 100, "used": 48},
            }

        def get_resource_usage(self, resource: str | None = None):
            assert resource == "session"
            return {"session": [{"current": 15}]}

    service = FortiGateIntegrationService(
        store=SqlAlchemyFortiGateIntegrationStore(
            engine=engine,
            secret_cipher=TokenCipher.from_secret("test-secret"),
            id_factory=lambda: "int_fgt_service",
        ),
        client_factory=lambda *, host, api_key, verify_tls: FakeClient(),
    )

    result = service.test_connection(
        host="https://fortigate.local/",
        api_key="secret-token",
        verify_tls=False,
    )

    assert result == {
        "ok": True,
        "status": "connected",
        "device": {
            "hostname": "FGT-VM",
            "model": "FortiGate-VM64",
            "version": "v7.4.3",
        },
    }


def test_fortigate_integration_endpoint_can_use_persistent_service():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    service = FortiGateIntegrationService(
        store=SqlAlchemyFortiGateIntegrationStore(
            engine=engine,
            secret_cipher=TokenCipher.from_secret("test-secret"),
            id_factory=lambda: "int_fgt_endpoint",
        )
    )
    app.dependency_overrides[integrations_router.get_fortigate_integration_service] = (
        lambda: service
    )
    client = TestClient(app)

    try:
        create_response = client.post(
            "/api/integrations/fortigate",
            headers=csrf_headers(client),
            json={
                "name": "FortiGate Lab",
                "host": "https://fortigate.local",
                "apiKey": "fg_api_key_from_user",
                "verifyTls": False,
            },
        )
        list_response = client.get("/api/integrations")
    finally:
        app.dependency_overrides.pop(
            integrations_router.get_fortigate_integration_service,
            None,
        )
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)

    assert create_response.status_code == 201
    assert "apiKey" not in create_response.json()
    assert create_response.json()["id"] == "int_fgt_endpoint"
    assert list_response.status_code == 200
    assert list_response.json()["items"] == [
        {
            "id": "int_fgt_endpoint",
            "type": "fortigate",
            "name": "FortiGate Lab",
            "host": "https://fortigate.local/",
            "status": "connected",
            "lastCheckedAt": create_response.json()["lastCheckedAt"],
        }
    ]


def test_fortigate_integration_endpoint_scopes_list_to_authenticated_user():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    ids = iter(["int_fgt_owner_a", "int_fgt_owner_b"])
    service = FortiGateIntegrationService(
        store=SqlAlchemyFortiGateIntegrationStore(
            engine=engine,
            secret_cipher=TokenCipher.from_secret("test-secret"),
            id_factory=lambda: next(ids),
        )
    )
    app.dependency_overrides[integrations_router.get_fortigate_integration_service] = (
        lambda: service
    )
    app.dependency_overrides[auth_dependencies.get_current_api_user] = lambda: {
        "id": "usr_a",
        "email": "a@example.com",
        "displayName": "Analyst A",
        "roles": ["analyst"],
    }
    client = TestClient(app)

    try:
        first_response = client.post(
            "/api/integrations/fortigate",
            headers=csrf_headers(client),
            json={
                "name": "Owner A FortiGate",
                "host": "https://fortigate-a.local",
                "apiKey": "owner-a-token",
                "verifyTls": False,
            },
        )
        app.dependency_overrides[auth_dependencies.get_current_api_user] = lambda: {
            "id": "usr_b",
            "email": "b@example.com",
            "displayName": "Analyst B",
            "roles": ["analyst"],
        }
        second_response = client.post(
            "/api/integrations/fortigate",
            headers=csrf_headers(client),
            json={
                "name": "Owner B FortiGate",
                "host": "https://fortigate-b.local",
                "apiKey": "owner-b-token",
                "verifyTls": False,
            },
        )
        app.dependency_overrides[auth_dependencies.get_current_api_user] = lambda: {
            "id": "usr_a",
            "email": "a@example.com",
            "displayName": "Analyst A",
            "roles": ["analyst"],
        }
        list_response = client.get("/api/integrations")
    finally:
        app.dependency_overrides.pop(
            integrations_router.get_fortigate_integration_service,
            None,
        )
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert [item["id"] for item in list_response.json()["items"]] == ["int_fgt_owner_a"]
