import logging
import re
from datetime import UTC, datetime
from functools import lru_cache
from secrets import token_urlsafe
from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.auth.audit import InMemoryAuthAuditStore, SqlAlchemyAuthAuditStore
from app.auth.csrf_dependency import require_csrf
from app.auth.dependencies import get_auth_audit_store, get_current_api_user
from app.auth.token_cipher import TokenCipher
from app.core.config import get_settings
from app.core.fixtures import load_fixture
from app.integrations.fortigate.store import SqlAlchemyFortiGateIntegrationStore
from app.integrations.penguin_tools import SqlAlchemyPenguinToolIntegrationStore
from app.workspaces.manifest import (
    MANIFEST_MAX_BYTES,
    PresentationMetadata,
    WorkspaceManifest,
    build_manifest,
    manifest_to_widgets,
    validate_manifest_payload,
)
from app.workspaces.store import SqlAlchemyWorkspaceStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["workspaces"])
AuthAuditStore = InMemoryAuthAuditStore | SqlAlchemyAuthAuditStore
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,62}[a-z0-9]$")


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
        presentation: dict | None = None,
    ) -> dict:
        pass

    def set_presentation(
        self,
        *,
        workspace_id: str,
        owner_user_id: str,
        presentation: dict | None,
    ) -> dict | None:
        pass

    def create_workspace_from_manifest(
        self,
        *,
        owner_user_id: str,
        workspace_id: str,
        name: str,
        widgets: list[dict],
        presentation: dict | None,
        origin: dict | None = None,
    ) -> dict:
        pass

    def list_workspaces(self, *, owner_user_id: str) -> list[dict]:
        pass

    def delete_workspace(self, *, workspace_id: str, owner_user_id: str) -> bool:
        pass

    def publish_template(
        self,
        *,
        slug: str,
        title: str,
        description: str | None,
        tags: list[str],
        manifest: dict,
        published_by_user_id: str,
        published_by_email: str | None,
    ) -> dict:
        pass

    def list_templates(self, *, limit: int = 100) -> list[dict]:
        pass

    def get_template(self, template_id: str) -> dict | None:
        pass

    def delete_template(self, *, template_id: str, published_by_user_id: str) -> bool:
        pass

    def increment_template_install(self, template_id: str) -> None:
        pass


class WidgetLayout(BaseModel):
    x: int
    y: int
    w: int
    h: int
    z: int


class WorkspaceFieldBinding(BaseModel):
    field_id: str = Field(alias="fieldId")
    label: str
    type: str
    unit: str | None = None
    source: str
    provider: str | None = None
    group_id: str | None = Field(default=None, alias="groupId")
    group_name: str | None = Field(default=None, alias="groupName")

    model_config = ConfigDict(populate_by_name=True)


class WorkspaceWidget(BaseModel):
    instanceId: str
    catalogId: str
    integrationId: str
    layout: WidgetLayout
    fieldBindings: list[WorkspaceFieldBinding] = Field(default_factory=list)


class WorkspaceUpdate(BaseModel):
    name: str
    widgets: list[WorkspaceWidget]


class PresentationUpdate(BaseModel):
    presentation: PresentationMetadata | None = None


class ImportManifestRequest(BaseModel):
    manifest: dict
    workspace_id: str | None = Field(default=None, alias="workspaceId")

    model_config = ConfigDict(populate_by_name=True)


class PublishTemplateRequest(BaseModel):
    slug: str
    title: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    presentation: PresentationMetadata | None = None
    incident_id: str | None = Field(default=None, alias="incidentId")

    model_config = ConfigDict(populate_by_name=True)


class InstallTemplateRequest(BaseModel):
    workspace_id: str | None = Field(default=None, alias="workspaceId")

    model_config = ConfigDict(populate_by_name=True)


@lru_cache
def get_workspace_store() -> WorkspaceStore | None:
    settings = get_settings()
    if settings.mock_mode:
        return None
    return SqlAlchemyWorkspaceStore(database_url=settings.database_url)


