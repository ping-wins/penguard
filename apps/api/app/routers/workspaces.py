from functools import lru_cache
from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.auth.audit import InMemoryAuthAuditStore, SqlAlchemyAuthAuditStore
from app.auth.csrf_dependency import require_csrf
from app.auth.dependencies import get_auth_audit_store, get_current_api_user
from app.core.config import get_settings
from app.core.fixtures import load_fixture
from app.workspaces.store import SqlAlchemyWorkspaceStore

router = APIRouter(tags=["workspaces"])
AuthAuditStore = InMemoryAuthAuditStore | SqlAlchemyAuthAuditStore


class WorkspaceStore(Protocol):
    def get(self, workspace_id: str, *, owner_user_id: str) -> dict | None:
        pass

    def save(
        self,
        *,
        workspace_id: str,
        owner_user_id: str,
        name: str,
        widgets: list[dict],
    ) -> dict:
        pass


class WidgetLayout(BaseModel):
    x: int
    y: int
    w: int
    h: int
    z: int


class WorkspaceWidget(BaseModel):
    instanceId: str
    catalogId: str
    integrationId: str
    layout: WidgetLayout


class WorkspaceUpdate(BaseModel):
    name: str
    widgets: list[WorkspaceWidget]


@lru_cache
def get_workspace_store() -> WorkspaceStore | None:
    settings = get_settings()
    if settings.mock_mode:
        return None
    return SqlAlchemyWorkspaceStore(database_url=settings.database_url)


@router.get("/workspaces/{workspace_id}")
def get_workspace(
    workspace_id: str,
    store: Annotated[WorkspaceStore | None, Depends(get_workspace_store)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    owner_user_id = str(current_user["id"])
    if store is not None:
        workspace = store.get(workspace_id, owner_user_id=owner_user_id)
        if workspace is not None:
            return workspace
        return {"id": workspace_id, "name": "Untitled", "widgets": [], "version": 0}

    workspace = load_fixture("workspace_default")
    if workspace_id != workspace["id"]:
        return {"id": workspace_id, "name": "Untitled", "widgets": []}
    return workspace


@router.put("/workspaces/{workspace_id}")
def update_workspace(
    workspace_id: str,
    payload: WorkspaceUpdate,
    request: Request,
    store: Annotated[WorkspaceStore | None, Depends(get_workspace_store)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuthAuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    owner_user_id = str(current_user["id"])
    if store is not None:
        widgets = [widget.model_dump(mode="json") for widget in payload.widgets]
        response = store.save(
            workspace_id=workspace_id,
            owner_user_id=owner_user_id,
            name=payload.name,
            widgets=widgets,
        )
        audit_store.record(
            action="workspace.updated",
            outcome="success",
            email=current_user.get("email"),
            user_id=owner_user_id,
            client_ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            details={
                "workspaceId": workspace_id,
                "widgetCount": len(widgets),
                "version": response["version"],
            },
        )
        return response

    response = load_fixture("workspace_update_response")
    return {**response, "id": workspace_id}


def _client_ip(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host
