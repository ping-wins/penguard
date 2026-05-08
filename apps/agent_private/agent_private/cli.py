from __future__ import annotations

import argparse
import getpass
import json
import os
import platform
import socket
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any

import httpx
import psutil
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

DEFAULT_TIMEOUT_SECONDS = 5.0
DEMO_OCCURRED_AT = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)


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
    if hasattr(address, "ip") and hasattr(address, "port"):
        return {"ip": address.ip, "port": address.port}
    if isinstance(address, tuple) and len(address) >= 2:
        return {"ip": address[0], "port": address[1]}
    return {"ip": str(address), "port": None}


def normalize_connection(row: Any) -> dict[str, Any]:
    return {
        "fd": getattr(row, "fd", None),
        "family": _socket_constant_name(socket.AddressFamily, getattr(row, "family", "")),
        "type": _socket_constant_name(socket.SocketKind, getattr(row, "type", "")),
        "localAddress": _address_payload(getattr(row, "laddr", None)),
        "remoteAddress": _address_payload(getattr(row, "raddr", None)),
        "status": getattr(row, "status", None),
        "pid": getattr(row, "pid", None),
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
    subparsers = parser.add_subparsers(dest="command", required=True)
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

    if args.command == "identity":
        print_json(build_identity_payload())
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
    else:
        parser.error(f"unknown command: {args.command}")

    _post_if_requested(parser, args, payload)
    print_json(payload)


if __name__ == "__main__":
    main()
