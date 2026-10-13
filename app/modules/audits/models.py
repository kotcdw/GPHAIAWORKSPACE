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
    from app.modules.users.models import User


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
    entity_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("entity_units.id", ondelete="SET NULL"), nullable=True
    )

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

    audit: Mapped[Audit] = relationship(back_populates="working_papers")
    uploader: Mapped[User | None] = relationship()

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
    criteria: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
    condition: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
    cause: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
    effect: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
    root_cause_whys: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
    management_response: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    audit: Mapped[Audit] = relationship(back_populates="findings")
    creator: Mapped[User | None] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Finding id={self.id} title={self.title!r} status={self.status.value}>"

class AuditAuditee(Base):
    """Grants an Auditee account visibility of one audit (and its records)."""

    __tablename__ = "audit_auditees"

    audit_id: Mapped[int] = mapped_column(ForeignKey("audits.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    assigned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
