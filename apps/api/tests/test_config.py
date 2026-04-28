from app.core.config import Settings


def test_mock_mode_defaults_to_live_when_env_is_absent(monkeypatch):
    monkeypatch.delenv("FORTIDASHBOARD_MOCK_MODE", raising=False)

    assert Settings(_env_file=None).mock_mode is False
