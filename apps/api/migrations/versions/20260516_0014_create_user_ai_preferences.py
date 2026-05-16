"""create user ai preferences

Revision ID: 20260516_0014
Revises: 20260516_0013
Create Date: 2026-05-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260516_0014"
down_revision: str | None = "20260516_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_ai_preferences",
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="api"),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="gemini"),
        sa.Column("model", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("api_key_blob", sa.Text(), nullable=True),
        sa.Column("cli_binary", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("user_ai_preferences")
