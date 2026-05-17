from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.integrations.wiring import get_wiring, set_wiring


def test_set_then_get_wiring() -> None:
    with _db_session() as db_session:
        set_wiring(
            db_session,
            "int_fweb_x",
            siem=True,
            soar=False,
            now=datetime.now(UTC),
        )
        state = get_wiring(db_session, "int_fweb_x")
    assert state == {"siem": True, "soar": False}


def test_get_wiring_defaults_false_when_absent() -> None:
    with _db_session() as db_session:
        state = get_wiring(db_session, "int_missing")
    assert state == {"siem": False, "soar": False}


def _db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()
