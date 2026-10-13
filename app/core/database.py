"""Database engine, session factory and declarative base.

Supports MySQL (default) and SQLite (ad-hoc override of GPHA_DATABASE_URL).
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
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


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()