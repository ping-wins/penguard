"""create penguin tool integrations

Revision ID: 20260508_0007
Revises: 20260427_0006
Create Date: 2026-05-08 17:45:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260508_0007"
down_revision: str | None = "20260427_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "penguin_tool_integrations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("host", sa.String(length=2048), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_penguin_tool_integrations_owner_user_id",
        "penguin_tool_integrations",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_penguin_tool_integrations_status",
        "penguin_tool_integrations",
        ["status"],
    )
    op.create_index(
        "ix_penguin_tool_integrations_type",
        "penguin_tool_integrations",
        ["type"],
    )


def downgrade() -> None:
    op.drop_index("ix_penguin_tool_integrations_type", table_name="penguin_tool_integrations")
    op.drop_index("ix_penguin_tool_integrations_status", table_name="penguin_tool_integrations")
    op.drop_index(
        "ix_penguin_tool_integrations_owner_user_id",
        table_name="penguin_tool_integrations",
    )
    op.drop_table("penguin_tool_integrations")
