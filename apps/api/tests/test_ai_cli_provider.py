"""Tests for the CLI subprocess provider."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.cli_provider import (
    CliAIProvider,
    CliInvocationError,
    _flatten_messages,
    describe_cli_invocation,
)
from app.ai.provider import AIConfigurationError, IncidentContext
from app.main import app


def _stub_runner(result: subprocess.CompletedProcess[str]):
    calls: list[dict[str, Any]] = []

    def runner(argv, **kwargs):
        calls.append({"argv": argv, "input": kwargs.get("input"), "timeout": kwargs.get("timeout")})
        return result

    runner.calls = calls  # type: ignore[attr-defined]
    return runner


def _make_binary(tmp_path: Path, name: str) -> Path:
    binary = tmp_path / name
    binary.write_text("#!/usr/bin/env bash\necho stub\n")
    binary.chmod(0o755)
    return binary


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_validate_binary_rejects_missing_path():
    with pytest.raises(AIConfigurationError):
        CliAIProvider(binary_path="/does/not/exist/claude")


def test_validate_binary_rejects_newline_injection(tmp_path):
    bogus = str(tmp_path / "claude") + "\nrm -rf /"
    with pytest.raises(AIConfigurationError):
        CliAIProvider(binary_path=bogus)


def test_detect_flavor_recognises_claude_and_codex(tmp_path):
    claude_bin = _make_binary(tmp_path, "claude")
    codex_bin = _make_binary(tmp_path, "codex")
    assert CliAIProvider(binary_path=str(claude_bin)).flavor == "claude"
    assert CliAIProvider(binary_path=str(codex_bin)).flavor == "codex"


# ---------------------------------------------------------------------------
# argv shape
# ---------------------------------------------------------------------------


def test_claude_argv_includes_bare_and_print_flags(tmp_path):
    binary = _make_binary(tmp_path, "claude")
    provider = CliAIProvider(binary_path=str(binary), model="sonnet")
    argv = provider._build_argv(output_format="json")
    assert "-p" in argv
    assert "--bare" in argv
    assert "--output-format" in argv
    assert "json" in argv
    assert "--model" in argv and "sonnet" in argv


def test_codex_argv_uses_exec_subcommand(tmp_path):
    binary = _make_binary(tmp_path, "codex")
    provider = CliAIProvider(binary_path=str(binary))
    argv = provider._build_argv(output_format="json")
    assert argv[1] == "exec"
    assert "--json" in argv


# ---------------------------------------------------------------------------
# chat / analyze round-trip with mocked subprocess
# ---------------------------------------------------------------------------


def test_chat_passes_prompt_via_stdin_and_returns_text(tmp_path):
    binary = _make_binary(tmp_path, "claude")
    runner = _stub_runner(
        subprocess.CompletedProcess(args=[], returncode=0, stdout="hello back\n", stderr="")
    )
    provider = CliAIProvider(binary_path=str(binary), runner=runner)

    reply = provider.chat([{"role": "user", "content": "hi"}])

    assert reply == "hello back"
    assert "[Assistant]" in runner.calls[0]["input"]


def test_analyze_unwraps_claude_json_envelope(tmp_path):
    binary = _make_binary(tmp_path, "claude")
    inner = (
        '{"headline":"x","summary":"y","risk_score":80,'
        '"suggested_triage":"T1","suggested_ticket_status":"investigating",'
        '"indicators_of_compromise":[],"next_steps":[],"references":[],'
        '"cvss_score":7.5,"cvss_severity":"High",'
        '"cvss_vector":"CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N"}'
    )
    envelope = json.dumps({"type": "result", "result": inner})
    runner = _stub_runner(
        subprocess.CompletedProcess(args=[], returncode=0, stdout=envelope, stderr="")
    )
    provider = CliAIProvider(binary_path=str(binary), runner=runner)

    ctx = IncidentContext(
        incident_id="inc-1",
        title="t",
        severity="high",
        triage_level="T1",
        ticket_status="new",
        summary="",
    )
    analysis = provider.analyze_incident(ctx)
    assert analysis.risk_score == 80
    assert analysis.cvss_severity == "High"


def test_nonzero_exit_raises_cli_invocation_error(tmp_path):
    binary = _make_binary(tmp_path, "claude")
    runner = _stub_runner(
        subprocess.CompletedProcess(args=[], returncode=2, stdout="", stderr="boom")
    )
    provider = CliAIProvider(binary_path=str(binary), runner=runner)
    with pytest.raises(CliInvocationError):
        provider.chat([{"role": "user", "content": "hi"}])


# ---------------------------------------------------------------------------
# Probe diagnostic
# ---------------------------------------------------------------------------


def test_describe_cli_invocation_reports_flavor(tmp_path):
    binary = _make_binary(tmp_path, "claude")
    probe = describe_cli_invocation(str(binary))
    assert probe["ok"] is True
    assert probe["flavor"] == "claude"
    assert "-p" in probe["argvPreview"]


def test_describe_cli_invocation_rejects_unknown_binary(tmp_path):
    binary = _make_binary(tmp_path, "weirdcli")
    probe = describe_cli_invocation(str(binary))
    assert probe["ok"] is False


def test_describe_cli_invocation_reports_missing_file():
    probe = describe_cli_invocation("/no/such/path/claude")
    assert probe["ok"] is False
    assert "not found" in probe["error"].lower() or "empty" in probe["error"].lower()


# ---------------------------------------------------------------------------
# HTTP probe endpoint
# ---------------------------------------------------------------------------


def test_probe_endpoint_returns_diagnostic(tmp_path):
    binary = _make_binary(tmp_path, "claude")
    client = TestClient(app)
    csrf = client.get("/api/auth/csrf").json()["csrfToken"]
    response = client.post(
        "/api/ai/preferences/cli/probe",
        headers={"X-CSRF-Token": csrf},
        json={"binaryPath": str(binary)},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["flavor"] == "claude"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_flatten_messages_includes_system_and_labels_turns():
    text = _flatten_messages(
        [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}],
        system="you are a SOC bot",
    )
    assert "[system]" in text
    assert "[User]" in text
    assert "[Assistant]" in text
