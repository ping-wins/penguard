import importlib.util
import sys
from pathlib import Path

import pytest

# The external packages repo sits next to the dashboard checkout.
PKGS = Path(__file__).resolve().parents[4] / "fortidashboard-addons"

CASES = [
    ("fortigate-core", "0.2.0"),
    ("fortiweb-core", "8.0.5"),
    ("penguin-siem", "1.0.0"),
    ("penguin-xdr", "1.0.0"),
    ("penguin-soar", "1.0.0"),
]


def _load(addon_id: str, version: str):
    entry = PKGS / addon_id / version / "connector" / "__init__.py"
    module_name = f"pkgtest_{addon_id.replace('-', '_')}_{version.replace('.', '_')}"
    spec = importlib.util.spec_from_file_location(
        module_name,
        entry,
        submodule_search_locations=[str(entry.parent)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load connector module from {entry}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


@pytest.mark.parametrize("addon_id,version", CASES)
def test_get_connector_present_and_missing_host_is_graceful(addon_id: str, version: str) -> None:
    if not (PKGS / addon_id / version / "addon.json").is_file():
        pytest.skip(f"{addon_id} package not present at {PKGS}")
    module = _load(addon_id, version)
    connector = module.get_connector({"host": ""})
    result = connector.health_check()
    assert result["ok"] is False
    assert result["status"] == "missing_host"
    connector.close()


def test_soar_package_exposes_playbook_actions() -> None:
    if not (PKGS / "penguin-soar" / "1.0.0" / "addon.json").is_file():
        pytest.skip("penguin-soar package not present")
    module = _load("penguin-soar", "1.0.0")
    connector = module.get_connector({"host": "http://x"})
    actions = connector.list_playbook_actions()
    assert any(action["id"] == "run_skipper_playbook" for action in actions)
