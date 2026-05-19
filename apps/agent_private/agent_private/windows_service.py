from __future__ import annotations

import platform
import sys
from typing import Any

SERVICE_NAME = "FortiDashboardAgent"
SERVICE_DISPLAY_NAME = "FortiDashboard XDR Agent"
SERVICE_DESCRIPTION = "FortiDashboard endpoint telemetry agent for Windows lab hosts."

_STATUS_NAMES = {
    1: "stopped",
    2: "start_pending",
    3: "stop_pending",
    4: "running",
    5: "continue_pending",
    6: "pause_pending",
    7: "paused",
}


def service_status(
    *,
    platform_name: str | None = None,
    service_util: Any | None = None,
) -> dict[str, str]:
    _require_windows(platform_name)
    util = service_util or _load_service_util()
    status = util.QueryServiceStatus(SERVICE_NAME)
    code = int(status[1])
    return {"service": SERVICE_NAME, "status": _STATUS_NAMES.get(code, f"unknown:{code}")}


def run_service_command(action: str) -> dict[str, str]:
    _require_windows(None)
    if action == "status":
        return service_status()
    command = "remove" if action == "uninstall" else action
    if command not in {"install", "start", "stop", "remove"}:
        raise ValueError(f"Unsupported service action: {action}")
    util = _load_service_util()
    util.HandleCommandLine(_service_class(), argv=[sys.argv[0], command])
    return {"service": SERVICE_NAME, "action": action}


def _require_windows(platform_name: str | None) -> None:
    if (platform_name or platform.system()) != "Windows":
        raise RuntimeError("Windows Service support requires Windows")


def _load_service_util() -> Any:
    import win32serviceutil  # type: ignore[import-not-found]

    return win32serviceutil


def _service_class() -> type[Any]:
    import servicemanager  # type: ignore[import-not-found]
    import win32event  # type: ignore[import-not-found]
    import win32service  # type: ignore[import-not-found]
    import win32serviceutil  # type: ignore[import-not-found]

    from agent_private.daemon import AgentDaemon
    from agent_private.tui import build_run_config, load_config

    class AgentPrivateWindowsService(win32serviceutil.ServiceFramework):
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = SERVICE_DISPLAY_NAME
        _svc_description_ = SERVICE_DESCRIPTION

        def __init__(self, args: list[str]) -> None:
            super().__init__(args)
            self._stop_event = win32event.CreateEvent(None, 0, 0, None)

        def SvcStop(self) -> None:  # noqa: N802
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self._stop_event)

        def SvcDoRun(self) -> None:  # noqa: N802
            servicemanager.LogInfoMsg(f"{SERVICE_NAME} started")
            config = build_run_config(load_config())
            daemon = AgentDaemon(config, log=servicemanager.LogInfoMsg)
            daemon.run_foreground()
            servicemanager.LogInfoMsg(f"{SERVICE_NAME} stopped")

    return AgentPrivateWindowsService
