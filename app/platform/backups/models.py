"""Backup checks (append-only): every verification of a backup set and every full restore test."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import utcnow


class BackupCheck(Base):
    __tablename__ = "backup_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    backup: Mapped[str] = mapped_column(String(80), nullable=False, index=True)  # set stamp or snapshot name
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # check | restore_test
    outcome: Mapped[str] = mapped_column(String(10), nullable=False)  # passed | failed
    details: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of the individual checks
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, index=True)
