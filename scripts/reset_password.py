"""Reset a user's password from the server (for a forgotten administrator password).

Run on the machine that hosts the app - it needs direct database access:
    uv run python -m scripts.reset_password            (asks for username and password)
    uv run python -m scripts.reset_password --list     (lists the user accounts)

It also unlocks the account, re-activates it, ends its open sessions and
records the reset in the audit log. Passwords are never printed or stored in
plain text - only the hash is saved.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select, update  # noqa: E402

import app.main  # noqa: E402, F401  (registers every model with SQLAlchemy)
from app.core.audit import log_action  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.dbcheck import ensure_schema  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.core.validators import password_problems  # noqa: E402
from app.platform.auth.models import Session  # noqa: E402
from app.platform.users.models import User  # noqa: E402


def list_users() -> None:
    db = SessionLocal()
    try:
        users = db.execute(select(User).order_by(User.id)).scalars().all()
        print(f"{'USERNAME':<24} {'ROLE':<12} {'ACTIVE':<7} LOCKED")
        for u in users:
            role = getattr(u.role, "value", u.role)
            active = "yes" if u.is_active else "no"
            locked = "yes" if u.locked_until else "no"
            print(f"{u.username:<24} {role!s:<12} {active:<7} {locked}")
    finally:
        db.close()


def reset(username: str, password: str) -> int:
    db = SessionLocal()
    try:
        wanted = username.strip().lower()
        user = db.execute(select(User).where(func.lower(User.username) == wanted)).scalar_one_or_none()
        if user is None:
            print(f"No user called '{username}'. Run with --list to see the accounts.")
            return 1
        problem = password_problems(password, user.username)
        if problem:
            print(f"Password not accepted: {problem}")
            return 1
        user.password_hash = hash_password(password)
        user.failed_login_count = 0
        user.locked_until = None
        user.is_active = True
        db.execute(update(Session).where(Session.user_id == user.id, Session.revoked.is_(False)).values(revoked=True))
        log_action(db, user_id=user.id, action=f"PASSWORD_RESET_CLI user={user.username}")
        db.commit()
        print(f"Password for '{user.username}' has been reset. The account is unlocked and active.")
        print("You can sign in now.")
        return 0
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset a GPHA INTERNAL AUDIT WORKSPACE password.")
    parser.add_argument("--list", action="store_true", help="list user accounts and exit")
    args = parser.parse_args()

    status = ensure_schema()
    if not status.ok:
        print(f"The database is not reachable: {status.error}")
        sys.exit(2)
    if args.list:
        list_users()
        return

    list_users()
    print()
    username = input("Username to reset: ").strip()
    if not username:
        sys.exit(1)
    while True:
        first = getpass.getpass("New password (typing is hidden): ")
        second = getpass.getpass("Type it again: ")
        if first != second:
            print("The two passwords do not match - try again.\n")
            continue
        if reset(username, first) == 0:
            return
        print()


if __name__ == "__main__":
    main()
