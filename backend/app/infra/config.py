from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    app_env: str = "local"
    app_debug: bool = True
    app_name: str = "price-monitor"

    database_url: str = "postgresql+asyncpg://app:app@postgres:5432/app"
    redis_url: str = "redis://redis:6379/0"

    jwt_secret_key: str = Field(default="change-me-in-production", repr=False)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    password_hash_iterations: int = 260_000
    internal_api_token: str | None = Field(default=None, repr=False)

    http_timeout_seconds: float = 15
    http_max_connections: int = 100

    check_default_interval_seconds: int = 3600
    check_batch_size: int = 100
    check_max_retries: int = 3

    telegram_bot_token: str | None = None
    email_smtp_host: str | None = None
    email_smtp_port: int | None = None
    email_smtp_user: str | None = None
    email_smtp_password: str | None = Field(default=None, repr=False)

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
