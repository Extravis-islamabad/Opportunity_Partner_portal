import json
from pydantic_settings import BaseSettings, SettingsConfigDict, NoDecode
from pydantic import field_validator, model_validator
from typing import Annotated, List, Any


# Defaults that are safe for local dev but must never reach production. The
# startup validator below refuses to boot with APP_ENV=production if any of
# these is still in place.
_INSECURE_DEFAULTS = {
    "JWT_SECRET_KEY": "change-me-to-a-secure-random-string-min-32-chars",
    "SUPERADMIN_PASSWORD": "change-me-immediately",
}


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

    # CORS — Annotated[..., NoDecode] tells pydantic-settings to skip its
    # built-in JSON decoding so the field_validator below can accept either
    # JSON arrays or comma-separated strings from env vars.
    CORS_ORIGINS: Annotated[List[str], NoDecode] = ["http://localhost:3000", "http://localhost:5173"]

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
    ALLOWED_FILE_TYPES: Annotated[List[str], NoDecode] = [
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

    # Allow CORS_ORIGINS and ALLOWED_FILE_TYPES to be specified as either a
    # JSON array (CORS_ORIGINS=["a","b"]) or a comma-separated string
    # (ALLOWED_FILE_TYPES=application/pdf,image/png) when sourced from env vars.
    @field_validator("CORS_ORIGINS", "ALLOWED_FILE_TYPES", mode="before")
    @classmethod
    def _parse_list(cls, value: Any) -> Any:
        if value is None or isinstance(value, list):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    pass
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.strip().lower() in ("production", "prod")

    @property
    def docs_enabled(self) -> bool:
        # Never expose interactive docs / OpenAPI schema in production, even
        # if APP_DEBUG was left on by mistake.
        return self.APP_DEBUG and not self.is_production

    @model_validator(mode="after")
    def _enforce_production_safety(self) -> "Settings":
        """Refuse to boot a production deployment with insecure defaults.

        A default JWT secret lets anyone with the repo forge an admin token;
        a default superadmin password is an open door. Failing loudly at
        startup is far safer than silently running wide open.
        """
        if not self.is_production:
            return self

        problems: list[str] = []

        if self.JWT_SECRET_KEY == _INSECURE_DEFAULTS["JWT_SECRET_KEY"]:
            problems.append("JWT_SECRET_KEY is still the built-in default")
        if len(self.JWT_SECRET_KEY) < 32:
            problems.append("JWT_SECRET_KEY must be at least 32 characters")
        if self.SUPERADMIN_PASSWORD == _INSECURE_DEFAULTS["SUPERADMIN_PASSWORD"]:
            problems.append("SUPERADMIN_PASSWORD is still the built-in default")
        if any(o.startswith("http://") and "localhost" not in o and "127.0.0.1" not in o
               for o in self.CORS_ORIGINS):
            problems.append("CORS_ORIGINS contains a non-local plaintext http:// origin")

        if problems:
            raise ValueError(
                "Insecure configuration for APP_ENV=production:\n  - "
                + "\n  - ".join(problems)
                + "\nSet these via environment variables before deploying."
            )
        return self

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    @property
    def ai_is_configured(self) -> bool:
        return self.AI_ENABLED and bool(self.GROQ_API_KEY)


settings = Settings()
