"""Database reachability and schema-version checks.

Used at start-up (to apply pending migrations automatically) and by
``/health`` so the UI can warn users *before* they lose work when the
database cannot accept writes.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.core.config import BASE_DIR, settings
from app.core.database import engine

logger = logging.getLogger("gpha")


@dataclass
class DbStatus:
    ok: bool
    backend: str
    url: str
    revision: str | None = None
    head: str | None = None
    up_to_date: bool = False
    error: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _alembic_config():  # noqa: ANN202
    from alembic.config import Config

    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    return cfg


def head_revision() -> str | None:
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(_alembic_config()).get_current_head()


def database_status() -> DbStatus:
    url = make_url(settings.database_url)
    status = DbStatus(
        ok=False,
        backend=url.get_backend_name(),
        url=url.render_as_string(hide_password=True),
        head=head_revision(),
    )
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            try:
                status.revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            except Exception:  # noqa: BLE001 - table missing on an empty database
                conn.rollback()
                status.revision = None
        status.ok = True
        status.up_to_date = status.revision == status.head
    except Exception as exc:  # noqa: BLE001 - report any connection problem
        status.error = _friendly(exc)
    return status


def _friendly(exc: Exception) -> str:
    raw = str(exc).splitlines()[0]
    if "Can't connect" in raw or "Connection refused" in raw or "2003" in raw:
        return (
            "Cannot reach the MySQL server. Start it with 'docker compose up -d' "
            f"(or check GPHA_DATABASE_URL). Details: {raw[:200]}"
        )
    if "Access denied" in raw or "1045" in raw:
        return f"MySQL rejected the user/password in GPHA_DATABASE_URL / GPHA_MYSQL_*. Details: {raw[:200]}"
    return raw[:300]


def upgrade_to_head() -> None:
    from alembic import command

    command.upgrade(_alembic_config(), "head")


def ensure_schema() -> DbStatus:
    """Apply pending migrations when the database is reachable but behind."""
    status = database_status()
    if not status.ok:
        logger.error("DATABASE UNAVAILABLE - data cannot be saved until this is fixed: %s", status.error)
        return status
    if not status.up_to_date and settings.auto_migrate:
        logger.warning("Database schema %s is behind %s - applying migrations", status.revision, status.head)
        try:
            upgrade_to_head()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Automatic migration failed")
            status.error = f"Automatic migration failed: {str(exc).splitlines()[0][:250]}"
            return status
        status = database_status()
    if not status.up_to_date:
        logger.error("Database schema is not current (%s, expected %s)", status.revision, status.head)
    return status
