import json
from pathlib import Path
from typing import Any

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "packages" / "contracts" / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    fixture_path = FIXTURES_DIR / f"{name}.json"
    with fixture_path.open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)
