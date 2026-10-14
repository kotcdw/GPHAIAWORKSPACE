"""Scheduler: who works on what, when. Engagements carry planned start and end dates; bookings put auditors on
engagements (or on leave, training and other work) for a date range, so double-booking can be seen."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import utcnow

BOOKING_KINDS = ("Engagement", "Leave", "Training", "Other work")
ENGAGEMENT_ROLES = ("Lead auditor", "Team member", "Reviewer")


class ScheduleBooking(Base):
    __tablename__ = "schedule_bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="Engagement")
    plan_engagement_id: Mapped[int | None] = mapped_column(ForeignKey("plan_engagements.id", ondelete="CASCADE"),
                                                           nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="Team member")
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
