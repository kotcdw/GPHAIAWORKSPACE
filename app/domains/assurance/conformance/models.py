"""Internal audit charter (IIA GIAS 6.2) and external quality assessments (GIAS 8.4)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import utcnow
from app.domains.assurance.committee import models as _committee  # noqa: F401 - charters keep their meeting link

CHARTER_STATUSES = ("Draft", "Submitted", "Approved", "Superseded")
EQA_TYPES = ("Full external assessment", "Self-assessment with independent validation")
CONCLUSIONS = ("Generally conforms", "Partially conforms", "Does not conform")


class InternalAuditCharter(Base):
    __tablename__ = "ia_charters"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Draft")
    change_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approval_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    meeting_id: Mapped[int | None] = mapped_column(ForeignKey("committee_meetings.id", ondelete="SET NULL"),
                                                   nullable=True)
    approved_recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"),
                                                             nullable=True)
    next_review_due: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class ExternalAssessment(Base):
    __tablename__ = "external_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_type: Mapped[str] = mapped_column(String(60), nullable=False)
    assessor: Mapped[str] = mapped_column(String(200), nullable=False)
    assessor_independent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    scope: Mapped[str] = mapped_column(Text, nullable=False, default="")
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    conclusion: Mapped[str] = mapped_column(String(40), nullable=False)
    report_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    action_plan: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reported_to_committee_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_due: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
