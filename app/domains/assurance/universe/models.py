"""Integrated audit universe (Diligent One / HighBond Audit model).

Org Structure (``organizations``) and the Process library (``processes``, linked to org units) are the shared
building blocks. An auditable entity (``entity_units``) is an org unit, or an org unit and one of its processes, or a
merge of several of these within one branch; the links live in ``entity_org_units`` and ``entity_processes``.

Audit risk assessments score the active auditable entities against assessment factors on a rating scale; the overall
score is the average of the factor scores. Concluding prioritises entities for audit, with notes and a conclusion,
and a completed assessment feeds the Assurance Plan.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.enums import utcnow

if TYPE_CHECKING:
    from app.platform.organizations.models import Organization


class Process(Base):
    """A business process of the Process library (e.g. Revenue collection, Procurement, Payroll)."""

    __tablename__ = "processes"

    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("processes.id", ondelete="SET NULL"), nullable=True)
    owner_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Active")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    org_units: Mapped[list[Organization]] = relationship(
        "Organization", secondary="process_org_units", order_by="Organization.name")


class ProcessOrgUnit(Base):
    """A process performed in an org unit (the pairs offered when the audit universe is defined)."""

    __tablename__ = "process_org_units"

    process_id: Mapped[int] = mapped_column(ForeignKey("processes.id", ondelete="CASCADE"), primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)


class EntityOrgUnit(Base):
    __tablename__ = "entity_org_units"

    entity_id: Mapped[int] = mapped_column(ForeignKey("entity_units.id", ondelete="CASCADE"), primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)


class EntityProcess(Base):
    __tablename__ = "entity_processes"

    entity_id: Mapped[int] = mapped_column(ForeignKey("entity_units.id", ondelete="CASCADE"), primary_key=True)
    process_id: Mapped[int] = mapped_column(ForeignKey("processes.id", ondelete="CASCADE"), primary_key=True)
    # The org unit the process was selected under (None: the process across the whole entity).
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)


class AssessmentFactor(Base):
    """A factor auditable entities are scored on (e.g. Financial materiality, Fraud risk, Time since last audit)."""

    __tablename__ = "assessment_factors"

    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class AuditRiskAssessment(Base):
    __tablename__ = "audit_risk_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    scale: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Draft")  # Draft, In progress, Completed
    conclusion: Mapped[str] = mapped_column(Text, nullable=False, default="")
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("assurance_plans.id", ondelete="SET NULL"), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    completed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AraEntity(Base):
    """An auditable entity included in an assessment, its priority for audit and its note."""

    __tablename__ = "ara_entities"

    ara_id: Mapped[int] = mapped_column(ForeignKey("audit_risk_assessments.id", ondelete="CASCADE"), primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity_units.id", ondelete="CASCADE"), primary_key=True)
    priority: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    note_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    note_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AraFactor(Base):
    __tablename__ = "ara_factors"

    ara_id: Mapped[int] = mapped_column(ForeignKey("audit_risk_assessments.id", ondelete="CASCADE"), primary_key=True)
    factor_id: Mapped[int] = mapped_column(ForeignKey("assessment_factors.id", ondelete="CASCADE"), primary_key=True)


class AraScore(Base):
    __tablename__ = "ara_scores"
    __table_args__ = (UniqueConstraint("ara_id", "entity_id", "factor_id", name="uq_ara_scores_cell"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ara_id: Mapped[int] = mapped_column(ForeignKey("audit_risk_assessments.id", ondelete="CASCADE"), nullable=False,
                                        index=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity_units.id", ondelete="CASCADE"), nullable=False)
    factor_id: Mapped[int] = mapped_column(ForeignKey("assessment_factors.id", ondelete="CASCADE"), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    scored_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    scored_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


# Rating scales (HighBond: "Low- to High-risk" and "Very low- to Very high-risk"). Higher scores mean higher risk.
SCALES: dict[str, list[str]] = {
    "Low- to High-risk": ["Low", "Medium", "High"],
    "Very low- to Very high-risk": ["Very low", "Low", "Medium", "High", "Very high"],
}


def scale_label(scale: str, score: float | None) -> str | None:
    levels = SCALES.get(scale) or SCALES["Low- to High-risk"]
    if score is None:
        return None
    idx = min(len(levels), max(1, int(score + 0.5))) - 1  # half rounds up (2.5 -> 3)
    return levels[idx]


def band(label: str | None) -> str | None:
    """Three-band view (Low / Medium / High) of any scale label, for plan coverage and cycle rules."""
    if label is None:
        return None
    return {"Very low": "Low", "Very high": "High"}.get(label, label)


__all__ = ["Process", "ProcessOrgUnit", "EntityOrgUnit", "EntityProcess", "AssessmentFactor", "AuditRiskAssessment",
           "AraEntity", "AraFactor", "AraScore", "SCALES", "scale_label", "band"]
