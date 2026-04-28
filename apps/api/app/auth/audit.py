from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AuthAuditEventModel

REDACTED = "[REDACTED]"
SECRET_KEY_MARKERS = (
    "apikey",
    "secret",
    "token",
    "password",
)


@dataclass(frozen=True)
class AuthAuditEvent:
    action: str
    outcome: str
    id: str | None = None
    email: str | None = None
    user_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    details: dict[str, Any] | None = None
    created_at: datetime | None = None


def sanitize_audit_details(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, nested_value in value.items():
            if _is_secret_key(str(key)):
                sanitized[key] = REDACTED
            else:
                sanitized[key] = sanitize_audit_details(nested_value)
        return sanitized
    if isinstance(value, list):
        return [sanitize_audit_details(item) for item in value]
    return value


def _is_secret_key(key: str) -> bool:
    normalized = key.replace("_", "").replace("-", "").lower()
    return any(marker in normalized for marker in SECRET_KEY_MARKERS)


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
                id=f"audit_memory_{len(self.events) + 1}",
                email=email,
                user_id=user_id,
                client_ip=client_ip,
                user_agent=user_agent,
                details=sanitize_audit_details(details or {}),
                created_at=datetime.now(UTC),
            )
        )

    def list_events(
        self,
        *,
        limit: int = 50,
        user_id: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        events = [
            event for event in self.events if user_id is None or event.user_id == user_id
        ]
        events = sorted(
            events,
            key=lambda event: event.created_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )[:limit]
        return {"items": [_event_payload(event) for event in events]}


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
            details=sanitize_audit_details(details or {}),
        )
        with self.session_factory() as db:
            db.add(model)
            db.commit()

    def list_events(
        self,
        *,
        limit: int = 50,
        user_id: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        from sqlalchemy import select

        with self.session_factory() as db:
            statement = select(AuthAuditEventModel)
            if user_id is not None:
                statement = statement.where(AuthAuditEventModel.user_id == user_id)
            rows = db.execute(
                statement.order_by(AuthAuditEventModel.created_at.desc()).limit(limit)
            ).scalars()
            return {
                "items": [
                    _event_payload(
                        AuthAuditEvent(
                            id=row.id,
                            action=row.action,
                            outcome=row.outcome,
                            email=row.email,
                            user_id=row.user_id,
                            client_ip=row.client_ip,
                            user_agent=row.user_agent,
                            details=row.details,
                            created_at=row.created_at,
                        )
                    )
                    for row in rows
                ]
            }


def _event_payload(event: AuthAuditEvent) -> dict[str, Any]:
    created_at = event.created_at
    if created_at is not None and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return {
        "id": event.id,
        "actor": {"id": event.user_id, "email": event.email},
        "action": event.action,
        "outcome": event.outcome,
        "ipAddress": event.client_ip,
        "userAgent": event.user_agent,
        "details": sanitize_audit_details(event.details or {}),
        "createdAt": (
            created_at.isoformat(timespec="milliseconds").replace("+00:00", "Z")
            if created_at
            else None
        ),
    }
