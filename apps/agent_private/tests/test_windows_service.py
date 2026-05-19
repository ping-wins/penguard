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
