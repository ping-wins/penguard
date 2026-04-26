from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AuthAuditEventModel


@dataclass(frozen=True)
class AuthAuditEvent:
    action: str
    outcome: str
    email: str | None = None
    user_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    details: dict[str, Any] | None = None
    created_at: datetime | None = None


class InMemoryAuthAuditStore:
    def __init__(self) -> None:
        self.events: list[AuthAuditEvent] = []

    def record(
        self,
        *,
        action: str,
        outcome: str,
        email: str | None = None,
        user_id: str | None = None,
        client_ip: str | None = None,
        user_agent: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.events.append(
            AuthAuditEvent(
                action=action,
                outcome=outcome,
                email=email,
                user_id=user_id,
                client_ip=client_ip,
                user_agent=user_agent,
                details=details,
                created_at=datetime.now(UTC),
            )
        )


class SqlAlchemyAuthAuditStore:
    def __init__(
        self,
        *,
        engine: Engine | None = None,
        session_factory: sessionmaker[Session] | None = None,
        database_url: str | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        if session_factory is not None:
            self.session_factory = session_factory
        else:
            if engine is None:
                if database_url is None:
                    raise ValueError("database_url, engine, or session_factory is required")
                engine = create_engine(database_url, pool_pre_ping=True)
            self.session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        self.id_factory = id_factory or (lambda: uuid4().hex)

    def record(
        self,
        *,
        action: str,
        outcome: str,
        email: str | None = None,
        user_id: str | None = None,
        client_ip: str | None = None,
        user_agent: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        model = AuthAuditEventModel(
            id=self.id_factory(),
            action=action,
            outcome=outcome,
            email=email,
            user_id=user_id,
            client_ip=client_ip,
            user_agent=user_agent,
            details=details or {},
        )
        with self.session_factory() as db:
            db.add(model)
            db.commit()
