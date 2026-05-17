"""create fortiweb provider tables

Revision ID: 20260517_0015
Revises: 20260516_0014
Create Date: 2026-05-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260517_0015"
down_revision: str | None = "20260516_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fortiweb_integrations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("host", sa.String(length=2048), nullable=False),
        sa.Column("verify_tls", sa.Boolean(), nullable=False),
        sa.Column("api_key_blob", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("target_server_policy", sa.String(length=255), nullable=False),
        sa.Column("managed_ip_list_policy", sa.String(length=255), nullable=False),
        sa.Column("device_identifiers", sa.JSON(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_fortiweb_integrations_owner_user_id"),
        "fortiweb_integrations",
        ["owner_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fortiweb_integrations_status"),
        "fortiweb_integrations",
        ["status"],
        unique=False,
    )

    op.create_table(
        "fortiweb_health_checks",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("integration_id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.String(length=255), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("device", sa.JSON(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_fortiweb_health_checks_checked_at"),
        "fortiweb_health_checks",
        ["checked_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fortiweb_health_checks_integration_id"),
        "fortiweb_health_checks",
        ["integration_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fortiweb_health_checks_owner_user_id"),
        "fortiweb_health_checks",
        ["owner_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fortiweb_health_checks_status"),
        "fortiweb_health_checks",
        ["status"],
        unique=False,
    )

    op.create_table(
        "fortiweb_block_requests",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.String(length=255), nullable=False),
        sa.Column("integration_id", sa.String(length=64), nullable=False),
        sa.Column("source_ip", sa.String(length=64), nullable=False),
        sa.Column("incident_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("intent_json", sa.JSON(), nullable=False),
        sa.Column("preflight_summary_json", sa.JSON(), nullable=False),
        sa.Column("proposed_changes_json", sa.JSON(), nullable=False),
        sa.Column("review_hash", sa.String(length=128), nullable=False),
        sa.Column("applied_result_json", sa.JSON(), nullable=True),
        sa.Column("removed_result_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_fortiweb_block_requests_incident_id"),
        "fortiweb_block_requests",
        ["incident_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fortiweb_block_requests_integration_id"),
        "fortiweb_block_requests",
        ["integration_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fortiweb_block_requests_owner_user_id"),
        "fortiweb_block_requests",
        ["owner_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fortiweb_block_requests_source_ip"),
        "fortiweb_block_requests",
        ["source_ip"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fortiweb_block_requests_status"),
        "fortiweb_block_requests",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_fortiweb_block_requests_status"), table_name="fortiweb_block_requests")
    op.drop_index(
        op.f("ix_fortiweb_block_requests_source_ip"),
        table_name="fortiweb_block_requests",
    )
    op.drop_index(
        op.f("ix_fortiweb_block_requests_owner_user_id"),
        table_name="fortiweb_block_requests",
    )
    op.drop_index(
        op.f("ix_fortiweb_block_requests_integration_id"),
        table_name="fortiweb_block_requests",
    )
    op.drop_index(
        op.f("ix_fortiweb_block_requests_incident_id"),
        table_name="fortiweb_block_requests",
    )
    op.drop_table("fortiweb_block_requests")

    op.drop_index(op.f("ix_fortiweb_health_checks_status"), table_name="fortiweb_health_checks")
    op.drop_index(
        op.f("ix_fortiweb_health_checks_owner_user_id"),
        table_name="fortiweb_health_checks",
    )
    op.drop_index(
        op.f("ix_fortiweb_health_checks_integration_id"),
        table_name="fortiweb_health_checks",
    )
    op.drop_index(
        op.f("ix_fortiweb_health_checks_checked_at"),
        table_name="fortiweb_health_checks",
    )
    op.drop_table("fortiweb_health_checks")

    op.drop_index(op.f("ix_fortiweb_integrations_status"), table_name="fortiweb_integrations")
    op.drop_index(
        op.f("ix_fortiweb_integrations_owner_user_id"),
        table_name="fortiweb_integrations",
    )
    op.drop_table("fortiweb_integrations")
