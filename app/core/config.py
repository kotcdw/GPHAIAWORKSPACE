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

    app_name: str = "GPHA Internal Audit Workspace"
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

    # Active Directory / LDAP sign-in (optional). When ldap_url is set, staff sign in
    # with their GPHA network password; the local bootstrap admin keeps a local
    # password as a break-glass account. Example: ldaps://dc01.gpha.local:636
    ldap_url: str = ""
    # How the username becomes a bind identity, e.g. "{username}@gpha.gov.gh" or "GPHA\\{username}".
    ldap_bind_template: str = "{username}@gpha.gov.gh"
    ldap_base_dn: str = ""  # e.g. "DC=gpha,DC=local" - used to read name and e-mail
    ldap_user_filter: str = "(sAMAccountName={username})"
    # First directory sign-in creates a pending account for an Admin to approve.
    ldap_auto_create: bool = True
    ldap_timeout_seconds: int = 5

    # E-mail notifications (optional). Leave smtp_host empty to keep the in-app
    # bell only. app_base_url is used for links in e-mails.
    smtp_host: str = ""
    smtp_port: int = 25
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "gpha-audit@localhost"
    smtp_starttls: bool = False
    app_base_url: str = "http://127.0.0.1:8001"

    # Follow-up: overdue actions escalate to the owner straight away, then to
    # Audit Managers after N days, then to the CAE. The watcher runs hourly.
    escalate_manager_days: int = 14
    escalate_cae_days: int = 30
    escalate_committee_days: int = 60
    escalation_check_minutes: int = 60

    # Audit closure gates (also editable on the Configuration screen).
    require_report_to_close: bool = True
    require_findings_actioned_to_close: bool = True
    # Fieldwork may only start once the planning memo is approved (GIAS 13.6).
    require_memo_approval_for_fieldwork: bool = True
    # Independence / conflict-of-interest declarations before fieldwork (IIA GIAS 2, 7.1).
    require_engagement_declaration: bool = True

    # Per-IP throttle on sign-in attempts (in addition to account lockout).
    login_rate_limit_per_minute: int = 10

    # Roles that must use multi-factor authentication (comma separated,
    # e.g. "Admin,Auditor"). Empty = optional for everyone.
    mfa_required_roles: str = ""
    # Required-role MFA is enforced on a production installation (GPHA_ENVIRONMENT=production). Set this to true
    # to enforce it on development / test installations as well.
    mfa_enforce_outside_production: bool = False

    # AI Service secret (GPHA_AI_API_KEY). Kept in the environment only - never stored in the database.
    # Whether AI is used at all, and which provider/model, is set by administrators under Configuration > AI.
    ai_api_key: str = ""

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