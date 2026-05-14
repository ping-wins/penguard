from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.addons.registry import get_addon, list_addons, reload_addons
from app.auth.dependencies import get_current_api_user, require_admin_user

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


@router.get("/addons")
def list_marketplace_addons(
    _current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    items = [manifest.model_dump(by_alias=True) for manifest in list_addons()]
    return {"items": items, "count": len(items)}


@router.get("/addons/{addon_id}")
def get_marketplace_addon(
    addon_id: str,
    _current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    manifest = get_addon(addon_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Add-on not found")
    return manifest.model_dump(by_alias=True)


@router.post("/addons/refresh")
def refresh_marketplace_addons(
    _admin: Annotated[dict, Depends(require_admin_user)],
) -> dict:
    items = reload_addons()
    return {"reloaded": len(items)}
