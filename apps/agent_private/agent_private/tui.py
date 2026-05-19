from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import Button, Footer, Header, Input, Static

from agent_private.cli import (
    build_connection_snapshot_payload,
    build_heartbeat_payload,
    build_identity_payload,
    build_process_snapshot_payload,
    build_simulated_events,
    build_windows_security_event_payloads,
    collect_connections,
    collect_processes,
    collect_windows_security_events,
    get_ip_addresses,
    post_endpoint_event,
)
from agent_private.runner import DEFAULT_WINDOWS_SECURITY_INTERVAL, AgentRunConfig


@dataclass(frozen=True)
class AgentPrivateConfig:
    api_url: str = ""
    endpoint_id: str = ""
    enrollment_token: str = ""
    heartbeat_interval: float = 30.0
    connection_interval: float = 60.0
    process_interval: float = 300.0
    windows_security_interval: float = DEFAULT_WINDOWS_SECURITY_INTERVAL
    allowed_admin_hosts: tuple[str, ...] = ()
    critical_paths: tuple[str, ...] = ()

    def safe_summary(self) -> dict[str, str]:
        return {
            "apiUrl": self.api_url,
            "endpointId": self.endpoint_id,
            "enrollmentToken": mask_secret(self.enrollment_token),
            "heartbeatInterval": f"{self.heartbeat_interval:g}s",
            "connectionInterval": f"{self.connection_interval:g}s",
            "processInterval": f"{self.process_interval:g}s",
            "windowsSecurityInterval": f"{self.windows_security_interval:g}s",
            "allowedAdminHosts": ", ".join(self.allowed_admin_hosts),
            "criticalPaths": ", ".join(self.critical_paths),
        }


def default_config_path() -> Path:
    if os.name == "nt":
        base = Path(_windows_config_base())
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "agent_private" / "config.json"


