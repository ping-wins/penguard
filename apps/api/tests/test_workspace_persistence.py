from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.auth import dependencies as auth_dependencies
from app.db.base import Base
from app.main import app
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


def test_workspace_store_persists_specs_and_scopes_them_by_owner():
    engine = sqlite_engine()
    Base.metadata.create_all(engine)
    store = SqlAlchemyWorkspaceStore(
        engine=engine,
        clock=lambda: datetime(2026, 4, 27, 20, 15, tzinfo=UTC),
    )

    result = store.save(
        workspace_id="ws_default",
        owner_user_id="usr_owner",
        name="SOC Overview",
        widgets=[
            {
                "instanceId": "w_01",
                "catalogId": "fortigate-system-status",
                "integrationId": "int_fgt_01",
                "layout": {"x": 0, "y": 0, "w": 3, "h": 2, "z": 10},
            }
        ],
    )

    assert result == {
        "id": "ws_default",
        "version": 1,
        "updatedAt": "2026-04-27T20:15:00.000Z",
    }
    assert store.get("ws_default", owner_user_id="usr_owner") == {
        "id": "ws_default",
        "name": "SOC Overview",
        "widgets": [
            {
                "instanceId": "w_01",
                "catalogId": "fortigate-system-status",
                "integrationId": "int_fgt_01",
                "layout": {"x": 0, "y": 0, "w": 3, "h": 2, "z": 10},
            }
        ],
        "version": 1,
        "updatedAt": "2026-04-27T20:15:00.000Z",
    }
    assert store.get("ws_default", owner_user_id="usr_other") is None


def test_workspace_endpoint_round_trips_persistent_specs_for_authenticated_user():
    engine = sqlite_engine()
    Base.metadata.create_all(engine)
    store = SqlAlchemyWorkspaceStore(
        engine=engine,
        clock=lambda: datetime(2026, 4, 27, 20, 20, tzinfo=UTC),
    )
    app.dependency_overrides[workspaces_router.get_workspace_store] = lambda: store
    app.dependency_overrides[auth_dependencies.get_current_api_user] = lambda: {
        "id": "usr_owner",
        "email": "owner@example.com",
        "displayName": "Owner",
        "roles": ["analyst"],
    }
    client = TestClient(app)

    try:
        put_response = client.put(
            "/api/workspaces/ws_default",
            headers=csrf_headers(client),
            json={
                "name": "SOC Overview",
                "widgets": [
                    {
                        "instanceId": "w_01",
                        "catalogId": "fortigate-system-status",
                        "integrationId": "int_fgt_01",
                        "layout": {"x": 10, "y": 20, "w": 4, "h": 2, "z": 11},
                        "fieldBindings": [
                            {
                                "fieldId": "system.cpu",
                                "label": "CPU Usage",
                                "type": "number",
                                "unit": "percent",
                                "source": "fortigate-system-status",
                                "provider": "fortigate",
                                "groupId": "system",
                                "groupName": "System Data",
                            }
                        ],
                    }
                ],
            },
        )
        get_response = client.get("/api/workspaces/ws_default")
    finally:
        app.dependency_overrides.pop(workspaces_router.get_workspace_store, None)
        app.dependency_overrides.pop(auth_dependencies.get_current_api_user, None)

    assert put_response.status_code == 200
    assert put_response.json() == {
        "id": "ws_default",
        "version": 1,
        "updatedAt": "2026-04-27T20:20:00.000Z",
    }
    assert get_response.status_code == 200
    assert get_response.json()["widgets"] == [
        {
            "instanceId": "w_01",
            "catalogId": "fortigate-system-status",
            "integrationId": "int_fgt_01",
            "layout": {"x": 10, "y": 20, "w": 4, "h": 2, "z": 11},
            "fieldBindings": [
                {
                    "fieldId": "system.cpu",
                    "label": "CPU Usage",
                    "type": "number",
                    "unit": "percent",
                    "source": "fortigate-system-status",
                    "provider": "fortigate",
                    "groupId": "system",
                    "groupName": "System Data",
                }
            ],
        }
    ]


def test_workspace_update_requires_csrf_header():
    client = TestClient(app)

    response = client.put(
        "/api/workspaces/ws_default",
        json={"name": "SOC Overview", "widgets": []},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "CSRF validation failed"}
