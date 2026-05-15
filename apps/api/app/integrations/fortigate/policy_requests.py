from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import FortiGatePolicyChangeRequestModel
from app.integrations.fortigate.policy_models import (
    FortiGatePolicyPreflightResponse,
    FortiGatePolicyReviewRequest,
    FortiGatePolicyReviewResponse,
)


def create_policy_request(
    db: Session,
    *,
    owner_user_id: str,
    integration_id: str,
    request: FortiGatePolicyReviewRequest,
    preflight: FortiGatePolicyReviewResponse | FortiGatePolicyPreflightResponse,
    expires_at: datetime | None,
    id_factory: Callable[[], str] | None = None,
) -> FortiGatePolicyChangeRequestModel:
    make_id = id_factory or (lambda: f"fgpcr_{secrets.token_urlsafe(18)}")
    record = FortiGatePolicyChangeRequestModel(
        id=make_id(),
        owner_user_id=owner_user_id,
        integration_id=integration_id,
        incident_id=request.incident_id,
        playbook_run_id=request.playbook_run_id,
        status="pending_review",
        intent_json=request.model_dump(mode="json"),
        preflight_summary_json=preflight.model_dump(mode="json", exclude={"changes"}),
        proposed_changes_json=[change.model_dump(mode="json") for change in preflight.changes],
        review_hash=preflight.review_hash,
        expires_at=expires_at,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_policy_request_for_user(
    db: Session,
    *,
    owner_user_id: str,
    request_id: str,
) -> FortiGatePolicyChangeRequestModel:
    record = db.get(FortiGatePolicyChangeRequestModel, request_id)
    if record is None or record.owner_user_id != owner_user_id:
        raise HTTPException(status_code=404, detail="Policy request not found")
    return record


def mark_policy_request_applied(
    db: Session,
    *,
    record: FortiGatePolicyChangeRequestModel,
    result: dict[str, Any],
) -> FortiGatePolicyChangeRequestModel:
    record.status = "applied"
    record.applied_result_json = result
    db.commit()
    db.refresh(record)
    return record
