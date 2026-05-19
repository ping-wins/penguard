from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx


@dataclass(frozen=True)
class AgentControlAddress:
    host: str
    port: int


@dataclass
class AgentControlState:
    endpoint_id: str
    started_at: float
    sent_count: int = 0
    failed_count: int = 0
    last_event: str = "none"
    running: bool = True

    def to_status_payload(self) -> dict[str, Any]:
        return {
            "endpointId": self.endpoint_id,
            "running": self.running,
            "sentCount": self.sent_count,
            "failedCount": self.failed_count,
            "lastEvent": self.last_event,
            "uptimeSeconds": max(0.0, time.monotonic() - self.started_at),
        }


CollectNowFn = Callable[[str], dict[str, Any]]
StopFn = Callable[[], None]


class AgentControlServer:
    def __init__(
        self,
        *,
        state: AgentControlState,
        collect_now: CollectNowFn,
        stop: StopFn | None = None,
        host: str = "127.0.0.1",
    ) -> None:
        self.state = state
        self.collect_now = collect_now
        self.stop = stop or (lambda: None)
        self.host = host

    @contextmanager
    def running(self, *, port: int = 8765) -> Iterator[AgentControlAddress]:
        handler = self._handler()
        server = ThreadingHTTPServer((self.host, port), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield AgentControlAddress(host=self.host, port=int(server.server_port))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        control = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path != "/status":
                    self._json({"detail": "not found"}, status=404)
                    return
                self._json(control.state.to_status_payload())

            def do_POST(self) -> None:  # noqa: N802
                if self.path == "/collect-now":
                    payload = self._read_json()
                    kind = str(payload.get("kind") or "all")
                    self._json(control.collect_now(kind))
                    return
                if self.path == "/stop":
                    control.stop()
                    self._json({"stopping": True})
                    return
                self._json({"detail": "not found"}, status=404)

            def log_message(self, _format: str, *_args: Any) -> None:
                return

            def _read_json(self) -> dict[str, Any]:
                length = int(self.headers.get("content-length") or 0)
                if length <= 0:
                    return {}
                raw = self.rfile.read(length)
                data = json.loads(raw.decode("utf-8"))
                return data if isinstance(data, dict) else {}

            def _json(self, payload: dict[str, Any], *, status: int = 200) -> None:
                raw = json.dumps(payload, sort_keys=True).encode("utf-8")
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        return Handler


class AgentControlClient:
    def __init__(self, *, base_url: str = "http://127.0.0.1:8765", timeout: float = 3.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def status(self) -> dict[str, Any]:
        return self._request("GET", "/status")

    def collect_now(self, kind: str) -> dict[str, Any]:
        return self._request("POST", "/collect-now", json={"kind": kind})

    def stop(self) -> dict[str, Any]:
        return self._request("POST", "/stop", json={})

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = httpx.request(
            method,
            f"{self.base_url}{path}",
            json=json,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}
