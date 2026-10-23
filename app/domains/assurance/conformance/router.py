"""Internal audit charter (IIA GIAS 6.2), external quality assessments (GIAS 8.4), the conformance statement
reported to the Audit Committee (GIAS 8.3, 15.1) and the records-retention review list."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.appconfig import cfg
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user, require_perm
from app.core.enums import utcnow
from app.domains.assurance.conformance.models import (
    CHARTER_STATUSES,
    CONCLUSIONS,
    EQA_TYPES,
    ExternalAssessment,
    InternalAuditCharter,
)
from app.platform.users.models import User
from app.services.documents import docx_response, new_document

router = APIRouter(tags=["charter & quality"])
Editor = Depends(require_perm("governance.charter"))
Viewer = Depends(require_perm("governance.charter", "governance.view", "committee.record", "oversight.qaip"))

DEFAULT_CHARTER = """1. Purpose and mandate
The Internal Audit Department provides independent, risk-based and objective assurance, advice, insight and foresight to the Director-General, the Board and the Audit Committee, established under the Internal Audit Agency Act, 2003 (Act 658) section 16 and the Public Financial Management Act, 2016 (Act 921).

2. Standards
Internal audit work conforms with the IIA Global Internal Audit Standards and the standards and procedures issued by the Internal Audit Agency.

3. Authority and access
Internal auditors have full, free and unrestricted access to all records, property and personnel relevant to their work, subject to confidentiality.

4. Independence and organisational position
The GM Audit reports functionally to the Audit Committee and administratively to the Director-General, and confirms the organisational independence of the activity to the Audit Committee at least annually.

5. Roles of the Audit Committee
The Audit Committee approves this charter, the risk-based internal audit plan and significant changes to it, receives internal audit reports and follow-up reports, and pursues implementation of recommendations (Act 921 ss.86-88).

6. Scope of internal audit services
Assurance and advisory services over governance, risk management and control processes across Headquarters and the Ports.

7. Reporting
Audit reports are issued to management and copied as required by Act 658 section 16. Quarterly follow-up reports go to the Audit Committee and the Internal Audit Agency.

