"""Corrective and preventive actions (CAPA)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.enums import CapaStatus, Severity, ValidationResult, _enum, utcnow

if TYPE_CHECKING:
    from app.domains.issues.nonconformances.models import Nonconformance


class Capa(Base):
    __tablename__ = "capa"

    id: Mapped[int] = mapped_column(primary_key=True)
    capa_ref: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    root_cause: Mapped[str] = mapped_column(Text, nullable=False, default="")
    corrective_action: Mapped[str] = mapped_column(Text, nullable=False, default="")
    preventive_action: Mapped[str] = mapped_column(Text, nullable=False, default="")
    effectiveness_check: Mapped[str] = mapped_column(Text, nullable=False, default="")
    severity: Mapped[Severity] = mapped_column(_enum(Severity), nullable=False, default=Severity.Medium)
    disposition: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[CapaStatus] = mapped_column(_enum(CapaStatus), nullable=False, default=CapaStatus.Open)
    owner_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_id: Mapped[int | None] = mapped_column(nullable=True)
    linked_nc_id: Mapped[int | None] = mapped_column(
        ForeignKey("nonconformances.id", ondelete="SET NULL"), nullable=True
    )
    # Follow-up: the owner records what was done, an auditor validates it.
    implementation_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    implemented_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    implemented_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    validation_result: Mapped[ValidationResult | None] = mapped_column(_enum(ValidationResult), nullable=True)
    validation_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_procedures: Mapped[str | None] = mapped_column(Text, nullable=True)
    validated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reopen_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    escalation_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_escalated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Follow-up reporting (MoF Audit Recommendations Implementation and Follow-up Instructions; Act 921 s.88)
    implementation_status: Mapped[str] = mapped_column(String(30), nullable=False, default="Not Implemented",
                                                       server_default="Not Implemented")
    timeframe: Mapped[str | None] = mapped_column(String(60), nullable=True)
    source_body: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    followup_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    withdrawal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    withdrawal_proposed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"),
                                                               nullable=True)
    withdrawal_proposed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    external_closure_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Revised target dates: the first agreed date is kept; every change needs a reason (capa_events).
    original_due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    extension_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Management accepts the residual risk instead of implementing (IIA GIAS 11.5): proposed by the follow-up
    # manager, decided by the GM Audit.
    # risk_acceptance_status: Proposed | Accepted | Rejected (Committee: referred before the register was retired).
    risk_acceptance_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    risk_proposed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_proposed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    risk_accepted_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    risk_acceptance: Mapped[str | None] = mapped_column(Text, nullable=True)
    custom_fields: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    linked_nc: Mapped[Nonconformance | None] = relationship(
        "Nonconformance", foreign_keys=[linked_nc_id], lazy="selectin"
    )


class CapaEvent(Base):
    """Append-only follow-up timeline of a remediation action (UPDATE/DELETE blocked by database triggers).

    ``kind``: created, progress, implementation, evidence_file, validation, extension, escalation, reopened,
    risk_proposed, risk_rejected, risk_accepted, withdrawal, closed. ``capa_id`` is a soft reference so the trail
    outlives the action.
    """

    __tablename__ = "capa_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    capa_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    old_due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    new_due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)


class CapaFile(Base):
    """An evidence file attached to a remediation action (encrypted at rest, SHA-256, never hard-deleted)."""

    __tablename__ = "capa_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    capa_id: Mapped[int] = mapped_column(ForeignKey("capa.id", ondelete="CASCADE"), nullable=False, index=True)
    original_name: Mapped[str] = mapped_column(String(200), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    deleted_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
