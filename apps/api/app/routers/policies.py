from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.auth.csrf_dependency import require_csrf
from app.auth.dependencies import get_auth_audit_store
from app.auth.permissions import require_permission
from app.policies.fortigate_adapter import FortiGatePolicyAdapter
from app.policies.fortiweb_adapter import FortiWebPolicyAdapter
from app.policies.models import PolicyReviewApplyRequest, PolicyReviewCreateRequest
from app.policies.service import PolicyService
from app.routers import integrations

router = APIRouter(tags=["policies"])


def get_policy_service() -> PolicyService:
    return PolicyService(
        adapters=[
            FortiGatePolicyAdapter(integrations.get_fortigate_integration_service()),
            FortiWebPolicyAdapter(integrations.get_fortiweb_integration_service()),
        ]
    )


def _owner_user_id(current_user: dict) -> str:
    return str(current_user.get("id") or current_user.get("user_id"))


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else None


def _audit(
    audit_store: Any,
    *,
    request: Request,
    current_user: dict,
    action: str,
    details: dict[str, Any],
) -> None:
    audit_store.record(
        action=action,
        outcome="success",
        email=current_user.get("email"),
        user_id=_owner_user_id(current_user),
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=details,
    )


@router.get("/policies/providers")
def list_policy_providers(
    request: Request,
    service: Annotated[PolicyService, Depends(get_policy_service)],
    current_user: Annotated[dict, Depends(require_permission("policies.manage"))],
    audit_store: Annotated[Any, Depends(get_auth_audit_store)],
) -> dict:
    result = service.list_providers(owner_user_id=_owner_user_id(current_user))
    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="policies.providers.viewed",
        details={"providerCount": len(result.get("items", []))},
    )
    return result


@router.get("/policies")
def list_policies(
    request: Request,
    service: Annotated[PolicyService, Depends(get_policy_service)],
    current_user: Annotated[dict, Depends(require_permission("policies.manage"))],
    audit_store: Annotated[Any, Depends(get_auth_audit_store)],
    provider_type: Annotated[str | None, Query(alias="providerType")] = None,
    integration_id: Annotated[str | None, Query(alias="integrationId")] = None,
    kind: str | None = None,
    policy_status: Annotated[str | None, Query(alias="status")] = None,
    ownership: str | None = None,
    q: str | None = None,
) -> dict:
    filters = {
        "providerType": provider_type,
        "integrationId": integration_id,
        "kind": kind,
        "status": policy_status,
        "ownership": ownership,
        "q": q,
    }
    result = service.list_policies(
        owner_user_id=_owner_user_id(current_user),
        filters=filters,
    )
    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="policies.inventory.viewed",
        details={"filters": filters, "policyCount": len(result.get("items", []))},
    )
    return result


@router.post("/policies/reviews", status_code=status.HTTP_201_CREATED)
def create_policy_review(
    request: Request,
    service: Annotated[PolicyService, Depends(get_policy_service)],
    current_user: Annotated[dict, Depends(require_permission("policies.manage"))],
    audit_store: Annotated[Any, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
    payload: PolicyReviewCreateRequest,
) -> dict:
    result = service.create_review(owner_user_id=_owner_user_id(current_user), payload=payload)
    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="policies.review.created",
        details={
            "reviewId": result.get("id"),
            "providerType": result.get("providerType"),
            "integrationId": result.get("integrationId"),
            "policyId": result.get("policyId"),
            "action": result.get("action"),
        },
    )
    return result


@router.post("/policies/reviews/{review_id}/apply")
def apply_policy_review(
    review_id: str,
    request: Request,
    _response: Response,
    service: Annotated[PolicyService, Depends(get_policy_service)],
    current_user: Annotated[dict, Depends(require_permission("policies.manage"))],
    audit_store: Annotated[Any, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
    payload: PolicyReviewApplyRequest,
) -> dict:
    result = service.apply_review(
        owner_user_id=_owner_user_id(current_user),
        review_id=review_id,
        payload=payload,
    )
    _audit(
        audit_store,
        request=request,
        current_user=current_user,
        action="policies.review.applied",
        details={
            "reviewId": review_id,
            "providerType": result.get("providerType"),
            "integrationId": result.get("integrationId"),
            "status": result.get("status"),
        },
    )
    return result
