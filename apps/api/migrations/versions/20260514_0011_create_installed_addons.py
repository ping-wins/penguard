"""create installed_addons

Revision ID: 20260514_0011
Revises: 20260513_0010
Create Date: 2026-05-14 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260514_0011"
down_revision: str | None = "20260513_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "installed_addons",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("tag", sa.String(length=128), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("installed_addons")
