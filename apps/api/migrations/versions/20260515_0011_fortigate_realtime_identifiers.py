"""fortigate realtime identifiers

Revision ID: 20260515_0011
Revises: 20260513_0010
Create Date: 2026-05-15 08:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260515_0011"
down_revision: str | None = "20260513_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fortigate_integrations",
        sa.Column("device_identifiers", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("fortigate_integrations", "device_identifiers")
