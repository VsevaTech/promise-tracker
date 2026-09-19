"""Runtime configuration. Everything comes from the environment; nothing is hardcoded."""

from __future__ import annotations

from datetime import time
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- AI ---------------------------------------------------------------
    gemini_api_key: str = Field(default="", description="Free-tier Google Gemini API key")
    gemini_model: str = Field(default="", description="Model id, e.g. gemini-3.5-flash")
    extractor: str = Field(
        default="auto",
        description="auto | gemini | rules — 'auto' uses Gemini when a key is configured",
    )
    ai_timeout_seconds: float = 45.0

    # --- calendar ---------------------------------------------------------
    default_due_time: str = Field(default="09:00", description="Time used when none was stated")
    alarm_minutes_before: int = Field(default=60, ge=0, le=60 * 24 * 14)
    event_duration_minutes: int = Field(default=30, ge=5, le=60 * 8)
    calendar_timezone: str = Field(default="UTC")

    # --- limits -----------------------------------------------------------
    max_conversation_chars: int = Field(default=60_000, ge=1_000)
    max_upload_bytes: int = Field(default=1_000_000, ge=1_000)

    @field_validator("extractor")
    @classmethod
    def _known_extractor(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"auto", "gemini", "rules"}:
            raise ValueError("EXTRACTOR must be one of: auto, gemini, rules")
        return value

    @property
    def due_time(self) -> time:
        hour, _, minute = self.default_due_time.partition(":")
        return time(int(hour), int(minute or 0))

    @property
    def gemini_enabled(self) -> bool:
        if self.extractor == "rules":
            return False
        if self.extractor == "gemini":
            return True
        return bool(self.gemini_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
