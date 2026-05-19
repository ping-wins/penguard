from __future__ import annotations

import argparse
import contextlib
import getpass
import io
import json
import os
import platform
import socket
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import httpx
import psutil
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from agent_private import windows_service
from agent_private.control import AgentControlClient
from agent_private.discovery import (
    DEFAULT_DISCOVERY_PORT,
    DEFAULT_DISCOVERY_TIMEOUT_SECONDS,
    discover_dashboard,
)

DEFAULT_TIMEOUT_SECONDS = 5.0
DEMO_OCCURRED_AT = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
WINDOWS_SECURITY_EVENT_IDS = (4625, 4672, 4663)
DEFAULT_CONTROL_URL = "http://127.0.0.1:8765"


def format_timestamp(value: datetime | None = None) -> str:
    timestamp = value or datetime.now(UTC)
    return timestamp.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def build_identity_payload(
    hostname: str | None = None,
    username: str | None = None,
    os_name: str | None = None,
) -> dict[str, str]:
    return {
        "service": "agent_private",
        "hostname": hostname or socket.gethostname(),
        "username": username or getpass.getuser(),
        "os": os_name or platform.system(),
    }


def get_ip_addresses() -> list[str]:
    addresses: set[str] = set()
    for rows in psutil.net_if_addrs().values():
        for row in rows:
            if row.family in {socket.AF_INET, socket.AF_INET6} and row.address:
                if not row.address.startswith("127.") and row.address != "::1":
                    addresses.add(row.address.split("%", maxsplit=1)[0])
    return sorted(addresses)


def build_endpoint_event(
    *,
    endpoint_id: str,
    event_type: str,
    hostname: str,
    ip_addresses: Sequence[str],
    attributes: dict[str, Any],
    current_user: str | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "endpointId": endpoint_id,
        "eventType": event_type,
        "occurredAt": format_timestamp(occurred_at),
        "hostname": hostname,
        "ipAddresses": list(ip_addresses),
        "attributes": attributes,
    }
    if current_user is not None:
        payload["currentUser"] = current_user
    return payload


