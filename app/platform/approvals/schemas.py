"""Approval / e-signature schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.enums import ApprovalDecision


class ApprovalSignIn(BaseModel):
    record_type: str = Field(min_length=1, max_length=50)
    record_id: int
    decision: ApprovalDecision = ApprovalDecision.Approve
    comment: str = ""
    password: str