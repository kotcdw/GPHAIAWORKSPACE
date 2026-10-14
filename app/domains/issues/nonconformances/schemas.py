"""Nonconformance schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import NCStatus, Severity
from app.core.schemas import ORMModel
from app.core.validators import OptEmail, Title


class NCCreate(BaseModel):
    title: Title
    description: str = ""
    severity: Severity = Severity.Medium
    disposition: str | None = Field(default=None, max_length=100)
    status: NCStatus = NCStatus.Open
    owner_email: OptEmail = None
    audit_id: int | None = None


class NCUpdate(BaseModel):
    title: Title | None = None
    description: str | None = None
    severity: Severity | None = None
    disposition: str | None = Field(default=None, max_length=100)
    status: NCStatus | None = None
    owner_email: OptEmail = None
    audit_id: int | None = None


class NCLink(BaseModel):
    capa_id: int


class NCOut(ORMModel):
    id: int
    nc_ref: str
    title: str
    description: str
    severity: Severity
    disposition: str | None
    status: NCStatus
    owner_email: str | None
    audit_id: int | None
    linked_capa_id: int | None
    created_by: int | None
    created_at: datetime
    updated_at: datetime


class NCList(BaseModel):
    total: int
    items: list[NCOut]