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
