"""create playbook webhook destinations

Revision ID: 20260517_0019
Revises: 20260517_0018
"""

import sqlalchemy as sa
from alembic import op

revision = "20260517_0019"
down_revision = "20260517_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "playbook_webhook_destinations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="discord"),
        sa.Column("url_blob", sa.Text(), nullable=False),
        sa.Column("redacted_url", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_playbook_webhook_destinations_owner_user_id",
        "playbook_webhook_destinations",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_playbook_webhook_destinations_kind",
        "playbook_webhook_destinations",
        ["kind"],
    )
    op.create_index(
        "ix_playbook_webhook_destinations_status",
        "playbook_webhook_destinations",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_playbook_webhook_destinations_status",
        table_name="playbook_webhook_destinations",
    )
    op.drop_index(
        "ix_playbook_webhook_destinations_kind",
        table_name="playbook_webhook_destinations",
    )
    op.drop_index(
        "ix_playbook_webhook_destinations_owner_user_id",
        table_name="playbook_webhook_destinations",
    )
    op.drop_table("playbook_webhook_destinations")
