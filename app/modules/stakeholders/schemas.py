"""Stakeholder schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.core.enums import StakeholderStatus
from app.core.schemas import ORMModel


class StakeholderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    stakeholder_type: str | None = Field(default=None, max_length=100)
    contact_name: str | None = Field(default=None, max_length=255)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=50)
    status: StakeholderStatus = StakeholderStatus.Active
    notes: str = ""


class StakeholderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    stakeholder_type: str | None = Field(default=None, max_length=100)
    contact_name: str | None = Field(default=None, max_length=255)
    contact_email: EmailStr | None = None
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