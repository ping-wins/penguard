import json
from pathlib import Path

from app.integrations.catalog import build_catalog


class _Rec:
    def __init__(self, id: str, version: str, path: str) -> None:
        self.id = id
        self.version = version
        self.path = path


def _write_manifest(tmp_path: Path) -> _Rec:
    pkg = tmp_path / "fortiweb-core" / "8.0.5"
    pkg.mkdir(parents=True)
    (pkg / "addon.json").write_text(
        json.dumps(
            {
                "id": "fortiweb-core",
                "version": "8.0.5",
                "name": "FortiWeb Core",
                "vendor": "Fortinet",
                "category": "waf",
                "description": "x",
                "provider": {
                    "type": "fortiweb",
                    "auth": {
                        "kind": "apiKey",
                        "fields": [
                            {
                                "id": "host",
                                "label": "URL",
                                "type": "url",
                                "required": True,
                            }
                        ],
                    },
                },
                "compatibility": {"testedVersions": ["8.0.5"]},
                "capabilities": {
                    "logSource": True,
                    "playbookTarget": True,
                    "managed": True,
                },
            }
        ),
        encoding="utf-8",
    )
    return _Rec("fortiweb-core", "8.0.5", str(pkg))


def test_build_catalog_reads_installed_manifest(tmp_path: Path) -> None:
    rec = _write_manifest(tmp_path)
    catalog = build_catalog([rec])
    assert len(catalog) == 1
    entry = catalog[0]
    assert entry["addonId"] == "fortiweb-core"
    assert entry["vendor"] == "Fortinet"
    assert entry["versions"] == ["8.0.5"]
    assert entry["authFields"][0]["id"] == "host"
    assert entry["capabilities"] == {
        "logSource": True,
        "playbookTarget": True,
        "managed": True,
    }


def test_build_catalog_skips_records_without_manifest(tmp_path: Path) -> None:
    assert build_catalog([_Rec("ghost", "1.0.0", str(tmp_path / "nope"))]) == []
