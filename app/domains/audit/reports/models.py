"""Audit reports (IIA GIAS 15.1 - final engagement communication).

One report per audit. Workflow:
  Draft -> Management Review (auditee comments) -> Manager Review (e-sign)
  -> CAE Approval (e-sign) -> Issued (locked, findings snapshotted).
A rejection at either review returns the report to Draft. An issued report found to contain a significant error or
omission is corrected by the GM Audit: the issued version is frozen in ``report_revisions`` and the report goes back
through the same workflow as the next version (IIA GIAS 11.4).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import ReportRating, ReportStatus, _enum, utcnow


class AuditReport(Base):
    __tablename__ = "audit_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    audit_id: Mapped[int] = mapped_column(ForeignKey("audits.id", ondelete="RESTRICT"), nullable=False, unique=True)
    report_ref: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        _enum(ReportStatus, length=30), nullable=False, default=ReportStatus.Draft
    )
    overall_rating: Mapped[ReportRating | None] = mapped_column(_enum(ReportRating, length=30), nullable=True)
    executive_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    background: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scope_objectives: Mapped[str] = mapped_column(Text, nullable=False, default="")
    methodology: Mapped[str] = mapped_column(Text, nullable=False, default="")
    overall_opinion: Mapped[str] = mapped_column(Text, nullable=False, default="")
    distribution_list: Mapped[str] = mapped_column(Text, nullable=False, default="")
    exit_meeting_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    exit_meeting_attendees: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_meeting_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    management_comments: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # JSON copy of the findings, CAPA links and sign-offs taken at issue time, so
    # the issued report never changes even if the records are edited later.
    issued_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Why the current version corrects the previous one (set while a correction is open and on the new version).
    correction_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    manager_reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    manager_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Review chain (Unit Head -> Audit Manager -> PIA): the level now due and who signed each stage (JSON).
    review_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    review_trail: Mapped[str | None] = mapped_column(Text, nullable=True)
    cae_approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    cae_approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Management response deadline on the draft (L.I. 1994 reg. 43(2)).
    draft_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    response_due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    response_received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class ReportDistribution(Base):
    """A copy of an issued report sent to a recipient (Internal Audit Agency Act, 2003 s.16)."""

    __tablename__ = "report_distributions"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("audit_reports.id", ondelete="CASCADE"), nullable=False,
                                           index=True)
    recipient: Mapped[str] = mapped_column(String(160), nullable=False)
    channel: Mapped[str] = mapped_column(String(40), nullable=False, default="Letter")
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class ReportRevision(Base):
    """An issued version of a report, frozen when a corrected version replaces it (append-only)."""

    __tablename__ = "report_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("audit_reports.id", ondelete="RESTRICT"), nullable=False,
                                           index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[str] = mapped_column(Text, nullable=False)  # JSON: report text, findings, sign-offs
    issued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    superseded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    correction_reason: Mapped[str] = mapped_column(Text, nullable=False)
    opened_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
