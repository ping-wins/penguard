from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_private.cli import collect_windows_security_events
from agent_private.logs import append_agent_log
from agent_private.state import default_state_path, load_state, save_state

CURSOR_KEY = "windowsSecurityLastRecordId"


def collect_new_windows_security_events(
    limit: int = 50,
    *,
    state_path: Path | None = None,
    collector=collect_windows_security_events,
) -> list[dict[str, Any]]:
    events = collector(limit)
    max_record_id = _max_record_id(events)
    if max_record_id is None:
        return []

    path = state_path or default_state_path()
    state = load_state(path)
    last_record_id = _coerce_record_id(state.get(CURSOR_KEY))
    state[CURSOR_KEY] = max(max_record_id, last_record_id or 0)
    save_state(state, path)

    if last_record_id is None:
        append_agent_log(
            f"initialized Windows Security cursor at record {max_record_id}; "
            "future intervals will forward new records"
        )
        return []

    fresh = [
        event
        for event in events
        if (_coerce_record_id(event.get("recordId")) or 0) > last_record_id
    ]
    return sorted(fresh, key=lambda event: _coerce_record_id(event.get("recordId")) or 0)


def _max_record_id(events: list[dict[str, Any]]) -> int | None:
    ids = [
        record_id
        for event in events
        if (record_id := _coerce_record_id(event.get("recordId"))) is not None
    ]
    return max(ids) if ids else None


def _coerce_record_id(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None
