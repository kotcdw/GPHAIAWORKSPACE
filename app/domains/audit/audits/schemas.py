"""Audits schemas: audits, findings and working papers."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator

from app.core.enums import ApprovalStatus, AuditStatus, FindingStatus, RiskRating
from app.core.schemas import ORMModel
from app.core.validators import OptEmail, Title


# --------------------------------------------------------------------------- audits
class AuditCreate(BaseModel):
    title: Title
    description: str = ""
    scope: str = ""
    status: AuditStatus = AuditStatus.Planned
    organization_id: int | None = None
    audit_type: str | None = Field(default=None, max_length=60)
    port_entity_id: int | None = None
    custom_fields: dict[str, Any] | None = None


class AuditUpdate(BaseModel):
    title: Title | None = None
    description: str | None = None
    scope: str | None = None
    status: AuditStatus | None = None
    organization_id: int | None = None
    audit_type: str | None = Field(default=None, max_length=60)
    port_entity_id: int | None = None
    custom_fields: dict[str, Any] | None = None


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
    audit_type: str | None = None
    port_entity_id: int | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    created_by: int | None
    created_at: datetime
    updated_at: datetime

    @field_validator("custom_fields", mode="before")
    @classmethod
    def _cf(cls, value):  # noqa: ANN001, ANN206
        if isinstance(value, str):
            try:
                return json.loads(value or "{}")
            except ValueError:
                return {}
        return value or {}


# --------------------------------------------------------------------------- findings
class FindingCreate(BaseModel):
    title: Title
    description: str = ""
    risk_rating: RiskRating = RiskRating.Medium
    status: FindingStatus = FindingStatus.Open
    assigned_owner_email: OptEmail = None
    criteria: str | None = None
    condition: str | None = None
    cause: str | None = None
    effect: str | None = None
    recommendation: str | None = None
    root_cause_whys: list[Annotated[str, Field(max_length=1000)]] | None = Field(default=None, max_length=5)
    control_id: int | None = None
    criterion_id: int | None = None
    custom_fields: dict[str, Any] | None = None


class FindingUpdate(BaseModel):
    title: Title | None = None
    description: str | None = None
    risk_rating: RiskRating | None = None
    status: FindingStatus | None = None
    assigned_owner_email: OptEmail = None
    criteria: str | None = None
    condition: str | None = None
    cause: str | None = None
    effect: str | None = None
    recommendation: str | None = None
    root_cause_whys: list[Annotated[str, Field(max_length=1000)]] | None = Field(default=None, max_length=5)
    control_id: int | None = None
    criterion_id: int | None = None
    custom_fields: dict[str, Any] | None = None


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
    criterion_id: int | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    created_by: int | None
    created_at: datetime
    updated_at: datetime

    @field_validator("custom_fields", mode="before")
    @classmethod
    def _cf(cls, value):  # noqa: ANN001, ANN206
        if isinstance(value, str):
            try:
                return json.loads(value or "{}")
            except ValueError:
                return {}
        return value or {}

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
    wp_ref: str | None = None
    test_id: int | None = None
    finding_id: int | None = None
    reviewed_by: int | None = None
    reviewed_at: datetime | None = None


class AuditeeAssign(BaseModel):
    user_id: int


class AuditeeOut(BaseModel):
    user_id: int
    username: str
    full_name: str
    email: str
    assigned_at: datetime | None = None
