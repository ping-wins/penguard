from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.auth.csrf_dependency import require_csrf
from app.auth.dependencies import get_current_api_user
from app.auth.permissions import require_permission
from app.policies.models import PolicyReviewApplyRequest, PolicyReviewCreateRequest
from app.policies.service import PolicyService

router = APIRouter(tags=["policies"])


def get_policy_service() -> PolicyService:
    return PolicyService(adapters=[])


def _owner_user_id(current_user: dict) -> str:
    return str(current_user.get("id") or current_user.get("user_id"))


@router.get("/policies/providers")
def list_policy_providers(
    service: Annotated[PolicyService, Depends(get_policy_service)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    return service.list_providers(owner_user_id=_owner_user_id(current_user))


@router.get("/policies")
def list_policies(
    service: Annotated[PolicyService, Depends(get_policy_service)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    provider_type: Annotated[str | None, Query(alias="providerType")] = None,
    integration_id: Annotated[str | None, Query(alias="integrationId")] = None,
    kind: str | None = None,
    policy_status: Annotated[str | None, Query(alias="status")] = None,
    ownership: str | None = None,
    q: str | None = None,
) -> dict:
    return service.list_policies(
        owner_user_id=_owner_user_id(current_user),
        filters={
            "providerType": provider_type,
            "integrationId": integration_id,
            "kind": kind,
            "status": policy_status,
            "ownership": ownership,
            "q": q,
        },
    )


@router.post("/policies/reviews", status_code=status.HTTP_201_CREATED)
def create_policy_review(
    _request: Request,
    service: Annotated[PolicyService, Depends(get_policy_service)],
    current_user: Annotated[dict, Depends(require_permission("policies.manage"))],
    _csrf: Annotated[None, Depends(require_csrf)],
    payload: PolicyReviewCreateRequest,
) -> dict:
    return service.create_review(owner_user_id=_owner_user_id(current_user), payload=payload)


@router.post("/policies/reviews/{review_id}/apply")
def apply_policy_review(
    review_id: str,
    _response: Response,
    service: Annotated[PolicyService, Depends(get_policy_service)],
    current_user: Annotated[dict, Depends(require_permission("policies.manage"))],
    _csrf: Annotated[None, Depends(require_csrf)],
    payload: PolicyReviewApplyRequest,
) -> dict:
    return service.apply_review(
        owner_user_id=_owner_user_id(current_user),
        review_id=review_id,
        payload=payload,
    )
