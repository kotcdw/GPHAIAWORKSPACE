"""Planning memo: the approved plan for one engagement (IIA GIAS 13.1-13.6)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import utcnow

MEMO_STATUSES = ("Draft", "Submitted", "Approved", "Returned")


class PlanningMemo(Base):
    __tablename__ = "planning_memos"

    id: Mapped[int] = mapped_column(primary_key=True)
    audit_id: Mapped[int] = mapped_column(ForeignKey("audits.id", ondelete="CASCADE"), unique=True, nullable=False)
    background: Mapped[str] = mapped_column(Text, nullable=False, default="")
    objectives: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scope: Mapped[str] = mapped_column(Text, nullable=False, default="")
    key_risks: Mapped[str] = mapped_column(Text, nullable=False, default="")
    approach: Mapped[str] = mapped_column(Text, nullable=False, default="")
    team: Mapped[str] = mapped_column(Text, nullable=False, default="")
    start_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    budget_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Draft")
    review_comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    prepared_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
