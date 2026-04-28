from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import get_auth_audit_store, get_current_api_user

router = APIRouter(tags=["audit"])


class AuditEventStore(Protocol):
    def list_events(self, *, limit: int = 50, user_id: str | None = None) -> dict:
        pass


@router.get("/audit/events")
def list_audit_events(
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuditEventStore, Depends(get_auth_audit_store)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict:
    return audit_store.list_events(limit=limit, user_id=str(current_user["id"]))
