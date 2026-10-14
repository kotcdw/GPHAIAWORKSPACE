"""Audit lifecycle rules: closure readiness, engagement notification and letter, action SLAs."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.access import ensure_can_view
from app.core.appconfig import cfg
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user
from app.core.enums import AuditStatus, FindingStatus, ReportStatus, RiskRating, Severity, TestStatus, utcnow
from app.domains.audit.audits.models import Audit, AuditAuditee, Finding
from app.domains.issues.capa.models import Capa
from app.platform.users.models import User
from app.services.documents import docx_response, new_document

router = APIRouter(tags=["audit lifecycle"])


# ------------------------------------------------------------------ action SLA


def default_due_date(severity: Severity | str | None, now: datetime | None = None) -> datetime:
    """Due date for a new action from the configured SLA for its severity."""
    level = (severity.value if hasattr(severity, "value") else str(severity or "Medium")).lower()
    days = cfg({"high": "capa_due_days_high", "low": "capa_due_days_low"}.get(level, "capa_due_days_medium"))
    return (now or utcnow()).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=int(days))


# ------------------------------------------------------------------ closure readiness


class Check(BaseModel):
    key: str
    label: str
    ok: bool
    required: bool
    detail: str = ""


class ClosureCheck(BaseModel):
    ready: bool
    checks: list[Check]


def closure_checks(db: DBSession, audit: Audit) -> list[Check]:
    from app.domains.audit.rcm.models import Control, ControlTest, Objective
    from app.domains.audit.reports.models import AuditReport

    checks: list[Check] = []
    checks.append(Check(key="status", label="Audit is in Review", ok=audit.status == AuditStatus.Review, required=True,
                        detail="" if audit.status == AuditStatus.Review else f"Currently {audit.status.value}"))

    pending = db.execute(
        select(ControlTest.ref).join(Control, Control.id == ControlTest.control_id)
        .join(Objective, Objective.id == Control.objective_id)
        .where(Objective.audit_id == audit.id, ControlTest.status.in_([TestStatus.InProgress, TestStatus.Completed]))
    ).scalars().all()
    checks.append(Check(key="tests", label="All control tests reviewed", ok=not pending, required=True,
                        detail=f"Awaiting review: {', '.join(pending)}" if pending else ""))

    report = db.execute(select(AuditReport).where(AuditReport.audit_id == audit.id)).scalar_one_or_none()
    issued = report is not None and report.status == ReportStatus.Issued
    checks.append(Check(
        key="report", label="Audit report issued", ok=issued, required=bool(cfg("require_report_to_close")),
        detail="" if issued else ("No report yet" if report is None else f"Report is in {report.status.value}")))

    findings = db.execute(select(Finding).where(Finding.audit_id == audit.id)).scalars().all()
    no_response = [f"#{f.id}" for f in findings if not (f.management_response or "").strip()]
    no_action = []
    for f in findings:
        if f.risk_rating in (RiskRating.High, RiskRating.Medium) and f.status != FindingStatus.Closed:
            has_action = db.execute(
                select(Capa.id).where(Capa.source_type == "finding", Capa.source_id == f.id)
            ).first()
            if not has_action:
                no_action.append(f"#{f.id}")
    need = bool(cfg("require_findings_actioned_to_close"))
    checks.append(Check(key="responses", label="Every finding has a management response", ok=not no_response,
                        required=need, detail=f"Missing on {', '.join(no_response)}" if no_response else ""))
    checks.append(Check(key="actions", label="Every open High/Medium finding has an agreed action", ok=not no_action,
                        required=need, detail=f"No action for {', '.join(no_action)}" if no_action else ""))
    from app.domains.audit.methodology.router import open_notes

    pending_notes = open_notes(db, audit.id)
    checks.append(Check(key="review_notes", label="All review notes cleared", ok=not pending_notes, required=True,
                        detail=f"{pending_notes} open review note(s)" if pending_notes else ""))
    return checks


def ensure_closable(db: DBSession, audit: Audit) -> None:
    failed = [c for c in closure_checks(db, audit) if c.required and not c.ok and c.key != "status"]
    if failed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The audit cannot be closed yet: " + "; ".join(
                f"{c.label.lower()} ({c.detail})" if c.detail else c.label.lower() for c in failed),
        )


@router.get("/api/audits/{audit_id}/closure-check", response_model=ClosureCheck)
def get_closure_check(audit_id: int, db: DBSession = Depends(get_db),
                      user: User = Depends(require_active_user)) -> ClosureCheck:
    audit = db.get(Audit, audit_id)
    ensure_can_view(db, user, "audit", audit)
    checks = closure_checks(db, audit)
    return ClosureCheck(ready=all(c.ok for c in checks if c.required), checks=checks)


# ------------------------------------------------------------------ engagement notification


def auditee_ids(db: DBSession, audit_id: int) -> list[int]:
    return list(db.execute(select(AuditAuditee.user_id).where(AuditAuditee.audit_id == audit_id)).scalars())


def notify_fieldwork_started(db: DBSession, audit: Audit, actor: User) -> int:
    if not cfg("notify_auditees_on_fieldwork"):
        return 0
    from app.platform.notifications.service import notify_many, user_id_by_email

    recipients: list[int | None] = list(auditee_ids(db, audit.id))
    if audit.entity_unit_id is not None:
        from app.domains.assurance.planning.models import EntityUnit

        unit = db.get(EntityUnit, audit.entity_unit_id)
        if unit is not None:
            recipients.append(user_id_by_email(db, getattr(unit, "owner_email", None)))
    recipients = [r for r in recipients if r != actor.id]
    return notify_many(
        db, recipients, f"Audit fieldwork has started: {audit.title}",
        f"The Internal Audit team has started fieldwork.\nScope: {audit.scope or 'see engagement letter'}\n"
        "Please make the requested documents and staff available.",
        link_type="audit", link_id=audit.id,
    )


@router.get("/api/audits/{audit_id}/engagement-letter.docx")
def engagement_letter(audit_id: int, request: Request, db: DBSession = Depends(get_db),
                      user: User = Depends(require_active_user)) -> Response:
    """Engagement (notification) letter to the auditee: objectives, scope, team, timeline."""

    audit = db.get(Audit, audit_id)
    ensure_can_view(db, user, "audit", audit)
    from app.domains.audit.rcm.models import Objective

    objectives = db.execute(
        select(Objective).where(Objective.audit_id == audit.id).order_by(Objective.id)
    ).scalars().all()
    auditees = [db.get(User, uid) for uid in auditee_ids(db, audit.id)]
    preparer = db.get(User, audit.created_by) if audit.created_by else None

    doc = new_document()
    doc.add_paragraph(f"Ref: AUD-{audit.id:04d}/EL\nDate: {utcnow():%d %B %Y}")
    to = ", ".join(u.full_name or u.username for u in auditees if u) or "The Head of Department"
    doc.add_paragraph(f"To: {to}")
    doc.add_heading(f"ENGAGEMENT LETTER: {audit.title.upper()}", level=1)
    doc.add_paragraph(
        "In line with the approved Internal Audit Plan, the Internal Audit Department will carry out the engagement "
        "described below. This letter sets out its objectives, scope and arrangements."
    )
    doc.add_heading("1. Objectives", level=2)
    if objectives:
        for o in objectives:
            doc.add_paragraph(o.title, style="List Bullet")
    else:
        doc.add_paragraph("To assess whether controls over the area are adequately designed and operating effectively.")
    doc.add_heading("2. Scope", level=2)
    doc.add_paragraph(audit.scope or "As agreed at the entry meeting.")
    doc.add_heading("3. Approach", level=2)
    doc.add_paragraph(cfg("report_methodology"))
    doc.add_heading("4. Information and access required", level=2)
    for item in ("Relevant policies, procedures and process documentation",
                 "Access to systems, records and transaction data for the period under review",
                 "Availability of key staff for walkthroughs and interviews"):
        doc.add_paragraph(item, style="List Bullet")
    doc.add_heading("5. Reporting", level=2)
    doc.add_paragraph(
        "Findings will be discussed with management as they arise. A draft report will be shared for management "
        "comments before the final report is approved by the Chief Audit Executive and issued."
    )
    doc.add_paragraph("\nYours faithfully,\n\n\n" + (preparer.full_name or preparer.username if preparer else "")
                      + "\nFor: Chief Audit Executive")
    log_action(db, user_id=user.id, action=f"ENGAGEMENT_LETTER audit={audit.id}", request=request)
    db.commit()
    return docx_response(doc, f"AUD-{audit.id:04d}-engagement-letter.docx")
