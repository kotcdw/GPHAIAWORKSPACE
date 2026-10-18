"""Organization / entity schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import OrganizationStatus
from app.core.validators import OptEmail, Title


class OrganizationCreate(BaseModel):
    name: Title
    category: str | None = Field(default=None, max_length=100)
    parent_id: int | None = None
    address: str | None = Field(default=None, max_length=2000)
    contact_name: str | None = Field(default=None, max_length=255)
    contact_email: OptEmail = None
    contact_phone: str | None = Field(default=None, max_length=50)
    evaluation_end_date: datetime | None = None
    notes: str = ""
    plan_destination: bool = False
    destination_label: str | None = Field(default=None, max_length=60)
    custom_fields: dict[str, Any] | None = None
    head_user_id: int | None = None


class OrganizationUpdate(BaseModel):
    """PATCH: only fields that are sent change; send null to clear parent / category / address."""

    name: Title | None = None
    category: str | None = Field(default=None, max_length=100)
    parent_id: int | None = None
    address: str | None = Field(default=None, max_length=2000)
    contact_name: str | None = Field(default=None, max_length=255)
    contact_email: OptEmail = None
    contact_phone: str | None = Field(default=None, max_length=50)
    evaluation_end_date: datetime | None = None
    notes: str | None = None
    plan_destination: bool | None = None
    destination_label: str | None = Field(default=None, max_length=60)
    custom_fields: dict[str, Any] | None = None
    head_user_id: int | None = None


class OrganizationOut(BaseModel):
    id: int
    org_ref: str
    name: str
    category: str | None
    is_port: bool = False
    parent_id: int | None = None
    parent_name: str | None = None
    port_id: int | None = None
    port_name: str | None = None
    children: int = 0
    address: str | None = None
    plan_destination: bool = False
    destination_label: str | None = None
    contact_name: str | None
    contact_email: str | None
    contact_phone: str | None
    status: OrganizationStatus
    evaluation_end_date: datetime | None
    approved_by: int | None
    approved_at: datetime | None
    notes: str
    custom_fields: dict[str, Any] = {}
    head_user_id: int | None = None
    head_name: str | None = None
    is_active: bool = True
    deactivated_at: datetime | None = None
    deactivation_reason: str | None = None
    created_by: int | None
    created_at: datetime
    updated_at: datetime


class DeactivateRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class OrganizationList(BaseModel):
    total: int
    items: list[OrganizationOut]


class EntityLite(BaseModel):
    """Name-only view used by pickers (e.g. "where I work"); no contact details."""

    id: int
    name: str
    category: str | None
    is_port: bool
    port_id: int | None
    port_name: str | None
    parent_id: int | None
    plan_destination: bool = False
    destination_label: str | None = None
    is_active: bool = True
