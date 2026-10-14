"""Planning schemas: audit universe and Assurance Plan."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.enums import EngagementStatus, PlanStatus
from app.core.schemas import ORMModel
from app.core.validators import Code, OptEmail, Title

Quarter = Literal["Q1", "Q2", "Q3", "Q4"]
Score = Field(ge=1, le=5)


class LocationIn(BaseModel):
    code: Code
    name: Title
    description: str = ""
    is_active: bool = True


class LocationUpdate(BaseModel):
    name: Title | None = None
    description: str | None = None
    is_active: bool | None = None


class LocationOut(ORMModel):
    id: int
    code: str
    name: str
    description: str
    is_active: bool


class EntityUnitIn(BaseModel):
    location_id: int
    code: Code
    name: Title
    description: str = ""
    owner_email: OptEmail = None
    risk_likelihood: int = Field(default=3, ge=1, le=5)
    risk_impact: int = Field(default=3, ge=1, le=5)
    is_active: bool = True


class EntityUnitUpdate(BaseModel):
    name: Title | None = None
    description: str | None = None
    owner_email: OptEmail = None
    risk_likelihood: int | None = Field(default=None, ge=1, le=5)
    risk_impact: int | None = Field(default=None, ge=1, le=5)
    is_active: bool | None = None


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


class PlanUpdate(BaseModel):
    title: Title | None = None
    description: str | None = None
    total_budget_hours: int | None = Field(default=None, ge=0, le=1_000_000)


class EngagementIn(BaseModel):
    title: Title
    entity_unit_id: int | None = None
    rationale: str = ""
    planned_quarter: Quarter = "Q1"
    budget_hours: int = Field(default=0, ge=0, le=10_000)
    lead_auditor_id: int | None = None


class EngagementUpdate(BaseModel):
    title: Title | None = None
    entity_unit_id: int | None = None
    rationale: str | None = None
    planned_quarter: Quarter | None = None
    budget_hours: int | None = Field(default=None, ge=0, le=10_000)
    lead_auditor_id: int | None = None


class EngagementOut(ORMModel):
    id: int
    plan_id: int
    entity_unit_id: int | None
    entity_unit_name: str | None = None
    entity_risk_score: int | None = None
    title: str
    rationale: str
    planned_quarter: str
    budget_hours: int
    lead_auditor_id: int | None
    status: EngagementStatus
    audit_id: int | None
    created_at: datetime


class PlanOut(ORMModel):
    id: int
    plan_ref: str
    fiscal_year: int
    title: str
    description: str
    status: PlanStatus
    total_budget_hours: int
    approved_by: int | None
    approved_at: datetime | None
    committee_meeting_date: datetime | None = None
    committee_reference: str | None = None
    committee_notes: str | None = None
    committee_recorded_at: datetime | None = None
    cycle_stage: str = "preparation"
    current_version: int = 0
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
