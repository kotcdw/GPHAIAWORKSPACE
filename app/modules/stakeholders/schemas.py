"""Stakeholder schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import StakeholderStatus
from app.core.schemas import ORMModel
from app.core.validators import OptEmail, Title


class StakeholderCreate(BaseModel):
    name: Title
    stakeholder_type: str | None = Field(default=None, max_length=100)
    contact_name: str | None = Field(default=None, max_length=255)
    contact_email: OptEmail = None
    contact_phone: str | None = Field(default=None, max_length=50)
    status: StakeholderStatus = StakeholderStatus.Active
    notes: str = ""


class StakeholderUpdate(BaseModel):
    name: Title | None = None
    stakeholder_type: str | None = Field(default=None, max_length=100)
    contact_name: str | None = Field(default=None, max_length=255)
    contact_email: OptEmail = None
    contact_phone: str | None = Field(default=None, max_length=50)
    status: StakeholderStatus | None = None
    notes: str | None = None


class StakeholderOut(ORMModel):
    id: int
    sh_ref: str
    name: str
    stakeholder_type: str | None
    contact_name: str | None
    contact_email: str | None
    contact_phone: str | None
    status: StakeholderStatus
    notes: str
    created_by: int | None
    created_at: datetime
    updated_at: datetime


class StakeholderList(BaseModel):
    total: int
    items: list[StakeholderOut]