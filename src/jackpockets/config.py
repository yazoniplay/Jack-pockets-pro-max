"""Environment-backed configuration with safe defaults."""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Jack Pockets Pro Max"
    database_path: str = "data/jackpockets.db"
    job_retention_days: int = 30
    request_timeout_seconds: float = 90.0
    max_provider_retries: int = 2
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-3-7-sonnet-latest"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1"
    cors_origins: str = "http://localhost:3000,http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
