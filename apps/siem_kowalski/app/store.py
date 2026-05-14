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

events_table = Table(
    "siem_kowalski_events",
    metadata,
    # Keep a separate row id so list ordering follows ingestion order even when
    # event timestamps are identical in deterministic fixtures.
    Column("row_id", Integer, primary_key=True, autoincrement=True),
    Column("id", String(64), nullable=False, unique=True, index=True),
    Column("event_type", String(128), nullable=False, index=True),
    Column("severity", String(64), nullable=False, index=True),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("payload", JSON, nullable=False),
)

incidents_table = Table(
    "siem_kowalski_incidents",
    metadata,
    Column("row_id", Integer, primary_key=True, autoincrement=True),
    Column("id", String(64), nullable=False, unique=True, index=True),
    Column("rule_id", String(128), nullable=True, index=True),
    Column("severity", String(64), nullable=False, index=True),
    Column("status", String(64), nullable=False, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("payload", JSON, nullable=False),
)


class SiemStore:
    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.getenv(
            "SIEM_KOWALSKI_DATABASE_URL",
            DEFAULT_DATABASE_URL,
        )
        self.engine = _create_engine(self.database_url)
        metadata.create_all(self.engine)

    def add_event(
        self,
        payload: dict[str, Any],
        *,
        event_type: str,
        severity: str,
        occurred_at: datetime,
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                events_table.insert().values(
                    id=payload["id"],
                    event_type=event_type,
                    severity=severity,
                    occurred_at=occurred_at,
                    payload=payload,
                )
            )

    def list_events(
        self,
        *,
        limit: int | None = None,
        event_type: str | None = None,
    ) -> list[dict[str, Any]]:
        statement = select(events_table.c.payload).order_by(events_table.c.row_id.desc())
        if event_type is not None:
            statement = statement.where(events_table.c.event_type == event_type)
        if limit is not None:
            statement = statement.limit(limit)
        with self.engine.begin() as connection:
            return [row.payload for row in connection.execute(statement)]

    def count_events(self) -> int:
        statement = select(func.count()).select_from(events_table)
        with self.engine.begin() as connection:
            return int(connection.execute(statement).scalar_one())

    def add_incident(
        self,
        payload: dict[str, Any],
        *,
        rule_id: str | None,
        severity: str,
        status: str,
        created_at: datetime,
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                incidents_table.insert().values(
                    id=payload["id"],
                    rule_id=rule_id,
                    severity=severity,
                    status=status,
                    created_at=created_at,
                    payload=payload,
                )
            )

    def list_incidents(
        self,
        *,
        status: str | None = None,
        severity: str | None = None,
    ) -> list[dict[str, Any]]:
        statement = select(incidents_table.c.payload).order_by(incidents_table.c.row_id.desc())
        if status is not None:
            statement = statement.where(incidents_table.c.status == status)
        if severity is not None:
            statement = statement.where(incidents_table.c.severity == severity)
        with self.engine.begin() as connection:
            return [row.payload for row in connection.execute(statement)]

    def count_incidents(self) -> int:
        statement = select(func.count()).select_from(incidents_table)
        with self.engine.begin() as connection:
            return int(connection.execute(statement).scalar_one())

    def get_incident(self, incident_id: str) -> dict[str, Any] | None:
        statement = select(incidents_table.c.payload).where(incidents_table.c.id == incident_id)
        with self.engine.begin() as connection:
            row = connection.execute(statement).first()
        if row is None:
            return None
        return row.payload

    def update_incident(
        self,
        payload: dict[str, Any],
        *,
        severity: str,
        status: str,
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                incidents_table.update()
                .where(incidents_table.c.id == payload["id"])
                .values(
                    severity=severity,
                    status=status,
                    payload=payload,
                )
            )


    def reset(self) -> dict[str, int]:
        with self.engine.begin() as connection:
            event_count = int(connection.execute(select(func.count()).select_from(events_table)).scalar_one())
            incident_count = int(connection.execute(select(func.count()).select_from(incidents_table)).scalar_one())
            connection.execute(incidents_table.delete())
            connection.execute(events_table.delete())
        return {"events": event_count, "incidents": incident_count}


def _create_engine(database_url: str) -> Engine:
    kwargs: dict[str, Any] = {"future": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if database_url.endswith(":memory:"):
            kwargs["poolclass"] = StaticPool
    return create_engine(database_url, **kwargs)
