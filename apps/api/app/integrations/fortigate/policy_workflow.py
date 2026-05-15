from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.integrations.fortigate.policy_models import (
    FortiGatePolicyApplyRequest,
    FortiGatePolicyApplyResponse,
    FortiGatePolicyObjectChange,
    FortiGatePolicyPreflightRequest,
    FortiGatePolicyPreflightResponse,
    FortiGatePolicyReviewRequest,
    FortiGatePolicyReviewResponse,
)
from app.integrations.fortigate.policy_orchestrator import FortiGatePolicyOrchestrator
from app.integrations.fortigate.policy_requests import (
    create_policy_request,
    get_policy_request_for_user,
    mark_policy_request_applied,
)


def preflight_policy_for_user(
    *,
    integration_id: str,
    owner_user_id: str,
    service: Any,
    payload: FortiGatePolicyPreflightRequest,
) -> FortiGatePolicyPreflightResponse:
    client = service.get_policy_client(
        integration_id=integration_id,
        owner_user_id=owner_user_id,
    )
    return FortiGatePolicyOrchestrator(client, integration_id=integration_id).preflight(payload)


def create_policy_review_for_user(
    *,
    db: Session,
    integration_id: str,
    owner_user_id: str,
    service: Any,
    payload: FortiGatePolicyReviewRequest,
    now: datetime | None = None,
) -> FortiGatePolicyReviewResponse:
    preflight = preflight_policy_for_user(
        integration_id=integration_id,
        owner_user_id=owner_user_id,
        service=service,
        payload=payload,
    )
    expires_at = None
    if payload.duration_minutes:
        base_time = now or datetime.now(UTC)
        expires_at = base_time + timedelta(minutes=payload.duration_minutes)
    record = create_policy_request(
        db,
        owner_user_id=owner_user_id,
        integration_id=integration_id,
        request=payload,
        preflight=preflight,
        expires_at=expires_at,
    )
    return FortiGatePolicyReviewResponse(
        **preflight.model_dump(mode="json"),
        request_id=record.id,
        status="pending_review",
        expires_at=expires_at,
    )


def apply_policy_review_for_user(
    *,
    db: Session,
    integration_id: str,
    owner_user_id: str,
    service: Any,
    payload: FortiGatePolicyApplyRequest,
) -> FortiGatePolicyApplyResponse:
    record = get_policy_request_for_user(
        db,
        owner_user_id=owner_user_id,
        request_id=payload.request_id,
    )
    if record.integration_id != integration_id:
        raise HTTPException(status_code=404, detail="Policy request not found")
    if record.status != "pending_review":
        raise HTTPException(status_code=409, detail="Policy request is not pending review")
    if record.review_hash != payload.review_hash:
        raise HTTPException(status_code=409, detail="Policy review hash mismatch")

    client = service.get_policy_client(
        integration_id=integration_id,
        owner_user_id=owner_user_id,
    )
    changes = [
        FortiGatePolicyObjectChange.model_validate(change)
        for change in record.proposed_changes_json
    ]
    applied_changes = FortiGatePolicyOrchestrator(
        client,
        integration_id=integration_id,
    ).apply_changes(changes)
    mark_policy_request_applied(
        db,
        record=record,
        result={"appliedChanges": applied_changes},
    )
    return FortiGatePolicyApplyResponse(
        request_id=record.id,
        status="applied",
        applied_changes=applied_changes,
    )
