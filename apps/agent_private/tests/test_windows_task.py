from __future__ import annotations

import pytest

from agent_private import windows_task


def test_task_commands_are_guarded_on_non_windows():
    with pytest.raises(RuntimeError, match="Windows Scheduled Task support requires Windows"):
        windows_task.task_status(platform_name="Linux")


def test_task_install_writes_runner_and_creates_task(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    monkeypatch.setenv("PROGRAMDATA", str(tmp_path))
    monkeypatch.setattr(windows_task.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        windows_task.sys,
        "executable",
        "C:/repo/apps/agent_private/.venv/python.exe",
    )

    def fake_run(command, *, capture_output, text, timeout, check):
        calls.append(command)
        return type("Result", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()

    monkeypatch.setattr(windows_task.subprocess, "run", fake_run)

    result = windows_task.run_task_command("install")

    script_path = tmp_path / "agent_private" / windows_task.RUNNER_SCRIPT_NAME
    assert result["create"]["returnCode"] == 0
    assert script_path.exists()
    assert "-m agent_private.cli daemon" in script_path.read_text(encoding="utf-8")
    assert calls == [
        [
            "schtasks.exe",
            "/Create",
            "/TN",
            windows_task.TASK_NAME,
            "/SC",
            "ONSTART",
            "/TR",
            str(script_path),
            "/RU",
            "SYSTEM",
            "/RL",
            "HIGHEST",
            "/F",
        ]
    ]


def test_task_status_reports_missing_when_query_fails(monkeypatch):
    monkeypatch.setattr(windows_task.platform, "system", lambda: "Windows")

    def fake_run(command, *, capture_output, text, timeout, check):
        return type("Result", (), {"returncode": 1, "stdout": "", "stderr": "not found"})()

    monkeypatch.setattr(windows_task.subprocess, "run", fake_run)

    assert windows_task.task_status()["status"] == "missing"
