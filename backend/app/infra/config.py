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

    database_url: str = "mysql+asyncmy://app:app@mariadb:3306/app?charset=utf8mb4"
    redis_url: str = "redis://redis:6379/0"

    jwt_secret_key: str = Field(default="change-me-in-production", repr=False)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    password_hash_iterations: int = 260_000
    internal_api_token: str | None = Field(default=None, repr=False)
    admin_emails: str = ""
    admin_secrets_key: str | None = Field(default=None, repr=False)

    http_timeout_seconds: float = 15
    http_max_connections: int = 100

    product_fetch_provider: str = "mock"
    product_fetch_request_timeout_seconds: float = 60
    product_fetch_retry_max_attempts: int = 3
    product_fetch_retry_base_delay_seconds: float = 0.25
    product_fetch_retry_max_delay_seconds: float = 5
    product_fetch_retry_jitter_ratio: float = 0.2

    apify_api_token: str | None = Field(default=None, repr=False)
    apify_actor_id: str | None = None
    apify_base_url: str = "https://api.apify.com"

    zyte_api_key: str | None = Field(default=None, repr=False)
    zyte_api_url: str = "https://api.zyte.com/v1/extract"

    check_default_interval_seconds: int = 3600
    check_batch_size: int = 100
    check_max_retries: int = 3
    check_lock_ttl_seconds: int = 180
    check_lock_retry_delay_seconds: int = 60
    check_scheduler_tick_seconds: int = 60
    dead_letter_max_items: int = 1000

    notification_dedupe_window_seconds: int = 86_400
    notification_max_retries: int = 3
    notification_retry_base_delay_seconds: int = 30
    notification_retry_max_delay_seconds: int = 300

    telegram_bot_token: str | None = None
    email_smtp_host: str | None = None
    email_smtp_port: int | None = None
    email_smtp_user: str | None = None
    email_smtp_password: str | None = Field(default=None, repr=False)
    email_smtp_from: str | None = None
    email_smtp_use_tls: bool = True

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
