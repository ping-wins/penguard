from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, Static

from agent_private.cli import (
    build_connection_snapshot_payload,
    build_heartbeat_payload,
    build_identity_payload,
    build_process_snapshot_payload,
    build_simulated_events,
    collect_connections,
    collect_processes,
    get_ip_addresses,
    post_endpoint_event,
)


@dataclass(frozen=True)
class AgentPrivateConfig:
    api_url: str = ""
    endpoint_id: str = ""
    enrollment_token: str = ""

    def safe_summary(self) -> dict[str, str]:
        return {
            "apiUrl": self.api_url,
            "endpointId": self.endpoint_id,
            "enrollmentToken": mask_secret(self.enrollment_token),
        }


def default_config_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "agent_private" / "config.json"


def load_config(path: Path | None = None) -> AgentPrivateConfig:
    config_path = path or default_config_path()
    if not config_path.exists():
        return AgentPrivateConfig(
            api_url=os.environ.get("AGENT_PRIVATE_API_URL", ""),
            endpoint_id=os.environ.get("AGENT_PRIVATE_ENDPOINT_ID", ""),
            enrollment_token=os.environ.get("AGENT_PRIVATE_ENROLLMENT_TOKEN", ""),
        )
    payload = json.loads(config_path.read_text())
    if not isinstance(payload, dict):
        return AgentPrivateConfig()
    return AgentPrivateConfig(
        api_url=str(payload.get("api_url") or payload.get("apiUrl") or ""),
        endpoint_id=str(payload.get("endpoint_id") or payload.get("endpointId") or ""),
        enrollment_token=str(
            payload.get("enrollment_token") or payload.get("enrollmentToken") or ""
        ),
    )


def save_config(config: AgentPrivateConfig, path: Path | None = None) -> None:
    config_path = path or default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(asdict(config), indent=2, sort_keys=True))
    if os.name != "nt":
        config_path.chmod(0o600)


def clear_config(path: Path | None = None) -> None:
    config_path = path or default_config_path()
    if config_path.exists():
        config_path.unlink()


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


