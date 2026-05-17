"""RBAC: permission dependency + /api/roles + /api/users endpoints.

These tests exercise the real DB-backed path, so they spin up an
in-memory SQLite engine and force ``mock_mode=False`` (the conftest
default is mock mode, which short-circuits permission resolution to the
legacy admin-only gate).
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.auth.permissions as permissions_module
import app.routers.auth as auth_router
from app.auth.dependencies import get_current_api_user
from app.db import models
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app

SUPER_ADMIN_ROLE_ID = "role_super_admin"


class _Settings:
    mock_mode = False


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    now = datetime.now(UTC)
    session.add(
        models.RoleModel(
            id=SUPER_ADMIN_ROLE_ID,
            name="super_admin",
            description="built-in",
            color="#5865F2",
            is_system=True,
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        models.RolePermissionModel(role_id=SUPER_ADMIN_ROLE_ID, permission="*")
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def make_client(db_session, monkeypatch):
    monkeypatch.setattr(permissions_module, "get_settings", lambda: _Settings())
    monkeypatch.setattr(auth_router, "get_settings", lambda: _Settings())

    def _override_db():
        yield db_session

    def _client(user: dict):
        app.dependency_overrides[get_db_session] = _override_db
        app.dependency_overrides[get_current_api_user] = lambda: user
        return TestClient(app)

    yield _client
    app.dependency_overrides.clear()


ANALYST = {"id": "usr_analyst", "email": "a@example.com", "roles": ["analyst"]}
KEYCLOAK_ADMIN = {"id": "usr_kc", "email": "kc@example.com", "roles": ["admin"]}


def test_non_admin_denied_roles_endpoint(make_client):
    client = make_client(ANALYST)
    r = client.get("/api/roles")
    assert r.status_code == 403
    assert r.json()["detail"] == "Permission required: roles.manage"


def test_keycloak_admin_bootstrap_bypasses(make_client):
    client = make_client(KEYCLOAK_ADMIN)
    r = client.get("/api/roles")
    assert r.status_code == 200
    assert r.json()[0]["name"] == "super_admin"


def test_db_super_admin_can_list_roles(make_client, db_session):
    db_session.add(
        models.UserRoleModel(
            user_id="usr_analyst",
            role_id=SUPER_ADMIN_ROLE_ID,
            granted_at=datetime.now(UTC),
        )
    )
    db_session.commit()
    client = make_client(ANALYST)
    r = client.get("/api/roles")
    assert r.status_code == 200


def test_create_update_delete_role(make_client):
    client = make_client(KEYCLOAK_ADMIN)

    created = client.post(
        "/api/roles",
        json={"name": "SOC Analyst", "color": "#10B981", "permissions": ["audit.read"]},
    )
    assert created.status_code == 201, created.text
    role_id = created.json()["id"]
    assert created.json()["permissions"] == ["audit.read"]

    patched = client.patch(
        f"/api/roles/{role_id}",
        json={"permissions": ["audit.read", "tickets.manage"]},
    )
    assert patched.status_code == 200
    assert sorted(patched.json()["permissions"]) == ["audit.read", "tickets.manage"]

    deleted = client.delete(f"/api/roles/{role_id}")
    assert deleted.status_code == 204


def test_reject_unknown_permission_slug(make_client):
    client = make_client(KEYCLOAK_ADMIN)
    r = client.post(
        "/api/roles",
        json={"name": "Bad", "permissions": ["does.not.exist"]},
    )
    assert r.status_code == 422


def test_wildcard_permission_rejected_on_custom_role(make_client):
    client = make_client(KEYCLOAK_ADMIN)
    r = client.post("/api/roles", json={"name": "Wild", "permissions": ["*"]})
    assert r.status_code == 400


def test_system_role_cannot_be_deleted(make_client):
    client = make_client(KEYCLOAK_ADMIN)
    r = client.delete(f"/api/roles/{SUPER_ADMIN_ROLE_ID}")
    assert r.status_code == 409
    assert r.json()["detail"] == "System roles cannot be deleted"


def test_duplicate_role_name_conflict(make_client):
    client = make_client(KEYCLOAK_ADMIN)
    first = client.post("/api/roles", json={"name": "Dup", "permissions": []})
    assert first.status_code == 201
    second = client.post("/api/roles", json={"name": "Dup", "permissions": []})
    assert second.status_code == 409


def test_member_grant_and_revoke(make_client, db_session):
    db_session.add(
        models.AuthSessionModel(
            id="sess_1",
            user_id="usr_target",
            email="target@example.com",
            display_name="Target User",
            roles=["analyst"],
            token_blob="x",
            created_at=datetime.now(UTC),
        )
    )
    db_session.commit()
    client = make_client(KEYCLOAK_ADMIN)

    role = client.post("/api/roles", json={"name": "Team", "permissions": ["audit.read"]})
    role_id = role.json()["id"]

    added = client.post(f"/api/roles/{role_id}/members", json={"userId": "usr_target"})
    assert added.status_code == 201
    assert added.json()["email"] == "target@example.com"

    members = client.get(f"/api/roles/{role_id}/members")
    assert [m["userId"] for m in members.json()] == ["usr_target"]

    removed = client.delete(f"/api/roles/{role_id}/members/usr_target")
    assert removed.status_code == 204
    assert client.get(f"/api/roles/{role_id}/members").json() == []


def test_me_permissions_endpoint(make_client, db_session):
    role = make_client  # noqa: F841 - keep fixture order explicit
    client = make_client(KEYCLOAK_ADMIN)
    r = client.get("/api/users/me/permissions")
    assert r.status_code == 200
    body = r.json()
    assert body["isAdmin"] is True
    assert "roles.manage" in body["permissions"]


def test_user_directory_and_role_toggle(make_client, db_session):
    db_session.add(
        models.AuthSessionModel(
            id="sess_2",
            user_id="usr_dir",
            email="dir@example.com",
            display_name="Dir User",
            roles=["analyst"],
            token_blob="x",
            created_at=datetime.now(UTC),
        )
    )
    db_session.commit()
    client = make_client(KEYCLOAK_ADMIN)

    role = client.post("/api/roles", json={"name": "Ops", "permissions": []})
    role_id = role.json()["id"]

    listed = client.get("/api/users")
    assert any(u["userId"] == "usr_dir" for u in listed.json())

    patched = client.patch(
        "/api/users/usr_dir/roles",
        json={"add": [role_id], "remove": []},
    )
    assert patched.status_code == 200
    assert any(r["id"] == role_id for r in patched.json()["roles"])