def _windows_config_base() -> str:
    return os.environ.get("PROGRAMDATA", "C:/ProgramData")


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
    stored = AgentPrivateConfig(
        api_url=str(payload.get("api_url") or payload.get("apiUrl") or ""),
        endpoint_id=str(payload.get("endpoint_id") or payload.get("endpointId") or ""),
        enrollment_token=str(
            payload.get("enrollment_token") or payload.get("enrollmentToken") or ""
        ),
        heartbeat_interval=_interval_value(
            payload,
            "heartbeat_interval",
            "heartbeatInterval",
            30.0,
        ),
        connection_interval=_interval_value(
            payload,
            "connection_interval",
            "connectionInterval",
            60.0,
        ),
        process_interval=_interval_value(payload, "process_interval", "processInterval", 300.0),
        windows_security_interval=_interval_value(
            payload,
            "windows_security_interval",
            "windowsSecurityInterval",
            DEFAULT_WINDOWS_SECURITY_INTERVAL,
            allow_zero=True,
        ),
        allowed_admin_hosts=_list_value(payload, "allowed_admin_hosts", "allowedAdminHosts"),
        critical_paths=_list_value(payload, "critical_paths", "criticalPaths"),
    )
    return AgentPrivateConfig(
        api_url=os.environ.get("AGENT_PRIVATE_API_URL") or stored.api_url,
        endpoint_id=os.environ.get("AGENT_PRIVATE_ENDPOINT_ID") or stored.endpoint_id,
        enrollment_token=(
            os.environ.get("AGENT_PRIVATE_ENROLLMENT_TOKEN") or stored.enrollment_token
        ),
        heartbeat_interval=stored.heartbeat_interval,
        connection_interval=stored.connection_interval,
        process_interval=stored.process_interval,
        windows_security_interval=stored.windows_security_interval,
        allowed_admin_hosts=stored.allowed_admin_hosts,
        critical_paths=stored.critical_paths,
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


def build_run_config(config: AgentPrivateConfig) -> AgentRunConfig:
    return AgentRunConfig(
        api_url=config.api_url,
        endpoint_id=config.endpoint_id,
        enrollment_token=config.enrollment_token,
        heartbeat_interval=config.heartbeat_interval,
        connection_interval=config.connection_interval,
        process_interval=config.process_interval,
        windows_security_interval=_runtime_windows_security_interval(
            config.windows_security_interval
        ),
        allowed_admin_hosts=config.allowed_admin_hosts,
        critical_paths=config.critical_paths,
    )


def _runtime_windows_security_interval(value: float | None) -> float:
    if value is None or value <= 0:
        return DEFAULT_WINDOWS_SECURITY_INTERVAL
    return value


def _list_value(payload: dict[str, Any], snake_key: str, camel_key: str) -> tuple[str, ...]:
    value = payload.get(snake_key, payload.get(camel_key, ()))
    if isinstance(value, str):
        return tuple(item.strip() for item in value.split(",") if item.strip())
    if isinstance(value, list | tuple):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _interval_value(
    payload: dict[str, Any],
    snake_key: str,
    camel_key: str,
    default: float,
    *,
    allow_zero: bool = False,
) -> float:
    return _parse_interval(
        payload.get(snake_key, payload.get(camel_key)),
        default,
        allow_zero=allow_zero,
    )


def _parse_interval(value: Any, default: float, *, allow_zero: bool = False) -> float:
    try:
        interval = float(value)
    except (TypeError, ValueError):
        return default
    if interval > 0 or (allow_zero and interval == 0):
        return interval
    return default


OPERATOR_HELP = (
    "Navigation: Tab / Shift+Tab moves between fields, Enter activates focused buttons, "
    "Ctrl+V pastes from the system clipboard, mouse wheel scrolls, q quits."
)


class SystemClipboardInput(Input):
    """Input with an OS clipboard fallback for terminals that do not emit paste events."""

    def action_paste(self) -> None:
        text = self.app.clipboard or read_system_clipboard()
        line = _first_clipboard_line(text)
        if not line:
            if hasattr(self.app, "_log"):
                self.app._log("Clipboard is empty or unavailable.")  # type: ignore[attr-defined]
            return
        start, end = self.selection
        self.replace(line, start, end)


class AgentPrivateTui(App[None]):
    CSS = """
    Screen {
        background: #0f1115;
        color: #e5edf8;
    }

    #root {
        height: 100%;
        width: 100%;
        padding: 1;
        overflow-y: auto;
    }

    .panel {
        border: solid #2f3b52;
        padding: 1 2;
        margin-bottom: 1;
        height: auto;
        width: 100%;
    }

    .title {
        color: #00ff88;
        text-style: bold;
        margin-bottom: 1;
    }

    .section-title {
        color: #00ff88;
        text-style: bold;
        margin-bottom: 1;
    }

    .help {
        color: #e5edf8;
        background: #18202b;
        border: tall #3a4a63;
        padding: 0 1;
        margin-bottom: 1;
    }

    .field-label {
        color: #d7e2f0;
        text-style: bold;
        margin-top: 1;
        margin-bottom: 0;
    }

    .muted {
        color: #96a3b8;
    }

    Input {
        background: #111827;
        color: #f8fafc;
        border: tall #52627a;
        height: 3;
        padding: 0 1;
        margin-bottom: 1;
        width: 100%;
    }

    Input:focus {
        border: tall #00ff88;
    }

    Button {
        background: #18202b;
        color: #f8fafc;
        border: tall #52627a;
        height: 3;
        min-width: 20;
        margin-right: 1;
        content-align: center middle;
    }

    Button:focus {
        background: #20324a;
        border: tall #00ff88;
    }

    .button-row {
        height: auto;
        margin-top: 1;
        margin-bottom: 1;
    }

    #status-log {
        border: tall #3a4a63;
        background: #111827;
        color: #f8fafc;
        min-height: 5;
        padding: 1;
    }
    """
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("tab", "focus_next", "Next field"),
        ("shift+tab", "focus_previous", "Previous field"),
        ("s", "save", "Save config"),
        ("r", "start_loop", "Run agent"),
        ("x", "stop_loop", "Stop agent"),
        ("h", "heartbeat", "Heartbeat"),
        ("d", "demo", "Demo burst"),
    ]

    def __init__(self, *, config_path: Path | None = None) -> None:
        super().__init__()
        self.config_path = config_path or default_config_path()
        self.config = load_config(self.config_path)
        self.loop_timers: list[Any] = []
        self.sent_count = 0
        self.failed_count = 0
        self.last_event = "none"
        self.is_loop_running = False

    def compose(self) -> ComposeResult:
        identity = build_identity_payload()
        ips = get_ip_addresses()
        yield Header(show_clock=True)
        with ScrollableContainer(id="root"):
            yield Static("agent_private endpoint sensor", classes="title")
            yield Static(OPERATOR_HELP, id="operator-help", classes="help")
            with Vertical(classes="panel"):
                yield Static("Setup", classes="section-title")
                yield Static("API URL", id="api-url-label", classes="field-label")
                yield SystemClipboardInput(
                    value=self.config.api_url,
                    placeholder="http://localhost:8000",
                    id="api-url",
                )
                yield Static("Endpoint ID", id="endpoint-id-label", classes="field-label")
                yield SystemClipboardInput(
                    value=self.config.endpoint_id or identity["hostname"],
                    placeholder="endpoint-id",
                    id="endpoint-id",
                )
                yield Static(
                    "Enrollment token",
                    id="enrollment-token-label",
                    classes="field-label",
                )
                yield SystemClipboardInput(
                    value=self.config.enrollment_token,
                    placeholder="enrollment token",
                    password=True,
                    id="enrollment-token",
                )
                with Horizontal(classes="button-row"):
                    yield Button("Save (s)", id="save-config", variant="primary")
                    yield Button("Clear config", id="clear-config")
            with Vertical(classes="panel"):
                yield Static("Run loop", classes="section-title")
                yield Static(
                    "Intervals are seconds. Windows Security 0 disables collection.",
                    classes="muted",
                )
                yield Static(
                    "Heartbeat interval",
                    id="heartbeat-interval-label",
                    classes="field-label",
                )
                yield SystemClipboardInput(
                    value=f"{self.config.heartbeat_interval:g}",
                    placeholder="heartbeat interval",
                    id="heartbeat-interval",
                )
                yield Static(
                    "Connection snapshot interval",
                    id="connection-interval-label",
                    classes="field-label",
                )
                yield SystemClipboardInput(
                    value=f"{self.config.connection_interval:g}",
                    placeholder="connection snapshot interval",
                    id="connection-interval",
                )
                yield Static(
                    "Process snapshot interval",
                    id="process-interval-label",
                    classes="field-label",
                )
                yield SystemClipboardInput(
                    value=f"{self.config.process_interval:g}",
                    placeholder="process snapshot interval",
                    id="process-interval",
                )
                yield Static(
                    "Windows Security interval",
                    id="windows-security-interval-label",
                    classes="field-label",
                )
                yield SystemClipboardInput(
                    value=f"{self.config.windows_security_interval:g}",
                    placeholder="windows security interval, 0 disables",
                    id="windows-security-interval",
                )
                with Horizontal(classes="button-row"):
                    yield Button("Start agent (r)", id="start-loop", variant="success")
                    yield Button("Stop agent (x)", id="stop-loop", variant="error")
            with Vertical(classes="panel"):
                yield Static("Status", classes="section-title")
                yield Static("Agent stopped", id="agent-state", classes="muted")
                yield Static(
                    "sent=0 failed=0 last=none",
                    id="telemetry-counters",
                    classes="muted",
                )
                yield Static(f"Hostname: {identity['hostname']}", classes="muted")
                yield Static(f"User: {identity['username']}", classes="muted")
                yield Static(f"OS: {identity['os']}", classes="muted")
                yield Static(f"IPs: {', '.join(ips) if ips else 'none'}", classes="muted")
            with Vertical(classes="panel"):
                yield Static("Telemetry", classes="section-title")
                with Horizontal(classes="button-row"):
                    yield Button("Heartbeat (h)", id="send-heartbeat", variant="success")
                    yield Button("Processes", id="send-processes")
                    yield Button("Connections", id="send-connections")
                    yield Button("Demo burst (d)", id="send-demo", variant="warning")
            yield Static("Ready. Save setup, then send telemetry.", id="status-log")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#api-url", Input).focus()

    def action_save(self) -> None:
        self._save_config_from_inputs()

    def action_heartbeat(self) -> None:
        self._send_single("heartbeat")

    def action_start_loop(self) -> None:
        self._start_loop()

    def action_stop_loop(self) -> None:
        self._stop_loop()

    def action_demo(self) -> None:
        self._send_demo_burst()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "save-config":
                self._save_config_from_inputs()
            case "clear-config":
                clear_config(self.config_path)
                self._log("Local config cleared.")
            case "start-loop":
                self._start_loop()
            case "stop-loop":
                self._stop_loop()
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
            heartbeat_interval=_parse_interval(
                self.query_one("#heartbeat-interval", Input).value.strip(),
                30.0,
            ),
            connection_interval=_parse_interval(
                self.query_one("#connection-interval", Input).value.strip(),
                60.0,
            ),
            process_interval=_parse_interval(
                self.query_one("#process-interval", Input).value.strip(),
                300.0,
            ),
            windows_security_interval=_parse_interval(
                self.query_one("#windows-security-interval", Input).value.strip(),
                DEFAULT_WINDOWS_SECURITY_INTERVAL,
                allow_zero=True,
            ),
        )

    def _save_config_from_inputs(self) -> None:
        config = self._current_config()
        save_config(config, self.config_path)
        self.config = config
        self._log(f"Config saved: {config.safe_summary()}")

    def _start_loop(self) -> None:
        config = self._current_config()
        error = _validate_post_config(config)
        if error:
            self._log(error)
            return
        self._stop_loop(silent=True)
        save_config(config, self.config_path)
        self.config = config
        self.loop_timers = [
            self.set_interval(
                config.heartbeat_interval,
                lambda: self._send_single("heartbeat"),
                name="heartbeat-loop",
            ),
            self.set_interval(
                config.connection_interval,
                lambda: self._send_single("connections"),
                name="connection-loop",
            ),
            self.set_interval(
                config.process_interval,
                lambda: self._send_single("processes"),
                name="process-loop",
            ),
        ]
        if config.windows_security_interval > 0:
            self.loop_timers.append(
                self.set_interval(
                    config.windows_security_interval,
                    self._send_windows_security,
                    name="windows-security-loop",
                )
            )
        self.is_loop_running = True
        self._render_agent_status()
        if self._send_single("heartbeat"):
            self._log(f"Agent loop running. Initial heartbeat OK: {config.safe_summary()}")
        else:
            self._log(
                "Agent loop started, but initial heartbeat failed. "
                "Check API URL, enrollment token and backend logs."
            )

    def _stop_loop(self, *, silent: bool = False) -> None:
        for timer in self.loop_timers:
            timer.stop()
        self.loop_timers = []
        self.is_loop_running = False
        self._render_agent_status()
        if not silent:
            self._log("Agent loop stopped.")

    def _send_single(self, kind: str) -> bool:
        config = self._current_config()
        error = _validate_post_config(config)
        if error:
            self._log(error)
            return False

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
            return False
        return self._post_payload(config, payload, success=f"Sent {payload['eventType']}.")

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

    def _send_windows_security(self) -> None:
        config = self._current_config()
        error = _validate_post_config(config)
        if error:
            self._log(error)
            return
        identity = build_identity_payload()
        ip_addresses = get_ip_addresses()
        payloads = build_windows_security_event_payloads(
            endpoint_id=config.endpoint_id,
            hostname=identity["hostname"],
            ip_addresses=ip_addresses,
            events=collect_windows_security_events(limit=50),
        )
        sent = 0
        for payload in payloads:
            if self._post_payload(config, payload, success=""):
                sent += 1
        self._log(f"Sent Windows Security batch with {sent} events.")

    def _post_payload(
        self,
        config: AgentPrivateConfig,
        payload: dict[str, Any],
        *,
        success: str,
    ) -> bool:
        event_type = str(payload.get("eventType") or "endpoint event")
        self.last_event = event_type
        self._log(f"Posting {event_type} for endpoint {config.endpoint_id}...")
        try:
            post_endpoint_event(
                api_url=config.api_url,
                enrollment_token=config.enrollment_token,
                payload=payload,
            )
        except Exception as exc:  # noqa: BLE001 - TUI must keep running after transport errors.
            self.failed_count += 1
            self._render_agent_status()
            self._log(
                f"Post failed for {event_type}: {_redact(str(exc), config.enrollment_token)}"
            )
            return False
        self.sent_count += 1
        self._render_agent_status()
        if success:
            self._log(f"{success} sent={self.sent_count} failed={self.failed_count}")
        return True

    def _log(self, message: str) -> None:
        self.query_one("#status-log", Static).update(message)

    def _render_agent_status(self) -> None:
        state = "running" if self.is_loop_running else "stopped"
        self.query_one("#agent-state", Static).update(f"Agent {state}")
        self.query_one("#telemetry-counters", Static).update(
            f"sent={self.sent_count} failed={self.failed_count} last={self.last_event}"
        )


