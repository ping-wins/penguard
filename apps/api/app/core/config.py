from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Values that must never reach a non-mock deployment. The bootstrap script
# (`scripts/bootstrap-secrets.{sh,ps1}`) replaces these with random per-deploy
# values. Add any new dev-default to this set when introducing a new secret.
DANGEROUS_DEFAULT_SECRETS: frozenset[str] = frozenset(
    {
        "dev-only-change-me",
        "change-me-in-local-env",
        "dev-client-secret",
    }
)


class DangerousDefaultSecretError(RuntimeError):
    """Raised at startup when a critical secret still equals its dev default."""


class Settings(BaseSettings):
    app_name: str = "FortiDashboard API"
    database_url: str = (
        "postgresql+psycopg://fortidashboard:fortidashboard@localhost:5432/fortidashboard"
    )
    secret_key: str = "dev-only-change-me"
    token_encryption_key: str | None = None
    mock_mode: bool = False
    session_cookie_name: str = "fortidashboard_session"
    session_cookie_secure: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "FORTIDASHBOARD_SESSION_COOKIE_SECURE",
            "SESSION_COOKIE_SECURE",
        ),
    )
    session_cookie_samesite: str = Field(
        default="lax",
        validation_alias=AliasChoices(
            "FORTIDASHBOARD_SESSION_COOKIE_SAMESITE",
            "SESSION_COOKIE_SAMESITE",
        ),
    )
    session_cookie_httponly: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "FORTIDASHBOARD_SESSION_COOKIE_HTTPONLY",
            "SESSION_COOKIE_HTTPONLY",
        ),
    )
    csrf_cookie_name: str = "fortidashboard_csrf"
    csrf_header_name: str = "X-CSRF-Token"
    auth_rate_limit_max_attempts: int = 10
    auth_rate_limit_window_seconds: int = 60
    keycloak_base_url: str = "http://localhost:8080"
    keycloak_browser_base_url: str = "http://localhost:8080"
    keycloak_realm: str = "fortidashboard"
    keycloak_client_id: str = "fortidashboard-bff"
    keycloak_client_secret: str = "dev-client-secret"
    keycloak_verify_ssl: bool = False
    oidc_issuer: str = "http://localhost:8080/realms/fortidashboard"
    sso_redirect_uri: str = "http://localhost:8000/api/auth/sso/kerberos/callback"
    sso_post_login_url: str = "http://localhost:5173/"
    sso_failure_redirect_url: str = "http://localhost:5173/login"
    sso_state_cookie_name: str = "fortidashboard_sso_state"
    siem_kowalski_url: str = "http://localhost:8011"
    soar_skipper_url: str = "http://localhost:8012"
    xdr_rico_url: str = "http://localhost:8013"
    internal_service_timeout_seconds: float = 3.0
    fortigate_ingestion_scheduler_enabled: bool = False
    fortigate_ingestion_scheduler_tick_seconds: int = 10
    fortigate_ingestion_default_interval_seconds: int = 30
    fortigate_ingestion_min_interval_seconds: int = 10
    fortigate_ingestion_max_interval_seconds: int = 3600
    fortigate_syslog_collector_host: str = "0.0.0.0"
    fortigate_syslog_collector_public_host: str | None = None
    fortigate_syslog_collector_port: int = 5514
    xdr_agent_discovery_enabled: bool = True
    xdr_agent_discovery_host: str = "0.0.0.0"
    xdr_agent_discovery_port: int = 8764
    xdr_agent_discovery_api_scheme: str = "http"
    xdr_agent_discovery_api_port: int = 8000
    enable_lab_demo_tools: bool = False
    ai_provider: str = ""
    ai_api_key: str = ""
    ai_model: str = ""
    ai_base_url: str = ""
    threat_intel_provider: str = "virustotal"
    threat_intel_cache_ttl_seconds: int = 3600
    virustotal_api_key: str = ""
    virustotal_base_url: str = "https://www.virustotal.com"
    soc_ingest_token: str = ""
    marketplace_gh_token: str | None = None
    marketplace_registry_repo: str = "ping-wins/fortidashboard-addons"
    addons_storage_dir: Path = Path("/app/data/addons")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="FORTIDASHBOARD_",
        extra="ignore",
    )


def _reject_dangerous_defaults(settings: Settings) -> None:
    """Fail-closed boot guard. `mock_mode=true` bypasses the check so local
    dev/test loops keep working. Production deployments must run with the
    real `.env` produced by `scripts/bootstrap-secrets.{sh,ps1}`.
    """
    if settings.mock_mode:
        return

    offenders: list[str] = []
    if settings.secret_key in DANGEROUS_DEFAULT_SECRETS:
        offenders.append("FORTIDASHBOARD_SECRET_KEY")
    if (
        not settings.token_encryption_key
        or settings.token_encryption_key in DANGEROUS_DEFAULT_SECRETS
    ):
        offenders.append("FORTIDASHBOARD_TOKEN_ENCRYPTION_KEY")
    if settings.keycloak_client_secret in DANGEROUS_DEFAULT_SECRETS:
        offenders.append("FORTIDASHBOARD_KEYCLOAK_CLIENT_SECRET")

    if offenders:
        joined = ", ".join(offenders)
        raise DangerousDefaultSecretError(
            f"Refusing to start: the following secrets still use the dev "
            f"default: {joined}. Run `scripts/bootstrap-secrets.sh` (or "
            f"`scripts/bootstrap-secrets.ps1` on Windows) to generate a "
            f"per-deploy .env, or set FORTIDASHBOARD_MOCK_MODE=true for "
            f"local development."
        )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    _reject_dangerous_defaults(settings)
    return settings
