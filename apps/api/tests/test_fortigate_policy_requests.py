from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import models  # noqa: F401 - register SQLAlchemy models
from app.db.base import Base
from app.integrations.fortigate.policy_models import (
    FortiGatePolicyIntent,
    FortiGatePolicyPreflightRequest,
    FortiGatePolicyScope,
)
from app.integrations.fortigate.policy_orchestrator import FortiGatePolicyOrchestrator
from app.integrations.fortigate.policy_requests import (
    create_policy_request,
    get_policy_request_for_user,
    mark_policy_request_applied,
)


class FakePolicyClient:
    def get_policies(self) -> list[dict]:
        return [{"name": "FD_LAB_ALLOW_SCAN", "policyid": 10}]

    def get_address_objects(self) -> list[dict]:
        return []


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()


def _policy_request() -> FortiGatePolicyPreflightRequest:
    return FortiGatePolicyPreflightRequest(
        intent=FortiGatePolicyIntent.TEMPORARY_BLOCK,
        scope=FortiGatePolicyScope.SOURCE_DESTINATION,
        source_interface="port2",
        destination_interface="port3",
        source_ip="192.0.2.50",
        destination_ip="198.51.100.10",
        duration_minutes=30,
        incident_id="inc_123",
        playbook_run_id="run_123",
    )


def test_create_fetch_and_apply_fortigate_policy_request(session):
    request = _policy_request()
    preflight = FortiGatePolicyOrchestrator(
        FakePolicyClient(),
        integration_id="int_fgt_lab",
    ).preflight(request)
    expires_at = datetime.now(UTC) + timedelta(minutes=30)

    record = create_policy_request(
        session,
        owner_user_id="usr_owner",
        integration_id="int_fgt_lab",
        request=request,
        preflight=preflight,
        expires_at=expires_at,
        id_factory=lambda: "fgpcr_test",
    )

    assert record.id == "fgpcr_test"
    assert record.status == "pending_review"
    assert record.owner_user_id == "usr_owner"
    assert record.integration_id == "int_fgt_lab"
    assert record.incident_id == "inc_123"
    assert record.playbook_run_id == "run_123"
    assert record.intent_json["intent"] == "temporary_block"
    assert record.preflight_summary_json["proposed_policy_name"].startswith("FD_TMP_BLOCK_")
    assert record.proposed_changes_json[-1]["object_type"] == "firewall.policy"
    assert record.review_hash == preflight.review_hash

    assert get_policy_request_for_user(
        session,
        owner_user_id="usr_owner",
        request_id="fgpcr_test",
    ).id == "fgpcr_test"
    with pytest.raises(HTTPException) as exc_info:
        get_policy_request_for_user(
            session,
            owner_user_id="usr_other",
            request_id="fgpcr_test",
        )
    assert exc_info.value.status_code == 404

    applied = mark_policy_request_applied(
        session,
        record=record,
        result={"appliedChanges": [{"name": "FD_TMP_BLOCK_192_0_2_50"}]},
    )

    assert applied.status == "applied"
    assert applied.applied_result_json == {
        "appliedChanges": [{"name": "FD_TMP_BLOCK_192_0_2_50"}]
    }
