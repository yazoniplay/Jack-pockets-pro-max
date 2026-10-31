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
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash-lite"
    ollama_api_key: str | None = None
    ollama_base_url: str = "https://ollama.com/v1"
    ollama_model: str = "gpt-oss:120b"
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "openai/gpt-oss-120b"
    pexels_api_key: str | None = None
    cors_origins: str = "http://localhost:3000,http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
