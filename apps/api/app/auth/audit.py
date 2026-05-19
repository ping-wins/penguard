import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AuthAuditEventModel

REDACTED = "[REDACTED]"
logger = logging.getLogger(__name__)
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
        created_at: datetime | None = None,
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
                created_at=created_at or datetime.now(UTC),
            )
        )

    def list_events(
        self,
        *,
        limit: int = 50,
        user_id: str | None = None,
        actor_user_id: str | None = None,
        action: str | None = None,
        outcome: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        effective_user_id = actor_user_id if actor_user_id is not None else user_id
        events = [
            event
            for event in self.events
            if (effective_user_id is None or event.user_id == effective_user_id)
            and (action is None or event.action == action)
            and (outcome is None or event.outcome == outcome)
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
        created_at: datetime | None = None,
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
            created_at=created_at or datetime.now(UTC),
        )
        with self.session_factory() as db:
            db.add(model)
            db.commit()

    def list_events(
        self,
        *,
        limit: int = 50,
        user_id: str | None = None,
        actor_user_id: str | None = None,
        action: str | None = None,
        outcome: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        from sqlalchemy import select

        with self.session_factory() as db:
            statement = select(AuthAuditEventModel)
            effective_user_id = actor_user_id if actor_user_id is not None else user_id
            if effective_user_id is not None:
                statement = statement.where(AuthAuditEventModel.user_id == effective_user_id)
            if action is not None:
                statement = statement.where(AuthAuditEventModel.action == action)
            if outcome is not None:
                statement = statement.where(AuthAuditEventModel.outcome == outcome)
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


class ForwardingAuthAuditStore:
    def __init__(
        self,
        *,
        primary: InMemoryAuthAuditStore | SqlAlchemyAuthAuditStore,
        forwarder: "AuditSiemForwarder",
    ) -> None:
        self.primary = primary
        self.forwarder = forwarder

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
        created_at = datetime.now(UTC)
        sanitized_details = sanitize_audit_details(details or {})
        self.primary.record(
            action=action,
            outcome=outcome,
            email=email,
            user_id=user_id,
            client_ip=client_ip,
            user_agent=user_agent,
            details=sanitized_details,
            created_at=created_at,
        )
        try:
            self.forwarder.forward(
                AuthAuditEvent(
                    action=action,
                    outcome=outcome,
                    email=email,
                    user_id=user_id,
                    client_ip=client_ip,
                    user_agent=user_agent,
                    details=sanitized_details,
                    created_at=created_at,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "audit_siem_forward_failed action=%s outcome=%s error=%s",
                action,
                outcome,
                exc,
            )

    def list_events(
        self,
        *,
        limit: int = 50,
        user_id: str | None = None,
        actor_user_id: str | None = None,
        action: str | None = None,
        outcome: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        return self.primary.list_events(
            limit=limit,
            user_id=user_id,
            actor_user_id=actor_user_id,
            action=action,
            outcome=outcome,
        )


class AuditSiemForwarder:
    def __init__(
        self,
        *,
        siem_client: Any,
        realtime_publisher: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.siem_client = siem_client
        self.realtime_publisher = realtime_publisher

    def forward(self, event: AuthAuditEvent) -> None:
        payload = audit_event_to_siem_event(event)
        created = self.siem_client.request("POST", "/events/ingest", json=payload)
        if self.realtime_publisher is None or not event.user_id:
            return
        created_event = created.get("event") if isinstance(created.get("event"), dict) else created
        ticket = created.get("incident") if isinstance(created.get("incident"), dict) else None
        self.realtime_publisher(
            {
                "type": "audit.siem.event",
                "ownerUserId": event.user_id,
                "eventId": created_event.get("id") if isinstance(created_event, dict) else None,
                "receivedAt": _event_time(event),
                "ticket": ticket,
            }
        )


def audit_event_to_siem_event(event: AuthAuditEvent) -> dict[str, Any]:
    entities: dict[str, Any] = {}
    if event.user_id:
        entities["actorUserId"] = event.user_id
    if event.client_ip:
        entities["sourceIp"] = event.client_ip
    if event.email:
        entities["user"] = event.email

    attributes: dict[str, Any] = {
        "originKind": "penguard.audit",
        "action": event.action,
        "outcome": event.outcome,
        "details": sanitize_audit_details(event.details or {}),
        "count": 1,
    }
    if event.user_agent:
        attributes["userAgent"] = event.user_agent

    return {
        "source": "penguard.audit",
        "eventType": _audit_siem_event_type(event),
        "severity": _audit_siem_severity(event),
        "occurredAt": _event_time(event),
        "entities": entities,
        "attributes": attributes,
    }


def _audit_siem_event_type(event: AuthAuditEvent) -> str:
    if event.action in {"login", "sso_kerberos"} and event.outcome != "success":
        return "auth.failed_login"
    if event.action == "login":
        return "auth.login"
    if event.action == "logout":
        return "auth.logout"
    return "platform.audit_action"


def _audit_siem_severity(event: AuthAuditEvent) -> str:
    if event.outcome != "success":
        return "medium"
    if event.action in {
        "integration.fortigate.log_forwarding_applied",
        "soc.playbook_run.approved",
        "soc.ticket.contained",
        "soc.incidents.reset",
    }:
        return "medium"
    return "low"


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


def _event_time(event: AuthAuditEvent) -> str:
    created_at = event.created_at or datetime.now(UTC)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return created_at.isoformat(timespec="milliseconds").replace("+00:00", "Z")
