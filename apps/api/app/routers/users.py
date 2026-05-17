"""User directory + per-user role management.

The directory aggregates two sources:
  1. ``auth_sessions`` (anyone who has logged in at least once).
  2. ``user_roles`` (anyone who has been granted a role manually).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_auth_audit_store, get_current_api_user
from app.auth.permissions import (
    PERMISSION_CATALOG,
    WILDCARD,
    current_user_id,
    require_permission,
    resolve_effective_permissions,
)
from app.db.models import AuthSessionModel, RoleModel, UserRoleModel
from app.db.session import get_db_session

router = APIRouter(tags=["users"], prefix="/users")

DB_DEP = Annotated[Session, Depends(get_db_session)]
ADMIN_USER_DEP = Annotated[dict[str, Any], Depends(require_permission("roles.manage"))]
CURRENT_USER_DEP = Annotated[dict[str, Any], Depends(get_current_api_user)]


class RolePill(BaseModel):
    id: str
    name: str
    color: str | None


class UserEntry(BaseModel):
    userId: str
    email: str | None
    displayName: str | None
    roles: list[RolePill]
    lastSeenAt: datetime | None


class UpdateUserRolesPayload(BaseModel):
    add: list[str] = Field(default_factory=list)
    remove: list[str] = Field(default_factory=list)


class MePermissionsResponse(BaseModel):
    permissions: list[str]
    isAdmin: bool


def _aggregate_users(db: Session, query: str | None) -> list[UserEntry]:
    session_stmt = (
        select(
            AuthSessionModel.user_id,
            AuthSessionModel.email,
            AuthSessionModel.display_name,
            AuthSessionModel.created_at,
        )
        .order_by(AuthSessionModel.created_at.desc())
    )
    rows = db.execute(session_stmt).all()
    latest: dict[str, dict[str, Any]] = {}
    for user_id, email, display_name, created_at in rows:
        if user_id in latest:
            continue
        latest[user_id] = {
            "userId": user_id,
            "email": email,
            "displayName": display_name,
            "lastSeenAt": created_at,
        }
    assignment_user_ids = {
        row[0]
        for row in db.execute(select(UserRoleModel.user_id).distinct()).all()
    }
    for user_id in assignment_user_ids:
        latest.setdefault(
            user_id,
            {"userId": user_id, "email": None, "displayName": None, "lastSeenAt": None},
        )

    roles_by_user: dict[str, list[RolePill]] = {}
    stmt = (
        select(UserRoleModel.user_id, RoleModel.id, RoleModel.name, RoleModel.color)
        .join(RoleModel, RoleModel.id == UserRoleModel.role_id)
    )
    for user_id, role_id, name, color in db.execute(stmt).all():
        roles_by_user.setdefault(user_id, []).append(
            RolePill(id=role_id, name=name, color=color)
        )

    out: list[UserEntry] = []
    needle = (query or "").strip().lower()
    for user_id, entry in latest.items():
        if needle:
            haystack = " ".join(
                str(v) for v in (entry.get("email"), entry.get("displayName"), user_id) if v
            ).lower()
            if needle not in haystack:
                continue
        out.append(
            UserEntry(
                userId=user_id,
                email=entry.get("email"),
                displayName=entry.get("displayName"),
                roles=sorted(roles_by_user.get(user_id, []), key=lambda r: r.name.lower()),
                lastSeenAt=entry.get("lastSeenAt"),
            )
        )
    out.sort(key=lambda u: ((u.displayName or u.email or u.userId).lower()))
    return out


@router.get("", response_model=list[UserEntry])
def list_users(
    _admin: ADMIN_USER_DEP,
    db: DB_DEP,
    q: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[UserEntry]:
    return _aggregate_users(db, q)[:limit]


@router.patch("/{user_id}/roles", response_model=UserEntry)
def update_user_roles(
    user_id: str,
    payload: UpdateUserRolesPayload,
    admin: ADMIN_USER_DEP,
    db: DB_DEP,
) -> UserEntry:
    if payload.add:
        existing = {
            row[0]
            for row in db.execute(
                select(RoleModel.id).where(RoleModel.id.in_(payload.add))
            ).all()
        }
        unknown = set(payload.add) - existing
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Unknown role ids: {sorted(unknown)}",
            )
        for role_id in payload.add:
            if db.get(UserRoleModel, (user_id, role_id)) is None:
                db.add(
                    UserRoleModel(
                        user_id=user_id,
                        role_id=role_id,
                        granted_by_user_id=current_user_id(admin),
                        granted_at=datetime.now(UTC),
                    )
                )
    if payload.remove:
        db.execute(
            UserRoleModel.__table__.delete().where(
                UserRoleModel.user_id == user_id,
                UserRoleModel.role_id.in_(payload.remove),
            )
        )
    db.commit()
    try:
        store = get_auth_audit_store()
        store.record(
            action="roles.user.update",
            outcome="ok",
            email=admin.get("email"),
            user_id=current_user_id(admin),
            details={"targetUserId": user_id, "add": payload.add, "remove": payload.remove},
        )
    except Exception:
        pass
    matches = [u for u in _aggregate_users(db, None) if u.userId == user_id]
    if not matches:
        return UserEntry(userId=user_id, email=None, displayName=None, roles=[], lastSeenAt=None)
    return matches[0]


@router.get("/me/permissions", response_model=MePermissionsResponse)
def my_permissions(
    current_user: CURRENT_USER_DEP,
    db: DB_DEP,
) -> MePermissionsResponse:
    perms = resolve_effective_permissions(db, current_user)
    if WILDCARD in perms:
        all_slugs = sorted({p.slug for p in PERMISSION_CATALOG})
        return MePermissionsResponse(permissions=all_slugs, isAdmin=True)
    return MePermissionsResponse(permissions=sorted(perms), isAdmin=False)
