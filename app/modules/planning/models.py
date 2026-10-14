"""Audit universe (locations -> entity units) and the annual Assurance Plan.

The Assurance Plan is GPHA's annual audit plan: it opens the fiscal year and
every audit (project) of that year starts from one of its planned engagements.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.enums import EngagementStatus, PlanStatus, _enum, utcnow


class Location(Base):
    """A site of the organization (e.g. Tema, Takoradi)."""

    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    units: Mapped[list[EntityUnit]] = relationship(back_populates="location", order_by="EntityUnit.code")


class EntityUnit(Base):
    """An auditable entity of the audit universe (e.g. GJT, Fishing Harbour)."""

    __tablename__ = "entity_units"
    __table_args__ = (UniqueConstraint("location_id", "code", name="uq_entity_units_location_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    owner_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Universe-level inherent risk assessment used to prioritise the plan.
    risk_likelihood: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    risk_impact: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    last_audited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    location: Mapped[Location] = relationship(back_populates="units")

    @property
    def risk_score(self) -> int:
        return self.risk_likelihood * self.risk_impact


class AssurancePlan(Base):
    __tablename__ = "assurance_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_ref: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[PlanStatus] = mapped_column(_enum(PlanStatus), nullable=False, default=PlanStatus.Draft)
    total_budget_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Audit Committee approval of the plan (GIAS 9.4), recorded after the CAE's e-signed approval.
    # Annual planning cycle (app.modules.plancycle): the stage awaiting completion and the approved version.
    cycle_stage: Mapped[str] = mapped_column(String(30), nullable=False, default="preparation",
                                             server_default="preparation")
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    committee_meeting_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    committee_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    committee_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    committee_recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"),
                                                              nullable=True)
    committee_recorded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    engagements: Mapped[list[PlanEngagement]] = relationship(
        back_populates="plan", order_by="PlanEngagement.id", cascade="all, delete-orphan"
    )


class PlanEngagement(Base):
    """A planned audit within an Assurance Plan; starting it creates the project."""

    __tablename__ = "plan_engagements"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("assurance_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("entity_units.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    planned_quarter: Mapped[str] = mapped_column(String(2), nullable=False, default="Q1")
    budget_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lead_auditor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[EngagementStatus] = mapped_column(
        _enum(EngagementStatus), nullable=False, default=EngagementStatus.Planned
    )
    audit_id: Mapped[int | None] = mapped_column(ForeignKey("audits.id", ondelete="SET NULL"), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    plan: Mapped[AssurancePlan] = relationship(back_populates="engagements")
    entity_unit: Mapped[EntityUnit | None] = relationship()


class PlanChange(Base):
    """A documented change to an approved plan (engagement added, cancelled or changed; committee approval)."""

    __tablename__ = "plan_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("assurance_plans.id", ondelete="CASCADE"), nullable=False,
                                         index=True)
    engagement_id: Mapped[int | None] = mapped_column(ForeignKey("plan_engagements.id", ondelete="SET NULL"),
                                                      nullable=True)
    change_type: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
