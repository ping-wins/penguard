from collections.abc import Callable
from dataclasses import dataclass
from secrets import token_urlsafe
from typing import Any


@dataclass(frozen=True)
class SessionRecord:
    user: dict[str, Any]
    tokens: dict[str, Any]


class InMemorySessionStore:
    def __init__(self, token_factory: Callable[[], str] | None = None) -> None:
        self.token_factory = token_factory or (lambda: token_urlsafe(32))
        self.sessions: dict[str, SessionRecord] = {}

    def create(self, *, user: dict[str, Any], tokens: dict[str, Any]) -> str:
        session_id = self.token_factory()
        self.sessions[session_id] = SessionRecord(user=user, tokens=tokens)
        return session_id

    def get(self, session_id: str | None) -> SessionRecord | None:
        if session_id is None:
            return None
        return self.sessions.get(session_id)

    def delete(self, session_id: str | None) -> None:
        if session_id is not None:
            self.sessions.pop(session_id, None)