8. Quality assurance and improvement programme
The programme includes ongoing monitoring, periodic internal assessments and an external assessment at least once every five years.
"""  # noqa: E501


class CharterIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    content: str = Field(min_length=100, max_length=60000)
    change_summary: str = Field(default="", max_length=5000)


class ApprovalIn(BaseModel):
    approved_at: datetime
    approval_reference: str = Field(min_length=3, max_length=120)


class EqaIn(BaseModel):
    assessment_type: str
    assessor: str = Field(min_length=3, max_length=200)
    assessor_independent: bool = True
    scope: str = Field(default="", max_length=10000)
    completed_at: datetime
    conclusion: str
    report_reference: str = Field(default="", max_length=120)
    action_plan: str = Field(default="", max_length=20000)
    reported_to_committee_at: datetime | None = None


def _charter_out(c: InternalAuditCharter) -> dict:
    return {"id": c.id, "version": c.version, "title": c.title, "content": c.content, "status": c.status,
            "change_summary": c.change_summary, "submitted_at": c.submitted_at, "approved_at": c.approved_at,
            "approval_reference": c.approval_reference, "meeting_id": c.meeting_id,
            "next_review_due": c.next_review_due, "created_by": c.created_by, "updated_at": c.updated_at,
            "review_overdue": bool(c.status == "Approved" and c.next_review_due and c.next_review_due < utcnow())}


def _charter(db: DBSession, charter_id: int) -> InternalAuditCharter:
    c = db.get(InternalAuditCharter, charter_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Charter version not found")
    return c


def current_charter(db: DBSession) -> InternalAuditCharter | None:
    return db.execute(select(InternalAuditCharter).where(InternalAuditCharter.status == "Approved")
                      .order_by(InternalAuditCharter.version.desc())).scalars().first()


@router.get("/api/charter")
def list_charters(db: DBSession = Depends(get_db), _: User = Viewer) -> dict:
    rows = db.execute(select(InternalAuditCharter).order_by(InternalAuditCharter.version.desc())).scalars().all()
    current = current_charter(db)
    return {"statuses": CHARTER_STATUSES, "current": _charter_out(current) if current else None,
            "versions": [_charter_out(c) for c in rows], "template": DEFAULT_CHARTER}


@router.post("/api/charter", status_code=201)
def create_charter(payload: CharterIn, request: Request, db: DBSession = Depends(get_db), user: User = Editor) -> dict:
    if db.execute(select(InternalAuditCharter.id).where(InternalAuditCharter.status.in_(("Draft", "Submitted"))))\
            .first():
        raise HTTPException(status_code=409, detail="A draft charter is already in progress; edit that one")
    version = (db.execute(select(func.max(InternalAuditCharter.version))).scalar() or 0) + 1
    c = InternalAuditCharter(version=version, title=payload.title.strip(), content=payload.content,
                             change_summary=payload.change_summary.strip(), status="Draft", created_by=user.id)
    db.add(c)
    db.flush()
    log_action(db, user_id=user.id, action=f"CHARTER_DRAFT v{version}", request=request)
    db.commit()
    return _charter_out(c)


@router.put("/api/charter/{charter_id}")
def update_charter(charter_id: int, payload: CharterIn, request: Request, db: DBSession = Depends(get_db),
                   user: User = Editor) -> dict:
    c = _charter(db, charter_id)
    if c.status != "Draft":
        raise HTTPException(status_code=409, detail="Only a draft can be edited")
    c.title, c.content, c.change_summary = payload.title.strip(), payload.content, payload.change_summary.strip()
    log_action(db, user_id=user.id, action=f"CHARTER_EDIT v{c.version}", request=request)
    db.commit()
    return _charter_out(c)


@router.post("/api/charter/{charter_id}/submit")
def submit_charter(charter_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Editor) -> dict:
    c = _charter(db, charter_id)
    if c.status != "Draft":
        raise HTTPException(status_code=409, detail="Only a draft can be submitted")
    c.status, c.submitted_at = "Submitted", utcnow()
    log_action(db, user_id=user.id, action=f"CHARTER_SUBMITTED v{c.version}", request=request)
    db.commit()
    return _charter_out(c)


@router.post("/api/charter/{charter_id}/return")
def return_charter(charter_id: int, request: Request, db: DBSession = Depends(get_db),
                   user: User = Depends(require_perm("committee.record"))) -> dict:
    c = _charter(db, charter_id)
    if c.status != "Submitted":
        raise HTTPException(status_code=409, detail="Only a submitted charter can be returned")
    c.status = "Draft"
    log_action(db, user_id=user.id, action=f"CHARTER_RETURNED v{c.version}", request=request)
    db.commit()
    return _charter_out(c)


@router.post("/api/charter/{charter_id}/approve")
def approve_charter(charter_id: int, payload: ApprovalIn, request: Request, db: DBSession = Depends(get_db),
                    user: User = Depends(require_perm("committee.record"))) -> dict:
    """Record the Audit Committee's approval (meeting and minute reference); the previous version is superseded."""
    c = _charter(db, charter_id)
    if c.status != "Submitted":
        raise HTTPException(status_code=409, detail="Only a charter submitted to the Audit Committee can be approved")
    approved = payload.approved_at.replace(tzinfo=None)
    if approved > utcnow() or (c.submitted_at and approved < c.submitted_at - timedelta(days=1)):
        raise HTTPException(status_code=422, detail="The approval date must be after submission and not in the future")
    for old in db.execute(select(InternalAuditCharter).where(InternalAuditCharter.status == "Approved")).scalars():
        old.status = "Superseded"
    c.status, c.approved_at = "Approved", approved
    c.approval_reference, c.approved_recorded_by = payload.approval_reference.strip(), user.id
    months = int(cfg("charter_review_months"))
    c.next_review_due = approved + timedelta(days=round(months * 30.44))
    log_action(db, user_id=user.id, action=f"CHARTER_APPROVED v{c.version} ref={c.approval_reference}",
               request=request)
    db.commit()
    return _charter_out(c)


@router.get("/api/charter/{charter_id}/export.docx")
def charter_docx(charter_id: int, request: Request, db: DBSession = Depends(get_db),
                 user: User = Depends(require_active_user)):  # noqa: ANN201
    c = _charter(db, charter_id)
    log_action(db, user_id=user.id, request=request, commit=True, action=f"CHARTER_EXPORT id={c.id} v{c.version}")
    doc = new_document()
    doc.add_heading(c.title, level=1)
    doc.add_paragraph(f"Version {c.version} · {c.status}" + (
        f" · approved by the Audit Committee on {c.approved_at:%d %B %Y} ({c.approval_reference})"
        if c.approved_at else ""))
    for block in c.content.split("\n\n"):
        lines = block.strip().split("\n", 1)
        if len(lines) == 2 and len(lines[0]) < 90 and lines[0][:1].isdigit():
            doc.add_heading(lines[0], level=2)
            doc.add_paragraph(lines[1])
        elif block.strip():
            doc.add_paragraph(block.strip())
    if c.next_review_due:
        doc.add_paragraph(f"Next review due: {c.next_review_due:%d %B %Y}")
    return docx_response(doc, f"internal-audit-charter-v{c.version}.docx")


# ---------------------------------------------------------------- external quality assessment

