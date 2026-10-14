"""Quality Assurance and Improvement Programme (IIA GIAS Principle 8 / Standard 8.3)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import utcnow


class QualityReview(Base):
    """Per-engagement quality checklist completed by a reviewer who did not perform the audit."""

    __tablename__ = "quality_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    audit_id: Mapped[int] = mapped_column(ForeignKey("audits.id", ondelete="CASCADE"), unique=True, nullable=False)
    answers: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # JSON {key: {answer, comment}}
    conclusion: Mapped[str] = mapped_column(Text, nullable=False, default="")
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class AuditSurvey(Base):
    """Post-audit satisfaction survey answered by an auditee."""

    __tablename__ = "audit_surveys"
    __table_args__ = (UniqueConstraint("audit_id", "respondent_id", name="uq_survey_audit_respondent"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    audit_id: Mapped[int] = mapped_column(ForeignKey("audits.id", ondelete="CASCADE"), nullable=False, index=True)
    respondent_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    scores: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # JSON {question_key: 1..5}
    average: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    comments: Mapped[str] = mapped_column(Text, nullable=False, default="")
    submitted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
