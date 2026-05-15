"""create fortigate policy change requests

Revision ID: 20260515_0012
Revises: 20260514_0011, 20260515_0011
Create Date: 2026-05-15 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260515_0012"
down_revision: tuple[str, str] = ("20260514_0011", "20260515_0011")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fortigate_policy_change_requests",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.String(length=255), nullable=False),
        sa.Column("integration_id", sa.String(length=64), nullable=False),
        sa.Column("incident_id", sa.String(length=64), nullable=True),
        sa.Column("playbook_run_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("intent_json", sa.JSON(), nullable=False),
        sa.Column("preflight_summary_json", sa.JSON(), nullable=False),
        sa.Column("proposed_changes_json", sa.JSON(), nullable=False),
        sa.Column("review_hash", sa.String(length=128), nullable=False),
        sa.Column("applied_result_json", sa.JSON(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_fortigate_policy_change_requests_integration_id"),
        "fortigate_policy_change_requests",
        ["integration_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fortigate_policy_change_requests_owner_user_id"),
        "fortigate_policy_change_requests",
        ["owner_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fortigate_policy_change_requests_incident_id"),
        "fortigate_policy_change_requests",
        ["incident_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fortigate_policy_change_requests_playbook_run_id"),
        "fortigate_policy_change_requests",
        ["playbook_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fortigate_policy_change_requests_status"),
        "fortigate_policy_change_requests",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_fortigate_policy_change_requests_status"),
        table_name="fortigate_policy_change_requests",
    )
    op.drop_index(
        op.f("ix_fortigate_policy_change_requests_playbook_run_id"),
        table_name="fortigate_policy_change_requests",
    )
    op.drop_index(
        op.f("ix_fortigate_policy_change_requests_incident_id"),
        table_name="fortigate_policy_change_requests",
    )
    op.drop_index(
        op.f("ix_fortigate_policy_change_requests_owner_user_id"),
        table_name="fortigate_policy_change_requests",
    )
    op.drop_index(
        op.f("ix_fortigate_policy_change_requests_integration_id"),
        table_name="fortigate_policy_change_requests",
    )
    op.drop_table("fortigate_policy_change_requests")
