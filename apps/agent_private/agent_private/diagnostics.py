from __future__ import annotations

import importlib
import os
import platform
import socket
import subprocess
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from agent_private.logs import agent_log_path, list_log_files, read_recent_log, redact_text

COMMAND_TIMEOUT_SECONDS = 5
COMMAND_OUTPUT_LIMIT = 12_000


def collect_agent_diagnostics(
    *,
    reason: str = "manual",
    extra_secrets: Sequence[str] = (),
    command_timeout: float = COMMAND_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    config_payload = _load_config_payload()
    secrets = [*extra_secrets]
    token = config_payload.get("enrollmentTokenRaw")
    if isinstance(token, str) and token:
        secrets.append(token)
    config_payload.pop("enrollmentTokenRaw", None)

    diagnostics: dict[str, Any] = {
        "collectedAt": _timestamp(),
        "reason": reason,
        "host": _host_payload(),
        "runtime": _runtime_payload(),
        "config": config_payload,
        "logs": _logs_payload(secrets),
        "imports": _imports_payload(),
        "network": _network_payload(config_payload),
    }
    if platform.system() == "Windows":
        diagnostics["windows"] = _windows_payload(command_timeout, secrets)
    return diagnostics


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _host_payload() -> dict[str, Any]:
    return {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "user": os.environ.get("USERNAME") or os.environ.get("USER") or "",
    }


def _runtime_payload() -> dict[str, Any]:
    return {
        "pythonExecutable": sys.executable,
        "pythonVersion": sys.version,
        "cwd": os.getcwd(),
        "argv0": sys.argv[0] if sys.argv else "",
        "packageDir": str(Path(__file__).resolve().parent),
        "pathHead": os.environ.get("PATH", "").split(os.pathsep)[:8],
        "programData": os.environ.get("PROGRAMDATA"),
        "virtualEnv": os.environ.get("VIRTUAL_ENV"),
    }


def _load_config_payload() -> dict[str, Any]:
    try:
        from agent_private.tui import default_config_path, load_config

        path = default_config_path()
        config = load_config(path)
        payload: dict[str, Any] = {
            "path": str(path),
            "exists": path.exists(),
            "safeSummary": config.safe_summary(),
            "enrollmentTokenRaw": config.enrollment_token,
            "envOverrides": {
                "AGENT_PRIVATE_API_URL": bool(os.environ.get("AGENT_PRIVATE_API_URL")),
                "AGENT_PRIVATE_ENDPOINT_ID": bool(os.environ.get("AGENT_PRIVATE_ENDPOINT_ID")),
                "AGENT_PRIVATE_ENROLLMENT_TOKEN": bool(
                    os.environ.get("AGENT_PRIVATE_ENROLLMENT_TOKEN")
                ),
            },
        }
        if path.exists():
            stat = path.stat()
            payload["sizeBytes"] = stat.st_size
        return payload
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def _logs_payload(secrets: Sequence[str]) -> dict[str, Any]:
    return {
        "files": list_log_files(),
        "agentLogPath": str(agent_log_path("agent.log")),
        "agentLogTail": redact_text(read_recent_log("agent.log"), secrets),
        "taskLogPath": str(agent_log_path("daemon-task.log")),
        "taskLogTail": redact_text(read_recent_log("daemon-task.log"), secrets),
        "serviceLogPath": str(agent_log_path("service.log")),
        "serviceLogTail": redact_text(read_recent_log("service.log"), secrets),
    }


def _imports_payload() -> dict[str, Any]:
    module_names = [
        "agent_private.cli",
        "agent_private.daemon",
        "agent_private.runner",
        "agent_private.tui",
        "httpx",
        "psutil",
        "textual",
        "win32serviceutil",
        "win32service",
        "win32event",
        "servicemanager",
    ]
    return {name: _import_status(name) for name in module_names}


def _import_status(module_name: str) -> dict[str, Any]:
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    version = getattr(module, "__version__", None)
    path = getattr(module, "__file__", None)
    return {"ok": True, "version": version, "path": path}


def _network_payload(config_payload: dict[str, Any]) -> dict[str, Any]:
    safe_summary = config_payload.get("safeSummary")
    api_url = ""
    if isinstance(safe_summary, dict):
        api_url = str(safe_summary.get("apiUrl") or "")
    if not api_url:
        return {"configured": False}

    parsed = urlparse(api_url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    payload: dict[str, Any] = {
        "configured": True,
        "apiUrl": api_url,
        "host": host,
        "port": port,
        "tcpConnect": _tcp_probe(host, port),
        "httpProbes": [],
    }
    for path in ("/health/live", "/api/health/live", "/"):
        payload["httpProbes"].append(_http_probe(api_url, path))
    return payload


def _tcp_probe(host: str, port: int) -> dict[str, Any]:
    try:
        with socket.create_connection((host, port), timeout=2):
            return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _http_probe(api_url: str, path: str) -> dict[str, Any]:
    try:
        response = httpx.get(f"{api_url.rstrip('/')}{path}", timeout=2, follow_redirects=False)
        return {"path": path, "ok": response.status_code < 500, "statusCode": response.status_code}
    except Exception as exc:  # noqa: BLE001
        return {"path": path, "ok": False, "error": str(exc)}


def _windows_payload(timeout: float, secrets: Sequence[str]) -> dict[str, Any]:
    commands = {
        "whoami": ["whoami.exe"],
        "whoamiAll": ["whoami.exe", "/all"],
        "wherePython": ["where.exe", "python"],
        "whereUv": ["where.exe", "uv"],
        "whereAgentPrivate": ["where.exe", "agent-private"],
        "taskListPython": ["tasklist.exe", "/FI", "IMAGENAME eq python.exe", "/V"],
        "taskListPythonService": ["tasklist.exe", "/FI", "IMAGENAME eq pythonservice.exe", "/V"],
        "taskListAgentPrivate": ["tasklist.exe", "/FI", "IMAGENAME eq agent-private.exe", "/V"],
        "ipconfigAll": ["ipconfig.exe", "/all"],
        "routePrint": ["route.exe", "print"],
        "netstatTcp": ["netstat.exe", "-ano", "-p", "tcp"],
        "serviceQuery": ["sc.exe", "queryex", "FortiDashboardAgent"],
        "serviceConfig": ["sc.exe", "qc", "FortiDashboardAgent"],
        "serviceRegistry": [
            "reg.exe",
            "query",
            "HKLM\\SYSTEM\\CurrentControlSet\\Services\\FortiDashboardAgent",
            "/s",
        ],
        "taskQuery": [
            "schtasks.exe",
            "/Query",
            "/TN",
            "FortiDashboardAgentDaemon",
            "/V",
            "/FO",
            "LIST",
        ],
        "serviceEvents": [
            "wevtutil.exe",
            "qe",
            "System",
            "/q:*[System[Provider[@Name='Service Control Manager']]]",
            "/c:30",
            "/rd:true",
            "/f:text",
        ],
        "taskEvents": [
            "wevtutil.exe",
            "qe",
            "Microsoft-Windows-TaskScheduler/Operational",
            "/c:30",
            "/rd:true",
            "/f:text",
        ],
        "applicationEvents": ["wevtutil.exe", "qe", "Application", "/c:30", "/rd:true", "/f:text"],
    }
    return {
        name: _run_command(command, timeout=timeout, secrets=secrets)
        for name, command in commands.items()
    }


def _run_command(
    command: Sequence[str],
    *,
    timeout: float,
    secrets: Sequence[str],
) -> dict[str, Any]:
    try:
        result = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return {"command": list(command), "returnCode": None, "error": str(exc)}
    except subprocess.TimeoutExpired as exc:
        return {
            "command": list(command),
            "returnCode": None,
            "error": f"timed out after {timeout:g}s",
            "stdout": _truncate(redact_text(exc.stdout or "", secrets)),
            "stderr": _truncate(redact_text(exc.stderr or "", secrets)),
        }
    except Exception as exc:  # noqa: BLE001
        return {"command": list(command), "returnCode": None, "error": str(exc)}
    return {
        "command": list(command),
        "returnCode": result.returncode,
        "stdout": _truncate(redact_text(result.stdout or "", secrets)),
        "stderr": _truncate(redact_text(result.stderr or "", secrets)),
    }


def _truncate(value: str, limit: int = COMMAND_OUTPUT_LIMIT) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}...<truncated>"
