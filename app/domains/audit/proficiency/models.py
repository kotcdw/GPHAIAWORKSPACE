"""Independence and ethics declarations (IIA GIAS 1-2, 5, 7.1; Act 658 ss.18-20) and CPD (GIAS 3)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import utcnow

DECLARATION_KINDS = ("annual", "engagement")
REVIEW_STATUSES = ("Not required", "Pending review", "Cleared", "Reassigned")
CPD_CATEGORIES = ("Formal training / course", "Conference / seminar", "Professional exam", "E-learning",
                  "Self-study", "Teaching / writing", "Other")


class Declaration(Base):
    __tablename__ = "declarations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    audit_id: Mapped[int | None] = mapped_column(ForeignKey("audits.id", ondelete="CASCADE"), nullable=True,
                                                 index=True)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    independence_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ethics_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidentiality_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_conflict: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    conflict_details: Mapped[str] = mapped_column(Text, nullable=False, default="")
    signed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, default="Not required")
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")


class CpdRecord(Base):
    __tablename__ = "cpd_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    activity_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    activity: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    hours: Mapped[float] = mapped_column(Float, nullable=False)
    ethics_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    evidence_ref: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class Certification(Base):
    __tablename__ = "certifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    issuer: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    number: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    obtained_on: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_on: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
