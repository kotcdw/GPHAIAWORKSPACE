"""Task Center schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import TaskStatus
from app.core.schemas import ORMModel


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = ""
    assignee_id: int | None = None
    due_date: datetime | None = None
    source_type: str | None = Field(default=None, max_length=50)
    source_id: int | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: TaskStatus | None = None
    due_date: datetime | None = None
    assignee_id: int | None = None


class TaskOut(ORMModel):
    id: int
    title: str
    description: str
    assignee_id: int | None
    assignor_id: int | None
    status: TaskStatus
    due_date: datetime | None
    source_type: str | None
    source_id: int | None
    system_generated: bool
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class TaskList(BaseModel):
    total: int
    items: list[TaskOut]