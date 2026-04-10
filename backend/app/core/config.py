from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://extravis:extravis_secret@localhost:5432/partner_portal"
    DATABASE_ECHO: bool = False

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET_KEY: str = "change-me-to-a-secure-random-string-min-32-chars"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Email
    SMTP_HOST: str = "smtp.sendgrid.net"
    SMTP_PORT: int = 587
    SMTP_USER: str = "apikey"
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@extravis.com"
    SMTP_FROM_NAME: str = "Extravis Partner Portal"
    SMTP_TLS: bool = True

    # File Storage
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE_MB: int = 20
    ALLOWED_FILE_TYPES: List[str] = [
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "image/png",
        "image/jpeg",
    ]

    # Application
    APP_NAME: str = "Extravis Partner Portal"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    # Support
    SUPPORT_EMAIL: str = "support@extravis.com"

    # Frontend
    FRONTEND_URL: str = "http://localhost:5173"

    # Superadmin
    SUPERADMIN_EMAIL: str = "admin@extravis.com"
    SUPERADMIN_PASSWORD: str = "change-me-immediately"
    SUPERADMIN_NAME: str = "System Administrator"

    # Tokens
    ACTIVATION_TOKEN_EXPIRE_HOURS: int = 72
    PASSWORD_RESET_TOKEN_EXPIRE_HOURS: int = 1

    # Rate Limiting
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 30

    # Session
    SESSION_TIMEOUT_HOURS: int = 8

    # AI / Groq (free tier, OpenAI-compatible API)
    AI_ENABLED: bool = True
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_MODEL_DEFAULT: str = "llama-3.3-70b-versatile"
    GROQ_MODEL_FAST: str = "llama-3.1-8b-instant"
    GROQ_TIMEOUT_SECONDS: float = 20.0
    AI_SCORE_CACHE_SECONDS: int = 86400  # 24h for summaries

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    @property
    def ai_is_configured(self) -> bool:
        return self.AI_ENABLED and bool(self.GROQ_API_KEY)


settings = Settings()
