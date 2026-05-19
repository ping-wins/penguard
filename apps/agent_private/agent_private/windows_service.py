from __future__ import annotations

import platform
import sys
from typing import Any

try:
    import servicemanager as _servicemanager  # type: ignore[import-not-found]
    import win32event as _win32event  # type: ignore[import-not-found]
    import win32service as _win32service  # type: ignore[import-not-found]
    import win32serviceutil as _win32serviceutil  # type: ignore[import-not-found]
except ImportError:
    _servicemanager = None
    _win32event = None
    _win32service = None
    _win32serviceutil = None

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


class _UnavailableServiceFramework:
    def __init__(self, _args: list[str]) -> None:
        raise RuntimeError("Windows Service support requires pywin32")


_ServiceFramework = (
    _win32serviceutil.ServiceFramework
    if _win32serviceutil is not None
    else _UnavailableServiceFramework
)


class AgentPrivateWindowsService(_ServiceFramework):
    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = SERVICE_DISPLAY_NAME
    _svc_description_ = SERVICE_DESCRIPTION

    def __init__(self, args: list[str]) -> None:
        super().__init__(args)
        if _win32event is None:
            raise RuntimeError("Windows Service support requires pywin32")
        self._stop_event = _win32event.CreateEvent(None, 0, 0, None)
        self._daemon: Any | None = None

    def SvcStop(self) -> None:  # noqa: N802
        if _win32event is None or _win32service is None:
            raise RuntimeError("Windows Service support requires pywin32")
        self.ReportServiceStatus(_win32service.SERVICE_STOP_PENDING)
        if self._daemon is not None:
            self._daemon.stop()
        _win32event.SetEvent(self._stop_event)

    def SvcDoRun(self) -> None:  # noqa: N802
        if _servicemanager is None or _win32service is None:
            raise RuntimeError("Windows Service support requires pywin32")
        self.ReportServiceStatus(_win32service.SERVICE_RUNNING)
        try:
            from agent_private.daemon import AgentDaemon
            from agent_private.tui import build_run_config, load_config

            _servicemanager.LogInfoMsg(f"{SERVICE_NAME} started")
            config = build_run_config(load_config())
            self._daemon = AgentDaemon(config, log=_servicemanager.LogInfoMsg)
            self._daemon.run_foreground()
        except Exception as exc:  # noqa: BLE001
            _log_service_error(f"{SERVICE_NAME} failed: {exc}")
            raise
        finally:
            _servicemanager.LogInfoMsg(f"{SERVICE_NAME} stopped")
            self.ReportServiceStatus(_win32service.SERVICE_STOPPED)


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
    return _require_pywin32_module(_win32serviceutil)


def _service_class() -> type[Any]:
    _require_pywin32_module(_win32serviceutil)
    return AgentPrivateWindowsService


def _require_pywin32_module(module: Any | None) -> Any:
    if module is None:
        raise RuntimeError("Windows Service support requires pywin32")
    return module


def _log_service_error(message: str) -> None:
    if _servicemanager is None:
        return
    log_error = getattr(_servicemanager, "LogErrorMsg", None)
    if callable(log_error):
        log_error(message)
    else:
        _servicemanager.LogInfoMsg(message)
