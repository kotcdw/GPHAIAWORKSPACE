"""Shared pytest fixtures.

The environment variables are set *before* importing the application so that
the app's settings and database engine point at an isolated MySQL test
database. A session-level fixture drops and recreates ``gpha_workspace_test``
and then applies all Alembic migrations against it.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# --- Determine the test database URL ---------------------------------------
# These mirror app/config.py defaults so pytest works out of the box with the
# docker-compose MySQL instance. Set GPHA_TEST_DATABASE_URL to override with a
# fully-qualified URL (e.g. for CI secrets).
_HOST = os.environ.get("GPHA_MYSQL_HOST", "127.0.0.1")
_PORT = os.environ.get("GPHA_MYSQL_PORT", "3307")
_USER = os.environ.get("GPHA_MYSQL_USER", "gpha")
_PASS = os.environ.get("GPHA_MYSQL_PASSWORD", "gpha_dev_pass")
_TEST_DB = "gpha_workspace_test"
_TEST_URL = os.environ.get(
    "GPHA_TEST_DATABASE_URL",
    f"mysql+pymysql://{_USER}:{_PASS}@{_HOST}:{_PORT}/{_TEST_DB}?charset=utf8mb4",
)

# Admin connection (no database selected) used to drop/create the test DB.
_ADMIN_URL = os.environ.get(
    "GPHA_TEST_ADMIN_URL",
    f"mysql+pymysql://{_USER}:{_PASS}@{_HOST}:{_PORT}/?charset=utf8mb4",
)

_TMP = Path(tempfile.mkdtemp(prefix="gpha_test_"))
os.environ["GPHA_DATABASE_URL"] = _TEST_URL
os.environ["GPHA_UPLOAD_DIR"] = str(_TMP / "uploads")
os.environ["GPHA_BACKUP_DIR"] = str(_TMP / "backups")
os.environ["GPHA_BACKUP_INTERVAL_HOURS"] = "0"
os.environ["GPHA_ADMIN_USERNAME"] = "admin"
os.environ["GPHA_ADMIN_PASSWORD"] = "Admin@12345"
os.environ["GPHA_COOKIE_SECURE"] = "false"
os.environ["GPHA_LOGIN_RATE_LIMIT_PER_MINUTE"] = "0"  # tests sign in many times from one client
os.environ["GPHA_ESCALATION_CHECK_MINUTES"] = "0"

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from alembic import command  # noqa: E402
from app.core.config import BASE_DIR  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.enums import Role  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.users.models import User  # noqa: E402

DEFAULT_PASSWORD = "Passw0rd!"


def _recreate_test_database() -> None:
    admin = create_engine(_ADMIN_URL, future=True)
    try:
        with admin.begin() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {_TEST_DB}"))
            conn.execute(
                text(
                    f"CREATE DATABASE {_TEST_DB} "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
    finally:
        admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def _migrate_database():
    _recreate_test_database()
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client2():
    """A second independent client (its own cookies/session).

    Useful when a test needs two users logged in at once (the session cookie and
    CSRF token are per-client).
    """
    with TestClient(app) as test_client:
        yield test_client


def make_user(
    db,
    username: str,
    role: Role = Role.Auditee,
    *,
    active: bool = True,
    password: str = DEFAULT_PASSWORD,
    full_name: str | None = None,
    email: str | None = None,
) -> User:
    user = User(
        username=username,
        password_hash=hash_password(password),
        email=email or f"{username}@example.com",
        full_name=full_name or username.title(),
        role=role,
        is_active=active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login(client: TestClient, username: str, password: str = DEFAULT_PASSWORD) -> str:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def csrf_headers(csrf_token: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf_token}