@router.get("/workspaces")
def list_workspaces(
    store: Annotated[WorkspaceStore | None, Depends(get_workspace_store)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    if store is None:
        return {"items": []}
    return {"items": store.list_workspaces(owner_user_id=str(current_user["id"]))}


@router.get("/workspaces/community")
def list_community_templates(
    store: Annotated[WorkspaceStore | None, Depends(get_workspace_store)],
    _current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    if store is None:
        return {"items": []}
    return {"items": store.list_templates(limit=100)}


@router.post("/workspaces/community/{template_id}/install", status_code=status.HTTP_201_CREATED)
def install_community_template(
    template_id: str,
    payload: InstallTemplateRequest,
    request: Request,
    store: Annotated[WorkspaceStore | None, Depends(get_workspace_store)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuthAuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    if store is None:
        raise HTTPException(status_code=503, detail="Workspace store unavailable")
    template = store.get_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    try:
        manifest = validate_manifest_payload(template["manifest"])
    except ValueError as exc:
        logger.warning("Template manifest invalid: id=%s error=%s", template_id, exc)
        raise HTTPException(status_code=422, detail=f"Template manifest invalid: {exc}") from exc

    workspace_id = payload.workspace_id or f"ws_{token_urlsafe(8)}"
    presentation = manifest.presentation.model_dump(by_alias=True) if manifest.presentation else None
    owner_user_id = str(current_user["id"])
    integration_map = _resolve_integration_bindings(owner_user_id)
    widgets = manifest_to_widgets(manifest, integration_id_by_provider=integration_map)
    missing_providers = sorted(
        {w.provider_type for w in manifest.widgets if w.provider_type not in integration_map and w.provider_type != "generic"}
    )
    origin = {
        "type": "template",
        "templateId": template["id"],
        "templateSlug": template.get("slug"),
        "templateTitle": template.get("title"),
        "templateDescription": template.get("description"),
        "tags": template.get("tags") or [],
        "publishedByEmail": template.get("publishedByEmail"),
        "publishedByUserId": template.get("publishedByUserId"),
        "installCount": template.get("installCount"),
        "installedAt": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "sourceWorkspaceId": manifest.workspace_id,
        "missingProviderTypes": missing_providers,
    }
    created = store.create_workspace_from_manifest(
        owner_user_id=owner_user_id,
        workspace_id=workspace_id,
        name=manifest.name,
        widgets=widgets,
        presentation=presentation,
        origin=origin,
    )
    store.increment_template_install(template_id)
    audit_store.record(
        action="workspace.template.installed",
        outcome="success",
        email=current_user.get("email"),
        user_id=str(current_user["id"]),
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={
            "templateId": template_id,
            "templateSlug": template.get("slug"),
            "workspaceId": workspace_id,
        },
    )
    return {"workspace": created, "templateId": template_id}


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
        return {
            "id": workspace_id,
            "name": "Untitled",
            "widgets": [],
            "presentation": None,
            "version": 0,
        }

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
        widgets = []
        for widget in payload.widgets:
            widget_payload = widget.model_dump(mode="json", by_alias=True)
            if not widget_payload["fieldBindings"]:
                widget_payload.pop("fieldBindings")
            widgets.append(widget_payload)
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


@router.delete("/workspaces/{workspace_id}")
def delete_workspace(
    workspace_id: str,
    request: Request,
    store: Annotated[WorkspaceStore | None, Depends(get_workspace_store)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuthAuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    if store is None:
        raise HTTPException(status_code=503, detail="Workspace store unavailable")
    deleted = store.delete_workspace(
        workspace_id=workspace_id,
        owner_user_id=str(current_user["id"]),
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Workspace not found")
    audit_store.record(
        action="workspace.deleted",
        outcome="success",
        email=current_user.get("email"),
        user_id=str(current_user["id"]),
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={"workspaceId": workspace_id},
    )
    return {"deleted": True, "id": workspace_id}


@router.put("/workspaces/{workspace_id}/presentation")
def update_workspace_presentation(
    workspace_id: str,
    payload: PresentationUpdate,
    request: Request,
    store: Annotated[WorkspaceStore | None, Depends(get_workspace_store)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuthAuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    if store is None:
        raise HTTPException(status_code=503, detail="Workspace store unavailable")
    owner_user_id = str(current_user["id"])
    presentation_payload = (
        payload.presentation.model_dump(by_alias=True) if payload.presentation else None
    )
    updated = store.set_presentation(
        workspace_id=workspace_id,
        owner_user_id=owner_user_id,
        presentation=presentation_payload,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    audit_store.record(
        action="workspace.presentation.updated",
        outcome="success",
        email=current_user.get("email"),
        user_id=owner_user_id,
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={
            "workspaceId": workspace_id,
            "hasPresentation": presentation_payload is not None,
        },
    )
    return updated


@router.get("/workspaces/{workspace_id}/export")
def export_workspace(
    workspace_id: str,
    request: Request,
    store: Annotated[WorkspaceStore | None, Depends(get_workspace_store)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuthAuditStore, Depends(get_auth_audit_store)],
) -> dict:
    if store is None:
        raise HTTPException(status_code=503, detail="Workspace store unavailable")
    owner_user_id = str(current_user["id"])
    workspace = store.get(workspace_id, owner_user_id=owner_user_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    presentation = workspace.get("presentation")
    presentation_model = (
        PresentationMetadata.model_validate(presentation) if presentation else None
    )
    manifest = build_manifest(
        workspace=workspace,
        exported_by_email=current_user.get("email"),
        presentation=presentation_model,
    )
    audit_store.record(
        action="workspace.exported",
        outcome="success",
        email=current_user.get("email"),
        user_id=owner_user_id,
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={"workspaceId": workspace_id, "widgetCount": len(manifest.widgets)},
    )
    return manifest.model_dump(by_alias=True)


@router.post("/workspaces/import", status_code=status.HTTP_201_CREATED)
def import_workspace(
    payload: ImportManifestRequest,
    request: Request,
    store: Annotated[WorkspaceStore | None, Depends(get_workspace_store)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuthAuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    if store is None:
        raise HTTPException(status_code=503, detail="Workspace store unavailable")
    _enforce_manifest_size(payload.manifest)
    try:
        manifest = validate_manifest_payload(payload.manifest)
    except ValueError as exc:
        logger.warning("Workspace import rejected: error=%s", exc)
        audit_store.record(
            action="workspace.imported",
            outcome="rejected",
            email=current_user.get("email"),
            user_id=str(current_user["id"]),
            client_ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            details={"error": str(exc)},
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    workspace_id = payload.workspace_id or f"ws_{token_urlsafe(8)}"
    presentation = (
        manifest.presentation.model_dump(by_alias=True) if manifest.presentation else None
    )
    owner_user_id = str(current_user["id"])
    integration_map = _resolve_integration_bindings(owner_user_id)
    widgets = manifest_to_widgets(manifest, integration_id_by_provider=integration_map)
    missing_providers = sorted(
        {w.provider_type for w in manifest.widgets if w.provider_type not in integration_map and w.provider_type != "generic"}
    )
    origin = {
        "type": "imported",
        "sourceWorkspaceId": manifest.workspace_id,
        "exportedByEmail": manifest.metadata.exported_by_email,
        "exportedAt": manifest.metadata.exported_at,
        "description": manifest.metadata.description,
        "tags": manifest.metadata.tags,
        "incidentId": manifest.metadata.incident_id,
        "importedAt": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "missingProviderTypes": missing_providers,
    }
    created = store.create_workspace_from_manifest(
        owner_user_id=owner_user_id,
        workspace_id=workspace_id,
        name=manifest.name,
        widgets=widgets,
        presentation=presentation,
        origin=origin,
    )
    audit_store.record(
        action="workspace.imported",
        outcome="success",
        email=current_user.get("email"),
        user_id=str(current_user["id"]),
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={
            "workspaceId": workspace_id,
            "widgetCount": len(manifest.widgets),
            "sourceWorkspaceId": manifest.workspace_id,
        },
    )
    return created


@router.post("/workspaces/{workspace_id}/publish", status_code=status.HTTP_201_CREATED)
def publish_workspace_template(
    workspace_id: str,
    payload: PublishTemplateRequest,
    request: Request,
    store: Annotated[WorkspaceStore | None, Depends(get_workspace_store)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuthAuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    if store is None:
        raise HTTPException(status_code=503, detail="Workspace store unavailable")
    if not _SLUG_RE.match(payload.slug):
        raise HTTPException(
            status_code=422,
            detail="Slug must be 4-64 lowercase letters, digits or hyphens",
        )
    owner_user_id = str(current_user["id"])
    workspace = store.get(workspace_id, owner_user_id=owner_user_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    stored_presentation = workspace.get("presentation")
    if payload.presentation is not None:
        presentation_model: PresentationMetadata | None = payload.presentation
    elif stored_presentation:
        presentation_model = PresentationMetadata.model_validate(stored_presentation)
    else:
        presentation_model = None
    manifest = build_manifest(
        workspace=workspace,
        exported_by_email=current_user.get("email"),
        presentation=presentation_model,
        description=payload.description,
        tags=payload.tags,
        incident_id=payload.incident_id,
    )
    try:
        template = store.publish_template(
            slug=payload.slug,
            title=payload.title,
            description=payload.description,
            tags=payload.tags,
            manifest=manifest.model_dump(by_alias=True),
            published_by_user_id=owner_user_id,
            published_by_email=current_user.get("email"),
        )
    except PermissionError as exc:
        audit_store.record(
            action="workspace.template.published",
            outcome="forbidden",
            email=current_user.get("email"),
            user_id=owner_user_id,
            client_ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            details={"slug": payload.slug, "workspaceId": workspace_id},
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    audit_store.record(
        action="workspace.template.published",
        outcome="success",
        email=current_user.get("email"),
        user_id=owner_user_id,
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={
            "templateId": template["id"],
            "slug": payload.slug,
            "workspaceId": workspace_id,
        },
    )
    return template


@router.delete("/workspaces/community/{template_id}")
def delete_community_template(
    template_id: str,
    request: Request,
    store: Annotated[WorkspaceStore | None, Depends(get_workspace_store)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
    audit_store: Annotated[AuthAuditStore, Depends(get_auth_audit_store)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> dict:
    if store is None:
        raise HTTPException(status_code=503, detail="Workspace store unavailable")
    try:
        deleted = store.delete_template(
            template_id=template_id,
            published_by_user_id=str(current_user["id"]),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found")
    audit_store.record(
        action="workspace.template.deleted",
        outcome="success",
        email=current_user.get("email"),
        user_id=str(current_user["id"]),
        client_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details={"templateId": template_id},
    )
    return {"deleted": True, "id": template_id}


def _resolve_integration_bindings(owner_user_id: str) -> dict[str, str]:
    """Return a `provider_type -> integrationId` map for the user's first
    integration of each kind. Used to auto-bind widgets on import/install.
    """
    settings = get_settings()
    if settings.mock_mode:
        return {}
    cipher = TokenCipher.from_secret(settings.token_encryption_key or settings.secret_key)
    fortigate_store = SqlAlchemyFortiGateIntegrationStore(
        database_url=settings.database_url,
        secret_cipher=cipher,
    )
    penguin_store = SqlAlchemyPenguinToolIntegrationStore(database_url=settings.database_url)
    mapping: dict[str, str] = {}
    fg_items = fortigate_store.list_public(owner_user_id=owner_user_id).get("items", [])
    if fg_items:
        mapping["fortigate"] = fg_items[0]["id"]
    pg_items = penguin_store.list_public(owner_user_id=owner_user_id).get("items", [])
    for item in pg_items:
        tool_type = item.get("type")
        if tool_type and tool_type not in mapping:
            mapping[tool_type] = item["id"]
    return mapping


def _enforce_manifest_size(manifest_payload: dict) -> None:
    import json

    encoded = json.dumps(manifest_payload).encode("utf-8")
    if len(encoded) > MANIFEST_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Manifest exceeds {MANIFEST_MAX_BYTES} bytes",
        )


def _client_ip(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host


def _get_workspace_or_404(
    store: WorkspaceStore | None,
    workspace_id: str,
    *,
    owner_user_id: str,
) -> dict:
    if store is None:
        raise HTTPException(status_code=503, detail="Workspace store unavailable")
    workspace = store.get(workspace_id, owner_user_id=owner_user_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


# Helper used by other routers if needed in the future.
WorkspaceManifest  # noqa: B018 -- exported alias reference
