"""Application settings (pydantic-settings). Fails fast on missing/invalid required values."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_ENV_FILES = (".env", "../../.env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILES, extra="ignore", case_sensitive=False)

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite+aiosqlite:///./var/jobpilot.db"

    # Required secrets - no defaults, so a missing value aborts startup.
    jwt_secret: str = Field(min_length=32)
    encryption_key: str = Field(min_length=44)

    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    cookie_secure: bool = False
    access_token_minutes: int = 15
    refresh_token_days: int = 14
    login_max_attempts: int = 5
    login_lockout_base_seconds: int = 60

    llm_provider: Literal["mock", "openai", "gemini"] = "mock"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"
    llm_timeout_seconds: float = 30.0
    ai_daily_token_budget_per_user: int = 50_000
    ai_daily_token_budget_global: int = 1_000_000

    upload_dir: Path = Path("./var/uploads")
    max_upload_mb: int = 5
    inline_tasks: bool = True
    analytics_min_n: int = 20

    source_url_fetch_enabled: bool = True
    source_greenhouse_enabled: bool = True
    source_lever_enabled: bool = True
    source_ashby_enabled: bool = True
    source_rss_enabled: bool = True
    fetch_user_agent: str = "JobPilotAI/1.0 (personal job-search assistant)"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @model_validator(mode="after")
    def _check(self) -> Settings:
        if self.app_env == "production":
            self.cookie_secure = True
            if "change-me" in self.jwt_secret:
                raise ValueError("JWT_SECRET must be changed in production")
        if self.llm_provider == "openai" and not self.openai_api_key:
            raise ValueError("LLM_PROVIDER=openai requires OPENAI_API_KEY")
        if self.llm_provider == "gemini" and not self.gemini_api_key:
            raise ValueError("LLM_PROVIDER=gemini requires GEMINI_API_KEY")
        return self

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
