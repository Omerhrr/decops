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

    # --- Attachments (Phase 6: private, task-scoped document storage) ---
    attachment_storage_dir: Path = BACKEND_DIR / "var" / "attachments"
    attachment_max_bytes: int = 25 * 1024 * 1024  # 25 MB (spec: file size restrictions)
    attachment_allowed_extensions: list[str] = [
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".txt", ".csv", ".md", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".zip",
    ]

    # --- CSV migration (Phase 8: import center) ---
    import_storage_dir: Path = BACKEND_DIR / "var" / "imports"
    import_max_bytes: int = 10 * 1024 * 1024  # 10 MB per uploaded CSV
    import_batch_size: int = 100

    # --- Notifications & transactional outbox (Phase 6) ---
    outbox_worker_enabled: bool = True
    outbox_worker_interval_seconds: float = 15.0
    outbox_max_attempts: int = 8
    outbox_base_backoff_seconds: float = 30.0
    deadline_reminder_days: int = 3
    deadline_dedup_hours: int = 20

    # --- Optional email delivery (spec: "Email, if approved") ---
    email_notifications_enabled: bool = False
    smtp_host: str = "localhost"
    smtp_port: int = 25
    smtp_username: str = ""
    smtp_password: str = ""
    email_from: str = "decops@interdec.com"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
