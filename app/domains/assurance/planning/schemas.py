"""Planning schemas: audit universe and Assurance Plan."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.enums import EngagementStatus, PlanStatus
from app.core.schemas import ORMModel
from app.core.validators import Title

Quarter = Literal["Q1", "Q2", "Q3", "Q4"]


class EntityUnitOut(ORMModel):
    id: int
    location_id: int
    location_name: str = ""
    code: str
    name: str
    description: str
    owner_email: str | None
    risk_likelihood: int
    risk_impact: int
    risk_score: int
    risk_rating: str = ""
    last_audited_at: datetime | None
    is_active: bool


class PlanIn(BaseModel):
    fiscal_year: int

    @field_validator("fiscal_year")
    @classmethod
    def _sane_year(cls, value: int) -> int:
        this_year = datetime.now(UTC).year
        if not this_year - 2 <= value <= this_year + 10:
            raise ValueError(f"must be between {this_year - 2} and {this_year + 10}")
        return value
    title: Title
    description: str = ""
    total_budget_hours: int = Field(default=0, ge=0, le=1_000_000)
    period_start: date | None = None
    period_end: date | None = None

    @field_validator("period_end")
    @classmethod
    def _period(cls, value: date | None, info) -> date | None:  # noqa: ANN001
        start = info.data.get("period_start")
        if value and start and value < start:
            raise ValueError("the planning period ends before it starts")
        return value


class PlanUpdate(BaseModel):
    title: Title | None = None
    description: str | None = None
    total_budget_hours: int | None = Field(default=None, ge=0, le=1_000_000)
    period_start: date | None = None
    period_end: date | None = None

    @field_validator("period_end")
    @classmethod
    def _period(cls, value: date | None, info) -> date | None:  # noqa: ANN001
        start = info.data.get("period_start")
        if value and start and value < start:
            raise ValueError("the planning period ends before it starts")
        return value


class EngagementIn(BaseModel):
    title: Title
    entity_unit_id: int | None = None
    rationale: str = ""
    planned_quarter: Quarter = "Q1"
    budget_hours: int = Field(default=0, ge=0, le=10_000)
    lead_auditor_id: int | None = None
    site_entity_id: int | None = None
    audit_type: str | None = Field(default=None, max_length=60)
    program_id: int | None = None
    source_audit_id: int | None = None


class EngagementUpdate(BaseModel):
    title: Title | None = None
    entity_unit_id: int | None = None
    rationale: str | None = None
    planned_quarter: Quarter | None = None
    budget_hours: int | None = Field(default=None, ge=0, le=10_000)
    lead_auditor_id: int | None = None
    site_entity_id: int | None = None
    # "" / 0 clear these.
    audit_type: str | None = Field(default=None, max_length=60)
    program_id: int | None = None
    source_audit_id: int | None = None


class EngagementOut(ORMModel):
    id: int
    plan_id: int
    entity_unit_id: int | None
    entity_unit_name: str | None = None
    entity_risk_score: int | None = None
    title: str
    rationale: str
    planned_quarter: str
    planned_start: date | None = None
    planned_end: date | None = None
    budget_hours: int
    lead_auditor_id: int | None
    site_entity_id: int | None = None
    site_name: str | None = None
    status: EngagementStatus
    audit_id: int | None
    audit_type: str | None = None
    program_id: int | None = None
    program_name: str | None = None
    source_audit_id: int | None = None
    source_audit_ref: str | None = None
    created_at: datetime


class PlanOut(ORMModel):
    id: int
    plan_ref: str
    fiscal_year: int
    title: str
    description: str
    status: PlanStatus
    total_budget_hours: int
    period_start: date | None = None
    period_end: date | None = None
    approved_by: int | None
    approved_at: datetime | None
    committee_meeting_date: datetime | None = None
    committee_reference: str | None = None
    committee_notes: str | None = None
    committee_recorded_at: datetime | None = None
    cycle_stage: str = "preparation"
    current_version: int = 0
    lifecycle_status: str = "Draft"
    archived_at: datetime | None = None
    created_by: int | None
    created_at: datetime
    updated_at: datetime


class UncoveredUnit(BaseModel):
    id: int
    name: str
    location_name: str
    risk_score: int
    risk_rating: str


class PlanSummary(BaseModel):
    engagements: int
    planned: int
    started: int
    cancelled: int
    planned_hours: int
    budget_hours: int
    universe_units: int
    covered_units: int
    coverage_pct: float
    uncovered_high_risk: list[UncoveredUnit]
    by_quarter: dict[str, int]


class PlanDetail(PlanOut):
    engagements: list[EngagementOut]
    summary: PlanSummary
