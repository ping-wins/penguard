from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

from agent_private.logs import agent_log_path, append_agent_log

TASK_NAME = "PenguardAgentDaemon"
TASK_DESCRIPTION = "Penguard endpoint telemetry daemon for Windows lab hosts."
RUNNER_SCRIPT_NAME = "run-agent-daemon.cmd"


def task_status(*, platform_name: str | None = None) -> dict[str, Any]:
    _require_windows(platform_name)
    result = _run_schtasks(
        ["/Query", "/TN", TASK_NAME, "/V", "/FO", "LIST"],
        timeout=10,
    )
    installed = result["returnCode"] == 0
    return {
        "task": TASK_NAME,
        "installed": installed,
        "status": _parse_task_state(result.get("stdout", "")) if installed else "missing",
        "query": result,
    }


def run_task_command(action: str) -> dict[str, Any]:
    _require_windows(None)
    if action == "status":
        return task_status()
    if action == "install":
        script_path = _write_runner_script()
        create_result = _run_schtasks(
            [
                "/Create",
                "/TN",
                TASK_NAME,
                "/SC",
                "ONSTART",
                "/TR",
                str(script_path),
                "/RU",
                "SYSTEM",
                "/RL",
                "HIGHEST",
                "/F",
            ],
            timeout=20,
        )
        return {
            "task": TASK_NAME,
            "action": action,
            "runnerScript": str(script_path),
            "create": create_result,
        }
    if action == "start":
        run_result = _run_schtasks(["/Run", "/TN", TASK_NAME])
        return {"task": TASK_NAME, "action": action, "run": run_result}
    if action == "stop":
        end_result = _run_schtasks(["/End", "/TN", TASK_NAME])
        return {"task": TASK_NAME, "action": action, "end": end_result}
    if action == "uninstall":
        delete_result = _run_schtasks(["/Delete", "/TN", TASK_NAME, "/F"], timeout=20)
        return {"task": TASK_NAME, "action": action, "delete": delete_result}
    raise ValueError(f"Unsupported task action: {action}")


def runner_script_path() -> Path:
    base = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData"))
    return base / "agent_private" / RUNNER_SCRIPT_NAME


def _write_runner_script() -> Path:
    script_path = runner_script_path()
    script_path.parent.mkdir(parents=True, exist_ok=True)
    workdir = Path.cwd()
    log_path = agent_log_path("daemon-task.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    content = "\r\n".join(
        [
            "@echo off",
            "setlocal",
            f'cd /d "{workdir}"',
            (
                f'"{sys.executable}" -m agent_private.cli daemon '
                f'>> "{log_path}" 2>&1'
            ),
            f"echo %DATE% %TIME% daemon exited with %ERRORLEVEL% >> \"{log_path}\"",
            "endlocal",
            "",
        ]
    )
    script_path.write_text(content, encoding="utf-8")
    append_agent_log(f"wrote scheduled task runner script at {script_path}", name="agent.log")
    return script_path


def _run_schtasks(args: list[str], *, timeout: float = 10) -> dict[str, Any]:
    command = ["schtasks.exe", *args]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return {"command": command, "returnCode": None, "error": str(exc)}
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "returnCode": None,
            "error": f"timed out after {timeout:g}s",
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
        }
    return {
        "command": command,
        "returnCode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def _parse_task_state(stdout: object) -> str:
    text = stdout if isinstance(stdout, str) else ""
    for line in text.splitlines():
        key, _, value = line.partition(":")
        if key.strip().lower() == "status" and value.strip():
            return value.strip().lower().replace(" ", "_")
    return "installed"


def _require_windows(platform_name: str | None) -> None:
    if (platform_name or platform.system()) != "Windows":
        raise RuntimeError("Windows Scheduled Task support requires Windows")
