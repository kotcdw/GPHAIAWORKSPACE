"""Audit report schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import ReportRating, ReportStatus
from app.core.validators import Title

_LONG = 50000


def _clean(value: str | None) -> str | None:
    return value.strip() if isinstance(value, str) else value


class ReportUpdate(BaseModel):
    title: Title | None = None
    overall_rating: ReportRating | None = None
    executive_summary: str | None = Field(default=None, max_length=_LONG)
    background: str | None = Field(default=None, max_length=_LONG)
    scope_objectives: str | None = Field(default=None, max_length=_LONG)
    methodology: str | None = Field(default=None, max_length=_LONG)
    overall_opinion: str | None = Field(default=None, max_length=_LONG)
    distribution_list: str | None = Field(default=None, max_length=5000)

    @field_validator(
        "executive_summary", "background", "scope_objectives", "methodology", "overall_opinion",
        "distribution_list",
    )
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return _clean(value)


class ManagementComments(BaseModel):
    management_comments: str = Field(max_length=_LONG)

    @field_validator("management_comments")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class SignoffOut(BaseModel):
    role: str
    name: str | None
    at: datetime | None


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    audit_id: int
    report_ref: str
    title: str
    status: ReportStatus
    overall_rating: ReportRating | None
    executive_summary: str
    background: str
    scope_objectives: str
    methodology: str
    overall_opinion: str
    distribution_list: str
    management_comments: str
    exit_meeting_date: datetime | None = None
    exit_meeting_attendees: str | None = None
    exit_meeting_notes: str | None = None
    version: int
    created_by: int | None
    manager_reviewed_by: int | None
    manager_reviewed_at: datetime | None
    cae_approved_by: int | None
    cae_approved_at: datetime | None
    issued_at: datetime | None
    created_at: datetime
    updated_at: datetime
    # Computed for the screen: what the signed-in user may do next.
    can_edit: bool = False
    can_comment: bool = False
    can_manager_review: bool = False
    can_cae_approve: bool = False
    blockers: list[str] = []
    signoffs: list[SignoffOut] = []
