"""fortigate ingestion status

Revision ID: 20260513_0010
Revises: 20260511_0009
Create Date: 2026-05-13 18:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260513_0010"
down_revision: str | None = "20260511_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fortigate_ingestion_statuses",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("integration_id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.String(length=255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_raw_event_count", sa.Integer(), nullable=False),
        sa.Column("last_created_count", sa.Integer(), nullable=False),
        sa.Column("last_event_ids", sa.JSON(), nullable=False),
        sa.Column("last_run_trigger", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "integration_id",
            name="uq_fortigate_ingestion_owner_integration",
        ),
    )
    op.create_index(
        op.f("ix_fortigate_ingestion_statuses_enabled"),
        "fortigate_ingestion_statuses",
        ["enabled"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fortigate_ingestion_statuses_integration_id"),
        "fortigate_ingestion_statuses",
        ["integration_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fortigate_ingestion_statuses_owner_user_id"),
        "fortigate_ingestion_statuses",
        ["owner_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fortigate_ingestion_statuses_status"),
        "fortigate_ingestion_statuses",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fortigate_ingestion_statuses_updated_at"),
        "fortigate_ingestion_statuses",
        ["updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_fortigate_ingestion_statuses_updated_at"),
        table_name="fortigate_ingestion_statuses",
    )
    op.drop_index(
        op.f("ix_fortigate_ingestion_statuses_status"),
        table_name="fortigate_ingestion_statuses",
    )
    op.drop_index(
        op.f("ix_fortigate_ingestion_statuses_owner_user_id"),
        table_name="fortigate_ingestion_statuses",
    )
    op.drop_index(
        op.f("ix_fortigate_ingestion_statuses_integration_id"),
        table_name="fortigate_ingestion_statuses",
    )
    op.drop_index(
        op.f("ix_fortigate_ingestion_statuses_enabled"),
        table_name="fortigate_ingestion_statuses",
    )
    op.drop_table("fortigate_ingestion_statuses")
