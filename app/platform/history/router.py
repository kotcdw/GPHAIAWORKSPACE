"""Audit-trail routes. The audit log is Admin-only and append-only; per-record
history and approval cycles are readable by Admins/Auditors and by an Auditee
only for records that Auditee may see (``app.core.access``)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.access import ensure_can_view, is_privileged, load_record
from app.core.database import get_db
from app.core.deps import require_active_user, require_perm
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
    _: User = Depends(require_perm("system.technical")),
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
    username: str | None
    category: str
    outcome: str
    entity_type: str | None
    entity_id: int | None
    ip_address: str | None
    user_agent: str | None
    action_performed: str
    event: str = ""
    details: str = ""


def _filtered(
    user_id: int | None, date_from: date | None, date_to: date | None, category: str | None, outcome: str | None,
    entity_type: str | None, entity_id: int | None, q: str | None,
):  # noqa: ANN202 - a SQLAlchemy select
    stmt = select(AuditLog)
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if date_from is not None:
        stmt = stmt.where(AuditLog.timestamp >= datetime.combine(date_from, time.min))
    if date_to is not None:
        stmt = stmt.where(AuditLog.timestamp < datetime.combine(date_to + timedelta(days=1), time.min))
    if category:
        if category == "authentication":
            # Entries written before categories existed are recognised by their action text.
            stmt = stmt.where((AuditLog.category == category) | (AuditLog.category.is_(None) & (
                AuditLog.action_performed.like("LOGIN%") | AuditLog.action_performed.like("LOGOUT%")
                | AuditLog.action_performed.like("ACCOUNT_LOCKED%") | AuditLog.action_performed.like("PASSWORD%")
                | AuditLog.action_performed.like("MFA_%") | AuditLog.action_performed.like("REGISTER%"))))
        else:
            stmt = stmt.where(AuditLog.category == category)
    if outcome == "failure":
        stmt = stmt.where((AuditLog.outcome == "failure") | (AuditLog.outcome.is_(None) & (
            AuditLog.action_performed.like("%FAILED%") | AuditLog.action_performed.like("%DENIED%")
            | AuditLog.action_performed.like("ACCOUNT_LOCKED%"))))
    elif outcome == "success":
        stmt = stmt.where(AuditLog.outcome != "failure")
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(AuditLog.action_performed).like(like) | AuditLog.ip_address.like(like)
                          | func.lower(AuditLog.username).like(like))
    return stmt


def _rows(db: DBSession, entries: list[AuditLog]) -> list[AuditLogRow]:
    from app.core.audit import classify
    from app.core.audit_describe import describe

    names = {u.id: (u.full_name or u.username) for u in db.execute(
        select(User).where(User.id.in_({r.user_id for r in entries if r.user_id} or {0}))).scalars()}
    out = []
    for r in entries:
        category, outcome, entity, entity_id = classify(r.action_performed)
        typed = r.username
        if typed is None and "username=" in r.action_performed:  # entries written before the username column
            typed = r.action_performed.split("username=", 1)[1].split(" ", 1)[0][:64] or None
        out.append(AuditLogRow(
            id=r.id, timestamp=r.timestamp, user_id=r.user_id,
            user=names.get(r.user_id) or typed or (None if r.user_id else "System / anonymous"),
            username=typed, category=r.category or category, outcome=r.outcome or outcome,
            entity_type=r.entity_type or entity, entity_id=r.entity_id if r.entity_id is not None else entity_id,
            ip_address=r.ip_address, user_agent=r.user_agent, action_performed=r.action_performed,
            event=describe(r.action_performed)[0], details=describe(r.action_performed)[1]))
    return out


PROTECTED_TABLES = {"audit_logs": "Audit trail", "workflow_transitions": "Workflow status history",
                    "app_config_history": "Settings history", "import_runs": "Import history",
                    "backup_checks": "Backup checks"}


@router.get("/integrity")
def audit_integrity(db: DBSession = Depends(get_db), _: User = Depends(require_perm("system.technical"))) -> dict:
    """Is the database still refusing changes to the protected records? Checks the triggers that block UPDATE
    and DELETE, and reports how much the trail holds."""
    from sqlalchemy import func, text

    dialect = db.get_bind().dialect.name
    if dialect == "mysql":
        rows = db.execute(text("SELECT EVENT_OBJECT_TABLE, EVENT_MANIPULATION FROM information_schema.TRIGGERS "
                               "WHERE TRIGGER_SCHEMA = DATABASE()")).all()
        found = {(t, e.upper()) for t, e in rows}
    else:  # SQLite: the event is part of the trigger's SQL
        rows = db.execute(text("SELECT tbl_name, sql FROM sqlite_master WHERE type = 'trigger'")).all()
        found = {(t, verb) for t, sql in rows for verb in ("UPDATE", "DELETE") if f"BEFORE {verb}" in (sql or "")}
    tables = [{"table": t, "label": label, "update_blocked": (t, "UPDATE") in found,
               "delete_blocked": (t, "DELETE") in found} for t, label in PROTECTED_TABLES.items()]
    oldest, total = db.execute(select(func.min(AuditLog.timestamp), func.count(AuditLog.id))).one()
    return {"protected": all(x["update_blocked"] and x["delete_blocked"] for x in tables), "tables": tables,
            "entries": total, "oldest": oldest.isoformat() if oldest else None}


@router.get("/register", response_model=Page[AuditLogRow])
def audit_log_register(
    db: DBSession = Depends(get_db),
    _: User = Depends(require_perm("system.technical")),
    params: PageParams = Depends(page_params),
    user_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    category: str | None = Query(default=None, max_length=20),
    outcome: str | None = Query(default=None, pattern="^(success|failure)$"),
    entity_type: str | None = Query(default=None, max_length=50),
    entity_id: int | None = Query(default=None),
) -> Page[AuditLogRow]:
    """The audit trail as a server-paged register: search the action text, user name or IP; filter by user,
    date range, category (authentication, user administration, security, export, system, data), outcome
    (success / failure) and record."""
    stmt = _filtered(user_id, date_from, date_to, category, outcome, entity_type, entity_id, params.q)
    rows, total, sort = paginate_query(db, stmt, params, {"timestamp": AuditLog.timestamp, "user": AuditLog.user_id},
                                       "-timestamp", AuditLog.id)
    return Page[AuditLogRow](items=_rows(db, rows), total=total, page=params.page, page_size=params.page_size,
                             sort=sort)


class AuditSummary(BaseModel):
    period_days: int
    sign_ins: int
    failed_sign_ins: int
    lockouts: int
    denied: int
    distinct_users: int
    distinct_ips: int
    exports: int
    security_events: int
    locked_now: list[str]
    top_failures: list[dict]


@router.get("/summary", response_model=AuditSummary)
def audit_summary(
    db: DBSession = Depends(get_db),
    _: User = Depends(require_perm("system.technical")),
    days: int = Query(default=7, ge=1, le=365),
) -> AuditSummary:
    """Sign-in and security activity for the last ``days`` days (the tiles above the audit trail)."""
    from app.core.enums import utcnow

    since = utcnow() - timedelta(days=days)
    entries = list(db.execute(select(AuditLog).where(AuditLog.timestamp >= since)).scalars())
    rows = _rows(db, entries)
    auth = [r for r in rows if r.category == "authentication"]
    failures = [r for r in auth if r.outcome == "failure" and r.action_performed.startswith("LOGIN_FAILED")]
    by_name: dict[str, int] = {}
    for r in failures:
        key = r.username or r.user or "unknown"
        by_name[key] = by_name.get(key, 0) + 1
    locked = [u.username for u in db.execute(select(User).where(User.locked_until.is_not(None),
                                                                 User.locked_until > utcnow())).scalars()]
    return AuditSummary(
        period_days=days,
        sign_ins=sum(1 for r in auth if r.action_performed.split(" ")[0] == "LOGIN"),
        failed_sign_ins=len(failures),
        lockouts=sum(1 for r in auth if r.action_performed.startswith("ACCOUNT_LOCKED")),
        denied=sum(1 for r in auth if r.action_performed.startswith("LOGIN_DENIED")),
        distinct_users=len({r.user_id for r in auth if r.user_id and r.outcome == "success"}),
        distinct_ips=len({r.ip_address for r in auth if r.ip_address}),
        exports=sum(1 for r in rows if r.category == "export"),
        security_events=sum(1 for r in rows if r.category == "security"
                            or (r.category == "authentication" and r.outcome == "failure")),
        locked_now=locked,
        top_failures=[{"username": k, "failures": v}
                      for k, v in sorted(by_name.items(), key=lambda kv: -kv[1])[:5]],
    )


@router.get("/export.csv")
def audit_log_export(
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_perm("system.technical")),
    q: str | None = Query(default=None, max_length=120),
    user_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    category: str | None = Query(default=None, max_length=20),
    outcome: str | None = Query(default=None, pattern="^(success|failure)$"),
    entity_type: str | None = Query(default=None, max_length=50),
    entity_id: int | None = Query(default=None),
) -> Response:
    """Export the filtered audit trail (at most 100,000 rows) as CSV. The export itself is logged."""
    import csv
    import io

    from app.core.audit import log_action

    stmt = _filtered(user_id, date_from, date_to, category, outcome, entity_type, entity_id, (q or "").strip() or None)
    entries = list(db.execute(stmt.order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).limit(100000)).scalars())
    out = io.StringIO()
    writer = csv.writer(out)
    from app.core.regional import fmt_datetime

    writer.writerow(["Id", "Timestamp (UTC)", "Local time", "User", "Username", "Event", "Category", "Outcome",
                     "Record type", "Record id", "Action (as recorded)", "IP address", "Browser"])
    for r in _rows(db, entries):
        writer.writerow([r.id, f"{r.timestamp:%Y-%m-%d %H:%M:%S}", fmt_datetime(r.timestamp), r.user or "",
                         r.username or "", r.event, r.category, r.outcome, r.entity_type or "", r.entity_id or "",
                         r.action_performed, r.ip_address or "", r.user_agent or ""])
    filters = ", ".join(f"{k}={v}" for k, v in {"q": q, "user": user_id, "from": date_from, "to": date_to,
                                                  "category": category, "outcome": outcome}.items() if v)
    log_action(db, user_id=user.id, request=request, commit=True,
               action=f"AUDIT_LOG_EXPORT rows={len(entries)}" + (f" [{filters}]" if filters else ""))
    from app.core.enums import utcnow

    return Response(content="\ufeff" + out.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="audit-trail-{utcnow():%Y%m%d-%H%M}.csv"'})


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
) -> list[RecordHistoryOut]:
    _check_record_access(db, user, record_type, record_id)
    stmt = (
        select(RecordHistory)
        .where(RecordHistory.record_type == record_type, RecordHistory.record_id == record_id)
        .order_by(RecordHistory.timestamp, RecordHistory.id)
    )
    if cycle_no is not None:
        stmt = stmt.where(RecordHistory.cycle_no == cycle_no)
    rows = list(db.execute(stmt).scalars().all())
    names = {u.id: (u.full_name or u.username) for u in db.execute(
        select(User).where(User.id.in_({r.user_id for r in rows if r.user_id} or {0}))).scalars()}
    out = []
    for r in rows:
        item = RecordHistoryOut.model_validate(r)
        item.user = names.get(r.user_id)
        out.append(item)
    return out


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