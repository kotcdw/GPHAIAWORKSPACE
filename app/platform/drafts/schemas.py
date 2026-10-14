"""Draft schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.schemas import ORMModel


class DraftIn(BaseModel):
    title: str = Field(default="", max_length=255)
    record_type: str | None = Field(default=None, max_length=50)
    record_id: int | None = None
    payload: dict[str, Any]


class DraftOut(ORMModel):
    form_key: str
    title: str
    record_type: str | None
    record_id: int | None
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class DraftSummary(ORMModel):
    form_key: str
    title: str
    record_type: str | None
    record_id: int | None
    updated_at: datetime
