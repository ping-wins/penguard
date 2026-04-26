from fastapi import APIRouter
from pydantic import BaseModel

from app.core.fixtures import load_fixture

router = APIRouter(tags=["workspaces"])


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


@router.get("/workspaces/{workspace_id}")
def get_workspace(workspace_id: str) -> dict:
    workspace = load_fixture("workspace_default")
    if workspace_id != workspace["id"]:
        return {"id": workspace_id, "name": "Untitled", "widgets": []}
    return workspace


@router.put("/workspaces/{workspace_id}")
def update_workspace(workspace_id: str, _: WorkspaceUpdate) -> dict:
    response = load_fixture("workspace_update_response")
    return {**response, "id": workspace_id}