def _eqa_out(e: ExternalAssessment) -> dict:
    return {"id": e.id, "assessment_type": e.assessment_type, "assessor": e.assessor,
            "assessor_independent": e.assessor_independent, "scope": e.scope, "completed_at": e.completed_at,
            "conclusion": e.conclusion, "report_reference": e.report_reference, "action_plan": e.action_plan,
            "reported_to_committee_at": e.reported_to_committee_at, "next_due": e.next_due}


def eqa_status(db: DBSession) -> dict:
    latest = db.execute(select(ExternalAssessment).order_by(ExternalAssessment.completed_at.desc())).scalars().first()
    if latest is None:
        return {"latest": None, "next_due": None, "overdue": True,
                "message": "No external quality assessment recorded (IIA GIAS 8.4: at least once every five years)."}
    return {"latest": _eqa_out(latest), "next_due": latest.next_due, "overdue": latest.next_due < utcnow(),
            "message": f"Last assessment {latest.completed_at:%B %Y}: {latest.conclusion}. "
                       f"Next due by {latest.next_due:%B %Y}."}


@router.get("/api/quality/external-assessments")
def list_eqa(db: DBSession = Depends(get_db), _: User = Viewer) -> dict:
    rows = db.execute(select(ExternalAssessment).order_by(ExternalAssessment.completed_at.desc())).scalars()
    return {"types": EQA_TYPES, "conclusions": CONCLUSIONS, "status": eqa_status(db),
            "items": [_eqa_out(e) for e in rows]}


@router.post("/api/quality/external-assessments", status_code=201)
def record_eqa(payload: EqaIn, request: Request, db: DBSession = Depends(get_db), user: User = Editor) -> dict:
    if payload.assessment_type not in EQA_TYPES:
        raise HTTPException(status_code=422, detail=f"Type must be one of: {', '.join(EQA_TYPES)}")
    if payload.conclusion not in CONCLUSIONS:
        raise HTTPException(status_code=422, detail=f"Conclusion must be one of: {', '.join(CONCLUSIONS)}")
    completed = payload.completed_at.replace(tzinfo=None)
    if completed > utcnow():
        raise HTTPException(status_code=422, detail="The completion date cannot be in the future")
    if not payload.assessor_independent:
        raise HTTPException(status_code=422, detail="IIA GIAS 8.4 requires a qualified, independent assessor or "
                                                    "assessment team")
    years = int(cfg("eqa_interval_years"))
    e = ExternalAssessment(assessment_type=payload.assessment_type, assessor=payload.assessor.strip(),
                           assessor_independent=True, scope=payload.scope, completed_at=completed,
                           conclusion=payload.conclusion, report_reference=payload.report_reference.strip() or None,
                           action_plan=payload.action_plan,
                           reported_to_committee_at=payload.reported_to_committee_at.replace(tzinfo=None)
                           if payload.reported_to_committee_at else None,
                           next_due=completed.replace(year=completed.year + years) if not
                           (completed.month == 2 and completed.day == 29) else completed.replace(
                               year=completed.year + years, day=28),
                           recorded_by=user.id)
    db.add(e)
    db.flush()
    log_action(db, user_id=user.id, action=f"EQA_RECORDED {e.conclusion} by {e.assessor}", request=request)
    db.commit()
    return _eqa_out(e)


# ---------------------------------------------------------------- conformance statement (Committee pack)

def conformance_summary(db: DBSession) -> dict:
    from app.domains.assurance.qaip.router import latest_internal_assessment

    charter = current_charter(db)
    return {
        "statement": cfg("conformance_statement"),
        "charter": (f"Version {charter.version}, approved {charter.approved_at:%d %b %Y}"
                    + (" - review overdue" if charter.next_review_due and charter.next_review_due < utcnow() else
                       f", next review {charter.next_review_due:%b %Y}" if charter.next_review_due else ""))
        if charter else "No approved charter recorded",
        "internal_assessment": latest_internal_assessment(db),
        "external_assessment": eqa_status(db)["message"],
    }


@router.get("/api/quality/conformance")
def conformance(db: DBSession = Depends(get_db), _: User = Viewer) -> dict:
    return conformance_summary(db)


# ---------------------------------------------------------------- records retention review

@router.get("/api/records/retention")
def retention(db: DBSession = Depends(get_db), _: User = Depends(require_perm("system.technical",
                                                                               "governance.charter"))) -> dict:
    """Closed audits older than the retention period, listed for a disposal review. Nothing is deleted."""
    from app.core.enums import AuditStatus
    from app.domains.audit.audits.models import Audit

    years = int(cfg("retention_years"))
    cutoff = utcnow() - timedelta(days=round(years * 365.25))
    rows = db.execute(select(Audit).where(Audit.status == AuditStatus.Closed, Audit.updated_at < cutoff)
                      .order_by(Audit.updated_at)).scalars()
    return {"retention_years": years, "cutoff": cutoff,
            "items": [{"id": a.id, "title": a.title, "closed": a.updated_at} for a in rows]}
