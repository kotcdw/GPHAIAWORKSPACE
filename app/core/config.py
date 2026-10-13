"""Application configuration.

All settings can be overridden with environment variables using the ``GPHA_``
prefix, or with a local ``.env`` file (see ``.env.example``).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_prefix="GPHA_",
        extra="ignore",
    )

    app_name: str = "GPHA Audit Workspace"
    # "development" (default) or "production". Production refuses to start with
    # insecure defaults (see ``insecure_settings``).
    environment: str = "development"
    app_version: str = "0.1.0"

    # Security
    secret_key: str = "dev-secret-change-me"
    session_ttl_hours: int = 12
    cookie_secure: bool = False

    # Apply pending database migrations automatically at start-up.
    auto_migrate: bool = True

    # Brute-force protection: lock an account after N consecutive failures.
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15

    # Explicit database URL override (e.g. GPHA_DATABASE_URL=sqlite:///...).
    # When unset, the MySQL URL below is used.
    database_url: str | None = None

    # MySQL connection (Docker default matches docker-compose.yml; the local
    # XAMPP MySQL owns 3306, so the container is exposed on 3307).
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3307
    mysql_user: str = "gpha"
    mysql_password: str = "gpha_dev_pass"
    mysql_database: str = "gpha_workspace"

    # MySQL drops idle connections after wait_timeout; recycle keeps the pool fresh.
    mysql_pool_recycle: int = 3600

    # Storage
    upload_dir: str = str(BASE_DIR / "uploads")
    backup_dir: str = str(BASE_DIR / "backups")
    backup_retention: int = 7  # number of most-recent backups to keep
    backup_interval_hours: int = 24  # background snapshot cadence (0 disables)
    # Key used to encrypt backups and stored working papers (Fernet). When unset
    # a key is derived from ``secret_key``; set it explicitly in production and
    # keep it safe - encrypted files cannot be read without it.
    encryption_key: str | None = None

    # Working papers
    max_upload_mb: int = 25
    upload_allowed_extensions: str = (
        ".pdf,.doc,.docx,.xls,.xlsx,.xlsm,.ppt,.pptx,.csv,.txt,.rtf,.odt,.ods,"
        ".png,.jpg,.jpeg,.gif,.bmp,.tif,.tiff,.msg,.eml,.zip,.mp3,.m4a,.wav,.mp4"
    )

    # Bootstrap administrator (created by scripts/init_db.py if missing)
    admin_username: str = "admin"
    admin_password: str = "Admin@12345"
    admin_email: str = "admin@gpha.local"
    admin_full_name: str = "GPHA Administrator"

    @model_validator(mode="after")
    def _resolve_database_url(self) -> Settings:
        if not self.database_url:
            self.database_url = (
                f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
                f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
            )
        return self

    @property
    def allowed_extensions(self) -> set[str]:
        return {e.strip().lower() for e in self.upload_allowed_extensions.split(",") if e.strip()}

    def insecure_settings(self) -> list[str]:
        """Return the list of settings that are unsafe for production use."""
        problems: list[str] = []
        if self.secret_key in ("", "dev-secret-change-me") or len(self.secret_key) < 32:
            problems.append("GPHA_SECRET_KEY must be a random value of at least 32 characters")
        if self.admin_password == "Admin@12345":
            problems.append("GPHA_ADMIN_PASSWORD is still the published default")
        if not self.cookie_secure:
            problems.append("GPHA_COOKIE_SECURE must be true (serve the app over HTTPS)")
        if not self.encryption_key:
            problems.append("GPHA_ENCRYPTION_KEY must be set explicitly")
        if (self.database_url or "").startswith("sqlite"):
            problems.append("GPHA_DATABASE_URL must point at MySQL, not SQLite")
        return problems


settings = Settings()