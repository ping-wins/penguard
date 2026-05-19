from __future__ import annotations

from agent_private import diagnostics, tui
from agent_private.logs import append_agent_log


def test_collect_diagnostics_redacts_config_token(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    tui.save_config(
        tui.AgentPrivateConfig(
            api_url="http://127.0.0.1:8000",
            endpoint_id="enr_01",
            enrollment_token="secret-token",
        ),
        config_path,
    )
    monkeypatch.setattr(tui, "default_config_path", lambda: config_path)
    monkeypatch.setattr(
        diagnostics,
        "_network_payload",
        lambda config_payload: {"configured": True},
    )
    monkeypatch.setattr(diagnostics, "_windows_payload", lambda timeout, secrets: {})

    payload = diagnostics.collect_agent_diagnostics(reason="unit-test")

    assert payload["reason"] == "unit-test"
    assert payload["config"]["safeSummary"]["enrollmentToken"] == "secr****oken"
    assert "secret-token" not in repr(payload)


def test_collect_diagnostics_includes_recent_logs(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    append_agent_log("post failed with secret-token", secrets=["secret-token"])
    monkeypatch.setattr(
        diagnostics,
        "_network_payload",
        lambda config_payload: {"configured": False},
    )
    monkeypatch.setattr(diagnostics, "_windows_payload", lambda timeout, secrets: {})

    payload = diagnostics.collect_agent_diagnostics(
        reason="unit-test",
        extra_secrets=["secret-token"],
    )

    assert "post failed with [redacted]" in payload["logs"]["agentLogTail"]
    assert "secret-token" not in payload["logs"]["agentLogTail"]
