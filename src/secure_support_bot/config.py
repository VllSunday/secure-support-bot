from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "test", "production"] = "development"
    bot_mode: Literal["mock"] = "mock"
    telegram_bot_token: str | None = None
    telegram_webhook_secret: str | None = None
    database_url: str = "sqlite+aiosqlite:///./secure_support.db"
    company_assignment_secret: str = Field(
        default="dev-company-assignment-secret",
        min_length=16,
    )
    confirmation_hmac_secret: str = Field(
        default="dev-confirmation-hmac-secret",
        min_length=16,
    )
    risk_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    openai_api_key: str | None = None
    openai_model: str | None = None

    @model_validator(mode="after")
    def reject_development_secrets_in_production(self) -> Settings:
        if self.app_env == "production" and (
            self.company_assignment_secret.startswith("dev-")
            or self.confirmation_hmac_secret.startswith("dev-")
        ):
            raise ValueError("production requires non-default signing secrets")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
