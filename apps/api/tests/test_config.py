import re
from pathlib import Path

from app.core.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]


REQUIRED_BOOTSTRAP_ENV_KEYS = {
    "PENGUARD_FORTIGATE_INGESTION_DEFAULT_INTERVAL_SECONDS",
    "PENGUARD_FORTIGATE_INGESTION_MAX_INTERVAL_SECONDS",
    "PENGUARD_FORTIGATE_INGESTION_MIN_INTERVAL_SECONDS",
    "PENGUARD_FORTIGATE_INGESTION_SCHEDULER_ENABLED",
    "PENGUARD_FORTIGATE_INGESTION_SCHEDULER_TICK_SECONDS",
    "PENGUARD_FORTIGATE_SYSLOG_COLLECTOR_HOST",
    "PENGUARD_FORTIGATE_SYSLOG_COLLECTOR_PORT",
    "PENGUARD_FORTIGATE_SYSLOG_COLLECTOR_PUBLIC_HOST",
    "PENGUARD_KEYCLOAK_BROWSER_BASE_URL",
    "PENGUARD_KEYCLOAK_INTERNAL_BASE_URL",
    "PENGUARD_KEYCLOAK_VERIFY_SSL",
    "PENGUARD_KEYTAB_PATH",
    "PENGUARD_OIDC_ISSUER",
    "PENGUARD_SESSION_COOKIE_HTTPONLY",
    "PENGUARD_SESSION_COOKIE_SAMESITE",
    "PENGUARD_SSO_FAILURE_REDIRECT_URL",
    "PENGUARD_SSO_POST_LOGIN_URL",
    "PENGUARD_SSO_REDIRECT_URI",
    "PENGUARD_ENABLE_LAB_DEMO_TOOLS",
}


def _env_keys_from(path: str) -> set[str]:
    return set(
        re.findall(
            r"^([A-Z][A-Z0-9_]+)=",
            (REPO_ROOT / path).read_text(encoding="utf-8"),
            re.MULTILINE,
        )
    )


def test_bootstrap_scripts_emit_current_deployment_env_keys():
    example_keys = _env_keys_from(".env.example")
    sh_keys = _env_keys_from("scripts/bootstrap-secrets.sh")
    ps1_keys = _env_keys_from("scripts/bootstrap-secrets.ps1")

    assert REQUIRED_BOOTSTRAP_ENV_KEYS <= example_keys
    assert REQUIRED_BOOTSTRAP_ENV_KEYS <= sh_keys
    assert REQUIRED_BOOTSTRAP_ENV_KEYS <= ps1_keys


def test_mock_mode_defaults_to_live_when_env_is_absent(monkeypatch):
    monkeypatch.delenv("PENGUARD_MOCK_MODE", raising=False)

    assert Settings(_env_file=None).mock_mode is False


def test_fortigate_syslog_collector_is_native_default():
    settings = Settings(_env_file=None)

    assert not hasattr(settings, "fortigate_syslog_collector_enabled")
    assert settings.fortigate_syslog_collector_host == "0.0.0.0"
    assert settings.fortigate_syslog_collector_port == 5514


def test_oauth_state_session_middleware_uses_secure_cookie_settings():
    from app.main import _session_middleware_options

    options = _session_middleware_options(
        Settings(
            _env_file=None,
            PENGUARD_MOCK_MODE=True,
            PENGUARD_SESSION_COOKIE_SECURE=True,
            PENGUARD_SESSION_COOKIE_SAMESITE="strict",
        )
    )

    assert options["https_only"] is True
    assert options["same_site"] == "strict"
