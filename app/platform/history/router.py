"""Audit-trail routes. The audit log is Admin-only and append-only; per-record
history and approval cycles are readable by Admins/Auditors and by an Auditee
only for records that Auditee may see (``app.core.access``)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.access import ensure_can_view, is_privileged, load_record
from app.core.database import get_db
from app.core.deps import require_active_user, require_role
from app.core.enums import Role
from app.core.paging import Page, PageParams, page_params, paginate_query
from app.platform.approvals.models import ApprovalCycle
from app.platform.history.models import AuditLog, RecordHistory
from app.platform.history.schemas import ApprovalCycleOut, AuditLogOut, RecordHistoryOut
from app.platform.users.models import User

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


class AuditLogRow(BaseModel):
    id: int
    timestamp: datetime
    user_id: int | None
    user: str | None
    ip_address: str | None
    action_performed: str


@router.get("/register", response_model=Page[AuditLogRow])
def audit_log_register(
    db: DBSession = Depends(get_db),
    _: User = Depends(require_role(Role.Admin)),
    params: PageParams = Depends(page_params),
    user_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
) -> Page[AuditLogRow]:
    """The audit log as a server-paged register: search the action text, filter by user and date range."""
    stmt = select(AuditLog)
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if date_from is not None:
        stmt = stmt.where(AuditLog.timestamp >= datetime.combine(date_from, time.min))
    if date_to is not None:
        stmt = stmt.where(AuditLog.timestamp < datetime.combine(date_to + timedelta(days=1), time.min))
    if params.q:
        like = f"%{params.q.lower()}%"
        stmt = stmt.where(func.lower(AuditLog.action_performed).like(like) | AuditLog.ip_address.like(like))
    rows, total, sort = paginate_query(db, stmt, params, {"timestamp": AuditLog.timestamp, "user": AuditLog.user_id},
                                       "-timestamp", AuditLog.id)
    names = {u.id: (u.full_name or u.username) for u in db.execute(
        select(User).where(User.id.in_({r.user_id for r in rows if r.user_id} or {0}))).scalars()}
    items = [AuditLogRow(id=r.id, timestamp=r.timestamp, user_id=r.user_id, user=names.get(r.user_id),
                         ip_address=r.ip_address, action_performed=r.action_performed) for r in rows]
    return Page[AuditLogRow](items=items, total=total, page=params.page, page_size=params.page_size, sort=sort)


def _check_record_access(db: DBSession, user: User, record_type: str, record_id: int) -> None:
    # Staff may also read the history of records that were deleted; existing records follow the access rules
    # (audit staff are limited to their port and teams).
    record = load_record(db, record_type, record_id)
    if is_privileged(user) and (user.role == Role.Admin or record is None):
        return
    ensure_can_view(db, user, record_type, record)


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