"""History schemas: append-only audit-trail records."""

from __future__ import annotations

from datetime import datetime

from app.core.schemas import ORMModel


class AuditLogOut(ORMModel):
    id: int
    user_id: int | None
    action_performed: str
    timestamp: datetime
    ip_address: str | None
    username: str | None = None
    category: str | None = None
    outcome: str | None = None


class RecordHistoryOut(ORMModel):
    id: int
    record_type: str
    record_id: int
    user_id: int | None
    action: str
    cycle_no: int | None
    timestamp: datetime
    ip_address: str | None
    user: str | None = None


class ApprovalCycleOut(ORMModel):
    id: int
    record_type: str
    record_id: int
    cycle_no: int
    approver_id: int | None
    decision: str
    comment: str
    timestamp: datetime