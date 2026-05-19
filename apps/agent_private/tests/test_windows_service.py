from __future__ import annotations

import pytest

from agent_private import windows_service


def test_service_commands_are_guarded_on_non_windows():
    with pytest.raises(RuntimeError, match="Windows Service support requires Windows"):
        windows_service.service_status(platform_name="Linux")


def test_service_status_delegates_to_service_util_on_windows():
    class FakeServiceUtil:
        @staticmethod
        def QueryServiceStatus(name):
            assert name == windows_service.SERVICE_NAME
            return (None, 4)

    status = windows_service.service_status(
        platform_name="Windows",
        service_util=FakeServiceUtil,
    )

    assert status == {"service": windows_service.SERVICE_NAME, "status": "running"}


def test_service_class_is_importable_by_module_name(monkeypatch):
    monkeypatch.setattr(windows_service, "_win32serviceutil", object())

    service_class = windows_service._service_class()

    assert service_class is windows_service.AgentPrivateWindowsService
    assert service_class.__module__ == "agent_private.windows_service"
    assert service_class.__name__ == "AgentPrivateWindowsService"


def test_service_run_reports_running_before_blocking(monkeypatch):
    import agent_private.daemon as daemon_module
    import agent_private.tui as tui_module

    reports: list[int] = []
    logs: list[str] = []

    class FakeServiceManager:
        @staticmethod
        def LogInfoMsg(message: str) -> None:
            logs.append(message)

    class FakeWin32Service:
        SERVICE_RUNNING = 4
        SERVICE_STOPPED = 1

    class FakeDaemon:
        def __init__(self, config, *, log):
            assert config == "run-config"
            self.log = log

        def run_foreground(self) -> None:
            return None

    monkeypatch.setattr(windows_service, "_servicemanager", FakeServiceManager)
    monkeypatch.setattr(windows_service, "_win32service", FakeWin32Service)
    monkeypatch.setattr(tui_module, "load_config", lambda: "stored-config")
    monkeypatch.setattr(tui_module, "build_run_config", lambda config: "run-config")
    monkeypatch.setattr(daemon_module, "AgentDaemon", FakeDaemon)

    service = object.__new__(windows_service.AgentPrivateWindowsService)
    service.ReportServiceStatus = reports.append

    service.SvcDoRun()

    assert reports == [FakeWin32Service.SERVICE_RUNNING, FakeWin32Service.SERVICE_STOPPED]
    assert logs == [
        f"{windows_service.SERVICE_NAME} started",
        f"{windows_service.SERVICE_NAME} stopped",
    ]


def test_service_stop_stops_daemon_and_reports_pending(monkeypatch):
    reports: list[int] = []
    events: list[str] = []
    stopped: list[bool] = []

    class FakeWin32Service:
        SERVICE_STOP_PENDING = 3

    class FakeWin32Event:
        @staticmethod
        def SetEvent(event: str) -> None:
            events.append(event)

    class FakeDaemon:
        def stop(self) -> None:
            stopped.append(True)

    monkeypatch.setattr(windows_service, "_win32service", FakeWin32Service)
    monkeypatch.setattr(windows_service, "_win32event", FakeWin32Event)

    service = object.__new__(windows_service.AgentPrivateWindowsService)
    service._daemon = FakeDaemon()
    service._stop_event = "stop-event"
    service.ReportServiceStatus = reports.append

    service.SvcStop()

    assert reports == [FakeWin32Service.SERVICE_STOP_PENDING]
    assert stopped == [True]
    assert events == ["stop-event"]
