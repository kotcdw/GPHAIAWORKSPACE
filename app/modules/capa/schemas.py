"""CAPA schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import CapaStatus, Severity
from app.core.schemas import ORMModel
from app.core.validators import FutureDate, OptEmail, Title


class CapaCreate(BaseModel):
    title: Title
    description: str = ""
    root_cause: str = ""
    corrective_action: str = ""
    preventive_action: str = ""
    effectiveness_check: str = ""
    severity: Severity = Severity.Medium
    disposition: str | None = Field(default=None, max_length=100)
    status: CapaStatus = CapaStatus.Open
    owner_email: OptEmail = None
    due_date: FutureDate = None
    linked_nc_id: int | None = None


class CapaUpdate(BaseModel):
    title: Title | None = None
    description: str | None = None
    root_cause: str | None = None
    corrective_action: str | None = None
    preventive_action: str | None = None
    effectiveness_check: str | None = None
    severity: Severity | None = None
    disposition: str | None = Field(default=None, max_length=100)
    status: CapaStatus | None = None
    owner_email: OptEmail = None
    due_date: FutureDate = None
    linked_nc_id: int | None = None


class CapaLink(BaseModel):
    nc_id: int


class CapaOut(ORMModel):
    id: int
    capa_ref: str
    title: str
    description: str
    root_cause: str
    corrective_action: str
    preventive_action: str
    effectiveness_check: str
    severity: Severity
    disposition: str | None
    status: CapaStatus
    owner_email: str | None
    due_date: datetime | None
    closed_by: int | None
    closed_at: datetime | None
    source_type: str | None
    source_id: int | None
    linked_nc_id: int | None
    implementation_evidence: str | None = None
    implemented_by: int | None = None
    implemented_at: datetime | None = None
    validation_result: str | None = None
    validation_comment: str | None = None
    validated_by: int | None = None
    validated_at: datetime | None = None
    reopen_count: int = 0
    escalation_level: int = 0
    created_by: int | None
    created_at: datetime
    updated_at: datetime


class CapaList(BaseModel):
    total: int
    items: list[CapaOut]