"""Distribution of issued audit reports and the register of audit reports.

The Internal Audit Agency Act, 2003 (Act 658) s.16(3)-(5) requires copies of internal audit reports to go to the
entity's management and to the Agency (or, for some bodies, the Auditor-General). The required recipients are an
admin setting (``report_statutory_recipients``); each copy actually sent is recorded here with its date, reference
and the version sent, and the register shows which reports are still missing a copy. When a corrected version is
issued, everyone who received an earlier version is due the corrected one (IIA GIAS 11.4).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.appconfig import cfg
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user, require_module_tier
from app.core.enums import ReportStatus, Role, utcnow
from app.core.history import log_record_history
from app.domains.audit.audits.models import Audit
from app.domains.audit.reports.models import AuditReport, ReportDistribution
from app.platform.users.models import User
from app.services.documents import workbook, xlsx_response

router = APIRouter(tags=["reports"])
Staff = Depends(require_module_tier("reports", Role.Admin, Role.Auditor))
CHANNELS = ("Letter", "E-mail", "Hand delivery", "Portal / system", "Meeting")


class DistributionIn(BaseModel):
    recipient: str = Field(min_length=2, max_length=160)
    channel: str = "Letter"
    sent_at: datetime
    reference: str = Field(default="", max_length=120)


def _issued(db: DBSession, report_id: int) -> AuditReport:
    report = db.get(AuditReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


def distributions(db: DBSession, report_id: int) -> list[ReportDistribution]:
    return list(db.execute(select(ReportDistribution).where(ReportDistribution.report_id == report_id)
                           .order_by(ReportDistribution.sent_at)).scalars())


def _sent_current(db: DBSession, report: AuditReport) -> set[str]:
    return {d.recipient.strip().lower() for d in distributions(db, report.id) if d.version == report.version}


def previous_recipients(db: DBSession, report: AuditReport) -> list[str]:
    """Who received an earlier version and has not yet been sent the current one."""
    sent = _sent_current(db, report)
    out: dict[str, str] = {}
    for d in distributions(db, report.id):
        if d.version < report.version and d.recipient.strip().lower() not in sent:
            out.setdefault(d.recipient.strip().lower(), d.recipient)
    return list(out.values())


def missing_recipients(db: DBSession, report: AuditReport) -> list[str]:
    sent = _sent_current(db, report)
    required = [r for r in (cfg("report_statutory_recipients") or []) if r.strip().lower() not in sent]
    known = {r.strip().lower() for r in required}
    return required + [r for r in previous_recipients(db, report) if r.strip().lower() not in known]


def _row(d: ReportDistribution) -> dict:
    return {"id": d.id, "recipient": d.recipient, "channel": d.channel, "sent_at": d.sent_at,
            "reference": d.reference, "recorded_by": d.recorded_by, "version": d.version}


@router.get("/api/reports/{report_id}/distribution")
def get_distribution(report_id: int, db: DBSession = Depends(get_db),
                     _: User = Depends(require_active_user)) -> dict:
    report = _issued(db, report_id)
    return {"required": cfg("report_statutory_recipients"), "channels": CHANNELS, "version": report.version,
            "sent": [_row(d) for d in distributions(db, report.id)],
            "missing": missing_recipients(db, report) if report.status == ReportStatus.Issued else []}


@router.post("/api/reports/{report_id}/distribution", status_code=201)
def add_distribution(report_id: int, payload: DistributionIn, request: Request, db: DBSession = Depends(get_db),
                     user: User = Staff) -> dict:
    report = _issued(db, report_id)
    payload.sent_at = payload.sent_at.replace(tzinfo=None)
    if report.status != ReportStatus.Issued:
        raise HTTPException(status_code=409, detail="Copies can only be recorded for an issued report")
    if payload.channel not in CHANNELS:
        raise HTTPException(status_code=422, detail=f"Channel must be one of: {', '.join(CHANNELS)}")
    if report.issued_at and payload.sent_at < report.issued_at.replace(hour=0, minute=0, second=0):
        raise HTTPException(status_code=422, detail="A copy cannot be sent before the report was issued")
    if payload.sent_at > utcnow():
        raise HTTPException(status_code=422, detail="The date sent cannot be in the future")
    d = ReportDistribution(report_id=report.id, recipient=payload.recipient.strip(), channel=payload.channel,
                           sent_at=payload.sent_at, reference=payload.reference.strip() or None, recorded_by=user.id,
                           version=report.version)
    db.add(d)
    log_record_history(db, record_type="audit_report", record_id=report.id, user_id=user.id,
                       action=f"DISTRIBUTED version {d.version} to {d.recipient} ({d.channel})", request=request)
    log_action(db, user_id=user.id, action=f"REPORT_DISTRIBUTED id={report.id} to={d.recipient}", request=request)
    db.commit()
    return get_distribution(report.id, db, user)


def register_rows(db: DBSession, year: int | None) -> list[dict]:
    q = select(AuditReport, Audit).join(Audit, Audit.id == AuditReport.audit_id).order_by(AuditReport.report_ref)
    out = []
    for report, audit in db.execute(q).all():
        ref_date = report.issued_at or report.created_at
        if year and ref_date.year != year:
            continue
        sent = distributions(db, report.id)
        out.append({
            "id": report.id, "report_ref": report.report_ref, "title": report.title, "audit_id": audit.id,
            "audit_title": audit.title, "status": report.status.value,
            "overall_rating": getattr(report.overall_rating, "value", None),
            "draft_sent_at": report.draft_sent_at, "response_due_at": report.response_due_at,
            "response_received_at": report.response_received_at, "issued_at": report.issued_at,
            "version": report.version,
            "distributed_to": [f"{d.recipient} ({d.sent_at:%d %b %Y}{f', v{d.version}' if report.version > 1 else ''})"
                               for d in sent],
            "missing": missing_recipients(db, report) if report.status == ReportStatus.Issued else [],
        })
    return out


def _scoped(db: DBSession, user: User, rows: list[dict]) -> list[dict]:
    """Only reports of audits in the caller's port/team scope."""
    from app.core.access import staff_audit_scope

    allowed = staff_audit_scope(db, user)
    return rows if allowed is None else [r for r in rows if r["audit_id"] in allowed]


@router.get("/api/reports/register")
def report_register(year: int | None = Query(default=None), db: DBSession = Depends(get_db),
                    user: User = Staff) -> list[dict]:
    return _scoped(db, user, register_rows(db, year))


@router.get("/api/reports/register.xlsx")
def report_register_xlsx(request: Request, year: int | None = Query(default=None), db: DBSession = Depends(get_db),
                         user: User = Staff):  # noqa: ANN201
    from app.core.deps import ensure_perm

    ensure_perm(user, "data.export")
    rows = _scoped(db, user, register_rows(db, year))
    log_action(db, user_id=user.id, request=request, commit=True,
               action=f"REPORT_REGISTER_EXPORT year={year or 'all'} rows={len(rows)}")
    headers = ["Ref", "Title", "Audit", "Status", "Rating", "Draft to management", "Response due",
               "Response received", "Issued", "Copies sent", "Copies outstanding"]
    data = [[r["report_ref"], r["title"], r["audit_title"], r["status"], r["overall_rating"], r["draft_sent_at"],
             r["response_due_at"], r["response_received_at"], r["issued_at"], "; ".join(r["distributed_to"]),
             "; ".join(r["missing"])] for r in rows]
    title = f"Register of audit reports{f' - {year}' if year else ''}"
    return xlsx_response(workbook([("Reports", headers, data)], title=title),
                         f"report-register{f'-{year}' if year else ''}.xlsx")
