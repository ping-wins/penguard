from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from agent_private.cli import (
    build_connection_snapshot_payload,
    build_heartbeat_payload,
    build_identity_payload,
    build_process_snapshot_payload,
    build_windows_security_event_payloads,
    collect_connections,
    collect_processes,
    get_ip_addresses,
    post_endpoint_event,
)
from agent_private.logs import append_agent_log
from agent_private.windows_security import collect_new_windows_security_events

DEFAULT_WINDOWS_SECURITY_INTERVAL = 60.0


@dataclass(frozen=True)
class AgentRunConfig:
    api_url: str
    endpoint_id: str
    enrollment_token: str
    heartbeat_interval: float = 30.0
    connection_interval: float = 60.0
    process_interval: float = 300.0
    windows_security_interval: float | None = None
    process_limit: int | None = None
    windows_security_limit: int = 50
    allowed_admin_hosts: tuple[str, ...] = ()
    critical_paths: tuple[str, ...] = ()


PostFn = Callable[..., None]
LogFn = Callable[[str], None]
IdentityProvider = Callable[[], dict[str, str]]
IpProvider = Callable[[], list[str]]
ProcessCollector = Callable[[int | None], list[dict[str, Any]]]
ConnectionCollector = Callable[[], list[dict[str, Any]]]
WindowsSecurityCollector = Callable[[int], list[dict[str, Any]]]


def run_agent(
    config: AgentRunConfig,
    *,
    once: bool = False,
    sleep: Callable[[float], None] = time.sleep,
    post: PostFn = post_endpoint_event,
    log: LogFn = print,
    identity_provider: IdentityProvider = build_identity_payload,
    ip_provider: IpProvider = get_ip_addresses,
    process_collector: ProcessCollector = collect_processes,
    connection_collector: ConnectionCollector = collect_connections,
    windows_security_collector: WindowsSecurityCollector = collect_new_windows_security_events,
) -> None:
    intervals: dict[str, float] = {
        "heartbeat": config.heartbeat_interval,
        "connection.snapshot": config.connection_interval,
        "process.snapshot": config.process_interval,
    }
    if config.windows_security_interval is not None:
        intervals["windows-security"] = config.windows_security_interval

    next_due = {name: 0.0 for name in intervals}
    _emit_log(log, f"agent_private run started for endpoint {config.endpoint_id}", config)

    while True:
        now = time.monotonic()
        ran = False
        for name, interval in intervals.items():
            if now < next_due[name]:
                continue
            try:
                payloads = build_payloads_for_kind(
                    name,
                    config,
                    identity_provider=identity_provider,
                    ip_provider=ip_provider,
                    process_collector=process_collector,
                    connection_collector=connection_collector,
                    windows_security_collector=windows_security_collector,
                )
            except Exception as exc:  # noqa: BLE001
                _emit_log(log, f"collect failed for {name}: {exc}", config)
                next_due[name] = now + interval
                ran = True
                continue
            for payload in payloads:
                _post_payload(config, payload, post=post, log=log)
            next_due[name] = now + interval
            ran = True

        if once:
            return

        sleep(_sleep_seconds(next_due.values(), ran=ran))


def build_payloads_for_kind(
    name: str,
    config: AgentRunConfig,
    *,
    identity_provider: IdentityProvider,
    ip_provider: IpProvider,
    process_collector: ProcessCollector,
    connection_collector: ConnectionCollector,
    windows_security_collector: WindowsSecurityCollector,
) -> Sequence[dict[str, Any]]:
    if name == "all":
        payloads: list[dict[str, Any]] = []
        for kind in ("heartbeat", "connection.snapshot", "process.snapshot", "windows-security"):
            payloads.extend(
                build_payloads_for_kind(
                    kind,
                    config,
                    identity_provider=identity_provider,
                    ip_provider=ip_provider,
                    process_collector=process_collector,
                    connection_collector=connection_collector,
                    windows_security_collector=windows_security_collector,
                )
            )
        return payloads
    if name == "processes":
        name = "process.snapshot"
    elif name == "connections":
        name = "connection.snapshot"
    elif name == "windows-security":
        name = "windows-security"

    identity = identity_provider()
    ip_addresses = ip_provider()
    hostname = identity["hostname"]
    if name == "heartbeat":
        return [
            build_heartbeat_payload(
                endpoint_id=config.endpoint_id,
                identity=identity,
                ip_addresses=ip_addresses,
            )
        ]
    if name == "connection.snapshot":
        return [
            build_connection_snapshot_payload(
                endpoint_id=config.endpoint_id,
                hostname=hostname,
                ip_addresses=ip_addresses,
                connections=connection_collector(),
            )
        ]
    if name == "process.snapshot":
        return [
            build_process_snapshot_payload(
                endpoint_id=config.endpoint_id,
                hostname=hostname,
                ip_addresses=ip_addresses,
                processes=process_collector(config.process_limit),
            )
        ]
    if name == "windows-security":
        return build_windows_security_event_payloads(
            endpoint_id=config.endpoint_id,
            hostname=hostname,
            ip_addresses=ip_addresses,
            events=windows_security_collector(config.windows_security_limit),
            allowed_admin_hosts=config.allowed_admin_hosts,
            critical_paths=config.critical_paths,
        )
    return []


def _post_payload(
    config: AgentRunConfig,
    payload: dict[str, Any],
    *,
    post: PostFn,
    log: LogFn,
) -> None:
    event_type = str(payload.get("eventType") or "unknown")
    try:
        post(
            api_url=config.api_url,
            enrollment_token=config.enrollment_token,
            payload=payload,
        )
    except Exception as exc:  # noqa: BLE001
        _emit_log(log, f"post failed for {event_type}: {exc}", config)
        return
    _emit_log(log, f"posted {event_type} for endpoint {config.endpoint_id}", config)


def _emit_log(log: LogFn, message: str, config: AgentRunConfig) -> None:
    safe_message = _redact(message, config.enrollment_token)
    append_agent_log(safe_message)
    log(safe_message)


def _redact(value: str, secret: str) -> str:
    if not secret:
        return value
    return value.replace(secret, "[redacted]")


def _sleep_seconds(next_due_values: Sequence[float], *, ran: bool) -> float:
    if ran:
        return 0.1
    now = time.monotonic()
    return max(0.1, min(1.0, min(next_due_values) - now))
