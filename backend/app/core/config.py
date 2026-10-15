"""Application configuration via environment variables (12-factor)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Backend root (backend/) - .env lives here
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        env_prefix="DECOPS_",
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "DecOps API"
    environment: str = "development"  # development | testing | staging | production
    debug: bool = True
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"

    # --- Database ---
    # Production target is PostgreSQL (spec); SQLite is used for local sandbox development.
    database_url: str = f"sqlite:///{BACKEND_DIR / 'decops.db'}"

    # --- Sessions ---
    session_cookie_name: str = "decops_session"
    session_lifetime_minutes: int = 12 * 60  # 12 hours
    session_secret_key: str = "change-me-in-production-generate-a-real-secret"
    secure_cookies: bool = False  # True behind HTTPS in staging/production

    # --- Login throttling ---
    max_failed_logins: int = 5
    login_lockout_minutes: int = 15

    # --- CORS (the Nuxt dev server proxies /api, so this is a fallback for direct access) ---
    cors_origins: list[str] = ["http://localhost:3000"]

    # --- Seed admin (change via env in any real deployment) ---
    seed_admin_email: str = "admin@interdec.com"
    seed_admin_password: str = "DecOps!2026"
    seed_admin_name: str = "Interdec Administrator"
    seed_admin_employee_code: str = "INT-0001"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
