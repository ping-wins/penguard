import asyncio

from textual.widgets import Button, Input, Static

import agent_private.tui as tui
from agent_private.tui import (
    AgentPrivateConfig,
    AgentPrivateTui,
    build_run_config,
    load_config,
    mask_secret,
    save_config,
)


def test_config_roundtrip_masks_token(tmp_path):
    config_path = tmp_path / "config.json"
    config = AgentPrivateConfig(
        api_url="http://localhost:8000",
        endpoint_id="raspi-01",
        enrollment_token="secret-enrollment-token",
        heartbeat_interval=10,
        connection_interval=20,
        process_interval=30,
        windows_security_interval=40,
    )

    save_config(config, config_path)
    loaded = load_config(config_path)

    assert loaded == config
    assert "secret-enrollment-token" in config_path.read_text()
    assert mask_secret(loaded.enrollment_token) == "secr***************oken"
    assert "secret-enrollment-token" not in loaded.safe_summary()
    assert loaded.safe_summary() == {
        "apiUrl": "http://localhost:8000",
        "endpointId": "raspi-01",
        "enrollmentToken": "secr***************oken",
        "heartbeatInterval": "10s",
        "connectionInterval": "20s",
        "processInterval": "30s",
        "windowsSecurityInterval": "40s",
    }


def test_windows_default_config_path_uses_programdata(monkeypatch):
    monkeypatch.setenv("PROGRAMDATA", "C:/ProgramData")

    assert tui._windows_config_base() == "C:/ProgramData"


def test_load_config_prefers_onboarding_env_over_stale_saved_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    save_config(
        AgentPrivateConfig(
            api_url="http://old-api:8000",
            endpoint_id="old-endpoint",
            enrollment_token="old-token",
            heartbeat_interval=12,
            connection_interval=34,
            process_interval=56,
            windows_security_interval=0,
        ),
        config_path,
    )
    monkeypatch.setenv("AGENT_PRIVATE_API_URL", "http://192.168.56.1:8000")
    monkeypatch.setenv("AGENT_PRIVATE_ENDPOINT_ID", "enr_new")
    monkeypatch.setenv("AGENT_PRIVATE_ENROLLMENT_TOKEN", "new-token")

    loaded = load_config(config_path)

    assert loaded.api_url == "http://192.168.56.1:8000"
    assert loaded.endpoint_id == "enr_new"
    assert loaded.enrollment_token == "new-token"
    assert loaded.heartbeat_interval == 12
    assert loaded.connection_interval == 34
    assert loaded.process_interval == 56


def test_build_run_config_disables_windows_security_when_interval_is_zero():
    config = AgentPrivateConfig(
        api_url="http://localhost:8000",
        endpoint_id="win-lab",
        enrollment_token="secret-enrollment-token",
        heartbeat_interval=10,
        connection_interval=20,
        process_interval=30,
        windows_security_interval=0,
    )

    run_config = build_run_config(config)

    assert run_config.api_url == "http://localhost:8000"
    assert run_config.endpoint_id == "win-lab"
    assert run_config.enrollment_token == "secret-enrollment-token"
    assert run_config.heartbeat_interval == 10
    assert run_config.connection_interval == 20
    assert run_config.process_interval == 30
    assert run_config.windows_security_interval is None


def test_tui_renders_windows_friendly_navigation_and_field_labels(tmp_path):
    async def run_app() -> None:
        app = AgentPrivateTui(config_path=tmp_path / "config.json")
        async with app.run_test():
            help_text = str(app.query_one("#operator-help", Static).render())
            assert "Tab" in help_text
            assert "Shift+Tab" in help_text
            assert "Enter" in help_text
            assert "Ctrl+V" in help_text

            assert str(app.query_one("#api-url-label", Static).render()) == "API URL"
            assert str(app.query_one("#endpoint-id-label", Static).render()) == "Endpoint ID"
            assert (
                str(app.query_one("#enrollment-token-label", Static).render())
                == "Enrollment token"
            )
            assert (
                str(app.query_one("#windows-security-interval-label", Static).render())
                == "Windows Security interval"
            )

            assert "Start" in str(app.query_one("#start-loop", Button).label)
            assert "(r)" in str(app.query_one("#start-loop", Button).label)
            assert "Stop" in str(app.query_one("#stop-loop", Button).label)
            assert "(x)" in str(app.query_one("#stop-loop", Button).label)

    asyncio.run(run_app())


def test_tui_ctrl_v_pastes_system_clipboard_into_focused_input(tmp_path, monkeypatch):
    monkeypatch.setattr(tui, "read_system_clipboard", lambda: "http://192.168.56.1:8000\nignored")

    async def run_app() -> None:
        app = AgentPrivateTui(config_path=tmp_path / "config.json")
        async with app.run_test() as pilot:
            api_url = app.query_one("#api-url", Input)
            api_url.value = ""
            api_url.focus()

            await pilot.press("ctrl+v")

            assert api_url.value == "http://192.168.56.1:8000"

    asyncio.run(run_app())


def test_tui_reports_post_failures_without_hiding_them(tmp_path, monkeypatch):
    def fail_post(**_kwargs):
        raise RuntimeError("401 Unauthorized for token secret-token")

    monkeypatch.setattr(tui, "post_endpoint_event", fail_post)

    async def run_app() -> None:
        app = AgentPrivateTui(config_path=tmp_path / "config.json")
        async with app.run_test():
            app.query_one("#api-url", Input).value = "http://localhost:8000"
            app.query_one("#endpoint-id", Input).value = "enr_01"
            app.query_one("#enrollment-token", Input).value = "secret-token"

            app._start_loop()

            log_text = str(app.query_one("#status-log", Static).render())
            counter_text = str(app.query_one("#telemetry-counters", Static).render())
            state_text = str(app.query_one("#agent-state", Static).render())
            assert "initial heartbeat failed" in log_text
            assert "secret-token" not in log_text
            assert "failed=1" in counter_text
            assert "running" in state_text

    asyncio.run(run_app())
