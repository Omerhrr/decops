"""Application configuration via environment variables (12-factor)."""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
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
    # Production target is PostgreSQL; SQLite is used for local sandbox development.
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
    # Env var must be JSON, e.g. DECOPS_CORS_ORIGINS='["https://ops.example.com"]'
    cors_origins: list[str] = ["http://localhost:3000"]

    # --- CSRF defence in depth: browser-sent Origin of unsafe requests must be listed here.
    # Empty = check disabled (dev). REQUIRED in production, e.g. '["https://ops.example.com"]'.
    trusted_origins: list[str] = []

    # --- Password reset / public links ---
    public_base_url: str = "http://localhost:3000"   # used in emailed reset links
    password_reset_minutes: int = 30

    # --- Abuse protection (in-process; the API runs a single worker) ---
    rate_limit_enabled: bool = True

    # --- Error tracking (optional) ---
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.0

    # --- Request limits ---
    max_request_bytes: int = 30 * 1024 * 1024  # hard cap on any request body (uploads are 25 MB)

    # --- Demo data (demo staff with a shared, known password + sample tasks) ---
    # None = auto: seeded outside production, never in production unless set to true.
    seed_demo_data: bool | None = None

    # --- Seed admin (change via env in any real deployment) ---
    seed_admin_email: str = "admin@interdec.com"
    seed_admin_password: str = "DecOps!2026"
    seed_admin_name: str = "Interdec Administrator"
    seed_admin_employee_code: str = "INT-0001"

    # --- Attachments (private, task-scoped document storage) ---
    attachment_storage_dir: Path = BACKEND_DIR / "var" / "attachments"
    attachment_max_bytes: int = 25 * 1024 * 1024  # 25 MB
    attachment_allowed_extensions: list[str] = [
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".txt", ".csv", ".md", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".zip",
    ]

    # --- CSV migration (import center) ---
    import_storage_dir: Path = BACKEND_DIR / "var" / "imports"
    import_max_bytes: int = 10 * 1024 * 1024  # 10 MB per uploaded CSV
    import_batch_size: int = 100

    # --- Notifications & transactional outbox ---
    outbox_worker_enabled: bool = True
    outbox_worker_interval_seconds: float = 15.0
    outbox_max_attempts: int = 8
    outbox_base_backoff_seconds: float = 30.0
    deadline_reminder_days: int = 3
    deadline_dedup_hours: int = 20

    # --- Optional email delivery ---
    email_notifications_enabled: bool = False
    smtp_host: str = "localhost"
    smtp_port: int = 25
    smtp_ssl: bool = False                # implicit TLS (port 465)
    smtp_username: str = ""
    smtp_password: str = ""
    email_from: str = "decops@interdec.com"

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        """Hosting platforms (Render, Heroku) hand out postgres:// or postgresql://
        URLs; SQLAlchemy needs the psycopg (v3) driver spelled out."""
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix):]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def should_seed_demo_data(self) -> bool:
        if self.seed_demo_data is not None:
            return self.seed_demo_data
        return not self.is_production

    def assert_production_ready(self) -> None:
        """Refuse to boot a production instance with insecure defaults."""
        if not self.is_production:
            return
        problems: list[str] = []
        if len(self.session_secret_key) < 32 or self.session_secret_key.startswith("change-me"):
            problems.append("DECOPS_SESSION_SECRET_KEY must be a random value of 32+ characters")
        if not self.secure_cookies:
            problems.append("DECOPS_SECURE_COOKIES must be true (serve over HTTPS)")
        if self.debug:
            problems.append("DECOPS_DEBUG must be false")
        if self.database_url.startswith("sqlite"):
            problems.append("DECOPS_DATABASE_URL must point at PostgreSQL, not SQLite")
        if self.seed_admin_password in {"DecOps!2026", ""} or len(self.seed_admin_password) < 12:
            problems.append("DECOPS_SEED_ADMIN_PASSWORD must be changed (12+ characters, not the default)")
        if not self.trusted_origins:
            problems.append('DECOPS_TRUSTED_ORIGINS must list the public site origin(s), e.g. \'["https://ops.example.com"]\'')
        if problems:
            raise RuntimeError(
                "Refusing to start in production with insecure configuration:\n  - "
                + "\n  - ".join(problems)
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
