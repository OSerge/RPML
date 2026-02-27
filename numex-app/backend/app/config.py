"""Application configuration via pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_name: str = "FinTech API"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://user:pass@localhost:5432/fintech"
    database_url_sync: str = "postgresql://user:pass@localhost:5432/fintech"

    redis_url: str = "redis://localhost:6379/0"

    secret_key: str = "change-me-in-production-use-openssl-rand-hex-32"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    supabase_jwt_secret: str = ""

    vllm_url: str = "http://localhost:8001/v1"
    vllm_api_key: str = "not-needed"


settings = Settings()
