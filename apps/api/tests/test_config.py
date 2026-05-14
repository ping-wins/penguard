from app.core.config import Settings


def test_mock_mode_defaults_to_live_when_env_is_absent(monkeypatch):
    monkeypatch.delenv("FORTIDASHBOARD_MOCK_MODE", raising=False)

    assert Settings(_env_file=None).mock_mode is False


def test_oauth_state_session_middleware_uses_secure_cookie_settings():
    from app.main import _session_middleware_options

    options = _session_middleware_options(
        Settings(
            _env_file=None,
            FORTIDASHBOARD_MOCK_MODE=True,
            FORTIDASHBOARD_SESSION_COOKIE_SECURE=True,
            FORTIDASHBOARD_SESSION_COOKIE_SAMESITE="strict",
        )
    )

    assert options["https_only"] is True
    assert options["same_site"] == "strict"
