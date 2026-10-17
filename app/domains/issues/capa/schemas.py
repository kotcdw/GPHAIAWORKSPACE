"""CAPA schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

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
    timeframe: str | None = Field(default=None, max_length=60)
    source_body: str | None = Field(default=None, max_length=100)
    source_reference: str | None = Field(default=None, max_length=120)
    source_year: int | None = Field(default=None, ge=1990, le=2100)
    followup_comment: str | None = Field(default=None, max_length=10000)
    external_closure_ref: str | None = Field(default=None, max_length=120)
    custom_fields: dict[str, Any] | None = None


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
    timeframe: str | None = Field(default=None, max_length=60)
    source_body: str | None = Field(default=None, max_length=100)
    source_reference: str | None = Field(default=None, max_length=120)
    source_year: int | None = Field(default=None, ge=1990, le=2100)
    followup_comment: str | None = Field(default=None, max_length=10000)
    external_closure_ref: str | None = Field(default=None, max_length=120)
    custom_fields: dict[str, Any] | None = None
    # Required when an agreed target date is revised.
    due_date_reason: str | None = Field(default=None, max_length=2000)


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
    validation_procedures: str | None = None
    validated_by: int | None = None
    validated_at: datetime | None = None
    reopen_count: int = 0
    escalation_level: int = 0
    implementation_status: str = "Not Implemented"
    timeframe: str | None = None
    source_body: str | None = None
    source_reference: str | None = None
    source_year: int | None = None
    followup_comment: str | None = None
    progress_note: str | None = None
    withdrawal_reason: str | None = None
    withdrawal_proposed_at: datetime | None = None
    external_closure_ref: str | None = None
    original_due_date: datetime | None = None
    extension_count: int = 0
    risk_accepted_by: int | None = None
    risk_accepted_at: datetime | None = None
    risk_acceptance: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    created_by: int | None
    created_at: datetime
    updated_at: datetime

    @field_validator("custom_fields", mode="before")
    @classmethod
    def _cf(cls, v: Any) -> dict:
        import json

        if isinstance(v, str):
            try:
                return json.loads(v or "{}")
            except ValueError:
                return {}
        return v or {}


class CapaList(BaseModel):
    total: int
    items: list[CapaOut]