def _validate_post_config(config: AgentPrivateConfig) -> str | None:
    if not config.api_url:
        return "API URL is required."
    if not config.endpoint_id:
        return "Endpoint ID is required."
    if not config.enrollment_token:
        return "Enrollment token is required."
    return None


def _redact(value: str, secret: str) -> str:
    if not secret:
        return value
    return value.replace(secret, "[redacted]")


def read_system_clipboard() -> str:
    if os.name == "nt":
        return _read_windows_clipboard()
    return _read_subprocess_clipboard()


def _read_windows_clipboard() -> str:
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return ""

    cf_unicode_text = 13
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL

    if not user32.OpenClipboard(None):
        return ""
    try:
        handle = user32.GetClipboardData(cf_unicode_text)
        if not handle:
            return ""
        locked = kernel32.GlobalLock(handle)
        if not locked:
            return ""
        try:
            return ctypes.wstring_at(locked)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _read_subprocess_clipboard() -> str:
    commands = [["pbpaste"]] if sys.platform == "darwin" else [
        ["wl-paste", "--no-newline"],
        ["xclip", "-selection", "clipboard", "-o"],
        ["xsel", "--clipboard", "--output"],
    ]
    for command in commands:
        try:
            result = subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=0.5,
            )
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            continue
        if result.stdout:
            return result.stdout
    return ""


def _first_clipboard_line(text: str) -> str:
    if not text:
        return ""
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n", maxsplit=1)[0]


def run_tui() -> None:
    AgentPrivateTui().run()
