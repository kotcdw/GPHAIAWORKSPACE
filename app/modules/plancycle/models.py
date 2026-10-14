"""Annual planning cycle records: stage events, approved plan versions and controlled distribution."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import utcnow


class PlanCycleEvent(Base):
    __tablename__ = "plan_cycle_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("assurance_plans.id", ondelete="CASCADE"), nullable=False,
                                         index=True)
    stage: Mapped[str] = mapped_column(String(30), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    decision: Mapped[str | None] = mapped_column(String(40), nullable=True)
    meeting_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    attendees: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    data: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class PlanVersion(Base):
    __tablename__ = "plan_versions"
    __table_args__ = (UniqueConstraint("plan_id", "version", name="uq_plan_versions_plan_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("assurance_plans.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(String(160), nullable=False)
    committee_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Submission of this approved version to the Internal Audit Agency (Ghana).
    iaa_submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    iaa_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    iaa_recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class PlanDistribution(Base):
    __tablename__ = "plan_distributions"
    __table_args__ = (UniqueConstraint("plan_id", "version", "user_id", name="uq_plan_distributions"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("assurance_plans.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PlanChangeRequest(Base):
    """A requested change to an approved plan: reason, items, computed impact, review and approval."""

    __tablename__ = "plan_change_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    cr_ref: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    plan_id: Mapped[int] = mapped_column(ForeignKey("assurance_plans.id", ondelete="CASCADE"), nullable=False,
                                         index=True)
    base_version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    items: Mapped[str] = mapped_column(Text, nullable=False)
    impact: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Submitted")
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    approver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Significant changes need Audit Committee approval (IIA GIAS 9.4) after the CAE's approval.
    significant: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    committee_decision: Mapped[str | None] = mapped_column(String(40), nullable=True)
    committee_meeting_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    committee_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    committee_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    committee_recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"),
                                                              nullable=True)
