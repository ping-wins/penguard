"""Dynamic loader for installed add-on packages.

Each add-on is imported as `fortidashboard_addons.<id>` via
`importlib.util.spec_from_file_location` to keep it off the global
`sys.path`. Submodule lookup is scoped to the package directory.
"""

import importlib.util
import json
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

from app.addons.contracts import AddonConnector, AddonLoadError
from app.addons.installed_store import InstalledAddonRecord
from app.addons.manifest import AddonManifest

logger = logging.getLogger(__name__)

_MODULE_NAMESPACE = "fortidashboard_addons"


class AddonLoader:
    def __init__(self) -> None:
        self._loaded: dict[str, ModuleType] = {}

    def load(self, install: InstalledAddonRecord) -> Callable[[dict], AddonConnector]:
        addon_root = Path(install.path).resolve()
        manifest_path = addon_root / "addon.json"
        if not manifest_path.is_file():
            raise AddonLoadError(f"addon manifest missing at {manifest_path}")

        manifest = AddonManifest.model_validate(
            json.loads(manifest_path.read_text(encoding="utf-8"))
        )
        entry_dir = (addon_root / manifest.entrypoint).resolve()

        try:
            entry_dir.relative_to(addon_root)
        except ValueError as exc:
            raise AddonLoadError(
                f"entrypoint '{manifest.entrypoint}' escapes package root"
            ) from exc

        if not entry_dir.is_dir():
            raise AddonLoadError(f"entrypoint directory not found: {entry_dir}")

        entry = entry_dir / "__init__.py"
        if not entry.is_file():
            raise AddonLoadError(f"entrypoint package has no __init__.py: {entry}")

        module_name = f"{_MODULE_NAMESPACE}.{install.id}"
        spec = importlib.util.spec_from_file_location(
            module_name,
            entry,
            submodule_search_locations=[str(entry_dir)],
        )
        if spec is None or spec.loader is None:
            raise AddonLoadError(f"failed to build import spec for {install.id}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            sys.modules.pop(module_name, None)
            raise AddonLoadError(f"failed to import add-on {install.id}: {exc}") from exc

        factory = getattr(module, "get_connector", None)
        if not callable(factory):
            sys.modules.pop(module_name, None)
            raise AddonLoadError(f"add-on {install.id} missing get_connector(config)")

        self._loaded[install.id] = module
        logger.info("addon_loaded id=%s version=%s", install.id, install.version)
        return factory

    def unload(self, addon_id: str) -> None:
        module = self._loaded.pop(addon_id, None)
        if module is not None:
            sys.modules.pop(module.__name__, None)
            logger.info("addon_unloaded id=%s", addon_id)
