"""Application Configuration module using pydantic-settings."""

from typing import List, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Runtime
    ENVIRONMENT: Literal["development", "production", "test"] = "development"
    LOG_LEVEL: str = "INFO"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    WEB_PORT: int = 5173
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Security & Auth
    JWT_SECRET: str = Field(
        default="dev_jwt_secret_must_be_over_32_characters_long_for_security_reasons",
        min_length=32,
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    FIELD_ENCRYPTION_KEY: str = Field(
        default="dGhpcy1pcy1hLTMyLWJ5dGUtc2VjcmV0LWtleS1mb3ItZGV2IQ==",
        description="Fernet key for sensitive credentials encryption at rest",
    )

    # Datastores
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgrespassword@localhost:5432/jobpilot"
    TEST_DATABASE_URL: str = "sqlite+aiosqlite:///:memory:"
    REDIS_URL: str = "redis://localhost:6379/0"

    # AI Configuration
    LLM_PROVIDER: Literal["mock", "gemini", "openai"] = "mock"
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    DEFAULT_EMBEDDING_MODEL: str = "text-embedding-004"
    AI_PER_USER_DAILY_TOKEN_LIMIT: int = 50000

    # Uploads & Safety
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB
    ALLOWED_MIME_TYPES: str = (
        "application/pdf,"
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
        "text/plain,"
        "message/rfc822"
    )

    @property
    def cors_origin_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def allowed_mime_type_list(self) -> List[str]:
        return [mime.strip() for mime in self.ALLOWED_MIME_TYPES.split(",") if mime.strip()]


settings = Settings()