class AgentPrivateTui(App[None]):
    CSS = """
    Screen {
        background: #0f1115;
    }

    #root {
        height: 100%;
        padding: 1;
    }

    .panel {
        border: solid #2f3b52;
        padding: 1 2;
        margin-bottom: 1;
    }

    .title {
        color: #00ff88;
        text-style: bold;
        margin-bottom: 1;
    }

    .muted {
        color: #96a3b8;
    }

    Input {
        margin-bottom: 1;
    }

    Button {
        margin-right: 1;
    }

    #status-log {
        min-height: 7;
    }
    """
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("s", "save", "Save config"),
        ("h", "heartbeat", "Heartbeat"),
        ("d", "demo", "Demo burst"),
    ]

    def __init__(self, *, config_path: Path | None = None) -> None:
        super().__init__()
        self.config_path = config_path or default_config_path()
        self.config = load_config(self.config_path)

    def compose(self) -> ComposeResult:
        identity = build_identity_payload()
        ips = get_ip_addresses()
        yield Header(show_clock=True)
        with Vertical(id="root"):
            yield Static("agent_private endpoint sensor", classes="title")
            with Vertical(classes="panel"):
                yield Static("Setup", classes="title")
                yield Input(
                    value=self.config.api_url,
                    placeholder="http://localhost:8000",
                    id="api-url",
                )
                yield Input(
                    value=self.config.endpoint_id or identity["hostname"],
                    placeholder="endpoint-id",
                    id="endpoint-id",
                )
                yield Input(
                    value=self.config.enrollment_token,
                    placeholder="enrollment token",
                    password=True,
                    id="enrollment-token",
                )
                with Horizontal():
                    yield Button("Save", id="save-config", variant="primary")
                    yield Button("Clear", id="clear-config")
            with Vertical(classes="panel"):
                yield Static("Status", classes="title")
                yield Static(f"Hostname: {identity['hostname']}", classes="muted")
                yield Static(f"User: {identity['username']}", classes="muted")
                yield Static(f"OS: {identity['os']}", classes="muted")
                yield Static(f"IPs: {', '.join(ips) if ips else 'none'}", classes="muted")
            with Vertical(classes="panel"):
                yield Static("Telemetry", classes="title")
                with Horizontal():
                    yield Button("Heartbeat", id="send-heartbeat", variant="success")
                    yield Button("Processes", id="send-processes")
                    yield Button("Connections", id="send-connections")
                    yield Button("Demo burst", id="send-demo", variant="warning")
            yield Static("Ready. Save setup, then send telemetry.", id="status-log")
        yield Footer()

    def action_save(self) -> None:
        self._save_config_from_inputs()

    def action_heartbeat(self) -> None:
        self._send_single("heartbeat")

    def action_demo(self) -> None:
        self._send_demo_burst()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "save-config":
                self._save_config_from_inputs()
            case "clear-config":
                clear_config(self.config_path)
                self._log("Local config cleared.")
            case "send-heartbeat":
                self._send_single("heartbeat")
            case "send-processes":
                self._send_single("processes")
            case "send-connections":
                self._send_single("connections")
            case "send-demo":
                self._send_demo_burst()

    def _current_config(self) -> AgentPrivateConfig:
        return AgentPrivateConfig(
            api_url=self.query_one("#api-url", Input).value.strip(),
            endpoint_id=self.query_one("#endpoint-id", Input).value.strip(),
            enrollment_token=self.query_one("#enrollment-token", Input).value.strip(),
        )

    def _save_config_from_inputs(self) -> None:
        config = self._current_config()
        save_config(config, self.config_path)
        self.config = config
        self._log(f"Config saved: {config.safe_summary()}")

    def _send_single(self, kind: str) -> None:
        config = self._current_config()
        error = _validate_post_config(config)
        if error:
            self._log(error)
            return

        identity = build_identity_payload()
        ip_addresses = get_ip_addresses()
        if kind == "heartbeat":
            payload = build_heartbeat_payload(
                endpoint_id=config.endpoint_id,
                identity=identity,
                ip_addresses=ip_addresses,
            )
        elif kind == "processes":
            payload = build_process_snapshot_payload(
                endpoint_id=config.endpoint_id,
                hostname=identity["hostname"],
                ip_addresses=ip_addresses,
                processes=collect_processes(limit=50),
            )
        elif kind == "connections":
            payload = build_connection_snapshot_payload(
                endpoint_id=config.endpoint_id,
                hostname=identity["hostname"],
                ip_addresses=ip_addresses,
                connections=collect_connections(),
            )
        else:
            self._log(f"Unknown telemetry action: {kind}")
            return
        self._post_payload(config, payload, success=f"Sent {payload['eventType']}.")

    def _send_demo_burst(self) -> None:
        config = self._current_config()
        error = _validate_post_config(config)
        if error:
            self._log(error)
            return
        sent = 0
        for payload in build_simulated_events(config.endpoint_id):
            if self._post_payload(config, payload, success=""):
                sent += 1
        self._log(f"Sent demo burst with {sent} events.")

    def _post_payload(
        self,
        config: AgentPrivateConfig,
        payload: dict[str, Any],
        *,
        success: str,
    ) -> bool:
        try:
            post_endpoint_event(
                api_url=config.api_url,
                enrollment_token=config.enrollment_token,
                payload=payload,
            )
        except Exception as exc:  # noqa: BLE001 - TUI must keep running after transport errors.
            self._log(f"Post failed: {exc}")
            return False
        if success:
            self._log(success)
        return True

    def _log(self, message: str) -> None:
        self.query_one("#status-log", Static).update(message)


def _validate_post_config(config: AgentPrivateConfig) -> str | None:
    if not config.api_url:
        return "API URL is required."
    if not config.endpoint_id:
        return "Endpoint ID is required."
    if not config.enrollment_token:
        return "Enrollment token is required."
    return None


def run_tui() -> None:
    AgentPrivateTui().run()
