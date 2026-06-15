from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql://hackathon:hackathon@localhost:5432/hotel_hackathon"
    )
    openai_api_key: str | None = None
    openai_model: str = "openai:gpt-5"
    openai_max_tokens: int = 900
    basic_auth_username: str = "gm"
    basic_auth_password: str = "change-me"
    app_base_url: str = "http://127.0.0.1:8000"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
