from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, Query, Request

from app.auth.dependencies import (
    get_auth_audit_store,
    get_current_api_user,
    require_admin_user,
)

router = APIRouter(tags=["audit"])


class AuditEventStore(Protocol):
    def list_events(
        self,
        *,
        limit: int = 50,
        user_id: str | None = None,
        actor_user_id: str | None = None,
        action: str | None = None,
        outcome: str | None = None,
    ) -> dict:
        pass

    def record(
        self,
        *,
        action: str,
        outcome: str,
        email: str | None = None,
        user_id: str | None = None,
        client_ip: str | None = None,
        user_agent: str | None = None,
        details: dict | None = None,
    ) -> None:
        pass


@router.get("/audit/events")
def list_audit_events(
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditEventStore, Depends(get_auth_audit_store)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict:
    return audit_store.list_events(limit=limit, user_id=str(current_user["id"]))


@router.get("/admin/audit/events")
def list_admin_audit_events(
    request: Request,
    current_user: Annotated[dict, Depends(require_admin_user)],
    audit_store: Annotated[AuditEventStore, Depends(get_auth_audit_store)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    actor_user_id: Annotated[str | None, Query(alias="actorUserId")] = None,
    action: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    outcome: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
) -> dict:
    payload = audit_store.list_events(
        limit=limit,
        actor_user_id=actor_user_id,
        action=action,
        outcome=outcome,
    )
    audit_store.record(
        action="audit.events.viewed",
        outcome="success",
        email=current_user.get("email"),
        user_id=str(current_user["id"]),
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={
            "scope": "admin",
            "limit": limit,
            "actorUserId": actor_user_id,
            "action": action,
            "outcome": outcome,
        },
    )
    return payload


def _client_ip(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host
