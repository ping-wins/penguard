from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.addons.installed_store import (
    InstalledAddonRecord,
    delete_installed,
    get_installed,
    list_installed,
    upsert_installed,
)
from app.db.base import Base
from app.db import models  # noqa: F401 — ensures all models register on Base.metadata


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()


def _record() -> InstalledAddonRecord:
    return InstalledAddonRecord(
        id="demo-core",
        version="1.0.0",
        path="/app/data/addons/demo-core/1.0.0",
        tag="demo-core-v1.0.0",
        sha256="a" * 64,
        status="active",
        installed_at=datetime.now(UTC),
    )


def test_upsert_inserts_new_row(session):
    upsert_installed(session, _record())
    assert get_installed(session, "demo-core").version == "1.0.0"


def test_upsert_replaces_existing(session):
    upsert_installed(session, _record())
    second = _record()
    second.version = "1.1.0"
    second.path = "/app/data/addons/demo-core/1.1.0"
    second.tag = "demo-core-v1.1.0"
    upsert_installed(session, second)

    got = get_installed(session, "demo-core")
    assert got.version == "1.1.0"
    assert got.path.endswith("1.1.0")


def test_list_returns_all(session):
    upsert_installed(session, _record())
    second = _record()
    second.id = "other"
    upsert_installed(session, second)
    ids = {r.id for r in list_installed(session)}
    assert ids == {"demo-core", "other"}


def test_delete_removes_row(session):
    upsert_installed(session, _record())
    delete_installed(session, "demo-core")
    assert get_installed(session, "demo-core") is None
