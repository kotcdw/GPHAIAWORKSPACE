"""Database engine, session factory and declarative base.

Supports MySQL (default) and SQLite (ad-hoc override of GPHA_DATABASE_URL).
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

from sqlalchemy import DateTime, create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

_database_url: str = settings.database_url or ""
_is_sqlite = _database_url.startswith("sqlite")

connect_args: dict[str, object] = {}
if _is_sqlite:
    # FastAPI may touch the connection from a different thread than the one that
    # created it; SQLite needs this flag to allow that.
    connect_args["check_same_thread"] = False

if not _is_sqlite:
    # MySQL-specific engine options: keep pooled connections fresh (the server
    # closes idle connections after wait_timeout) and verify them on checkout.
    engine = create_engine(
        settings.database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
        pool_recycle=settings.mysql_pool_recycle,
        future=True,
    )
else:
    engine = create_engine(settings.database_url, connect_args=connect_args, future=True)


if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # noqa: ANN001
        """Ensure foreign key enforcement is always on for SQLite."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


@event.listens_for(Session, "before_flush")
def _naive_utc(session: Session, _flush_context, _instances) -> None:  # noqa: ANN001
    """Store every date-time as naive UTC, the convention used throughout the app.

    An API caller may send a time-zone-aware value (``2026-10-18T09:00:00+00:00``). Left as is, it would be saved
    but later compared with naive UTC values (500 after the record was already committed).
    """
    for obj in list(session.new) + list(session.dirty):
        for prop in inspect(obj).mapper.column_attrs:
            if not isinstance(prop.columns[0].type, DateTime):
                continue
            value = getattr(obj, prop.key, None)
            if isinstance(value, datetime) and value.tzinfo is not None:
                setattr(obj, prop.key, value.astimezone(UTC).replace(tzinfo=None))


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _install_workflow_engine() -> None:
    # Every session records status changes and keeps the "My work" inbox in step (app.platform.workflow).
    from app.platform.workflow.engine import install

    install()


_install_workflow_engine()
