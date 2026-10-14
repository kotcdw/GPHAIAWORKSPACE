"""Production readiness check: run before go-live and after any configuration change.

    uv run python scripts/production_check.py            # report
    uv run python scripts/production_check.py --secrets  # also print fresh random secrets to paste into .env
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cryptography.fernet import Fernet  # noqa: E402

from app.core.config import settings  # noqa: E402


def _outside_app(path: str) -> bool:
    try:
        return not Path(path).resolve().is_relative_to(Path(__file__).resolve().parents[1])
    except (OSError, ValueError):
        return False


def _database_checks() -> list[tuple[str, bool]]:
    """Checks that need the database: demo data, administrators, two-step verification, backups location."""
    out = [
        ("Backups stored outside the application folder", _outside_app(settings.backup_dir)),
        ("Uploads stored outside the application folder", _outside_app(settings.upload_dir)),
        ("Links in e-mails use https:// (GPHA_APP_BASE_URL)", settings.app_base_url.startswith("https://")),
    ]
    try:
        from sqlalchemy import func, select

        import app.main  # noqa: F401 - registers the models
        from app.core.appconfig import cfg
        from app.core.database import SessionLocal
        from app.core.enums import Role
        from app.platform.users.models import User

        db = SessionLocal()
        try:
            demo = db.execute(select(func.count()).select_from(User).where(
                User.username.in_(("aud1", "ee1", "signer", "aa1", "pia1", "com1", "gm1", "mgr2")))).scalar_one()
            admins = db.execute(select(func.count()).select_from(User).where(
                User.role == Role.Admin, User.is_active.is_(True))).scalar_one()
            out += [
                ("No demo / test accounts in this database", demo == 0),
                ("At least two active Platform Administrators (no single point of failure)", admins >= 2),
                ("Two-step verification enforced (Configuration > Security) - switch on at go-live",
                 bool(cfg("mfa_enforced")) and bool(cfg("mfa_required_roles"))),
            ]
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        out.append((f"Database reachable ({exc.__class__.__name__})", False))
    return out


def main() -> int:
    if "--secrets" in sys.argv:
        print("GPHA_SECRET_KEY=" + secrets.token_urlsafe(48))
        print("GPHA_ENCRYPTION_KEY=" + Fernet.generate_key().decode())
        print()
    problems = settings.insecure_settings()
    checks = [
        ("Environment is 'production'", settings.environment.lower() == "production"),
        ("Secrets and cookies are production-grade", not problems),
        ("Database is MySQL", (settings.database_url or "").startswith("mysql")),
        ("E-mail relay configured (GPHA_SMTP_HOST)", bool(settings.smtp_host)),
        ("Directory sign-in configured (GPHA_LDAP_URL) - optional", bool(settings.ldap_url)),
        ("Automatic backups on (GPHA_BACKUP_INTERVAL_HOURS > 0)", settings.backup_interval_hours > 0),
    ]
    checks += _database_checks()
    width = max(len(c) for c, _ in checks)
    for label, ok in checks:
        print(f"  [{'OK' if ok else '--'}] {label.ljust(width)}")
    for p in problems:
        print(f"       ! {p}")
    blocking = [c for c, ok in checks[:3] if not ok]
    print("\nReady for production." if not blocking else f"\nNot ready: {len(blocking)} blocking item(s).")
    return 0 if not blocking else 1


if __name__ == "__main__":
    raise SystemExit(main())
