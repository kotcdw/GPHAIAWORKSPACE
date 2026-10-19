"""Audit Committee meetings, minutes and decisions (PFM Act 2016, Act 921 ss.86-88; IIA GIAS 6.1, 11.1).

Decisions on recommendations (close, withdraw, extend, escalate) are applied to the action record so the
register and the follow-up reports always reflect what the Committee decided.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.enums import utcnow

MEETING_TYPES = ("Ordinary", "Extraordinary", "Special")
MEETING_STATUSES = ("Scheduled", "Held", "Minutes approved", "Cancelled")
DECISIONS = ("Close", "Withdraw", "Extend deadline", "Escalate to management", "Accept risk", "Reject risk acceptance",
             "Noted")


class CommitteeMeeting(Base):
    __tablename__ = "committee_meetings"

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_ref: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    meeting_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    meeting_type: Mapped[str] = mapped_column(String(20), nullable=False, default="Ordinary")
    venue: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    agenda: Mapped[str] = mapped_column(Text, nullable=False, default="")
    attendees: Mapped[str] = mapped_column(Text, nullable=False, default="")
    apologies: Mapped[str] = mapped_column(Text, nullable=False, default="")
    quorum: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    minutes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    followup_report_considered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Scheduled")
    minutes_approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    minutes_approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"),
                                                            nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    decisions: Mapped[list[CommitteeDecision]] = relationship(back_populates="meeting",
                                                               cascade="all, delete-orphan",
                                                               order_by="CommitteeDecision.id")


class CommitteeDecision(Base):
    __tablename__ = "committee_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("committee_meetings.id", ondelete="CASCADE"),
                                            nullable=False, index=True)
    subject_type: Mapped[str] = mapped_column(String(30), nullable=False)  # capa | other
    subject_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decision: Mapped[str] = mapped_column(String(40), nullable=False)
    new_due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    meeting: Mapped[CommitteeMeeting] = relationship(back_populates="decisions")
