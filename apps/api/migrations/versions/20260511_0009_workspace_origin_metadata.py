"""workspace origin metadata

Revision ID: 20260511_0009
Revises: 20260511_0008
Create Date: 2026-05-11 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260511_0009"
down_revision: str | None = "20260511_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workspace_specs",
        sa.Column("origin", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workspace_specs", "origin")
