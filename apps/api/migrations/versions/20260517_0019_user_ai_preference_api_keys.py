"""add provider key map to user AI preferences

Revision ID: 20260517_0019
Revises: 20260517_0018
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260517_0019"
down_revision: str | None = "20260517_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_ai_preferences", sa.Column("api_keys_blob", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_ai_preferences", "api_keys_blob")
