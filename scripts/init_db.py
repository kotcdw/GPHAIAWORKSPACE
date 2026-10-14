"""Create the database schema and seed the bootstrap administrator.

Usage:
    uv run python -m scripts.init_db
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alembic.config import Config  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from alembic import command  # noqa: E402
from app.core.audit import log_action  # noqa: E402
from app.core.config import BASE_DIR, settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.dbcheck import database_status  # noqa: E402
from app.core.enums import Role  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.platform.users.models import User  # noqa: E402


def run_migrations() -> None:
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    command.upgrade(cfg, "head")


def seed_admin() -> None:
    db = SessionLocal()
    try:
        existing = db.execute(
            select(User).where(func.lower(User.username) == settings.admin_username.lower())
        ).scalar_one_or_none()
        if existing is not None:
            print(f"[init_db] admin user '{existing.username}' already exists (id={existing.id})")
            return
        if not settings.admin_password:
            print("[init_db] GPHA_ADMIN_PASSWORD is empty - no administrator created")
            return

        admin = User(
            username=settings.admin_username,
            password_hash=hash_password(settings.admin_password),
            email=settings.admin_email,
            full_name=settings.admin_full_name,
            role=Role.Admin,
            is_active=True,
        )
        db.add(admin)
        db.flush()
        log_action(db, user_id=admin.id, action="BOOTSTRAP_ADMIN")
        db.commit()
        print(f"[init_db] created admin user '{admin.username}' (id={admin.id})")
    finally:
        db.close()


def main() -> None:
    print(f"[init_db] database: {make_url(settings.database_url).render_as_string(hide_password=True)}")
    status = database_status()
    if not status.ok:
        print(f"[init_db] ERROR: {status.error}")
        sys.exit(2)
    run_migrations()
    seed_admin()
    for problem in settings.insecure_settings():
        print(f"[init_db] WARNING (fix before production): {problem}")
    print("[init_db] done. You can now run: uv run uvicorn app.main:app --port 8001")


if __name__ == "__main__":
    main()
