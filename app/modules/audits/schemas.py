"""Audits schemas: audits, findings and working papers."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

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


class FindingUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    risk_rating: RiskRating | None = None
    status: FindingStatus | None = None
    assigned_owner_email: EmailStr | None = None


class FindingOut(ORMModel):
    id: int
    audit_id: int
    title: str
    description: str
    risk_rating: RiskRating
    status: FindingStatus
    assigned_owner_email: str | None
    created_by: int | None
    created_at: datetime
    updated_at: datetime


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
