"""Boot-time guard: refuse to start when critical secrets still equal the
dev defaults. The check lives in `get_settings()` (not on the model itself)
so direct `Settings(...)` instantiation stays usable in tests.
"""

from __future__ import annotations

import pytest

from app.core.config import (
    DANGEROUS_DEFAULT_SECRETS,
    DangerousDefaultSecretError,
    Settings,
    _reject_dangerous_defaults,
    get_settings,
)


def _strong_settings(**overrides) -> Settings:
    safe = {
        "secret_key": "test-only-strong-secret-key",
        "token_encryption_key": "test-only-strong-fernet-key",
        "keycloak_client_secret": "test-only-strong-client-secret",
        "mock_mode": False,
    }
    safe.update(overrides)
    return Settings(_env_file=None, **safe)


def test_strong_secrets_pass_validation():
    _reject_dangerous_defaults(_strong_settings())


def test_mock_mode_bypasses_check():
    # Mock mode is the only legitimate way to boot without rotating secrets.
    _reject_dangerous_defaults(
        Settings(
            _env_file=None,
            secret_key="dev-only-change-me",
            token_encryption_key=None,
            keycloak_client_secret="dev-client-secret",
            mock_mode=True,
        )
    )


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("secret_key", "dev-only-change-me", "PENGUARD_SECRET_KEY"),
        ("secret_key", "change-me-in-local-env", "PENGUARD_SECRET_KEY"),
        ("keycloak_client_secret", "dev-client-secret", "PENGUARD_KEYCLOAK_CLIENT_SECRET"),
    ],
)
def test_dangerous_default_is_rejected(field: str, value: str, expected: str) -> None:
    s = _strong_settings(**{field: value})
    with pytest.raises(DangerousDefaultSecretError) as exc_info:
        _reject_dangerous_defaults(s)
    assert expected in str(exc_info.value)


def test_missing_token_encryption_key_is_rejected():
    s = _strong_settings(token_encryption_key=None)
    with pytest.raises(DangerousDefaultSecretError) as exc_info:
        _reject_dangerous_defaults(s)
    assert "PENGUARD_TOKEN_ENCRYPTION_KEY" in str(exc_info.value)


def test_get_settings_enforces_check(monkeypatch):
    # Clear the lru_cache so each call rebuilds Settings from the env.
    get_settings.cache_clear()
    for name, value in [
        ("PENGUARD_MOCK_MODE", "false"),
        ("PENGUARD_SECRET_KEY", "dev-only-change-me"),
        ("PENGUARD_TOKEN_ENCRYPTION_KEY", ""),
        ("PENGUARD_KEYCLOAK_CLIENT_SECRET", "dev-client-secret"),
    ]:
        monkeypatch.setenv(name, value)

    with pytest.raises(DangerousDefaultSecretError):
        get_settings()

    get_settings.cache_clear()


def test_dangerous_default_set_is_authoritative():
    # Anyone adding a new dev default must add it to DANGEROUS_DEFAULT_SECRETS
    # so the boot guard catches it. This test is a tripwire if someone
    # silently introduces a new dev string but forgets to register it.
    assert "dev-only-change-me" in DANGEROUS_DEFAULT_SECRETS
    assert "change-me-in-local-env" in DANGEROUS_DEFAULT_SECRETS
    assert "dev-client-secret" in DANGEROUS_DEFAULT_SECRETS
