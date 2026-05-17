import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException

from app.addons.dependencies import get_connector_registry
from app.addons.installed_store import list_installed
from app.addons.registry_runtime import ConnectorRegistry
from app.auth.csrf_dependency import require_csrf
from app.auth.dependencies import get_current_api_user
from app.auth.permissions import require_permission
from app.db.session import SessionLocal
from app.integrations.catalog import build_catalog
from app.integrations.connect_persistence import (
    UnsupportedProviderType,
    persist_integration,
    validate_auth,
)
from app.integrations.fortiweb.auth import fortiweb_runtime_auth
from app.integrations.wiring import apply_wiring, get_soar_actions
from app.routers.integrations import (
    get_fortigate_integration_service,
    get_fortiweb_integration_service,
    get_penguin_tool_integration_service,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations", tags=["integrations-v2"])
ConnectBody = Annotated[dict[str, Any], Body()]


def _catalog_entry(addon_id: str) -> dict[str, Any]:
    with SessionLocal() as session:
        entries = build_catalog(list_installed(session))
    for entry in entries:
        if entry["addonId"] == addon_id:
            return entry
    raise HTTPException(status_code=404, detail=f"Add-on not installed: {addon_id}")


@router.get("/catalog")
def get_catalog(
    _user: Annotated[dict[str, Any], Depends(get_current_api_user)],
    _perm: Annotated[
        dict[str, Any], Depends(require_permission("integrations.write"))
    ],
) -> dict[str, Any]:
    with SessionLocal() as session:
        return {"items": build_catalog(list_installed(session))}


def _resolve_and_test(
    body: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    addon_id = body.get("addonId")
    version = body.get("version")
    if not addon_id or not version:
        raise HTTPException(status_code=400, detail="addonId and version are required")
    entry = _catalog_entry(str(addon_id))
    if version not in entry["versions"]:
        raise HTTPException(status_code=422, detail=f"Unknown version: {version}")
    try:
        auth = validate_auth(entry["authFields"], body.get("auth") or {})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    runtime_auth = (
        fortiweb_runtime_auth(auth) if entry["providerType"] == "fortiweb" else auth
    )

    registry: ConnectorRegistry = get_connector_registry()
    try:
        connector = registry.get(
            str(addon_id),
            integration_id="__probe__",
            config=runtime_auth,
        )
        result = connector.health_check()
    except Exception as exc:
        logger.exception("connect_health_check_failed addon=%s", addon_id)
        result = {"ok": False, "status": "error", "device": {}, "message": str(exc)}
    return entry, runtime_auth, result


@router.post("/connect/test")
def connect_test(
    _user: Annotated[dict[str, Any], Depends(get_current_api_user)],
    _perm: Annotated[
        dict[str, Any], Depends(require_permission("integrations.write"))
    ],
    _csrf: Annotated[None, Depends(require_csrf)],
    body: ConnectBody,
) -> dict[str, Any]:
    _entry, _auth, result = _resolve_and_test(body)
    return result


@router.post("/connect")
def connect(
    current_user: Annotated[dict[str, Any], Depends(get_current_api_user)],
    _perm: Annotated[
        dict[str, Any], Depends(require_permission("integrations.write"))
    ],
    _csrf: Annotated[None, Depends(require_csrf)],
    body: ConnectBody,
    fortigate: Annotated[Any, Depends(get_fortigate_integration_service)],
    fortiweb: Annotated[Any, Depends(get_fortiweb_integration_service)],
    penguin: Annotated[Any, Depends(get_penguin_tool_integration_service)],
) -> dict[str, Any]:
    entry, auth, result = _resolve_and_test(body)
    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=result.get("message") or "Connection failed",
        )
    name = str(body.get("name") or entry["name"])
    try:
        integration = persist_integration(
            provider_type=entry["providerType"],
            owner_user_id=str(current_user["id"]),
            name=name,
            auth=auth,
            device=result.get("device") or {},
            services={"fortigate": fortigate, "fortiweb": fortiweb, "penguin": penguin},
        )
    except UnsupportedProviderType as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    integration_id = str(integration["id"])
    wire = body.get("wire") or {"siem": False, "soar": False}
    connector = get_connector_registry().get(
        entry["addonId"],
        integration_id=integration_id,
        config=auth,
    )
    with SessionLocal() as session:
        wiring = apply_wiring(
            session,
            integration_id=integration_id,
            provider_type=entry["providerType"],
            capabilities=entry["capabilities"],
            wire={"siem": bool(wire.get("siem")), "soar": bool(wire.get("soar"))},
            connector=connector,
            now=datetime.now(UTC),
        )
    return {"integration": integration, "wiring": wiring}


@router.get("/{integration_id}/soar-actions")
def soar_actions(
    integration_id: str,
    _user: Annotated[dict[str, Any], Depends(get_current_api_user)],
    _perm: Annotated[
        dict[str, Any], Depends(require_permission("integrations.write"))
    ],
) -> dict[str, Any]:
    with SessionLocal() as session:
        return {"items": get_soar_actions(session, integration_id)}
