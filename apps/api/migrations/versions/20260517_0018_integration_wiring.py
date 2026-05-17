"""integration wiring and soar targets

Revision ID: 20260517_0018
Revises: 20260517_0017
"""

from alembic import op
import sqlalchemy as sa

revision = "20260517_0018"
down_revision = "20260517_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_wiring",
        sa.Column("integration_id", sa.String(length=128), primary_key=True),
        sa.Column("siem_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("soar_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "soar_targets",
        sa.Column("integration_id", sa.String(length=128), primary_key=True),
        sa.Column("actions", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("soar_targets")
    op.drop_table("integration_wiring")
