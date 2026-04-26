from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.session_store import SqlAlchemySessionStore
from app.auth.token_cipher import TokenCipher
from app.db.base import Base
from app.db.models import AuthSessionModel


def test_sqlalchemy_session_store_encrypts_tokens_and_revokes_sessions():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    store = SqlAlchemySessionStore(
        engine=engine,
        token_cipher=TokenCipher.from_secret("test-secret"),
        token_factory=lambda: "session_01",
    )

    session_id = store.create(
        user={
            "id": "usr_01",
            "email": "analyst@example.com",
            "displayName": "SOC Analyst",
            "roles": ["analyst"],
        },
        tokens={
            "access_token": "server-side-access-token",
            "refresh_token": "server-side-refresh-token",
            "expires_in": 300,
        },
    )

    with Session(engine) as db:
        row = db.execute(select(AuthSessionModel)).scalar_one()

    assert session_id == "session_01"
    assert row.token_blob != ""
    assert "server-side-access-token" not in row.token_blob
    assert "server-side-refresh-token" not in row.token_blob

    record = store.get("session_01")
    assert record is not None
    assert record.user == {
        "id": "usr_01",
        "email": "analyst@example.com",
        "displayName": "SOC Analyst",
        "roles": ["analyst"],
    }
    assert record.tokens["access_token"] == "server-side-access-token"

    store.delete("session_01")

    assert store.get("session_01") is None


def test_sqlalchemy_session_store_rejects_expired_sessions():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    store = SqlAlchemySessionStore(
        engine=engine,
        token_cipher=TokenCipher.from_secret("test-secret"),
        token_factory=lambda: "session_expired",
    )

    session_id = store.create(
        user={
            "id": "usr_01",
            "email": "analyst@example.com",
            "displayName": "SOC Analyst",
            "roles": ["analyst"],
        },
        tokens={"access_token": "expired-access-token", "expires_in": 1},
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    assert session_id == "session_expired"
    assert store.get("session_expired") is None
