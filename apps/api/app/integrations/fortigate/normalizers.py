import re
from datetime import UTC, datetime
from typing import Any


def normalize_system_status(
    raw: dict[str, Any],
    *,
    performance: dict[str, Any] | None = None,
    resource_usage: dict[str, Any] | None = None,
    web_ui_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = {
        "hostname": _string(raw, "hostname", "host_name"),
        "model": _string(raw, "model_name", "model", "model_number"),
        "version": _string(raw, "version", "firmware_version"),
        "serial": _string(raw, "serial", "serial_number", default=None),
        "cpu": _cpu_percent(raw, performance),
        "memory": _memory_percent(raw, performance),
        "sessions": _session_count(raw, resource_usage),
        "uptimeSeconds": _uptime_seconds(raw, performance, web_ui_state),
    }
    build = _integer(raw, "build")
    if build is not None:
        normalized["build"] = build
    return normalized


def normalize_interfaces(
    raw: list[dict[str, Any]] | dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized = []
    items = raw.items() if isinstance(raw, dict) else ((None, item) for item in raw)
    for key, item in items:
        name = str(item.get("name") or item.get("id") or key or "")
        normalized.append(
            {
                "id": name,
                "name": name,
                "alias": _string(item, "alias", default=""),
                "status": _interface_status(item),
                "ip": _interface_ip(item.get("ip")),
                "role": _string(item, "role", default="unknown"),
                "type": _string(item, "type", default="unknown"),
                "rxBytes": _coerce_int(item.get("rx_bytes")) or 0,
                "txBytes": _coerce_int(item.get("tx_bytes")) or 0,
                "rxPackets": _coerce_int(item.get("rx_packets")) or 0,
                "txPackets": _coerce_int(item.get("tx_packets")) or 0,
            }
        )
    return normalized


def normalize_policies(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for item in raw:
        name = _string(item, "name", default="") or ""
        action = (_string(item, "action", default="unknown") or "unknown").lower()
        comments = _string(item, "comments", "comment", default="") or ""
        normalized.append(
            {
                "id": str(item.get("policyid", item.get("id", ""))),
                "name": name,
                "status": _policy_status(item.get("status")),
                "action": action,
                "sourceInterfaces": _named_list(item.get("srcintf")),
                "destinationInterfaces": _named_list(item.get("dstintf")),
                "services": _named_list(item.get("service")),
                "schedule": _string(item, "schedule", default=""),
                "sourceAddresses": _named_list(item.get("srcaddr")),
                "destinationAddresses": _named_list(item.get("dstaddr")),
                "logging": _string(item, "logtraffic", "logTraffic", default="") or "",
                "comments": comments,
                "isBlocking": _policy_is_blocking(action),
                "isPenguardOwned": _policy_is_penguard_owned(name, comments),
                "policyKind": _policy_kind(name),
            }
        )
    return normalized


def normalize_admin_login_failures(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in raw:
        if str(item.get("status") or "").lower() != "failed":
            continue
        if str(item.get("action") or "").lower() != "login":
            continue
        timestamp_value = _event_timestamp(item)
        source_ip = _string(item, "srcip", "source_ip", default="") or ""
        user_name = _string(item, "user", default="") or ""
        normalized.append(
            {
                "id": f"admin-login-fail-{timestamp_value}-{source_ip}-{user_name}",
                "timestamp": _timestamp(timestamp_value),
                "type": "event",
                "subtype": "admin_login_failed",
                "severity": _string(item, "level", "severity", default="medium"),
                "sourceIp": source_ip,
                "destinationIp": "",
                "action": "login_failed",
                "eventType": "auth.failed_login",
                "user": user_name,
                "message": _string(item, "msg", "logdesc", "message", default=""),
            }
        )
    return normalized


def _event_timestamp(item: dict[str, Any]) -> int:
    raw = item.get("eventtime") or item.get("itime") or item.get("timestamp") or 0
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    if value > 10_000_000_000_000_000:
        value //= 1_000_000_000
    elif value > 10_000_000_000_000:
        value //= 1_000_000
    elif value > 10_000_000_000:
        value //= 1_000
    return value


def normalize_threat_logs(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for item in raw:
        timestamp_value = int(item.get("itime", item.get("timestamp", 0)) or 0)
        subtype = _string(item, "subtype", default="unknown")
        source_ip = _string(item, "srcip", "source_ip", default="")
        destination_ip = _string(item, "dstip", "destination_ip", default="")
        normalized.append(
            {
                "id": f"{timestamp_value}-{source_ip}-{destination_ip}-{subtype}",
                "timestamp": _timestamp(timestamp_value),
                "type": _string(item, "type", default="unknown"),
                "subtype": subtype,
                "severity": _string(item, "severity", "level", default="unknown"),
                "sourceIp": source_ip,
                "destinationIp": destination_ip,
                "action": _string(item, "action", default="unknown"),
                "message": _string(item, "msg", "message", default=""),
            }
        )
    return normalized


def _string(
    data: dict[str, Any],
    *keys: str,
    default: str | None = "unknown",
) -> str | None:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return str(value)
    return default


def _integer(data: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None


def _cpu_percent(raw: dict[str, Any], performance: dict[str, Any] | None) -> int | None:
    direct = _integer(raw, "cpu", "cpu_usage")
    if direct is not None:
        return direct
    if performance is None or not isinstance(performance.get("cpu"), dict):
        return None
    cpu = performance["cpu"]
    if "current" in cpu:
        return _coerce_int(cpu["current"])
    if "idle" in cpu:
        idle = _coerce_int(cpu["idle"])
        return None if idle is None else max(0, min(100, 100 - idle))
    total = 0
    for key in ("user", "system", "nice", "iowait"):
        value = _coerce_int(cpu.get(key))
        if value is not None:
            total += value
    return total


def _memory_percent(raw: dict[str, Any], performance: dict[str, Any] | None) -> int | None:
    direct = _integer(raw, "mem", "memory", "memory_usage")
    if direct is not None:
        return direct
    if performance is None or not isinstance(performance.get("mem"), dict):
        return None
    mem = performance["mem"]
    used = _coerce_int(mem.get("used"))
    total = _coerce_int(mem.get("total"))
    if used is None or total in (None, 0):
        return None
    return round((used / total) * 100)


def _session_count(raw: dict[str, Any], resource_usage: dict[str, Any] | None) -> int | None:
    direct = _integer(raw, "current_sessions", "sessions", "session_count")
    if direct is not None:
        return direct
    if resource_usage is None:
        return None
    session = resource_usage.get("session")
    if isinstance(session, list) and session:
        first = session[0]
        if isinstance(first, dict):
            return _coerce_int(first.get("current"))
    if isinstance(session, dict):
        return _coerce_int(session.get("current"))
    return None


def _uptime_seconds(
    raw: dict[str, Any],
    performance: dict[str, Any] | None,
    web_ui_state: dict[str, Any] | None,
) -> int | None:
    direct = _duration_seconds_from_keys(raw, "uptime", "uptime_seconds", "uptimeSeconds")
    if direct is not None:
        return direct
    if performance is not None:
        performance_uptime = _duration_seconds_from_keys(
            performance,
            "uptime",
            "uptime_seconds",
            "uptimeSeconds",
        )
        if performance_uptime is not None:
            return performance_uptime
    if web_ui_state is None:
        return None
    return _web_ui_state_uptime_seconds(web_ui_state)


def _duration_seconds_from_keys(data: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            parsed = _duration_seconds(value)
            if parsed is not None:
                return parsed
    return None


def _duration_seconds(value: Any) -> int | None:
    direct = _coerce_int(value)
    if direct is not None:
        return direct
    if not isinstance(value, str):
        return None

    normalized = value.strip().lower()
    if not normalized:
        return None

    total = 0
    matched = False
    unit_seconds = {
        "day": 86400,
        "days": 86400,
        "hour": 3600,
        "hours": 3600,
        "hr": 3600,
        "hrs": 3600,
        "minute": 60,
        "minutes": 60,
        "min": 60,
        "mins": 60,
        "second": 1,
        "seconds": 1,
        "sec": 1,
        "secs": 1,
    }
    for amount, unit in re.findall(r"(\d+)\s*([a-z]+)", normalized):
        if unit in unit_seconds:
            total += int(amount) * unit_seconds[unit]
            matched = True

    if matched:
        return total

    colon_parts = normalized.split(":")
    if len(colon_parts) in {2, 3} and all(part.isdigit() for part in colon_parts):
        numbers = [int(part) for part in colon_parts]
        if len(numbers) == 2:
            minutes, seconds = numbers
            return minutes * 60 + seconds
        hours, minutes, seconds = numbers
        return hours * 3600 + minutes * 60 + seconds

    return None


def _web_ui_state_uptime_seconds(web_ui_state: dict[str, Any]) -> int | None:
    snapshot = _epoch_seconds(web_ui_state.get("snapshot_utc_time"))
    last_reboot = _epoch_seconds(web_ui_state.get("utc_last_reboot"))
    if snapshot is None or last_reboot is None or snapshot < last_reboot:
        return None
    return int(snapshot - last_reboot)


def _epoch_seconds(value: Any) -> float | None:
    numeric = _coerce_int(value)
    if numeric is None:
        return None
    if numeric > 1_000_000_000_000:
        return numeric / 1000
    return float(numeric)


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _interface_ip(value: Any) -> str:
    if not value:
        return ""
    return str(value).split()[0]


def _interface_status(item: dict[str, Any]) -> str:
    if "link" in item:
        return "up" if item.get("link") else "down"
    return str(_string(item, "status", default="unknown"))


def _named_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names = []
    for item in value:
        if isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
        elif isinstance(item, str):
            names.append(item)
    return names


def _policy_status(value: Any) -> str:
    if value == "enable":
        return "enabled"
    if value == "disable":
        return "disabled"
    if value:
        return str(value)
    return "unknown"


def _policy_is_blocking(action: str) -> bool:
    return action.lower() in {"deny", "block", "blocked", "reject"}


def _policy_is_penguard_owned(name: str, comments: str) -> bool:
    return name.startswith("PG_") or "penguard owned" in comments.lower()


def _policy_kind(name: str) -> str:
    if name.startswith("PG_TMP_BLOCK_"):
        return "temporary_block"
    if name.startswith("PG_LAB_ALLOW_"):
        return "lab_allow_log"
    if name.startswith("PG_"):
        return "penguard"
    return "standard"


def _timestamp(value: int) -> str:
    return datetime.fromtimestamp(value, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
