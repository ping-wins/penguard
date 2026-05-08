from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FortiDashboard API"
    database_url: str = "postgresql+psycopg://fortidashboard:fortidashboard@localhost:5432/fortidashboard"
    secret_key: str = "dev-only-change-me"
    token_encryption_key: str | None = None
    mock_mode: bool = False
    session_cookie_name: str = "fortidashboard_session"
    session_cookie_secure: bool = False
    csrf_cookie_name: str = "fortidashboard_csrf"
    csrf_header_name: str = "X-CSRF-Token"
    auth_rate_limit_max_attempts: int = 10
    auth_rate_limit_window_seconds: int = 60
    keycloak_base_url: str = "http://localhost:8080"
    keycloak_realm: str = "fortidashboard"
    keycloak_client_id: str = "fortidashboard-bff"
    keycloak_client_secret: str = "dev-client-secret"
    siem_kowalski_url: str = "http://localhost:8011"
    soar_skipper_url: str = "http://localhost:8012"
    xdr_rico_url: str = "http://localhost:8013"
    internal_service_timeout_seconds: float = 3.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="FORTIDASHBOARD_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
