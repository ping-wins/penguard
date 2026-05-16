"""create ai agent tool calls

Revision ID: 20260516_0013
Revises: 20260515_0012
Create Date: 2026-05-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260516_0013"
down_revision: str | None = "20260515_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_agent_tool_calls",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("backend", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("args_keys", sa.JSON(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_agent_tool_calls_session_id",
        "ai_agent_tool_calls",
        ["session_id"],
    )
    op.create_index(
        "ix_ai_agent_tool_calls_user_id",
        "ai_agent_tool_calls",
        ["user_id"],
    )
    op.create_index(
        "ix_ai_agent_tool_calls_tool_name",
        "ai_agent_tool_calls",
        ["tool_name"],
    )
    op.create_index(
        "ix_ai_agent_tool_calls_created_at",
        "ai_agent_tool_calls",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_agent_tool_calls_created_at", table_name="ai_agent_tool_calls")
    op.drop_index("ix_ai_agent_tool_calls_tool_name", table_name="ai_agent_tool_calls")
    op.drop_index("ix_ai_agent_tool_calls_user_id", table_name="ai_agent_tool_calls")
    op.drop_index("ix_ai_agent_tool_calls_session_id", table_name="ai_agent_tool_calls")
    op.drop_table("ai_agent_tool_calls")
