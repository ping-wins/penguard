"""update curated workspace templates

Revision ID: 20260519_0022
Revises: 20260518_0020
Create Date: 2026-05-19
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "20260519_0022"
down_revision: str | None = "20260518_0020"
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


def _template_id(slug: str) -> str:
    return f"tpl_curated_{slug.replace('-', '_')}"


def upgrade() -> None:
    bind = op.get_bind()
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

    for preset in _load_presets():
        slug = preset["slug"]
        values = {
            "title": preset["title"],
            "description": preset.get("description"),
            "tags": preset.get("tags", []),
            "manifest": preset["manifest"],
            "published_by_user_id": PRESET_OWNER_USER_ID,
            "published_by_email": None,
            "is_visible": True,
            "updated_at": now,
            "category": preset.get("category", "community"),
            "is_curated": True,
            "icon": preset.get("icon"),
        }
        existing = bind.execute(
            sa.select(templates_table.c.id).where(templates_table.c.slug == slug)
        ).first()
        if existing is None:
            bind.execute(
                templates_table.insert().values(
                    id=_template_id(slug),
                    slug=slug,
                    install_count=0,
                    created_at=now,
                    **values,
                )
            )
            continue
        bind.execute(
            templates_table.update()
            .where(templates_table.c.slug == slug)
            .values(**values)
        )


def downgrade() -> None:
    """Keep template content as-is.

    This migration refreshes curated seed data. Rolling back application code
    should not delete user-installed workspaces or hide curated templates.
    """
