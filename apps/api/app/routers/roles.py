"""Roles & permissions admin endpoints.

All routes (except ``/permissions/catalog``) require the ``roles.manage``
permission, which is granted by the built-in ``super_admin`` role.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import get_auth_audit_store, get_current_api_user
from app.auth.permissions import (
    PERMISSION_CATALOG,
    VALID_PERMISSION_SLUGS,
    WILDCARD,
    current_user_id,
    require_permission,
)
from app.db.models import (
    AuthSessionModel,
    RoleModel,
    RolePermissionModel,
    UserRoleModel,
)
from app.db.session import get_db_session

router = APIRouter(tags=["roles"], prefix="/roles")

DB_DEP = Annotated[Session, Depends(get_db_session)]
ADMIN_USER_DEP = Annotated[dict[str, Any], Depends(require_permission("roles.manage"))]


class PermissionCatalogEntry(BaseModel):
    slug: str
    category: str
    labelKey: str
    descriptionKey: str


class RolePayload(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    permissions: list[str] = Field(default_factory=list)


class RolePatchPayload(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    permissions: list[str] | None = None


class RoleResponse(BaseModel):
    id: str
    name: str
    description: str | None
    color: str | None
    isSystem: bool
    permissions: list[str]
    memberCount: int
    createdAt: datetime
    updatedAt: datetime


class MemberResponse(BaseModel):
    userId: str
    email: str | None
    displayName: str | None
    grantedAt: datetime
    grantedBy: str | None


class AddMemberPayload(BaseModel):
    userId: str | None = None
    email: str | None = None


def _normalize_permissions(perms: list[str]) -> list[str]:
    out: set[str] = set()
    for slug in perms:
        if slug == WILDCARD:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Wildcard permission is reserved for system roles",
            )
        if slug not in VALID_PERMISSION_SLUGS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown permission slug: {slug}",
            )
        out.add(slug)
    return sorted(out)


def _serialize_role(role: RoleModel, perms: list[str], member_count: int) -> RoleResponse:
    return RoleResponse(
        id=role.id,
        name=role.name,
        description=role.description,
        color=role.color,
        isSystem=role.is_system,
        permissions=perms,
        memberCount=member_count,
        createdAt=role.created_at,
        updatedAt=role.updated_at,
    )


def _list_role_perms(db: Session, role_id: str) -> list[str]:
    stmt = select(RolePermissionModel.permission).where(
        RolePermissionModel.role_id == role_id
    )
    return sorted(row[0] for row in db.execute(stmt).all())


def _count_members(db: Session, role_id: str) -> int:
    stmt = select(func.count()).select_from(UserRoleModel).where(
        UserRoleModel.role_id == role_id
    )
    return int(db.execute(stmt).scalar_one() or 0)


def _resolve_user_display(db: Session, user_id: str) -> tuple[str | None, str | None]:
    stmt = (
        select(AuthSessionModel.email, AuthSessionModel.display_name)
        .where(AuthSessionModel.user_id == user_id)
        .order_by(AuthSessionModel.created_at.desc())
        .limit(1)
    )
    row = db.execute(stmt).first()
    if not row:
        return None, None
    return row[0], row[1]


@router.get("/permissions/catalog", response_model=list[PermissionCatalogEntry])
def get_permission_catalog(
    _current_user: Annotated[dict[str, Any], Depends(get_current_api_user)],
) -> list[PermissionCatalogEntry]:
    return [
        PermissionCatalogEntry(
            slug=p.slug,
            category=p.category,
            labelKey=p.label_key,
            descriptionKey=p.description_key,
        )
        for p in PERMISSION_CATALOG
    ]


@router.get("", response_model=list[RoleResponse])
def list_roles(_admin: ADMIN_USER_DEP, db: DB_DEP) -> list[RoleResponse]:
    roles = db.execute(select(RoleModel).order_by(RoleModel.is_system.desc(), RoleModel.name)).scalars().all()
    return [
        _serialize_role(role, _list_role_perms(db, role.id), _count_members(db, role.id))
        for role in roles
    ]


@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
def create_role(payload: RolePayload, admin: ADMIN_USER_DEP, db: DB_DEP) -> RoleResponse:
    normalized_perms = _normalize_permissions(payload.permissions)
    role = RoleModel(
        id=f"role_{uuid.uuid4().hex[:24]}",
        name=payload.name.strip(),
        description=payload.description,
        color=payload.color,
        is_system=False,
    )
    db.add(role)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Role name already exists",
        )
    for slug in normalized_perms:
        db.add(RolePermissionModel(role_id=role.id, permission=slug))
    db.commit()
    db.refresh(role)
    _audit(admin, action="roles.role.create", details={"roleId": role.id, "name": role.name, "permissions": normalized_perms})
    return _serialize_role(role, normalized_perms, 0)


@router.patch("/{role_id}", response_model=RoleResponse)
def update_role(
    role_id: str,
    payload: RolePatchPayload,
    admin: ADMIN_USER_DEP,
    db: DB_DEP,
) -> RoleResponse:
    role = db.get(RoleModel, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_system and payload.name is not None and payload.name != role.name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="System roles cannot be renamed",
        )
    if payload.name is not None:
        role.name = payload.name.strip()
    if payload.description is not None:
        role.description = payload.description
    if payload.color is not None:
        role.color = payload.color
    if payload.permissions is not None:
        if role.is_system:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="System role permissions cannot be edited",
            )
        normalized_perms = _normalize_permissions(payload.permissions)
        db.execute(
            RolePermissionModel.__table__.delete().where(
                RolePermissionModel.role_id == role_id
            )
        )
        for slug in normalized_perms:
            db.add(RolePermissionModel(role_id=role.id, permission=slug))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Role name already exists",
        )
    db.refresh(role)
    perms = _list_role_perms(db, role.id)
    _audit(admin, action="roles.role.update", details={"roleId": role.id, "permissions": perms})
    return _serialize_role(role, perms, _count_members(db, role.id))


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(role_id: str, admin: ADMIN_USER_DEP, db: DB_DEP) -> None:
    role = db.get(RoleModel, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="System roles cannot be deleted",
        )
    db.delete(role)
    db.commit()
    _audit(admin, action="roles.role.delete", details={"roleId": role_id, "name": role.name})


@router.get("/{role_id}/members", response_model=list[MemberResponse])
def list_members(role_id: str, _admin: ADMIN_USER_DEP, db: DB_DEP) -> list[MemberResponse]:
    role = db.get(RoleModel, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    stmt = select(UserRoleModel).where(UserRoleModel.role_id == role_id)
    members: list[MemberResponse] = []
    for assignment in db.execute(stmt).scalars().all():
        email, display = _resolve_user_display(db, assignment.user_id)
        members.append(
            MemberResponse(
                userId=assignment.user_id,
                email=email,
                displayName=display,
                grantedAt=assignment.granted_at,
                grantedBy=assignment.granted_by_user_id,
            )
        )
    members.sort(key=lambda m: ((m.displayName or m.email or m.userId).lower()))
    return members


@router.post("/{role_id}/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
def add_member(
    role_id: str,
    payload: AddMemberPayload,
    admin: ADMIN_USER_DEP,
    db: DB_DEP,
) -> MemberResponse:
    role = db.get(RoleModel, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    user_id = (payload.userId or "").strip()
    if not user_id and payload.email:
        stmt = (
            select(AuthSessionModel.user_id)
            .where(AuthSessionModel.email == payload.email.strip().lower())
            .order_by(AuthSessionModel.created_at.desc())
            .limit(1)
        )
        row = db.execute(stmt).first()
        if row:
            user_id = row[0]
    if not user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    existing = db.get(UserRoleModel, (user_id, role_id))
    if existing is not None:
        email, display = _resolve_user_display(db, user_id)
        return MemberResponse(
            userId=user_id,
            email=email,
            displayName=display,
            grantedAt=existing.granted_at,
            grantedBy=existing.granted_by_user_id,
        )
    assignment = UserRoleModel(
        user_id=user_id,
        role_id=role_id,
        granted_by_user_id=current_user_id(admin),
        granted_at=datetime.now(UTC),
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    email, display = _resolve_user_display(db, user_id)
    _audit(admin, action="roles.member.grant", details={"roleId": role_id, "userId": user_id})
    return MemberResponse(
        userId=user_id,
        email=email,
        displayName=display,
        grantedAt=assignment.granted_at,
        grantedBy=assignment.granted_by_user_id,
    )


@router.delete("/{role_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    role_id: str,
    user_id: str,
    admin: ADMIN_USER_DEP,
    db: DB_DEP,
) -> None:
    assignment = db.get(UserRoleModel, (user_id, role_id))
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")
    db.delete(assignment)
    db.commit()
    _audit(admin, action="roles.member.revoke", details={"roleId": role_id, "userId": user_id})


def _audit(admin: dict[str, Any], *, action: str, details: dict[str, Any]) -> None:
    """Best-effort write to auth_audit_events; failure does not block the request."""
    try:
        store = get_auth_audit_store()
        store.record(
            action=action,
            outcome="ok",
            email=admin.get("email"),
            user_id=current_user_id(admin),
            details=details,
        )
    except Exception:
        pass
