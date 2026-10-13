"""Immutable audit trail and per-record history.

Owns the ``audit_logs`` table (immutable appendix: UPDATE and DELETE are
blocked at the database level by triggers created in the initial Alembic
migration) and the ``record_history`` table (per-record activity trail, with
optional approval-cycle numbers).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import utcnow


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Soft reference to users.id (no FK): the trail must survive user deletion
    # and must never be updated. See the triggers in the initial migration.
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    action_performed: Mapped[str] = mapped_column(String(500), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<AuditLog id={self.id} action={self.action_performed!r}>"


class RecordHistory(Base):
    """Per-record activity trail (record_type + record_id + optional cycle)."""

    __tablename__ = "record_history"
    __table_args__ = (Index("ix_record_history_record", "record_type", "record_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    record_type: Mapped[str] = mapped_column(String(50), nullable=False)
    record_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(500), nullable=False)
    cycle_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<RecordHistory {self.record_type}#{self.record_id} action={self.action!r}>"