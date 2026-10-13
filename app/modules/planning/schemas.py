"""Planning schemas: audit universe and Assurance Plan."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.enums import EngagementStatus, PlanStatus
from app.core.schemas import ORMModel

Quarter = Literal["Q1", "Q2", "Q3", "Q4"]
Score = Field(ge=1, le=5)


class LocationIn(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    is_active: bool = True


class LocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
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
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    owner_email: str | None = Field(default=None, max_length=255)
    risk_likelihood: int = Field(default=3, ge=1, le=5)
    risk_impact: int = Field(default=3, ge=1, le=5)
    is_active: bool = True


class EntityUnitUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    owner_email: str | None = Field(default=None, max_length=255)
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
    fiscal_year: int = Field(ge=2000, le=2100)
    title: str = Field(min_length=1, max_length=255)
    description: str = ""
    total_budget_hours: int = Field(default=0, ge=0)


class PlanUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    total_budget_hours: int | None = Field(default=None, ge=0)


class EngagementIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    entity_unit_id: int | None = None
    rationale: str = ""
    planned_quarter: Quarter = "Q1"
    budget_hours: int = Field(default=0, ge=0)
    lead_auditor_id: int | None = None


class EngagementUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    entity_unit_id: int | None = None
    rationale: str | None = None
    planned_quarter: Quarter | None = None
    budget_hours: int | None = Field(default=None, ge=0)
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
