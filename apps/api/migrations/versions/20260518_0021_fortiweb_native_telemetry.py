"""add native FortiWeb telemetry state

Revision ID: 20260518_0021
Revises: 20260517_0020
Create Date: 2026-05-18 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260518_0021"
down_revision: str | None = "20260517_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fortiweb_integrations",
        sa.Column("telemetry_token_hash", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "fortiweb_integrations",
        sa.Column("telemetry_token_created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "fortiweb_integrations",
        sa.Column("telemetry_last_event_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "fortiweb_integrations",
        sa.Column("telemetry_last_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "fortiweb_integrations",
        sa.Column(
            "telemetry_events_received",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("fortiweb_integrations", "telemetry_events_received")
    op.drop_column("fortiweb_integrations", "telemetry_last_error")
    op.drop_column("fortiweb_integrations", "telemetry_last_event_at")
    op.drop_column("fortiweb_integrations", "telemetry_token_created_at")
    op.drop_column("fortiweb_integrations", "telemetry_token_hash")
