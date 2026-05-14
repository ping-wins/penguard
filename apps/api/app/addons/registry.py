import json
import logging
import os
from functools import lru_cache
from pathlib import Path

from app.addons.manifest import AddonManifest

logger = logging.getLogger(__name__)

DEFAULT_ADDONS_DIR = Path("/app/addons")


def _addons_dir() -> Path:
    override = os.environ.get("FORTIDASHBOARD_ADDONS_DIR")
    if override:
        return Path(override)
    if DEFAULT_ADDONS_DIR.is_dir():
        return DEFAULT_ADDONS_DIR
    # Fallback for local (non-docker) runs where the working dir is repo root.
    return Path(__file__).resolve().parents[4] / "addons"


def _discover() -> list[AddonManifest]:
    base = _addons_dir()
    if not base.is_dir():
        logger.warning("addons_dir_missing path=%s", base)
        return []
    manifests: list[AddonManifest] = []
    for entry in sorted(base.iterdir()):
        if not entry.is_dir():
            continue
        manifest_path = entry / "addon.json"
        if not manifest_path.is_file():
            continue
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifests.append(AddonManifest.model_validate(payload))
        except Exception as exc:
            logger.exception("addon_manifest_invalid path=%s error=%s", manifest_path, exc)
    return manifests


@lru_cache
def list_addons() -> list[AddonManifest]:
    addons = _discover()
    logger.info("addons_registry_loaded count=%s", len(addons))
    return addons


def get_addon(addon_id: str) -> AddonManifest | None:
    for manifest in list_addons():
        if manifest.id == addon_id:
            return manifest
    return None


def reload_addons() -> list[AddonManifest]:
    list_addons.cache_clear()
    return list_addons()
