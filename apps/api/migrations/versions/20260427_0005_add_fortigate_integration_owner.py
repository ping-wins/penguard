"""add fortigate integration owner

Revision ID: 20260427_0005
Revises: 20260426_0004
Create Date: 2026-04-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260427_0005"
down_revision: str | None = "20260426_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fortigate_integrations",
        sa.Column(
            "owner_user_id",
            sa.String(length=255),
            nullable=False,
            server_default="legacy-system",
        ),
    )
    op.create_index(
        "ix_fortigate_integrations_owner_user_id",
        "fortigate_integrations",
        ["owner_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fortigate_integrations_owner_user_id",
        table_name="fortigate_integrations",
    )
    op.drop_column("fortigate_integrations", "owner_user_id")
