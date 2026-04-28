"""add workspaces and fortigate health checks

Revision ID: 20260427_0006
Revises: 20260427_0005
Create Date: 2026-04-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260427_0006"
down_revision: str | None = "20260427_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fortigate_health_checks",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("integration_id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.String(length=255), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("device", sa.JSON(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_fortigate_health_checks_checked_at",
        "fortigate_health_checks",
        ["checked_at"],
    )
    op.create_index(
        "ix_fortigate_health_checks_integration_id",
        "fortigate_health_checks",
        ["integration_id"],
    )
    op.create_index(
        "ix_fortigate_health_checks_owner_user_id",
        "fortigate_health_checks",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_fortigate_health_checks_status",
        "fortigate_health_checks",
        ["status"],
    )

    op.create_table(
        "workspace_specs",
        sa.Column("workspace_id", sa.String(length=128), nullable=False),
        sa.Column("owner_user_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("widgets", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("workspace_id", "owner_user_id"),
    )
    op.create_index(
        "ix_workspace_specs_owner_user_id",
        "workspace_specs",
        ["owner_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_workspace_specs_owner_user_id", table_name="workspace_specs")
    op.drop_table("workspace_specs")

    op.drop_index("ix_fortigate_health_checks_status", table_name="fortigate_health_checks")
    op.drop_index(
        "ix_fortigate_health_checks_owner_user_id",
        table_name="fortigate_health_checks",
    )
    op.drop_index(
        "ix_fortigate_health_checks_integration_id",
        table_name="fortigate_health_checks",
    )
    op.drop_index("ix_fortigate_health_checks_checked_at", table_name="fortigate_health_checks")
    op.drop_table("fortigate_health_checks")
