from datetime import UTC, datetime
from typing import Any


def normalize_system_status(
    raw: dict[str, Any],
    *,
    performance: dict[str, Any] | None = None,
    resource_usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = {
        "hostname": _string(raw, "hostname", "host_name"),
        "model": _string(raw, "model_name", "model", "model_number"),
        "version": _string(raw, "version", "firmware_version"),
        "serial": _string(raw, "serial", "serial_number", default=None),
        "cpu": _cpu_percent(raw, performance),
        "memory": _memory_percent(raw, performance),
        "sessions": _session_count(raw, resource_usage),
        "uptimeSeconds": _integer(raw, "uptime", "uptime_seconds", "uptimeSeconds"),
    }
    build = _integer(raw, "build")
    if build is not None:
        normalized["build"] = build
    return normalized


def normalize_interfaces(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for item in raw:
        name = str(item.get("name", ""))
        normalized.append(
            {
                "id": name,
                "name": name,
                "alias": _string(item, "alias", default=""),
                "status": _string(item, "status", default="unknown"),
                "ip": _interface_ip(item.get("ip")),
                "role": _string(item, "role", default="unknown"),
                "type": _string(item, "type", default="unknown"),
            }
        )
    return normalized


def normalize_policies(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for item in raw:
        normalized.append(
            {
                "id": str(item.get("policyid", item.get("id", ""))),
                "name": _string(item, "name", default=""),
                "status": _policy_status(item.get("status")),
                "action": _string(item, "action", default="unknown"),
                "sourceInterfaces": _named_list(item.get("srcintf")),
                "destinationInterfaces": _named_list(item.get("dstintf")),
                "services": _named_list(item.get("service")),
                "schedule": _string(item, "schedule", default=""),
            }
        )
    return normalized


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


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _interface_ip(value: Any) -> str:
    if not value:
        return ""
    return str(value).split()[0]


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


def _timestamp(value: int) -> str:
    return datetime.fromtimestamp(value, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
