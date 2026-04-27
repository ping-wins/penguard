"""create fortigate integrations

Revision ID: 20260426_0004
Revises: 20260426_0003
Create Date: 2026-04-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260426_0004"
down_revision: str | None = "20260426_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fortigate_integrations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("host", sa.String(length=2048), nullable=False),
        sa.Column("verify_tls", sa.Boolean(), nullable=False),
        sa.Column("api_key_blob", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fortigate_integrations_status", "fortigate_integrations", ["status"])


def downgrade() -> None:
    op.drop_index("ix_fortigate_integrations_status", table_name="fortigate_integrations")
    op.drop_table("fortigate_integrations")
