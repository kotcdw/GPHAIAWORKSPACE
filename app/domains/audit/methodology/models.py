"""Criteria library and supervisory review notes."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import utcnow

CRITERIA_SOURCES = ("Law / Regulation", "GPHA Policy", "Procedure / SOP", "Standard", "Contract / Agreement",
                    "Board resolution", "Leading practice", "Other")


class Criterion(Base):
    """A reusable audit criterion: the "what should be" a finding is measured against (GIAS 13.4)."""

    __tablename__ = "criteria"

    id: Mapped[int] = mapped_column(primary_key=True)
    crit_ref: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="GPHA Policy")
    reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Active")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class ReviewNote(Base):
    """A reviewer's note on engagement work: raised -> responded by the preparer -> cleared by the reviewer."""

    __tablename__ = "review_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    audit_id: Mapped[int] = mapped_column(ForeignKey("audits.id", ondelete="CASCADE"), nullable=False, index=True)
    # audit | working_paper | control_test | finding
    target_type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_id: Mapped[int | None] = mapped_column(nullable=True)
    target_label: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    note: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Open")
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    raised_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    raised_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    responded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cleared_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
