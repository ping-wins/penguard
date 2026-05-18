"""Agent session store.

Stores message history + tool-call trace per session. In-memory now; the
shape matches what a Redis-backed implementation would look like, so we
can swap it out later without touching callers.
"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class AgentMessage:
    role: str  # user | assistant | tool
    content: str = ""
    tool_call_id: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    tool_result: Any = None
    tool_calls: list[dict[str, Any]] | None = None
    created_at: float = field(default_factory=time.time)


@dataclass
class AgentSession:
    id: str
    user_id: str
    backend: str = "scripted"
    model: str = ""
    role_id: str = "chat"
    locale: str = "pt-BR"
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    history: list[AgentMessage] = field(default_factory=list)
    used_tools: list[str] = field(default_factory=list)
    tokens_in_total: int = 0
    tokens_out_total: int = 0
    pending_approvals: dict[str, asyncio.Future] = field(default_factory=dict)
    turn_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def touch(self) -> None:
        self.last_used_at = time.time()


class SessionStore:
    """In-memory session store with TTL.

    Thread-safe via a coarse lock — agent sessions are low-frequency
    (analyst-driven) so lock contention is not a concern.
    """

    def __init__(self, *, ttl_seconds: int = 3600, max_sessions_per_user: int = 10) -> None:
        self._ttl = ttl_seconds
        self._max_per_user = max_sessions_per_user
        self._sessions: dict[str, AgentSession] = {}
        self._lock = threading.Lock()

    def create(
        self,
        *,
        user_id: str,
        backend: str = "scripted",
        model: str = "",
        role_id: str = "chat",
        locale: str = "pt-BR",
    ) -> AgentSession:
        session = AgentSession(
            id=uuid4().hex,
            user_id=user_id,
            backend=backend,
            model=model,
            role_id=role_id,
            locale=locale,
        )
        with self._lock:
            self._evict_expired_locked()
            self._enforce_user_quota_locked(user_id)
            self._sessions[session.id] = session
        return session

    def get(self, session_id: str, *, user_id: str) -> AgentSession | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if session.user_id != user_id:
                return None
            if self._is_expired_locked(session):
                self._sessions.pop(session_id, None)
                return None
            session.touch()
            return session

    def delete(self, session_id: str, *, user_id: str) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.user_id != user_id:
                return False
            self._sessions.pop(session_id, None)
            return True

    def list_for_user(self, user_id: str) -> list[AgentSession]:
        with self._lock:
            self._evict_expired_locked()
            return [s for s in self._sessions.values() if s.user_id == user_id]

    def append_message(self, session: AgentSession, message: AgentMessage) -> None:
        with self._lock:
            session.history.append(message)
            session.touch()

    def reset_for_tests(self) -> None:
        with self._lock:
            self._sessions.clear()

    def _is_expired_locked(self, session: AgentSession) -> bool:
        return (time.time() - session.last_used_at) > self._ttl

    def _evict_expired_locked(self) -> None:
        stale = [sid for sid, s in self._sessions.items() if self._is_expired_locked(s)]
        for sid in stale:
            self._sessions.pop(sid, None)

    def _enforce_user_quota_locked(self, user_id: str) -> None:
        user_sessions = sorted(
            (s for s in self._sessions.values() if s.user_id == user_id),
            key=lambda s: s.last_used_at,
        )
        # Reserve one slot for the new session by trimming down to max-1.
        while len(user_sessions) >= self._max_per_user:
            oldest = user_sessions.pop(0)
            self._sessions.pop(oldest.id, None)


_DEFAULT_STORE = SessionStore()


def get_session_store() -> SessionStore:
    return _DEFAULT_STORE
