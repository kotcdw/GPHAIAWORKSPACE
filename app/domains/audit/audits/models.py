"""Audit, working paper and finding records.

Owns the ``audits``, ``working_papers`` and ``findings`` tables. Cross-module
references (to ``users``) are plain strings resolved via the mapper registry.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.enums import ApprovalStatus, AuditStatus, FindingStatus, RiskRating, _enum, utcnow

if TYPE_CHECKING:  # pragma: no cover - resolved by the mapper registry at runtime
    from app.platform.users.models import User


class Audit(Base):
    __tablename__ = "audits"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scope: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[AuditStatus] = mapped_column(_enum(AuditStatus), nullable=False, default=AuditStatus.Planned)
    approval_status: Mapped[ApprovalStatus | None] = mapped_column(_enum(ApprovalStatus), nullable=True)
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    # Assurance Plan linkage (set when the audit is started from a plan engagement).
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("assurance_plans.id", ondelete="SET NULL"), nullable=True)
    audit_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    custom_fields: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # The port / site the engagement belongs to (an organization entity of a port type).
    port_entity_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"),
                                                       nullable=True)
    entity_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("entity_units.id", ondelete="SET NULL"), nullable=True
    )
    # HighBond-style project workflow: "Workplan" (procedures) or "Internal Control" (RCM, walkthroughs, tests).
    workflow: Mapped[str] = mapped_column(String(20), nullable=False, default="Internal Control",
                                          server_default="Internal Control")
    # Internal Control testing rounds: 1 (Testing), 2 (Interim, Final) or 4 (Q1-Q4); fixed once testing starts.
    testing_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    creator: Mapped[User | None] = relationship(back_populates="audits")
    working_papers: Mapped[list[WorkingPaper]] = relationship(back_populates="audit", cascade="all, delete-orphan")
    findings: Mapped[list[Finding]] = relationship(back_populates="audit", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Audit id={self.id} title={self.title!r} status={self.status.value}>"


class WorkingPaper(Base):
    __tablename__ = "working_papers"
    __table_args__ = (UniqueConstraint("audit_id", "title", "version_number", name="uq_wp_audit_title_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    audit_id: Mapped[int] = mapped_column(ForeignKey("audits.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    # Evidence is never physically removed: a "deleted" paper is withdrawn
    # (hidden from normal views) but its file and row are retained.
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    deleted_by: Mapped[int | None] = mapped_column(nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    encrypted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Cross-referencing (GIAS 14.6) and reviewer sign-off.
    wp_ref: Mapped[str | None] = mapped_column(String(30), nullable=True)
    test_id: Mapped[int | None] = mapped_column(ForeignKey("control_tests.id", ondelete="SET NULL"), nullable=True)
    finding_id: Mapped[int | None] = mapped_column(ForeignKey("findings.id", ondelete="SET NULL"), nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Review chain progress: the level now due and who signed each stage (JSON). reviewed_* is set at the end.
    review_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    review_trail: Mapped[str | None] = mapped_column(Text, nullable=True)
    # GPHA Working Paper Template content (JSON: field key -> text); see wp_template.FIELDS.
    template: Mapped[str | None] = mapped_column(Text, nullable=True)

    audit: Mapped[Audit] = relationship(back_populates="working_papers")
    uploader: Mapped[User | None] = relationship(foreign_keys="WorkingPaper.uploaded_by")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<WorkingPaper id={self.id} title={self.title!r} v{self.version_number}>"


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    audit_id: Mapped[int] = mapped_column(ForeignKey("audits.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    risk_rating: Mapped[RiskRating] = mapped_column(_enum(RiskRating), nullable=False, default=RiskRating.Medium)
    status: Mapped[FindingStatus] = mapped_column(_enum(FindingStatus), nullable=False, default=FindingStatus.Open)
    assigned_owner_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Issue attributes (IIA "5 Cs") and its place in the risk & control matrix.
    control_id: Mapped[int | None] = mapped_column(ForeignKey("controls.id", ondelete="SET NULL"), nullable=True)
    test_id: Mapped[int | None] = mapped_column(ForeignKey("control_tests.id", ondelete="SET NULL"), nullable=True)
    procedure_id: Mapped[int | None] = mapped_column(ForeignKey("procedures.id", ondelete="SET NULL"), nullable=True)
    criteria: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
    condition: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
    cause: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
    effect: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
    root_cause_whys: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
    management_response: Mapped[str | None] = mapped_column(Text, nullable=True, default="")  # the action plan
    # GPHA template: Management Response = Action Plan + Responsible Officer + Target Date.
    responsible_officer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    management_response_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"),
                                                               nullable=True)
    management_response_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # GPHA template: the Audit Client (HOD) response, confirmed at the exit meeting.
    client_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_response_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    client_response_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    client_confirmed_at_exit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                                           server_default="0")
    # Issue Tracker attributes: issue type (configurable list), publication to the auditee, review sign-offs.
    issue_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    review_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    review_trail: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criterion_id: Mapped[int | None] = mapped_column(ForeignKey("criteria.id", ondelete="SET NULL"), nullable=True)
    custom_fields: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    audit: Mapped[Audit] = relationship(back_populates="findings")
    creator: Mapped[User | None] = relationship(foreign_keys="Finding.created_by")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Finding id={self.id} title={self.title!r} status={self.status.value}>"

class AuditTeamMember(Base):
    """A member of an engagement team. Team members see and work on the audit even outside their own port."""

    __tablename__ = "audit_team_members"

    audit_id: Mapped[int] = mapped_column(ForeignKey("audits.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    team_role: Mapped[str] = mapped_column(String(30), nullable=False, default="Auditor")
    added_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class AuditAuditee(Base):
    """Grants an Auditee account visibility of one audit (and its records)."""

    __tablename__ = "audit_auditees"

    audit_id: Mapped[int] = mapped_column(ForeignKey("audits.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    assigned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
