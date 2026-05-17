"""create roles, role_permissions, user_roles

Revision ID: 20260517_0015
Revises: 20260516_0014
Create Date: 2026-05-17
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "20260517_0015"
down_revision: str | None = "20260516_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SUPER_ADMIN_ROLE_ID = "role_super_admin"


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("color", sa.String(length=7), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.String(length=64), nullable=False),
        sa.Column("permission", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission"),
    )

    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("role_id", sa.String(length=64), nullable=False),
        sa.Column("granted_by_user_id", sa.String(length=255), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "role_id"),
    )
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])

    now = datetime.now(UTC)
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO roles (id, name, description, color, is_system, created_at, updated_at) "
            "VALUES (:id, :name, :description, :color, TRUE, :created_at, :updated_at)"
        ),
        {
            "id": SUPER_ADMIN_ROLE_ID,
            "name": "super_admin",
            "description": "Built-in administrator role with all permissions.",
            "color": "#5865F2",
            "created_at": now,
            "updated_at": now,
        },
    )
    bind.execute(
        sa.text("INSERT INTO role_permissions (role_id, permission) VALUES (:role_id, '*')"),
        {"role_id": SUPER_ADMIN_ROLE_ID},
    )

    # Backfill: every distinct user_id in auth_sessions whose roles JSON list
    # contains "admin" gets a super_admin membership. Idempotent via DISTINCT
    # + NOT EXISTS guard.
    bind.execute(
        sa.text(
            """
            INSERT INTO user_roles (user_id, role_id, granted_by_user_id, granted_at)
            SELECT DISTINCT s.user_id, :role_id, NULL, :granted_at
            FROM auth_sessions s
            WHERE s.roles::jsonb ? 'admin'
              AND NOT EXISTS (
                SELECT 1 FROM user_roles ur
                WHERE ur.user_id = s.user_id AND ur.role_id = :role_id
              )
            """
        ),
        {"role_id": SUPER_ADMIN_ROLE_ID, "granted_at": now},
    )


def downgrade() -> None:
    op.drop_index("ix_user_roles_user_id", table_name="user_roles")
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.drop_table("roles")
