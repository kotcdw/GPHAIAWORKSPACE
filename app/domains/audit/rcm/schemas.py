"""Risk & control matrix schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import ControlFrequency, ControlNature, ControlType, TestConclusion, TestStatus, TestType
from app.core.schemas import ORMModel
from app.core.validators import OptEmail, Title


class ObjectiveIn(BaseModel):
    title: Title
    description: str = ""


class ObjectiveUpdate(BaseModel):
    title: Title | None = None
    description: str | None = None


class RiskIn(BaseModel):
    title: Title
    description: str = ""
    likelihood: int = Field(default=3, ge=1, le=5)
    impact: int = Field(default=3, ge=1, le=5)
    enterprise_risk_id: int | None = None


class RiskUpdate(BaseModel):
    title: Title | None = None
    description: str | None = None
    likelihood: int | None = Field(default=None, ge=1, le=5)
    impact: int | None = Field(default=None, ge=1, le=5)
    enterprise_risk_id: int | None = None  # 0 clears


class ControlIn(BaseModel):
    title: Title
    description: str = ""
    control_type: ControlType = ControlType.Preventive
    nature: ControlNature = ControlNature.Manual
    frequency: ControlFrequency = ControlFrequency.Monthly
    owner_email: OptEmail = None
    is_key: bool = True
    risk_ids: list[int] = []
    test_method: str | None = Field(default=None, max_length=60)
    total_sample_size: int | None = Field(default=None, ge=0, le=100000)
    test_steps: str | None = Field(default=None, max_length=20000)


class ControlUpdate(BaseModel):
    title: Title | None = None
    description: str | None = None
    control_type: ControlType | None = None
    nature: ControlNature | None = None
    frequency: ControlFrequency | None = None
    owner_email: OptEmail = None
    is_key: bool | None = None
    test_method: str | None = Field(default=None, max_length=60)
    total_sample_size: int | None = Field(default=None, ge=0, le=100000)
    test_steps: str | None = Field(default=None, max_length=20000)


class RiskMapping(BaseModel):
    risk_ids: list[int]


class TestIn(BaseModel):
    test_type: TestType
    procedure: str = ""
    round_no: int | None = Field(default=None, ge=1, le=4)  # operating-effectiveness tests
    assigned_to: int | None = None


class TestUpdate(BaseModel):
    procedure: str | None = None
    population_size: int | None = Field(default=None, ge=0)
    sample_size: int | None = Field(default=None, ge=0)
    exceptions_found: int | None = Field(default=None, ge=0)
    results: str | None = None
    status: TestStatus | None = None
    conclusion: TestConclusion | None = None
    assigned_to: int | None = None  # 0 clears
    in_scope: bool | None = None  # HighBond: "Are you testing this key control this round?"


class SampleRequest(BaseModel):
    population_size: int = Field(ge=1, le=1_000_000)
    sample_size: int | None = Field(default=None, ge=1)
    seed: int | None = None


class SampleRecommendation(BaseModel):
    frequency: str
    nature: str
    test_type: str
    recommended_size: int
    basis: str


class TestOut(ORMModel):
    id: int
    control_id: int
    ref: str
    test_type: TestType
    procedure: str
    population_size: int | None
    sample_size: int | None
    sample_seed: int | None
    sample_items: str
    exceptions_found: int
    results: str
    status: TestStatus
    conclusion: TestConclusion
    performed_by: int | None
    performed_at: datetime | None
    reviewed_by: int | None
    reviewed_at: datetime | None
    review_comment: str
    round_no: int | None = None
    in_scope: bool = True
    assigned_to: int | None = None
    created_at: datetime


class RiskOut(ORMModel):
    id: int
    objective_id: int
    ref: str
    title: str
    description: str
    likelihood: int
    impact: int
    inherent_score: int
    inherent_rating: str
    enterprise_risk_id: int | None = None
    enterprise_risk: str | None = None
    control_ids: list[int] = []
    residual_rating: str = ""


class ControlOut(ORMModel):
    id: int
    objective_id: int
    ref: str
    title: str
    description: str
    control_type: ControlType
    nature: ControlNature
    frequency: ControlFrequency
    owner_email: str | None
    is_key: bool
    library_control_id: int | None = None
    test_method: str | None = None
    total_sample_size: int | None = None
    test_steps: str | None = None
    risk_ids: list[int] = []
    tests: list[TestOut] = []
    effectiveness: str = "Not Tested"


class ObjectiveOut(ORMModel):
    id: int
    audit_id: int
    ref: str
    title: str
    description: str
    risks: list[RiskOut] = []
    controls: list[ControlOut] = []


class RcmSummary(BaseModel):
    objectives: int
    risks: int
    risks_by_rating: dict[str, int]
    risks_without_controls: list[str]
    controls: int
    key_controls: int
    controls_by_effectiveness: dict[str, int]
    key_controls_untested: list[str]
    tests: int
    tests_awaiting_review: int
    open_issues: int


class RcmOut(BaseModel):
    audit_id: int
    locked: bool
    objectives: list[ObjectiveOut]
    summary: RcmSummary
