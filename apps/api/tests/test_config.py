import re
from pathlib import Path

from app.core.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]


REQUIRED_BOOTSTRAP_ENV_KEYS = {
    "FORTIDASHBOARD_FORTIGATE_INGESTION_DEFAULT_INTERVAL_SECONDS",
    "FORTIDASHBOARD_FORTIGATE_INGESTION_MAX_INTERVAL_SECONDS",
    "FORTIDASHBOARD_FORTIGATE_INGESTION_MIN_INTERVAL_SECONDS",
    "FORTIDASHBOARD_FORTIGATE_INGESTION_SCHEDULER_ENABLED",
    "FORTIDASHBOARD_FORTIGATE_INGESTION_SCHEDULER_TICK_SECONDS",
    "FORTIDASHBOARD_FORTIGATE_SYSLOG_COLLECTOR_HOST",
    "FORTIDASHBOARD_FORTIGATE_SYSLOG_COLLECTOR_PORT",
    "FORTIDASHBOARD_FORTIGATE_SYSLOG_COLLECTOR_PUBLIC_HOST",
    "FORTIDASHBOARD_KEYCLOAK_BROWSER_BASE_URL",
    "FORTIDASHBOARD_KEYCLOAK_INTERNAL_BASE_URL",
    "FORTIDASHBOARD_KEYCLOAK_VERIFY_SSL",
    "FORTIDASHBOARD_KEYTAB_PATH",
    "FORTIDASHBOARD_OIDC_ISSUER",
    "FORTIDASHBOARD_SESSION_COOKIE_HTTPONLY",
    "FORTIDASHBOARD_SESSION_COOKIE_SAMESITE",
    "FORTIDASHBOARD_SSO_FAILURE_REDIRECT_URL",
    "FORTIDASHBOARD_SSO_POST_LOGIN_URL",
    "FORTIDASHBOARD_SSO_REDIRECT_URI",
    "FORTIDASHBOARD_ENABLE_LAB_DEMO_TOOLS",
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
    monkeypatch.delenv("FORTIDASHBOARD_MOCK_MODE", raising=False)

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
            FORTIDASHBOARD_MOCK_MODE=True,
            FORTIDASHBOARD_SESSION_COOKIE_SECURE=True,
            FORTIDASHBOARD_SESSION_COOKIE_SAMESITE="strict",
        )
    )

    assert options["https_only"] is True
    assert options["same_site"] == "strict"
