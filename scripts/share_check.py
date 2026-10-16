"""Check that the app is safe to share outside the office (used by run-external.ps1).

Usage:
    uv run python -m scripts.share_check

Lists every active account whose password is still a published one (the bootstrap
administrator default, the GPHA_ADMIN_PASSWORD in .env, or the demo-data password).
Anyone on the internet can reach the sign-in page while the app is shared, so these
accounts must get a new password (User accounts > Reset password) or be deactivated first.

Exit code 0 = safe to share, 1 = accounts to fix, 2 = database not reachable.
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402

import app.main  # noqa: E402, F401  (registers every model with SQLAlchemy)
from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.security import verify_password  # noqa: E402
from app.platform.users.models import User  # noqa: E402

# Passwords written in this repository's code or documentation.
PUBLISHED = ("Admin@12345", "DemoPass!123")


def weak_accounts(db) -> list[str]:  # noqa: ANN001
    known = {p for p in (*PUBLISHED, settings.admin_password) if p}
    users = db.execute(select(User).where(User.is_active.is_(True))).scalars().all()

    def weak(user: User) -> bool:
        return any(verify_password(p, user.password_hash) for p in known)

    # bcrypt is slow by design and releases the GIL, so check accounts in parallel.
    with ThreadPoolExecutor(max_workers=8) as pool:
        flags = list(pool.map(weak, users))
    return sorted(u.username for u, bad in zip(users, flags, strict=True) if bad)


def main() -> int:
    print("[share_check] Checking that no active account uses a published password...")
    db = SessionLocal()
    try:
        weak = weak_accounts(db)
    except SQLAlchemyError as exc:
        print(f"[share_check] database not reachable: {exc.__class__.__name__}")
        return 2
    finally:
        db.close()
    if not weak:
        print("[share_check] OK - no active account uses a published password")
        return 0
    print("[share_check] These active accounts still use a published password:")
    for name in weak:
        print(f"    - {name}")
    print("[share_check] Sign in and give each a new password: your own under Profile & users > Change password,")
    print("              anyone else's under User accounts > Reset password (or deactivate it). Then try again.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
