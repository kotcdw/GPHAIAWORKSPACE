"""Shared Pydantic bases used by every module."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.core.enums import ApprovalDecision


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MessageOut(BaseModel):
    ok: bool = True
    message: str = ""


class ESignRequest(BaseModel):
    """Password attestation for an electronic signature."""

    password: str
    comment: str = ""
    decision: ApprovalDecision = ApprovalDecision.Approve