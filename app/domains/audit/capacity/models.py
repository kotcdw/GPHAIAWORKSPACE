"""Auditor capacity: skills, available hours and time sheets."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import utcnow

TIME_CATEGORIES = ("Audit", "Follow-up", "Training", "Administration", "Leave", "Other")


class AuditorProfile(Base):
    __tablename__ = "auditor_profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    grade: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    skills: Mapped[str] = mapped_column(Text, nullable=False, default="")  # comma separated
    certifications: Mapped[str] = mapped_column(Text, nullable=False, default="")
    annual_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=1600)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class TimeEntry(Base):
    __tablename__ = "time_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    audit_id: Mapped[int | None] = mapped_column(ForeignKey("audits.id", ondelete="SET NULL"), nullable=True,
                                                 index=True)
    category: Mapped[str] = mapped_column(String(30), nullable=False, default="Audit")
    entry_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    hours: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