def build_heartbeat_payload(
    *,
    endpoint_id: str,
    identity: dict[str, str],
    ip_addresses: Sequence[str],
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    return build_endpoint_event(
        endpoint_id=endpoint_id,
        event_type="heartbeat",
        hostname=identity["hostname"],
        ip_addresses=ip_addresses,
        occurred_at=occurred_at,
        current_user=identity["username"],
        attributes={
            "service": identity["service"],
            "username": identity["username"],
            "os": identity["os"],
        },
    )


def _memory_rss_bytes(memory_info: Any) -> int | None:
    return getattr(memory_info, "rss", None) if memory_info is not None else None


def normalize_process(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "pid": row.get("pid"),
        "name": row.get("name"),
        "username": row.get("username"),
        "status": row.get("status"),
        "cpuPercent": row.get("cpuPercent", row.get("cpu_percent")),
        "memoryRssBytes": row.get(
            "memoryRssBytes",
            _memory_rss_bytes(row.get("memory_info")),
        ),
    }


def collect_processes(limit: int | None = None) -> list[dict[str, Any]]:
    attrs = ["pid", "name", "username", "status", "cpu_percent", "memory_info"]
    rows: list[dict[str, Any]] = []
    for process in psutil.process_iter(attrs=attrs):
        try:
            rows.append(normalize_process(process.info))
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
        if limit is not None and len(rows) >= limit:
            break
    return rows


def build_process_snapshot_payload(
    *,
    endpoint_id: str,
    hostname: str,
    ip_addresses: Sequence[str],
    processes: Iterable[dict[str, Any]],
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    return build_endpoint_event(
        endpoint_id=endpoint_id,
        event_type="process.snapshot",
        hostname=hostname,
        ip_addresses=ip_addresses,
        occurred_at=occurred_at,
        attributes={"processes": [normalize_process(row) for row in processes]},
    )


def _socket_constant_name(
    enum_type: type[socket.AddressFamily] | type[socket.SocketKind],
    value: Any,
) -> str:
    try:
        return enum_type(value).name
    except ValueError:
        return str(value)


def _address_payload(address: Any) -> dict[str, Any] | None:
    if not address:
        return None
    if isinstance(address, dict):
        ip = address.get("ip")
        port = address.get("port")
        if ip is None and port is None:
            return None
        return {"ip": ip, "port": port}
    if hasattr(address, "ip") and hasattr(address, "port"):
        return {"ip": address.ip, "port": address.port}
    if isinstance(address, tuple) and len(address) >= 2:
        return {"ip": address[0], "port": address[1]}
    return {"ip": str(address), "port": None}


def _connection_value(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def normalize_connection(row: Any) -> dict[str, Any]:
    local_address = _connection_value(row, "localAddress", _connection_value(row, "laddr"))
    remote_address = _connection_value(row, "remoteAddress", _connection_value(row, "raddr"))
    return {
        "fd": _connection_value(row, "fd"),
        "family": _socket_constant_name(socket.AddressFamily, _connection_value(row, "family", "")),
        "type": _socket_constant_name(socket.SocketKind, _connection_value(row, "type", "")),
        "localAddress": _address_payload(local_address),
        "remoteAddress": _address_payload(remote_address),
        "status": _connection_value(row, "status"),
        "pid": _connection_value(row, "pid"),
    }


def collect_connections() -> list[dict[str, Any]]:
    try:
        connections = psutil.net_connections(kind="inet")
    except psutil.AccessDenied:
        return []
    return [normalize_connection(row) for row in connections]


def build_connection_snapshot_payload(
    *,
    endpoint_id: str,
    hostname: str,
    ip_addresses: Sequence[str],
    connections: Iterable[Any],
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    return build_endpoint_event(
        endpoint_id=endpoint_id,
        event_type="connection.snapshot",
        hostname=hostname,
        ip_addresses=ip_addresses,
        occurred_at=occurred_at,
        attributes={"connections": [normalize_connection(row) for row in connections]},
    )


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]


def _parse_windows_system_time(value: str | None) -> str:
    if not value:
        return format_timestamp()
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    if "." in normalized:
        prefix, suffix = normalized.split(".", maxsplit=1)
        fraction = suffix
        timezone = ""
        for marker in ("+", "-"):
            if marker in suffix:
                fraction, timezone = suffix.split(marker, maxsplit=1)
                timezone = marker + timezone
                break
        normalized = f"{prefix}.{fraction[:6].ljust(6, '0')}{timezone}"
    return format_timestamp(datetime.fromisoformat(normalized).astimezone(UTC))


def parse_windows_security_events(raw_xml: str) -> list[dict[str, Any]]:
    sanitized = raw_xml.replace('<?xml version="1.0" encoding="utf-8"?>', "").strip()
    if not sanitized:
        return []
    root = ET.fromstring(f"<Events>{sanitized}</Events>")
    parsed: list[dict[str, Any]] = []
    for event in [item for item in root.iter() if _xml_local_name(item.tag) == "Event"]:
        system = next(
            (item for item in event if _xml_local_name(item.tag) == "System"),
            None,
        )
        event_data = next(
            (item for item in event if _xml_local_name(item.tag) == "EventData"),
            None,
        )
        if system is None:
            continue
        system_values: dict[str, str] = {}
        for item in system:
            name = _xml_local_name(item.tag)
            if name == "TimeCreated":
                system_values[name] = item.attrib.get("SystemTime", "")
            elif item.text:
                system_values[name] = item.text
        event_id = system_values.get("EventID")
        if event_id is None:
            continue
        data: dict[str, str] = {}
        if event_data is not None:
            for item in event_data:
                if _xml_local_name(item.tag) == "Data":
                    name = item.attrib.get("Name")
                    if name:
                        data[name] = item.text or ""
        parsed.append(
            {
                "eventId": int(event_id),
                "occurredAt": _parse_windows_system_time(system_values.get("TimeCreated")),
                "computer": system_values.get("Computer", ""),
                "recordId": system_values.get("EventRecordID", ""),
                "data": data,
            }
        )
    return parsed


def collect_windows_security_events(limit: int = 50) -> list[dict[str, Any]]:
    if platform.system() != "Windows":
        return []
    query = "*[System[(" + " or ".join(
        f"EventID={event_id}" for event_id in WINDOWS_SECURITY_EVENT_IDS
    ) + ")]]"
    result = subprocess.run(
        [
            "wevtutil",
            "qe",
            "Security",
            f"/q:{query}",
            "/f:xml",
            f"/c:{limit}",
            "/rd:true",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return parse_windows_security_events(result.stdout)


def _first_present(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _domain_user(data: dict[str, Any], user_key: str, domain_key: str) -> str | None:
    username = _first_present(data, user_key)
    if username is None or username == "-":
        return None
    domain = _first_present(data, domain_key)
    if domain and domain != "-":
        return f"{domain}\\{username}"
    return username


def _path_is_under(path: str, roots: Sequence[str]) -> bool:
    normalized = path.replace("/", "\\").rstrip("\\").casefold()
    for root in roots:
        root_normalized = root.replace("/", "\\").rstrip("\\").casefold()
        if normalized == root_normalized or normalized.startswith(f"{root_normalized}\\"):
            return True
    return False


def build_windows_security_event_payloads(
    *,
    endpoint_id: str,
    hostname: str,
    ip_addresses: Sequence[str],
    events: Iterable[dict[str, Any]],
    allowed_admin_hosts: Sequence[str] = (),
    critical_paths: Sequence[str] = (),
) -> list[dict[str, Any]]:
    failed_logons: dict[tuple[str, str], dict[str, Any]] = {}
    payloads: list[dict[str, Any]] = []
    allowed_hosts = {host.casefold() for host in allowed_admin_hosts}

    for event in events:
        event_id = event.get("eventId")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        occurred_at = str(event.get("occurredAt") or format_timestamp())
        record_id = str(event.get("recordId") or "")

        if event_id == 4625:
            username = _domain_user(data, "TargetUserName", "TargetDomainName") or "unknown"
            source_ip = _first_present(data, "IpAddress", "WorkstationName") or "unknown"
            key = (username, source_ip)
            group = failed_logons.setdefault(
                key,
                {
                    "occurredAt": occurred_at,
                    "recordIds": [],
                    "count": 0,
                    "username": username,
                    "sourceIp": source_ip,
                },
            )
            group["occurredAt"] = max(str(group["occurredAt"]), occurred_at)
            group["recordIds"].append(record_id)
            group["count"] += 1
            continue

        if event_id == 4672:
            username = _domain_user(data, "SubjectUserName", "SubjectDomainName") or "unknown"
            payloads.append(
                {
                    "endpointId": endpoint_id,
                    "eventType": "auth.privileged_logon",
                    "occurredAt": occurred_at,
                    "hostname": hostname,
                    "ipAddresses": list(ip_addresses),
                    "currentUser": username,
                    "attributes": {
                        "source": "agent_private.windows_security",
                        "windowsEventId": 4672,
                        "recordId": record_id,
                        "username": username,
                        "privileged": True,
                        "unusualHost": bool(allowed_hosts)
                        and hostname.casefold() not in allowed_hosts,
                        "privileges": _first_present(data, "PrivilegeList") or "",
                    },
                }
            )
            continue

        if event_id == 4663:
            username = _domain_user(data, "SubjectUserName", "SubjectDomainName") or "unknown"
            object_name = _first_present(data, "ObjectName") or ""
            payloads.append(
                {
                    "endpointId": endpoint_id,
                    "eventType": "file.change",
                    "occurredAt": occurred_at,
                    "hostname": hostname,
                    "ipAddresses": list(ip_addresses),
                    "currentUser": username,
                    "attributes": {
                        "source": "agent_private.windows_security",
                        "windowsEventId": 4663,
                        "recordId": record_id,
                        "username": username,
                        "objectName": object_name,
                        "accesses": _first_present(data, "Accesses") or "",
                        "criticalPath": bool(object_name)
                        and _path_is_under(object_name, critical_paths),
                    },
                }
            )

    for group in failed_logons.values():
        payloads.insert(
            0,
            {
                "endpointId": endpoint_id,
                "eventType": "auth.failed_login",
                "occurredAt": group["occurredAt"],
                "hostname": hostname,
                "ipAddresses": list(ip_addresses),
                "currentUser": group["username"],
                "attributes": {
                    "source": "agent_private.windows_security",
                    "windowsEventId": 4625,
                    "count": group["count"],
                    "username": group["username"],
                    "sourceIp": group["sourceIp"],
                    "recordIds": group["recordIds"],
                },
            },
        )
    return payloads


def build_simulated_events(endpoint_id: str) -> list[dict[str, Any]]:
    identity = build_identity_payload(
        hostname="demo-endpoint-01",
        username="SOC-DEMO\\analyst",
        os_name="Linux",
    )
    ip_addresses = ["192.0.2.50"]
    return [
        build_heartbeat_payload(
            endpoint_id=endpoint_id,
            identity=identity,
            ip_addresses=ip_addresses,
            occurred_at=DEMO_OCCURRED_AT,
        ),
        build_process_snapshot_payload(
            endpoint_id=endpoint_id,
            hostname=identity["hostname"],
            ip_addresses=ip_addresses,
            occurred_at=DEMO_OCCURRED_AT,
            processes=[
                {
                    "pid": 1200,
                    "name": "powershell.exe",
                    "username": identity["username"],
                    "status": "running",
                    "cpu_percent": 3.2,
                    "memory_info": type("Memory", (), {"rss": 123456})(),
                }
            ],
        ),
        build_connection_snapshot_payload(
            endpoint_id=endpoint_id,
            hostname=identity["hostname"],
            ip_addresses=ip_addresses,
            occurred_at=DEMO_OCCURRED_AT,
            connections=[
                type(
                    "Connection",
                    (),
                    {
                        "fd": 7,
                        "family": socket.AF_INET,
                        "type": socket.SOCK_STREAM,
                        "laddr": ("192.0.2.50", 54122),
                        "raddr": ("198.51.100.20", 443),
                        "status": "ESTABLISHED",
                        "pid": 1200,
                    },
                )()
            ],
        ),
    ]


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.25, max=2),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError)),
    reraise=True,
)
def post_endpoint_event(
    *,
    api_url: str,
    enrollment_token: str,
    payload: dict[str, Any],
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> None:
    endpoint = f"{api_url.rstrip('/')}/api/weapons/endpoint-events"
    response = httpx.post(
        endpoint,
        headers={"Authorization": f"Bearer {enrollment_token}"},
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()


def print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def pair_with_dashboard(
    *,
    enrollment_token: str,
    api_url: str | None = None,
    discovery_timeout: float = DEFAULT_DISCOVERY_TIMEOUT_SECONDS,
    discovery_port: int = DEFAULT_DISCOVERY_PORT,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
):
    from agent_private.tui import AgentPrivateConfig

    resolved_api_url = api_url.rstrip("/") if api_url else discover_dashboard(
        timeout_seconds=discovery_timeout,
        port=discovery_port,
    ).api_url
    identity, ip_addresses = _identity_context()
    response = httpx.post(
        f"{resolved_api_url}/api/weapons/agent/pair",
        json={
            "enrollmentToken": enrollment_token,
            "hostname": identity["hostname"],
            "ipAddresses": ip_addresses,
            "currentUser": identity["username"],
            "os": identity["os"],
            "agentVersion": "0.1.0",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    endpoint_id = payload.get("endpointId")
    if not isinstance(endpoint_id, str) or not endpoint_id:
        raise RuntimeError("Pairing response did not include endpointId.")
    return AgentPrivateConfig(
        api_url=resolved_api_url,
        endpoint_id=endpoint_id,
        enrollment_token=enrollment_token,
    )


def run_service_command_with_reporting(service_action: str) -> dict[str, Any]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    error: BaseException | None = None
    result: dict[str, Any]
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            result = windows_service.run_service_command(service_action)
        except BaseException as exc:  # noqa: BLE001
            if isinstance(exc, KeyboardInterrupt):
                raise
            error = exc
            result = {"service": windows_service.SERVICE_NAME, "action": service_action}

    stdout_text = stdout.getvalue().strip()
    stderr_text = stderr.getvalue().strip()
    service_status_payload = _service_status_payload()
    outcome = _service_command_outcome(
        service_action,
        stdout_text=stdout_text,
        stderr_text=stderr_text,
        error=error,
        service_status_payload=service_status_payload,
    )
    payload: dict[str, Any] = {
        **result,
        "action": result.get("action", service_action),
        "outcome": outcome,
    }
    if service_status_payload is not None:
        payload["serviceStatus"] = service_status_payload
    if stdout_text:
        payload["stdout"] = _truncate_log(stdout_text)
    if stderr_text:
        payload["stderr"] = _truncate_log(stderr_text)
    if error is not None:
        payload["error"] = _truncate_log(str(error))

    payload["telemetry"] = _report_service_command(payload)
    return payload


def _service_status_payload() -> dict[str, str] | None:
    try:
        return windows_service.service_status()
    except Exception:  # noqa: BLE001
        return None


def _service_command_outcome(
    service_action: str,
    *,
    stdout_text: str,
    stderr_text: str,
    error: BaseException | None,
    service_status_payload: dict[str, str] | None,
) -> str:
    if error is not None:
        return "failed"
    combined = f"{stdout_text}\n{stderr_text}".lower()
    if "error " in combined or "error:" in combined or "traceback" in combined:
        return "failed"
    status_name = service_status_payload.get("status") if service_status_payload else None
    if service_action == "start" and status_name != "running":
        return "failed"
    if service_action == "stop" and status_name not in {None, "stopped"}:
        return "failed"
    return "success"


def _report_service_command(command_payload: dict[str, Any]) -> dict[str, Any]:
    from agent_private.tui import load_config

    config = load_config()
    if not config.api_url or not config.endpoint_id or not config.enrollment_token:
        return {"sent": False, "reason": "agent config is incomplete"}

    identity, ip_addresses = _identity_context()
    outcome = str(command_payload.get("outcome") or "unknown")
    event = build_endpoint_event(
        endpoint_id=config.endpoint_id,
        event_type="health.signal",
        hostname=identity["hostname"],
        ip_addresses=ip_addresses,
        current_user=identity["username"],
        attributes={
            "source": "agent_private.windows_service",
            "service": command_payload.get("service"),
            "serviceAction": command_payload.get("action"),
            "outcome": outcome,
            "serviceStatus": command_payload.get("serviceStatus"),
            "stdout": command_payload.get("stdout"),
            "stderr": command_payload.get("stderr"),
            "error": command_payload.get("error"),
            "os": identity["os"],
        },
    )
    event["health"] = "warning" if outcome == "failed" else "healthy"
    try:
        post_endpoint_event(
            api_url=config.api_url,
            enrollment_token=config.enrollment_token,
            payload=event,
        )
    except Exception as exc:  # noqa: BLE001
        return {"sent": False, "reason": _truncate_log(str(exc))}
    return {"sent": True, "eventType": "health.signal"}


def _truncate_log(value: str, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}...<truncated>"


def run_tui() -> None:
    from agent_private.tui import run_tui as start_tui

    start_tui()


def _common_parent() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "--api-url",
        default=os.environ.get("AGENT_PRIVATE_API_URL"),
        help="Base URL for FortiDashboard API, for example http://localhost:8000.",
    )
    parent.add_argument(
        "--endpoint-id",
        default=os.environ.get("AGENT_PRIVATE_ENDPOINT_ID"),
    )
    parent.add_argument(
        "--enrollment-token",
        default=os.environ.get("AGENT_PRIVATE_ENROLLMENT_TOKEN"),
    )
    parent.add_argument("--post", action="store_true")
    return parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-private",
        description="Safe explicit FortiDashboard endpoint telemetry CLI.",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("tui", help="Open the interactive endpoint sensor TUI.")
    subparsers.add_parser("identity", help="Print host identity JSON.")
    common = _common_parent()
    subparsers.add_parser("heartbeat", parents=[common], help="Build or post a heartbeat event.")
    subparsers.add_parser(
        "process-snapshot",
        parents=[common],
        help="Build or post a process.snapshot endpoint event.",
    )
    subparsers.add_parser(
        "connection-snapshot",
        parents=[common],
        help="Build or post a connection.snapshot endpoint event.",
    )
    windows_security = subparsers.add_parser(
        "windows-security",
        parents=[common],
        help="Collect Windows Security Log events and build endpoint security events.",
    )
    windows_security.add_argument("--limit", type=int, default=50)
    windows_security.add_argument("--allowed-admin-host", action="append", default=[])
    windows_security.add_argument("--critical-path", action="append", default=[])
    subparsers.add_parser(
        "run",
        help="Open the interactive setup TUI and run the agent from there.",
    )
    daemon_parser = subparsers.add_parser(
        "daemon",
        parents=[common],
        help="Run the endpoint daemon in the foreground.",
    )
    daemon_parser.add_argument("--heartbeat-interval", type=float, default=30.0)
    daemon_parser.add_argument("--connection-interval", type=float, default=60.0)
    daemon_parser.add_argument("--process-interval", type=float, default=300.0)
    daemon_parser.add_argument("--windows-security-interval", type=float)
    daemon_parser.add_argument("--windows-security-limit", type=int, default=50)
    daemon_parser.add_argument("--control-port", type=int, default=8765)
    run_parser = subparsers.add_parser(
        "run-headless",
        parents=[common],
        help="Run the foreground endpoint sensor loop without the TUI.",
    )
    run_parser.add_argument("--heartbeat-interval", type=float, default=30.0)
    run_parser.add_argument("--connection-interval", type=float, default=60.0)
    run_parser.add_argument("--process-interval", type=float, default=300.0)
    run_parser.add_argument("--windows-security-interval", type=float)
    run_parser.add_argument("--windows-security-limit", type=int, default=50)
    run_parser.add_argument("--once", action="store_true")
    status_parser = subparsers.add_parser("status", help="Read status from the local daemon.")
    status_parser.add_argument("--control-url", default=DEFAULT_CONTROL_URL)
    collect_parser = subparsers.add_parser(
        "collect-now",
        help="Ask the local daemon to post telemetry now.",
    )
    collect_parser.add_argument(
        "kind",
        choices=["heartbeat", "processes", "connections", "windows-security", "all"],
    )
    collect_parser.add_argument("--control-url", default=DEFAULT_CONTROL_URL)
    pair_parser = subparsers.add_parser(
        "pair",
        help="Discover FortiDashboard on the VMware network and save local agent config.",
    )
    pair_parser.add_argument("enrollment_token")
    pair_parser.add_argument(
        "--api-url",
        help="Advanced fallback when UDP discovery is unavailable.",
    )
    pair_parser.add_argument(
        "--discovery-timeout",
        type=float,
        default=DEFAULT_DISCOVERY_TIMEOUT_SECONDS,
    )
    pair_parser.add_argument("--discovery-port", type=int, default=DEFAULT_DISCOVERY_PORT)
    config_parser = subparsers.add_parser("config", help="Read or update local daemon config.")
    config_subparsers = config_parser.add_subparsers(dest="config_command")
    config_subparsers.add_parser("show")
    config_set = config_subparsers.add_parser("set")
    config_set.add_argument("--api-url")
    config_set.add_argument("--endpoint-id")
    config_set.add_argument("--enrollment-token")
    service_parser = subparsers.add_parser("service", help="Manage the Windows Service.")
    service_parser.add_argument(
        "service_action",
        choices=["install", "start", "stop", "status", "uninstall"],
    )
    subparsers.add_parser("simulate", parents=[common], help="Print deterministic demo events.")
    return parser


def _require_endpoint_id(parser: argparse.ArgumentParser, args: argparse.Namespace) -> str:
    if not args.endpoint_id:
        parser.error("--endpoint-id or AGENT_PRIVATE_ENDPOINT_ID is required")
    return args.endpoint_id


def _post_if_requested(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    payload: dict[str, Any],
) -> None:
    if not args.post:
        return
    if not args.api_url:
        parser.error("--api-url or AGENT_PRIVATE_API_URL is required with --post")
    if not args.enrollment_token:
        parser.error("--enrollment-token or AGENT_PRIVATE_ENROLLMENT_TOKEN is required with --post")
    post_endpoint_event(
        api_url=args.api_url,
        enrollment_token=args.enrollment_token,
        payload=payload,
    )


def _identity_context() -> tuple[dict[str, str], list[str]]:
    return build_identity_payload(), get_ip_addresses()


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None or args.command in {"tui", "run"}:
        run_tui()
        return

    if args.command == "identity":
        print_json(build_identity_payload())
        return

    if args.command == "status":
        print_json(AgentControlClient(base_url=args.control_url).status())
        return

    if args.command == "collect-now":
        print_json(AgentControlClient(base_url=args.control_url).collect_now(args.kind))
        return

    if args.command == "pair":
        from agent_private.tui import save_config

        config = pair_with_dashboard(
            enrollment_token=args.enrollment_token,
            api_url=args.api_url,
            discovery_timeout=args.discovery_timeout,
            discovery_port=args.discovery_port,
        )
        save_config(config)
        print_json({"paired": True, **config.safe_summary()})
        return

    if args.command == "config":
        from agent_private.tui import load_config, save_config

        if args.config_command == "show":
            print_json(asdict(load_config()))
            return
        if args.config_command == "set":
            current = load_config()
            updated = current.__class__(
                api_url=args.api_url or current.api_url,
                endpoint_id=args.endpoint_id or current.endpoint_id,
                enrollment_token=args.enrollment_token or current.enrollment_token,
                heartbeat_interval=current.heartbeat_interval,
                connection_interval=current.connection_interval,
                process_interval=current.process_interval,
                windows_security_interval=current.windows_security_interval,
            )
            save_config(updated)
            print_json(updated.safe_summary())
            return
        parser.error("config requires show or set")

    if args.command == "service":
        print_json(run_service_command_with_reporting(args.service_action))
        return

    if args.command == "daemon":
        from agent_private.daemon import AgentDaemon
        from agent_private.runner import AgentRunConfig
        from agent_private.tui import load_config

        stored = load_config()
        api_url = args.api_url or stored.api_url
        endpoint_id = args.endpoint_id or stored.endpoint_id
        enrollment_token = args.enrollment_token or stored.enrollment_token
        if not api_url:
            parser.error("--api-url or AGENT_PRIVATE_API_URL is required with daemon")
        if not endpoint_id:
            parser.error("--endpoint-id or AGENT_PRIVATE_ENDPOINT_ID is required with daemon")
        if not enrollment_token:
            parser.error(
                "--enrollment-token or AGENT_PRIVATE_ENROLLMENT_TOKEN is required with daemon"
            )

        AgentDaemon(
            AgentRunConfig(
                api_url=api_url,
                endpoint_id=endpoint_id,
                enrollment_token=enrollment_token,
                heartbeat_interval=args.heartbeat_interval,
                connection_interval=args.connection_interval,
                process_interval=args.process_interval,
                windows_security_interval=args.windows_security_interval,
                windows_security_limit=args.windows_security_limit,
            )
        ).run_foreground(control_port=args.control_port)
        return

    if args.command == "run-headless":
        from agent_private.runner import AgentRunConfig, run_agent
        from agent_private.tui import load_config

        stored = load_config()
        api_url = args.api_url or stored.api_url
        endpoint_id = args.endpoint_id or stored.endpoint_id
        enrollment_token = args.enrollment_token or stored.enrollment_token
        if not api_url:
            parser.error("--api-url or AGENT_PRIVATE_API_URL is required with run-headless")
        if not endpoint_id:
            parser.error("--endpoint-id or AGENT_PRIVATE_ENDPOINT_ID is required with run-headless")
        if not enrollment_token:
            parser.error(
                "--enrollment-token or AGENT_PRIVATE_ENROLLMENT_TOKEN is required with "
                "run-headless"
            )

        run_agent(
            AgentRunConfig(
                api_url=api_url,
                endpoint_id=endpoint_id,
                enrollment_token=enrollment_token,
                heartbeat_interval=args.heartbeat_interval,
                connection_interval=args.connection_interval,
                process_interval=args.process_interval,
                windows_security_interval=args.windows_security_interval,
                windows_security_limit=args.windows_security_limit,
            ),
            once=args.once,
        )
        return

    endpoint_id = _require_endpoint_id(parser, args)

    if args.command == "simulate":
        events = build_simulated_events(endpoint_id)
        if args.post:
            for event in events:
                _post_if_requested(parser, args, event)
        print_json(events)
        return

    identity, ip_addresses = _identity_context()
    if args.command == "heartbeat":
        payload = build_heartbeat_payload(
            endpoint_id=endpoint_id,
            identity=identity,
            ip_addresses=ip_addresses,
        )
    elif args.command == "process-snapshot":
        payload = build_process_snapshot_payload(
            endpoint_id=endpoint_id,
            hostname=identity["hostname"],
            ip_addresses=ip_addresses,
            processes=collect_processes(),
        )
    elif args.command == "connection-snapshot":
        payload = build_connection_snapshot_payload(
            endpoint_id=endpoint_id,
            hostname=identity["hostname"],
            ip_addresses=ip_addresses,
            connections=collect_connections(),
        )
    elif args.command == "windows-security":
        payloads = build_windows_security_event_payloads(
            endpoint_id=endpoint_id,
            hostname=identity["hostname"],
            ip_addresses=ip_addresses,
            events=collect_windows_security_events(limit=args.limit),
            allowed_admin_hosts=args.allowed_admin_host,
            critical_paths=args.critical_path,
        )
        if args.post:
            for event in payloads:
                _post_if_requested(parser, args, event)
        print_json(payloads)
        return
    else:
        parser.error(f"unknown command: {args.command}")

    _post_if_requested(parser, args, payload)
    print_json(payload)


if __name__ == "__main__":
    main()
