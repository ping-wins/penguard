from agent_private.tui import AgentPrivateConfig, load_config, mask_secret, save_config


def test_config_roundtrip_masks_token(tmp_path):
    config_path = tmp_path / "config.json"
    config = AgentPrivateConfig(
        api_url="http://localhost:8000",
        endpoint_id="raspi-01",
        enrollment_token="secret-enrollment-token",
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
    }
