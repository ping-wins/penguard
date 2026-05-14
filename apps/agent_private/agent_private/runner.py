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
    collect_windows_security_events,
    get_ip_addresses,
    post_endpoint_event,
)


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


PostFn = Callable[..., None]
LogFn = Callable[[str], None]


def run_agent(
    config: AgentRunConfig,
    *,
    once: bool = False,
    sleep: Callable[[float], None] = time.sleep,
    post: PostFn = post_endpoint_event,
    log: LogFn = print,
    identity_provider: Callable[[], dict[str, str]] = build_identity_payload,
    ip_provider: Callable[[], list[str]] = get_ip_addresses,
    process_collector: Callable[[int | None], list[dict[str, Any]]] = collect_processes,
    connection_collector: Callable[[], list[dict[str, Any]]] = collect_connections,
    windows_security_collector: Callable[
        [int], list[dict[str, Any]]
    ] = collect_windows_security_events,
) -> None:
    intervals: dict[str, float] = {
        "heartbeat": config.heartbeat_interval,
        "connection.snapshot": config.connection_interval,
        "process.snapshot": config.process_interval,
    }
    if config.windows_security_interval is not None:
        intervals["windows-security"] = config.windows_security_interval

    next_due = {name: 0.0 for name in intervals}
    log(f"agent_private run started for endpoint {config.endpoint_id}")

    while True:
        now = time.monotonic()
        ran = False
        for name, interval in intervals.items():
            if now < next_due[name]:
                continue
            for payload in _build_due_payloads(
                name,
                config,
                identity_provider=identity_provider,
                ip_provider=ip_provider,
                process_collector=process_collector,
                connection_collector=connection_collector,
                windows_security_collector=windows_security_collector,
            ):
                _post_payload(config, payload, post=post, log=log)
            next_due[name] = now + interval
            ran = True

        if once:
            return

        sleep(_sleep_seconds(next_due.values(), ran=ran))


def _build_due_payloads(
    name: str,
    config: AgentRunConfig,
    *,
    identity_provider: Callable[[], dict[str, str]],
    ip_provider: Callable[[], list[str]],
    process_collector: Callable[[int | None], list[dict[str, Any]]],
    connection_collector: Callable[[], list[dict[str, Any]]],
    windows_security_collector: Callable[[int], list[dict[str, Any]]],
) -> Sequence[dict[str, Any]]:
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
        log(f"post failed for {event_type}: {_redact(str(exc), config.enrollment_token)}")
        return
    log(f"posted {event_type} for endpoint {config.endpoint_id}")


def _redact(value: str, secret: str) -> str:
    if not secret:
        return value
    return value.replace(secret, "[redacted]")


def _sleep_seconds(next_due_values: Sequence[float], *, ran: bool) -> float:
    if ran:
        return 0.1
    now = time.monotonic()
    return max(0.1, min(1.0, min(next_due_values) - now))
