from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from secrets import token_urlsafe
from typing import Any

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.token_cipher import TokenCipher
from app.db.models import AuthSessionModel


@dataclass(frozen=True)
class SessionRecord:
    user: dict[str, Any]
    tokens: dict[str, Any]
    expires_at: datetime | None = None


class InMemorySessionStore:
    def __init__(self, token_factory: Callable[[], str] | None = None) -> None:
        self.token_factory = token_factory or (lambda: token_urlsafe(32))
        self.sessions: dict[str, SessionRecord] = {}

    def create(
        self,
        *,
        user: dict[str, Any],
        tokens: dict[str, Any],
        expires_at: datetime | None = None,
    ) -> str:
        session_id = self.token_factory()
        self.sessions[session_id] = SessionRecord(user=user, tokens=tokens, expires_at=expires_at)
        return session_id

    def get(self, session_id: str | None) -> SessionRecord | None:
        if session_id is None:
            return None
        record = self.sessions.get(session_id)
        if record is None or _is_expired(record.expires_at):
            return None
        return record

    def delete(self, session_id: str | None) -> None:
        if session_id is not None:
            self.sessions.pop(session_id, None)


class SqlAlchemySessionStore:
    def __init__(
        self,
        *,
        engine: Engine | None = None,
        session_factory: sessionmaker[Session] | None = None,
        database_url: str | None = None,
        token_cipher: TokenCipher,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        if session_factory is not None:
            self.session_factory = session_factory
        else:
            if engine is None:
                if database_url is None:
                    raise ValueError("database_url, engine, or session_factory is required")
                engine = create_engine(database_url, pool_pre_ping=True)
            self.session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        self.token_cipher = token_cipher
        self.token_factory = token_factory or (lambda: token_urlsafe(32))

    def create(
        self,
        *,
        user: dict[str, Any],
        tokens: dict[str, Any],
        expires_at: datetime | None = None,
    ) -> str:
        session_id = self.token_factory()
        model = AuthSessionModel(
            id=session_id,
            user_id=str(user["id"]),
            email=str(user["email"]),
            display_name=str(user["displayName"]),
            roles=list(user.get("roles", [])),
            token_blob=self.token_cipher.encrypt(tokens),
            expires_at=expires_at,
        )
        with self.session_factory() as db:
            db.add(model)
            db.commit()
        return session_id

    def get(self, session_id: str | None) -> SessionRecord | None:
        if session_id is None:
            return None
        with self.session_factory() as db:
            model = db.get(AuthSessionModel, session_id)
            if model is None or model.revoked_at is not None or _is_expired(model.expires_at):
                return None
            return SessionRecord(
                user={
                    "id": model.user_id,
                    "email": model.email,
                    "displayName": model.display_name,
                    "roles": model.roles,
                },
                tokens=self.token_cipher.decrypt(model.token_blob),
                expires_at=model.expires_at,
            )

    def delete(self, session_id: str | None) -> None:
        if session_id is None:
            return
        with self.session_factory() as db:
            model = db.execute(
                select(AuthSessionModel).where(AuthSessionModel.id == session_id)
            ).scalar_one_or_none()
            if model is None or model.revoked_at is not None:
                return
            model.revoked_at = datetime.now(UTC)
            db.commit()


def _is_expired(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= datetime.now(UTC)
