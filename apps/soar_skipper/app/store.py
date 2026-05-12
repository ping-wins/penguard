"""SQL-backed persistence for soar_skipper.

Mirrors `apps/siem_kowalski/app/store.py`: SQLite in-memory by default so the
unit tests have no extra setup, real Postgres in production via the
`SOAR_SKIPPER_DATABASE_URL` env var. Before this module existed the service
kept playbooks and runs in process-level dicts, which meant a
`docker compose restart soar-skipper` wiped every custom playbook and
every dry-run history — unacceptable for an audit trail.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    func,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

DEFAULT_DATABASE_URL = "sqlite+pysqlite:///:memory:"

metadata = MetaData()

playbooks_table = Table(
    "soar_skipper_playbooks",
    metadata,
    Column("row_id", Integer, primary_key=True, autoincrement=True),
    Column("id", String(64), nullable=False, unique=True, index=True),
    Column("payload", JSON, nullable=False),
)

playbook_runs_table = Table(
    "soar_skipper_playbook_runs",
    metadata,
    Column("row_id", Integer, primary_key=True, autoincrement=True),
    Column("id", String(128), nullable=False, unique=True, index=True),
    Column("incident_id", String(64), nullable=False, index=True),
    Column("playbook_id", String(64), nullable=False, index=True),
    Column("status", String(32), nullable=False, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("payload", JSON, nullable=False),
)


class SoarStore:
    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.getenv(
            "SOAR_SKIPPER_DATABASE_URL",
            DEFAULT_DATABASE_URL,
        )
        self.engine = _create_engine(self.database_url)
        metadata.create_all(self.engine)

    # ------------------------------------------------------------------ playbooks

    def get_playbook(self, playbook_id: str) -> dict[str, Any] | None:
        statement = select(playbooks_table.c.payload).where(
            playbooks_table.c.id == playbook_id
        )
        with self.engine.begin() as connection:
            row = connection.execute(statement).first()
        return row.payload if row is not None else None

    def list_playbooks(self) -> list[dict[str, Any]]:
        statement = select(playbooks_table.c.payload).order_by(playbooks_table.c.row_id)
        with self.engine.begin() as connection:
            return [row.payload for row in connection.execute(statement)]

    def save_playbook(self, playbook_id: str, payload: dict[str, Any]) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                playbooks_table.insert().values(id=playbook_id, payload=payload)
            )

    def update_playbook(self, playbook_id: str, payload: dict[str, Any]) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                playbooks_table.update()
                .where(playbooks_table.c.id == playbook_id)
                .values(payload=payload)
            )

    def count_playbooks(self) -> int:
        statement = select(func.count()).select_from(playbooks_table)
        with self.engine.begin() as connection:
            return int(connection.execute(statement).scalar_one())

    # ----------------------------------------------------------------- run history

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        statement = select(playbook_runs_table.c.payload).where(
            playbook_runs_table.c.id == run_id
        )
        with self.engine.begin() as connection:
            row = connection.execute(statement).first()
        return row.payload if row is not None else None

    def list_runs(self, *, status: str | None = None) -> list[dict[str, Any]]:
        statement = select(playbook_runs_table.c.payload).order_by(
            playbook_runs_table.c.row_id.desc()
        )
        if status is not None:
            statement = statement.where(playbook_runs_table.c.status == status)
        with self.engine.begin() as connection:
            return [row.payload for row in connection.execute(statement)]

    def save_run(
        self,
        payload: dict[str, Any],
        *,
        incident_id: str,
        playbook_id: str,
        status: str,
        created_at: datetime,
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                playbook_runs_table.insert().values(
                    id=payload["id"],
                    incident_id=incident_id,
                    playbook_id=playbook_id,
                    status=status,
                    created_at=created_at,
                    payload=payload,
                )
            )

    def update_run(self, payload: dict[str, Any], *, status: str) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                playbook_runs_table.update()
                .where(playbook_runs_table.c.id == payload["id"])
                .values(status=status, payload=payload)
            )


def _create_engine(database_url: str) -> Engine:
    kwargs: dict[str, Any] = {"future": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if database_url.endswith(":memory:"):
            kwargs["poolclass"] = StaticPool
    return create_engine(database_url, **kwargs)
