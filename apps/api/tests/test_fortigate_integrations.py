from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.token_cipher import TokenCipher
from app.db.base import Base
from app.db.models import FortiGateIntegrationModel
from app.integrations.fortigate.service import FortiGateIntegrationService
from app.integrations.fortigate.store import SqlAlchemyFortiGateIntegrationStore
from app.main import app
from app.routers import integrations as integrations_router


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
    assert row.api_key_blob != ""
    assert "fg_api_key_from_user" not in row.api_key_blob
    assert store.get_api_key("int_fgt_test") == "fg_api_key_from_user"

    listed = store.list_public()

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
        name="FortiGate Lab",
        host="https://fortigate.local/",
        api_key="fg_api_key_from_user",
        verify_tls=False,
    )
    listed = service.list()

    assert created["id"] == "int_fgt_service"
    assert listed["items"][0]["id"] == "int_fgt_service"


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
