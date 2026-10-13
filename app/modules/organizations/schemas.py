"""Organization schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.core.enums import OrganizationStatus
from app.core.schemas import ORMModel


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    category: str | None = Field(default=None, max_length=100)
    contact_name: str | None = Field(default=None, max_length=255)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=50)
    evaluation_end_date: datetime | None = None
    notes: str = ""


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, max_length=100)
    contact_name: str | None = Field(default=None, max_length=255)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=50)
    evaluation_end_date: datetime | None = None
    notes: str | None = None


class OrganizationOut(ORMModel):
    id: int
    org_ref: str
    name: str
    category: str | None
    contact_name: str | None
    contact_email: str | None
    contact_phone: str | None
    status: OrganizationStatus
    evaluation_end_date: datetime | None
    approved_by: int | None
    approved_at: datetime | None
    notes: str
    created_by: int | None
    created_at: datetime
    updated_at: datetime


class OrganizationList(BaseModel):
    total: int
    items: list[OrganizationOut]