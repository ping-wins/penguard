import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.addons.contracts import AddonLoadError
from app.addons.installed_store import InstalledAddonRecord
from app.addons.loader import AddonLoader


def _write_addon(root: Path, addon_id: str = "demo-core", version: str = "1.0.0") -> Path:
    addon_dir = root / addon_id / version
    connector_dir = addon_dir / "connector"
    connector_dir.mkdir(parents=True)

    (addon_dir / "addon.json").write_text(
        json.dumps(
            {
                "id": addon_id,
                "version": version,
                "name": "Demo",
                "vendor": "Demo",
                "category": "demo",
                "description": "demo",
                "provider": {"type": "demo", "auth": {"kind": "none", "fields": []}},
                "entrypoint": "connector",
            }
        )
    )
    (connector_dir / "__init__.py").write_text(
        "class _C:\n"
        "    def health_check(self): return {'ok': True}\n"
        "    def get_widget_data(self, req): return {'data': req}\n"
        "    def ingest_events(self, since): return []\n"
        "    def close(self): pass\n"
        "def get_connector(config):\n"
        "    return _C()\n"
    )
    return addon_dir


def _record(
    path: Path,
    addon_id: str = "demo-core",
    version: str = "1.0.0",
) -> InstalledAddonRecord:
    return InstalledAddonRecord(
        id=addon_id,
        version=version,
        path=str(path),
        tag=f"{addon_id}-v{version}",
        sha256="a" * 64,
        status="active",
        installed_at=datetime.now(UTC),
    )


def test_loader_returns_get_connector_factory(tmp_path):
    addon_dir = _write_addon(tmp_path)
    loader = AddonLoader()

    factory = loader.load(_record(addon_dir))

    connector = factory({})
    assert connector.health_check() == {"ok": True}


def test_loader_uses_namespaced_module(tmp_path):
    addon_dir = _write_addon(tmp_path)
    loader = AddonLoader()

    loader.load(_record(addon_dir))

    assert "fortidashboard_addons.demo-core" in sys.modules


def test_loader_unload_clears_sys_modules(tmp_path):
    addon_dir = _write_addon(tmp_path)
    loader = AddonLoader()
    loader.load(_record(addon_dir))

    loader.unload("demo-core")

    assert "fortidashboard_addons.demo-core" not in sys.modules


def test_loader_rejects_missing_entrypoint(tmp_path):
    addon_dir = tmp_path / "broken" / "1.0.0"
    addon_dir.mkdir(parents=True)
    (addon_dir / "addon.json").write_text(
        json.dumps(
            {
                "id": "broken",
                "version": "1.0.0",
                "name": "Broken",
                "vendor": "x",
                "category": "x",
                "description": "x",
                "provider": {"type": "x", "auth": {"kind": "none", "fields": []}},
                "entrypoint": "connector",
            }
        )
    )

    with pytest.raises(AddonLoadError, match="entrypoint"):
        AddonLoader().load(_record(addon_dir, addon_id="broken"))


def test_loader_rejects_missing_get_connector(tmp_path):
    addon_dir = _write_addon(tmp_path, addon_id="no-factory")
    (addon_dir / "connector" / "__init__.py").write_text("# no get_connector\n")

    with pytest.raises(AddonLoadError, match="get_connector"):
        AddonLoader().load(_record(addon_dir, addon_id="no-factory"))


def test_loader_rejects_path_traversal_entrypoint(tmp_path):
    addon_dir = tmp_path / "traverse" / "1.0.0"
    (addon_dir / "connector").mkdir(parents=True)
    (addon_dir / "addon.json").write_text(
        json.dumps(
            {
                "id": "traverse",
                "version": "1.0.0",
                "name": "x",
                "vendor": "x",
                "category": "x",
                "description": "x",
                "provider": {"type": "x", "auth": {"kind": "none", "fields": []}},
                "entrypoint": "../../etc",
            }
        )
    )

    with pytest.raises(AddonLoadError, match="entrypoint"):
        AddonLoader().load(_record(addon_dir, addon_id="traverse"))
