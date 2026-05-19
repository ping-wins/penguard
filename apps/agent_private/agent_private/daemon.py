from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from agent_private.actions import EndpointActionClient
from agent_private.control import AgentControlServer, AgentControlState
from agent_private.logs import append_agent_log
from agent_private.runner import (
    AgentRunConfig,
    ConnectionCollector,
    IdentityProvider,
    IpProvider,
    PostFn,
    ProcessCollector,
    WindowsSecurityCollector,
    build_identity_payload,
    build_payloads_for_kind,
    collect_connections,
    collect_new_windows_security_events,
    collect_processes,
    get_ip_addresses,
    post_endpoint_event,
)

LogFn = Callable[[str], None]
REMOTE_ACTION_INTERVAL_SECONDS = 10.0


class AgentDaemon:
    def __init__(
        self,
        config: AgentRunConfig,
        *,
        post: PostFn = post_endpoint_event,
        log: LogFn = print,
        identity_provider: IdentityProvider = build_identity_payload,
        ip_provider: IpProvider = get_ip_addresses,
        process_collector: ProcessCollector = collect_processes,
        connection_collector: ConnectionCollector = collect_connections,
        windows_security_collector: WindowsSecurityCollector = collect_new_windows_security_events,
    ) -> None:
        self.config = config
        self.post = post
        self.log = log
        self.identity_provider = identity_provider
        self.ip_provider = ip_provider
        self.process_collector = process_collector
        self.connection_collector = connection_collector
        self.windows_security_collector = windows_security_collector
        self.state = AgentControlState(
            endpoint_id=config.endpoint_id,
            started_at=time.monotonic(),
        )
        self._stop_event = threading.Event()

    def status(self) -> dict[str, Any]:
        return self.state.to_status_payload()

    def stop(self) -> None:
        self.state.running = False
        self._stop_event.set()

    def collect_now(self, kind: str) -> dict[str, Any]:
        try:
            payloads = build_payloads_for_kind(
                kind,
                self.config,
                identity_provider=self.identity_provider,
                ip_provider=self.ip_provider,
                process_collector=self.process_collector,
                connection_collector=self.connection_collector,
                windows_security_collector=self.windows_security_collector,
            )
        except Exception as exc:  # noqa: BLE001
            self.state.failed_count += 1
            error = _redact(str(exc), self.config.enrollment_token)
            self._log(f"collect failed for {kind}: {error}")
            return {"posted": [], "failed": [{"eventType": kind, "error": error}]}
        posted: list[str] = []
        failed: list[dict[str, str]] = []
        for payload in payloads:
            event_type = str(payload.get("eventType") or "unknown")
            self.state.last_event = event_type
            try:
                self.post(
                    api_url=self.config.api_url,
                    enrollment_token=self.config.enrollment_token,
                    payload=payload,
                )
            except Exception as exc:  # noqa: BLE001
                self.state.failed_count += 1
                failed.append(
                    {
                        "eventType": event_type,
                        "error": _redact(str(exc), self.config.enrollment_token),
                    }
                )
                self._log(f"post failed for {event_type}: {failed[-1]['error']}")
                continue
            self.state.sent_count += 1
            self._log(f"posted {event_type} for endpoint {self.config.endpoint_id}")
            posted.append(event_type)
        return {"posted": posted, "failed": failed}

    def process_remote_action(self, action_client: Any | None = None) -> bool:
        client = action_client or EndpointActionClient(
            api_url=self.config.api_url,
            enrollment_token=self.config.enrollment_token,
        )
        action = client.claim_next(self.config.endpoint_id)
        if action is None:
            return False
        action_id = str(action.get("id") or "")
        kind = str(action.get("kind") or "")
        parameters = action.get("parameters") if isinstance(action.get("parameters"), dict) else {}
        if kind == "collect_now":
            result = self.collect_now(str(parameters.get("kind") or "all"))
            status = "failed" if result["failed"] and not result["posted"] else "completed"
        elif kind == "run_diagnostic":
            result = {"status": self.status()}
            status = "completed"
        else:
            result = {"error": f"Unsupported action kind: {kind}"}
            status = "failed"
        if action_id:
            client.report_result(
                self.config.endpoint_id,
                action_id,
                status=status,
                result=result,
            )
            self._log(f"reported action {action_id} as {status}")
        return True

    def run_foreground(self, *, control_port: int = 8765) -> None:
        server = AgentControlServer(
            state=self.state,
            collect_now=self.collect_now,
            stop=self.stop,
        )
        with server.running(port=control_port):
            self._log(f"agent_private daemon running for endpoint {self.config.endpoint_id}")
            intervals = self._telemetry_intervals()
            next_due = {kind: 0.0 for kind in intervals}
            next_remote_action_due = 0.0
            while not self._stop_event.is_set():
                now = time.monotonic()
                ran = False
                for kind, interval in intervals.items():
                    if now < next_due[kind]:
                        continue
                    self.collect_now(kind)
                    next_due[kind] = now + interval
                    ran = True
                if now >= next_remote_action_due:
                    next_remote_action_due = now + REMOTE_ACTION_INTERVAL_SECONDS
                    ran = True
                    self._process_remote_action_safely()
                wait_seconds = _daemon_sleep_seconds(
                    [*next_due.values(), next_remote_action_due],
                    ran=ran,
                )
                self._stop_event.wait(wait_seconds)

    def _telemetry_intervals(self) -> dict[str, float]:
        intervals = {
            "heartbeat": self.config.heartbeat_interval,
            "connection.snapshot": self.config.connection_interval,
            "process.snapshot": self.config.process_interval,
        }
        if self.config.windows_security_interval is not None:
            intervals["windows-security"] = self.config.windows_security_interval
        return intervals

    def _process_remote_action_safely(self) -> None:
        try:
            self.process_remote_action()
        except Exception as exc:  # noqa: BLE001
            self.state.failed_count += 1
            error = _redact(str(exc), self.config.enrollment_token)
            self._log(f"remote action polling failed: {error}")

    def _log(self, message: str) -> None:
        safe_message = _redact(message, self.config.enrollment_token)
        append_agent_log(safe_message)
        self.log(safe_message)


def _daemon_sleep_seconds(next_due_values: list[float], *, ran: bool) -> float:
    if ran:
        return 0.1
    now = time.monotonic()
    return max(0.1, min(1.0, min(next_due_values) - now))


def _redact(value: str, secret: str) -> str:
    if not secret:
        return value
    return value.replace(secret, "[redacted]")
