from agent_private.tui import (
    AgentPrivateConfig,
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
