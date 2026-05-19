from __future__ import annotations

import os
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_LOG_LIMIT = 24_000


def default_log_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData"))
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "agent_private" / "logs"


def agent_log_path(name: str = "agent.log") -> Path:
    safe_name = name.replace("\\", "_").replace("/", "_")
    return default_log_dir() / safe_name


def append_agent_log(message: str, *, name: str = "agent.log", secrets: Iterable[str] = ()) -> None:
    path = agent_log_path(name)
    timestamp = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    line = f"{timestamp} {redact_text(message, secrets)}\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
    except OSError:
        return


def read_recent_log(name: str = "agent.log", *, limit: int = DEFAULT_LOG_LIMIT) -> str:
    path = agent_log_path(name)
    if not path.exists():
        return ""
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            data = handle.read()
    except OSError as exc:
        return f"Unable to read {path}: {exc}"
    return data.decode("utf-8", errors="replace")


def list_log_files() -> list[dict[str, object]]:
    directory = default_log_dir()
    if not directory.exists():
        return []
    rows: list[dict[str, object]] = []
    for path in sorted(directory.glob("*")):
        if not path.is_file():
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        rows.append({"path": str(path), "sizeBytes": stat.st_size})
    return rows


def redact_text(value: str, secrets: Iterable[str] = ()) -> str:
    redacted = value
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[redacted]")
    return redacted
