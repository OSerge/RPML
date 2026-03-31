from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_WEAK_JWT_SECRET = "dev-change-me-use-at-least-32-characters-secret"


class Settings(BaseSettings):
    """Application configuration loaded from environment."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "RPML Backend"
    database_url: str = "sqlite:///./local.db"
    debug: bool = False
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"
    celery_task_always_eager: bool = False
    jwt_secret_key: str = _DEFAULT_WEAK_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    @model_validator(mode="after")
    def reject_weak_jwt_secret_when_not_debug(self) -> Settings:
        if not self.debug and self.jwt_secret_key == _DEFAULT_WEAK_JWT_SECRET:
            msg = (
                "JWT_SECRET_KEY is set to the insecure default. "
                "Set a strong JWT_SECRET_KEY in the environment, or set DEBUG=true only for local development."
            )
            raise ValueError(msg)
        return self


settings = Settings()
