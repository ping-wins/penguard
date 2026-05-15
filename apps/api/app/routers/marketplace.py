from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException

from app.addons.catalog_fetcher import CatalogFetcher, CatalogFetchError
from app.addons.contracts import AddonInstallError, AddonLoadError
from app.addons.dependencies import (
    get_catalog_fetcher,
    get_connector_registry,
    get_install_service,
)
from app.addons.install_service import InstallService
from app.addons.installed_store import list_installed
from app.addons.registry import get_addon, list_addons, reload_addons
from app.addons.registry_runtime import ConnectorRegistry
from app.auth.dependencies import get_current_api_user, require_admin_user
from app.db.session import SessionLocal

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


def _bundled_items() -> list[dict[str, Any]]:
    return [m.model_dump(by_alias=True) for m in list_addons()]


def _installed_index() -> dict[str, dict[str, Any]]:
    with SessionLocal() as session:
        return {
            r.id: {"version": r.version, "installed_at": r.installed_at.isoformat()}
            for r in list_installed(session)
        }


@router.get("/addons")
def list_marketplace_addons(
    _user: Annotated[dict, Depends(get_current_api_user)],
    catalog: Annotated[CatalogFetcher, Depends(get_catalog_fetcher)],
) -> dict:
    installed = _installed_index()
    bundled = _bundled_items()

    remote_items: list[dict[str, Any]] = []
    catalog_error: str | None = None
    try:
        remote_items = catalog.fetch().get("addons", [])
    except CatalogFetchError as exc:
        catalog_error = str(exc)

    by_id: dict[str, dict[str, Any]] = {}
    for entry in bundled:
        by_id[entry["id"]] = {**entry, "source": "bundled"}
    for entry in remote_items:
        merged = {**by_id.get(entry["id"], {}), **entry, "source": "remote"}
        by_id[entry["id"]] = merged

    items: list[dict[str, Any]] = []
    for entry in by_id.values():
        info = installed.get(entry["id"])
        items.append(
            {
                **entry,
                "installed": info is not None,
                "installedVersion": info["version"] if info else None,
            }
        )
    return {"items": items, "count": len(items), "catalogError": catalog_error}


@router.get("/addons/{addon_id}")
def get_marketplace_addon(
    addon_id: str,
    _user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    manifest = get_addon(addon_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Add-on not found")
    return manifest.model_dump(by_alias=True)


@router.post("/addons/refresh")
def refresh_marketplace_addons(
    _admin: Annotated[dict, Depends(require_admin_user)],
    catalog: Annotated[CatalogFetcher, Depends(get_catalog_fetcher)],
) -> dict:
    catalog.invalidate()
    return {"reloaded": len(reload_addons())}


@router.post("/addons/{addon_id}/install")
def install_marketplace_addon(
    addon_id: str,
    _admin: Annotated[dict, Depends(require_admin_user)],
    service: Annotated[InstallService, Depends(get_install_service)],
    registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
    body: dict = Body(...),
) -> dict:
    version = body.get("version")
    if not version:
        raise HTTPException(status_code=400, detail="version is required")
    try:
        factory = service.install(addon_id, version=version)
    except AddonInstallError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AddonLoadError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    registry.register(addon_id, factory)
    return {"id": addon_id, "version": version, "status": "installed"}


@router.delete("/addons/{addon_id}")
def uninstall_marketplace_addon(
    addon_id: str,
    _admin: Annotated[dict, Depends(require_admin_user)],
    service: Annotated[InstallService, Depends(get_install_service)],
    registry: Annotated[ConnectorRegistry, Depends(get_connector_registry)],
) -> dict:
    try:
        service.uninstall(addon_id)
    except AddonInstallError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    registry.unregister(addon_id)
    return {"id": addon_id, "status": "uninstalled"}
