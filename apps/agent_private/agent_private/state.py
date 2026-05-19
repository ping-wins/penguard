from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def default_state_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData"))
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "agent_private" / "state.json"


def load_state(path: Path | None = None) -> dict[str, Any]:
    state_path = path or default_state_path()
    if not state_path.exists():
        return {}
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_state(state: dict[str, Any], path: Path | None = None) -> None:
    state_path = path or default_state_path()
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    except OSError:
        return
    if os.name != "nt":
        state_path.chmod(0o600)
