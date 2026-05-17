"""workspace template categories and curated presets

Revision ID: 20260517_0016
Revises: 20260517_0015
Create Date: 2026-05-17
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "20260517_0016"
down_revision: str | None = "20260517_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PRESET_OWNER_USER_ID = "system"
PRESETS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "app"
    / "workspaces"
    / "presets"
)


def _load_presets() -> list[dict]:
    if not PRESETS_DIR.exists():
        return []
    presets: list[dict] = []
    for path in sorted(PRESETS_DIR.glob("*.json")):
        with path.open("r", encoding="utf-8") as handle:
            presets.append(json.load(handle))
    return presets


def upgrade() -> None:
    op.add_column(
        "workspace_templates",
        sa.Column(
            "category",
            sa.String(length=32),
            nullable=False,
            server_default="community",
        ),
    )
    op.add_column(
        "workspace_templates",
        sa.Column(
            "is_curated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "workspace_templates",
        sa.Column("icon", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_workspace_templates_category",
        "workspace_templates",
        ["category"],
    )
    op.create_index(
        "ix_workspace_templates_is_curated",
        "workspace_templates",
        ["is_curated"],
    )

    now = datetime.now(UTC)
    templates_table = sa.table(
        "workspace_templates",
        sa.column("id", sa.String),
        sa.column("slug", sa.String),
        sa.column("title", sa.String),
        sa.column("description", sa.Text),
        sa.column("tags", sa.JSON),
        sa.column("manifest", sa.JSON),
        sa.column("published_by_user_id", sa.String),
        sa.column("published_by_email", sa.String),
        sa.column("install_count", sa.Integer),
        sa.column("is_visible", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("category", sa.String),
        sa.column("is_curated", sa.Boolean),
        sa.column("icon", sa.String),
    )

    rows = []
    for index, preset in enumerate(_load_presets()):
        slug = preset["slug"]
        rows.append(
            {
                "id": f"tpl_curated_{slug.replace('-', '_')}",
                "slug": slug,
                "title": preset["title"],
                "description": preset.get("description"),
                "tags": preset.get("tags", []),
                "manifest": preset["manifest"],
                "published_by_user_id": PRESET_OWNER_USER_ID,
                "published_by_email": None,
                "install_count": 0,
                "is_visible": True,
                "created_at": now,
                "updated_at": now,
                "category": preset.get("category", "community"),
                "is_curated": True,
                "icon": preset.get("icon"),
            }
        )
    if rows:
        op.bulk_insert(templates_table, rows)


def downgrade() -> None:
    op.execute(
        "DELETE FROM workspace_templates WHERE is_curated = true"
    )
    op.drop_index(
        "ix_workspace_templates_is_curated", table_name="workspace_templates"
    )
    op.drop_index(
        "ix_workspace_templates_category", table_name="workspace_templates"
    )
    op.drop_column("workspace_templates", "icon")
    op.drop_column("workspace_templates", "is_curated")
    op.drop_column("workspace_templates", "category")
