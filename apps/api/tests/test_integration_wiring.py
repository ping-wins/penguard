from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.integrations.wiring import apply_wiring, get_soar_actions


class _Connector:
    def list_playbook_actions(self):
        return [{"id": "block_source_ip", "label": "Block", "paramsSchema": {}}]


def test_apply_wiring_records_soar_actions_when_capable() -> None:
    with _db_session() as db_session:
        result = apply_wiring(
            db_session,
            integration_id="int_fweb_1",
            provider_type="fortiweb",
            capabilities={"logSource": True, "playbookTarget": True, "managed": True},
            wire={"siem": False, "soar": True},
            connector=_Connector(),
            now=datetime.now(UTC),
        )
        actions = get_soar_actions(db_session, "int_fweb_1")
    assert result["soar"]["ok"] is True
    assert result["siem"] is None
    assert actions[0]["id"] == "block_source_ip"


def test_apply_wiring_soar_skipped_when_not_capable() -> None:
    with _db_session() as db_session:
        result = apply_wiring(
            db_session,
            integration_id="int_xdr_1",
            provider_type="xdr_rico",
            capabilities={"logSource": False, "playbookTarget": False, "managed": False},
            wire={"siem": True, "soar": True},
            connector=object(),
            now=datetime.now(UTC),
        )
    assert result["soar"]["ok"] is False
    assert "not a playbook target" in result["soar"]["detail"]


def _db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()
