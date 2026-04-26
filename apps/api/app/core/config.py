from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FortiDashboard API"
    database_url: str = "postgresql+psycopg://fortidashboard:fortidashboard@localhost:5432/fortidashboard"
    secret_key: str = "dev-only-change-me"
    mock_mode: bool = True
    session_cookie_name: str = "fortidashboard_session"
    session_cookie_secure: bool = False
    keycloak_base_url: str = "http://localhost:8080"
    keycloak_realm: str = "fortidashboard"
    keycloak_client_id: str = "fortidashboard-bff"
    keycloak_client_secret: str = "dev-client-secret"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="FORTIDASHBOARD_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
