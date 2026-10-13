"""Service feedback schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import FeedbackStatus
from app.core.schemas import ORMModel


class SFCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    description: str = ""
    source: str | None = Field(default=None, max_length=100)
    received_date: datetime | None = None
    status: FeedbackStatus = FeedbackStatus.Open
    owner_email: str | None = Field(default=None, max_length=255)


class SFUpdate(BaseModel):
    subject: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    source: str | None = Field(default=None, max_length=100)
    received_date: datetime | None = None
    status: FeedbackStatus | None = None
    owner_email: str | None = Field(default=None, max_length=255)


class SFLink(BaseModel):
    nc_id: int | None = None
    capa_id: int | None = None


class SFOut(ORMModel):
    id: int
    sf_ref: str
    subject: str
    description: str
    source: str | None
    received_date: datetime
    status: FeedbackStatus
    owner_email: str | None
    linked_nc_id: int | None
    linked_capa_id: int | None
    created_by: int | None
    created_at: datetime
    updated_at: datetime


class SFList(BaseModel):
    total: int
    items: list[SFOut]