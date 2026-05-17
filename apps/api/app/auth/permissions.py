"""Permission catalog + effective permission resolution.

The permission slug is the stable identifier. Display labels are i18n keys on
the frontend side. Adding a permission = append to PERMISSION_CATALOG plus the
matching ``Depends(require_permission(...))`` on the gated router.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_api_user
from app.db.models import RolePermissionModel, UserRoleModel
from app.db.session import get_db_session

WILDCARD = "*"
SUPER_ADMIN_ROLE_ID = "role_super_admin"


@dataclass(frozen=True)
class PermissionDef:
    slug: str
    category: str
    label_key: str
    description_key: str


PERMISSION_CATALOG: tuple[PermissionDef, ...] = (
    PermissionDef(
        slug="integrations.write",
        category="integrations",
        label_key="settings.roles.permission.integrations.write.label",
        description_key="settings.roles.permission.integrations.write.description",
    ),
    PermissionDef(
        slug="audit.read",
        category="audit",
        label_key="settings.roles.permission.audit.read.label",
        description_key="settings.roles.permission.audit.read.description",
    ),
    PermissionDef(
        slug="roles.manage",
        category="roles",
        label_key="settings.roles.permission.roles.manage.label",
        description_key="settings.roles.permission.roles.manage.description",
    ),
    PermissionDef(
        slug="marketplace.install",
        category="marketplace",
        label_key="settings.roles.permission.marketplace.install.label",
        description_key="settings.roles.permission.marketplace.install.description",
    ),
    PermissionDef(
        slug="workspaces.share",
        category="workspaces",
        label_key="settings.roles.permission.workspaces.share.label",
        description_key="settings.roles.permission.workspaces.share.description",
    ),
    PermissionDef(
        slug="playbooks.execute",
        category="playbooks",
        label_key="settings.roles.permission.playbooks.execute.label",
        description_key="settings.roles.permission.playbooks.execute.description",
    ),
    PermissionDef(
        slug="tickets.manage",
        category="tickets",
        label_key="settings.roles.permission.tickets.manage.label",
        description_key="settings.roles.permission.tickets.manage.description",
    ),
)

VALID_PERMISSION_SLUGS: frozenset[str] = frozenset(p.slug for p in PERMISSION_CATALOG)


def has_keycloak_admin_claim(current_user: dict[str, Any]) -> bool:
    return "admin" in (current_user.get("roles") or [])


def current_user_id(current_user: dict[str, Any]) -> str | None:
    """Extract the stable user id from a session payload (handles both keys)."""
    return current_user.get("user_id") or current_user.get("id")


def effective_permissions(db: Session, user_id: str) -> set[str]:
    """Union of permissions granted by every role assigned to the user."""
    stmt = (
        select(RolePermissionModel.permission)
        .join(UserRoleModel, UserRoleModel.role_id == RolePermissionModel.role_id)
        .where(UserRoleModel.user_id == user_id)
    )
    return {row[0] for row in db.execute(stmt).all()}


def resolve_effective_permissions(
    db: Session, current_user: dict[str, Any]
) -> set[str]:
    """Effective set after applying the keycloak-admin bootstrap rule."""
    if has_keycloak_admin_claim(current_user):
        return {WILDCARD}
    user_id = current_user_id(current_user)
    if not user_id:
        return set()
    return effective_permissions(db, user_id)


def require_permission(slug: str):
    """Build a FastAPI dependency that gates a route on ``slug``.

    Keycloak ``admin`` claim still bypasses (anti-lockout). For everyone else,
    the slug must be present in their effective permission set, or the set
    must contain the wildcard ``"*"``.
    """

    if slug != WILDCARD and slug not in VALID_PERMISSION_SLUGS:
        raise ValueError(f"Unknown permission slug: {slug}")

    def _dep(
        current_user: Annotated[dict[str, Any], Depends(get_current_api_user)],
        db: Annotated[Session, Depends(get_db_session)],
    ) -> dict[str, Any]:
        if has_keycloak_admin_claim(current_user):
            return current_user
        user_id = current_user_id(current_user)
        perms = effective_permissions(db, user_id) if user_id else set()
        if slug in perms or WILDCARD in perms:
            return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission required: {slug}",
        )

    return _dep
