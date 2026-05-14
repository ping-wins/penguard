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
    delete,
    func,
    select,
    update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

DEFAULT_DATABASE_URL = "sqlite+pysqlite:///:memory:"

metadata = MetaData()

enrollments_table = Table(
    "xdr_rico_enrollments",
    metadata,
    Column("row_id", Integer, primary_key=True, autoincrement=True),
    Column("id", String(64), nullable=False, unique=True, index=True),
    Column("token_hash", String(128), nullable=False, unique=True, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("payload", JSON, nullable=False),
)

endpoints_table = Table(
    "xdr_rico_endpoints",
    metadata,
    Column("id", String(128), primary_key=True),
    Column("hostname", String(255), nullable=True, index=True),
    Column("current_user", String(255), nullable=True, index=True),
    Column("health", String(64), nullable=False, index=True),
    Column("last_seen_at", DateTime(timezone=True), nullable=True, index=True),
    Column("payload", JSON, nullable=False),
)

timeline_table = Table(
    "xdr_rico_timeline",
    metadata,
    # Row id keeps newest-first timeline ordering stable for deterministic test
    # fixtures that can share identical timestamps.
    Column("row_id", Integer, primary_key=True, autoincrement=True),
    Column("id", String(128), nullable=False, unique=True, index=True),
    Column("endpoint_id", String(128), nullable=False, index=True),
    Column("event_type", String(128), nullable=False, index=True),
    Column("occurred_at", DateTime(timezone=True), nullable=False, index=True),
    Column("payload", JSON, nullable=False),
)


class XdrStore:
    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.getenv("XDR_RICO_DATABASE_URL", DEFAULT_DATABASE_URL)
        self.engine = _create_engine(self.database_url)
        metadata.create_all(self.engine)

    @property
    def enrollments(self) -> dict[str, dict[str, Any]]:
        with self.engine.begin() as connection:
            rows = connection.execute(select(enrollments_table.c.id, enrollments_table.c.payload))
        return {row.id: row.payload for row in rows}

    @property
    def endpoints(self) -> dict[str, dict[str, Any]]:
        with self.engine.begin() as connection:
            rows = connection.execute(select(endpoints_table.c.id, endpoints_table.c.payload))
        return {row.id: row.payload for row in rows}

    @property
    def timeline(self) -> dict[str, list[dict[str, Any]]]:
        statement = select(timeline_table.c.endpoint_id, timeline_table.c.payload).order_by(
            timeline_table.c.occurred_at.desc(),
            timeline_table.c.row_id.desc(),
        )
        grouped: dict[str, list[dict[str, Any]]] = {}
        with self.engine.begin() as connection:
            for row in connection.execute(statement):
                grouped.setdefault(row.endpoint_id, []).append(row.payload)
        return grouped

    def reset(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(delete(timeline_table))
            connection.execute(delete(endpoints_table))
            connection.execute(delete(enrollments_table))

    def add_enrollment(
        self,
        payload: dict[str, Any],
        *,
        token_hash: str,
        created_at: datetime,
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                enrollments_table.insert().values(
                    id=payload["id"],
                    token_hash=token_hash,
                    created_at=created_at,
                    payload=payload,
                )
            )

    def has_enrollment_token_hash(self, hashed_token: str) -> bool:
        statement = select(enrollments_table.c.id).where(
            enrollments_table.c.token_hash == hashed_token
        )
        with self.engine.begin() as connection:
            return connection.execute(statement).first() is not None

    def get_enrollment_by_token_hash(self, hashed_token: str) -> dict[str, Any] | None:
        statement = select(enrollments_table.c.payload).where(
            enrollments_table.c.token_hash == hashed_token
        )
        with self.engine.begin() as connection:
            row = connection.execute(statement).first()
        if row is None:
            return None
        return row.payload

    def claim_enrollment_endpoint(
        self,
        enrollment_id: str,
        endpoint_id: str,
    ) -> dict[str, Any] | None:
        statement = select(enrollments_table.c.payload).where(
            enrollments_table.c.id == enrollment_id
        )
        with self.engine.begin() as connection:
            row = connection.execute(statement).first()
            if row is None:
                return None
            payload = {**row.payload, "claimedEndpointId": endpoint_id}
            connection.execute(
                update(enrollments_table)
                .where(enrollments_table.c.id == enrollment_id)
                .values(payload=payload)
            )
        return payload

    def upsert_endpoint(
        self,
        payload: dict[str, Any],
        *,
        hostname: str | None,
        current_user: str | None,
        health: str,
        last_seen_at: datetime | None,
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(delete(endpoints_table).where(endpoints_table.c.id == payload["id"]))
            connection.execute(
                endpoints_table.insert().values(
                    id=payload["id"],
                    hostname=hostname,
                    current_user=current_user,
                    health=health,
                    last_seen_at=last_seen_at,
                    payload=payload,
                )
            )

    def list_endpoints(self) -> list[dict[str, Any]]:
        statement = select(endpoints_table.c.payload).order_by(
            endpoints_table.c.last_seen_at.desc().nullslast(),
            endpoints_table.c.id.asc(),
        )
        with self.engine.begin() as connection:
            return [row.payload for row in connection.execute(statement)]

    def get_endpoint(self, endpoint_id: str) -> dict[str, Any] | None:
        statement = select(endpoints_table.c.payload).where(endpoints_table.c.id == endpoint_id)
        with self.engine.begin() as connection:
            row = connection.execute(statement).first()
        if row is None:
            return None
        return row.payload

    def delete_endpoint(self, endpoint_id: str) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                delete(timeline_table).where(timeline_table.c.endpoint_id == endpoint_id)
            )
            connection.execute(delete(endpoints_table).where(endpoints_table.c.id == endpoint_id))

    def add_timeline_item(
        self,
        payload: dict[str, Any],
        *,
        endpoint_id: str,
        event_type: str,
        occurred_at: datetime,
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                timeline_table.insert().values(
                    id=payload["id"],
                    endpoint_id=endpoint_id,
                    event_type=event_type,
                    occurred_at=occurred_at,
                    payload=payload,
                )
            )

    def list_timeline(self, endpoint_id: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        statement = (
            select(timeline_table.c.payload)
            .where(timeline_table.c.endpoint_id == endpoint_id)
            .order_by(timeline_table.c.occurred_at.desc(), timeline_table.c.row_id.desc())
        )
        if limit is not None:
            statement = statement.limit(limit)
        with self.engine.begin() as connection:
            return [row.payload for row in connection.execute(statement)]

    def count_endpoints(self) -> int:
        statement = select(func.count()).select_from(endpoints_table)
        with self.engine.begin() as connection:
            return int(connection.execute(statement).scalar_one())

    def count_timeline_items(self, endpoint_id: str) -> int:
        statement = select(func.count()).select_from(timeline_table).where(
            timeline_table.c.endpoint_id == endpoint_id
        )
        with self.engine.begin() as connection:
            return int(connection.execute(statement).scalar_one())


def _create_engine(database_url: str) -> Engine:
    kwargs: dict[str, Any] = {"future": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if database_url.endswith(":memory:"):
            kwargs["poolclass"] = StaticPool
    return create_engine(database_url, **kwargs)
