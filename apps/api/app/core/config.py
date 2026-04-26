from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FortiDashboard API"
    database_url: str = "postgresql+psycopg://fortidashboard:fortidashboard@localhost:5432/fortidashboard"
    secret_key: str = "dev-only-change-me"
    mock_mode: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="FORTIDASHBOARD_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
