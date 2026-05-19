from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import dependencies as auth_dependencies
from app.db.base import Base
from app.db.models import PenguinToolIntegrationModel
from app.integrations.penguin_tools import SqlAlchemyPenguinToolIntegrationStore
from app.main import app
from app.routers import integrations as integrations_router


class FakePenguinToolIntegrationService:
    def __init__(self) -> None:
        self.created: list[dict] = []
        self.deleted: list[dict] = []
        self.connections: dict[str, dict] = {
            "int_siem_01": {
                "id": "int_siem_01",
                "type": "siem_kowalski",
                "name": "Kowalski SIEM",
                "host": "http://siem-kowalski:8000",
                "status": "connected",
                "capabilities": ["events", "incidents"],
                "lastCheckedAt": "2026-05-08T12:00:00.000Z",
            }
        }

    def test_connection(self, *, tool_type: str) -> dict:
        return {
            "ok": True,
            "status": "connected",
            "service": tool_type,
            "capabilities": ["events", "incidents"],
        }

    def create(self, *, owner_user_id: str, tool_type: str, name: str | None = None) -> dict:
        created = {
            "id": f"int_{tool_type}_test",
            "type": tool_type,
            "name": name or "Kowalski SIEM",
            "host": "http://siem-kowalski:8000",
            "status": "connected",
            "capabilities": ["events", "incidents"],
            "lastCheckedAt": "2026-05-08T12:00:00.000Z",
        }
        self.created.append({"owner_user_id": owner_user_id, "tool_type": tool_type, "name": name})
        self.connections[created["id"]] = created
        return created

    def list(self, *, owner_user_id: str) -> dict:
        assert owner_user_id
        return {"items": list(self.connections.values())}

    def get(self, *, integration_id: str, owner_user_id: str) -> dict | None:
        assert owner_user_id
        return self.connections.get(integration_id)

    def delete(self, *, owner_user_id: str, integration_id: str) -> bool:
        self.deleted.append({"owner_user_id": owner_user_id, "integration_id": integration_id})
        return self.connections.pop(integration_id, None) is not None


def csrf_headers(client: TestClient) -> dict[str, str]:
    response = client.get("/api/auth/csrf")
    return {"X-CSRF-Token": response.json()["csrfToken"]}


def teardown_function():
    app.dependency_overrides.clear()


def test_penguin_tool_connection_test_uses_configured_service_and_audits_nothing_sensitive():
    client = TestClient(app)
    service = FakePenguinToolIntegrationService()
    app.dependency_overrides[integrations_router.get_penguin_tool_integration_service] = lambda: (
        service
    )

    response = client.post(
        "/api/integrations/penguin-tools/test",
        headers=csrf_headers(client),
        json={"type": "siem_kowalski"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "status": "connected",
        "service": "siem_kowalski",
        "capabilities": ["events", "incidents"],
    }


def test_penguin_tool_create_lists_as_optional_integration_and_audits():
    client = TestClient(app)
    service = FakePenguinToolIntegrationService()
    app.dependency_overrides[integrations_router.get_penguin_tool_integration_service] = lambda: (
        service
    )

    response = client.post(
        "/api/integrations/penguin-tools",
        headers=csrf_headers(client),
        json={"type": "siem_kowalski", "name": "Kowalski Lab"},
    )
    listed = client.get("/api/integrations")
    audit = auth_dependencies.get_auth_audit_store().list_events(
        action="integration.penguin_tool.created"
    )

    assert response.status_code == 201
    assert response.json()["type"] == "siem_kowalski"
    assert response.json()["name"] == "Kowalski Lab"
    assert any(item["type"] == "siem_kowalski" for item in listed.json()["items"])
    assert audit["items"][0]["details"] == {
        "integrationId": "int_siem_kowalski_test",
        "type": "siem_kowalski",
        "service": "siem_kowalski",
    }


def test_delete_integration_removes_penguin_tool_when_not_a_fortigate_id():
    client = TestClient(app)
    service = FakePenguinToolIntegrationService()
    app.dependency_overrides[integrations_router.get_penguin_tool_integration_service] = lambda: (
        service
    )

    response = client.delete(
        "/api/integrations/int_siem_01",
        headers=csrf_headers(client),
    )
    audit = auth_dependencies.get_auth_audit_store().list_events(
        action="integration.penguin_tool.deleted"
    )

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "id": "int_siem_01"}
    assert service.deleted[0]["integration_id"] == "int_siem_01"
    assert audit["items"][0]["details"] == {
        "integrationId": "int_siem_01",
        "type": "siem_kowalski",
    }


def test_penguin_tool_store_scopes_rows_by_owner_and_returns_public_payload():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    ids = iter(["int_siem_owner_a", "int_xdr_owner_b"])
    store = SqlAlchemyPenguinToolIntegrationStore(
        engine=engine,
        id_factory=lambda _tool_type: next(ids),
    )

    created = store.create(
        owner_user_id="usr_a",
        tool_type="siem_kowalski",
        name="Kowalski Lab",
        host="http://siem-kowalski:8000",
        capabilities=["events", "incidents"],
        checked_at=datetime.now(UTC),
    )
    store.create(
        owner_user_id="usr_b",
        tool_type="xdr_rico",
        name="Rico Lab",
        host="http://xdr-rico:8000",
        capabilities=["endpoints"],
        checked_at=datetime.now(UTC),
    )

    with Session(engine) as db:
        rows = list(db.execute(select(PenguinToolIntegrationModel)).scalars())

    assert created["id"] == "int_siem_owner_a"
    assert created["type"] == "siem_kowalski"
    assert created["host"] == "http://siem-kowalski:8000"
    assert [row.owner_user_id for row in rows] == ["usr_a", "usr_b"]
    all_items = store.list_public(owner_user_id="usr_a")["items"]
    assert [item["id"] for item in all_items] == ["int_siem_owner_a", "int_xdr_owner_b"]
    assert store.get(integration_id="int_xdr_owner_b", owner_user_id="usr_a") is None
    assert store.delete(integration_id="int_xdr_owner_b", owner_user_id="usr_a") is False
    assert store.delete(integration_id="int_siem_owner_a", owner_user_id="usr_a") is True
