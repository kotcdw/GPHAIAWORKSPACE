"""Audit-trail routes. The audit log is Admin-only and append-only; per-record
history and approval cycles are readable by Admins/Auditors and by an Auditee
only for records that Auditee may see (``app.core.access``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.access import ensure_can_view, is_privileged, load_record
from app.core.database import get_db
from app.core.deps import require_active_user, require_role
from app.core.enums import Role
from app.modules.approvals.models import ApprovalCycle
from app.modules.history.models import AuditLog, RecordHistory
from app.modules.history.schemas import ApprovalCycleOut, AuditLogOut, RecordHistoryOut
from app.modules.users.models import User

router = APIRouter(prefix="/api/audit-logs", tags=["audit-logs"])
records_router = APIRouter(prefix="/api/records", tags=["record-history"])


@router.get("", response_model=list[AuditLogOut])
def list_audit_logs(
    db: DBSession = Depends(get_db),
    _: User = Depends(require_role(Role.Admin)),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    user_id: int | None = Query(default=None),
) -> list[AuditLog]:
    stmt = select(AuditLog).order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    stmt = stmt.limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


def _check_record_access(db: DBSession, user: User, record_type: str, record_id: int) -> None:
    # Privileged users may also read the history of records that were deleted.
    if is_privileged(user):
        return
    ensure_can_view(db, user, record_type, load_record(db, record_type, record_id))


@records_router.get("/{record_type}/{record_id}/history", response_model=list[RecordHistoryOut])
def get_record_history(
    record_type: str,
    record_id: int,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_active_user),
    cycle_no: int | None = Query(default=None, alias="cycle"),
) -> list[RecordHistory]:
    _check_record_access(db, user, record_type, record_id)
    stmt = (
        select(RecordHistory)
        .where(RecordHistory.record_type == record_type, RecordHistory.record_id == record_id)
        .order_by(RecordHistory.timestamp, RecordHistory.id)
    )
    if cycle_no is not None:
        stmt = stmt.where(RecordHistory.cycle_no == cycle_no)
    return list(db.execute(stmt).scalars().all())


@records_router.get("/{record_type}/{record_id}/approval-cycles", response_model=list[ApprovalCycleOut])
def get_approval_cycles(
    record_type: str,
    record_id: int,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_active_user),
) -> list[ApprovalCycle]:
    _check_record_access(db, user, record_type, record_id)
    stmt = (
        select(ApprovalCycle)
        .where(ApprovalCycle.record_type == record_type, ApprovalCycle.record_id == record_id)
        .order_by(ApprovalCycle.cycle_no, ApprovalCycle.id)
    )
    return list(db.execute(stmt).scalars().all())