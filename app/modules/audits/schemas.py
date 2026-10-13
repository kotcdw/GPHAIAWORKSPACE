"""Audits schemas: audits, findings and working papers."""

from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.enums import ApprovalStatus, AuditStatus, FindingStatus, RiskRating
from app.core.schemas import ORMModel


# --------------------------------------------------------------------------- audits
class AuditCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = ""
    scope: str = ""
    status: AuditStatus = AuditStatus.Planned
    organization_id: int | None = None


class AuditUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    scope: str | None = None
    status: AuditStatus | None = None
    organization_id: int | None = None


class AuditOut(ORMModel):
    id: int
    title: str
    description: str
    scope: str
    status: AuditStatus
    approval_status: ApprovalStatus | None
    organization_id: int | None
    plan_id: int | None = None
    entity_unit_id: int | None = None
    created_by: int | None
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- findings
class FindingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = ""
    risk_rating: RiskRating = RiskRating.Medium
    status: FindingStatus = FindingStatus.Open
    assigned_owner_email: EmailStr | None = None
    criteria: str | None = None
    condition: str | None = None
    cause: str | None = None
    effect: str | None = None
    recommendation: str | None = None
    root_cause_whys: list[str] | None = Field(default=None, max_length=5)
    control_id: int | None = None


class FindingUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    risk_rating: RiskRating | None = None
    status: FindingStatus | None = None
    assigned_owner_email: EmailStr | None = None
    criteria: str | None = None
    condition: str | None = None
    cause: str | None = None
    effect: str | None = None
    recommendation: str | None = None
    root_cause_whys: list[str] | None = Field(default=None, max_length=5)
    control_id: int | None = None


class ManagementResponse(BaseModel):
    management_response: str = Field(min_length=1, max_length=10000)


class FindingOut(ORMModel):
    id: int
    audit_id: int
    title: str
    description: str
    risk_rating: RiskRating
    status: FindingStatus
    assigned_owner_email: str | None
    control_id: int | None = None
    test_id: int | None = None
    criteria: str | None = ""
    condition: str | None = ""
    cause: str | None = ""
    effect: str | None = ""
    recommendation: str | None = ""
    root_cause_whys: list[str] = []
    management_response: str | None = ""
    created_by: int | None
    created_at: datetime
    updated_at: datetime

    @field_validator("root_cause_whys", mode="before")
    @classmethod
    def _parse_whys(cls, value):  # noqa: ANN001, ANN206
        if value is None or value == "":
            return []
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except ValueError:
                return [value]
            return [str(v) for v in parsed] if isinstance(parsed, list) else [str(parsed)]
        return value


# --------------------------------------------------------------------------- working papers
class WorkingPaperOut(ORMModel):
    id: int
    audit_id: int
    title: str
    file_path: str
    version_number: int
    uploaded_by: int | None
    uploaded_at: datetime
    is_deleted: bool = False
    deleted_at: datetime | None = None
    sha256: str | None = None


class AuditeeAssign(BaseModel):
    user_id: int


class AuditeeOut(BaseModel):
    user_id: int
    username: str
    full_name: str
    email: str
    assigned_at: datetime | None = None
