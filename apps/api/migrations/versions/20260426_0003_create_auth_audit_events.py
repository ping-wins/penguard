"""create auth audit events

Revision ID: 20260426_0003
Revises: 20260426_0002
Create Date: 2026-04-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260426_0003"
down_revision: str | None = "20260426_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_audit_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("user_id", sa.String(length=255), nullable=True),
        sa.Column("client_ip", sa.String(length=255), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_audit_events_action", "auth_audit_events", ["action"])
    op.create_index("ix_auth_audit_events_created_at", "auth_audit_events", ["created_at"])
    op.create_index("ix_auth_audit_events_email", "auth_audit_events", ["email"])
    op.create_index("ix_auth_audit_events_outcome", "auth_audit_events", ["outcome"])
    op.create_index("ix_auth_audit_events_user_id", "auth_audit_events", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_auth_audit_events_user_id", table_name="auth_audit_events")
    op.drop_index("ix_auth_audit_events_outcome", table_name="auth_audit_events")
    op.drop_index("ix_auth_audit_events_email", table_name="auth_audit_events")
    op.drop_index("ix_auth_audit_events_created_at", table_name="auth_audit_events")
    op.drop_index("ix_auth_audit_events_action", table_name="auth_audit_events")
    op.drop_table("auth_audit_events")
