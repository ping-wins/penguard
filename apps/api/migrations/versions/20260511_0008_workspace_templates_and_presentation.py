"""workspace templates and presentation metadata

Revision ID: 20260511_0008
Revises: 20260508_0007
Create Date: 2026-05-11 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260511_0008"
down_revision: str | None = "20260508_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workspace_specs",
        sa.Column("presentation", sa.JSON(), nullable=True),
    )

    op.create_table(
        "workspace_templates",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("published_by_user_id", sa.String(length=255), nullable=False),
        sa.Column("published_by_email", sa.String(length=320), nullable=True),
        sa.Column("install_count", sa.Integer(), nullable=False),
        sa.Column("is_visible", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(
        "ix_workspace_templates_slug",
        "workspace_templates",
        ["slug"],
        unique=True,
    )
    op.create_index(
        "ix_workspace_templates_published_by_user_id",
        "workspace_templates",
        ["published_by_user_id"],
    )
    op.create_index(
        "ix_workspace_templates_is_visible",
        "workspace_templates",
        ["is_visible"],
    )
    op.create_index(
        "ix_workspace_templates_created_at",
        "workspace_templates",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_workspace_templates_created_at", table_name="workspace_templates")
    op.drop_index("ix_workspace_templates_is_visible", table_name="workspace_templates")
    op.drop_index(
        "ix_workspace_templates_published_by_user_id",
        table_name="workspace_templates",
    )
    op.drop_index("ix_workspace_templates_slug", table_name="workspace_templates")
    op.drop_table("workspace_templates")

    op.drop_column("workspace_specs", "presentation")
