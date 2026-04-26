"""add auth session expiry

Revision ID: 20260426_0002
Revises: 20260426_0001
Create Date: 2026-04-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260426_0002"
down_revision: str | None = "20260426_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "auth_sessions",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("auth_sessions", "expires_at")
