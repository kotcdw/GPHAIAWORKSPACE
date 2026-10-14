"""Planning memo per engagement: draft -> submitted -> approved (e-signed) or returned.

Fieldwork (Planned -> In Progress) can be gated on an approved memo through the
``require_memo_approval_for_fieldwork`` rule on the Configuration screen.
"""

from __future__ import annotations

import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.access import ensure_can_view
from app.core.appconfig import cfg
from app.core.approvalsvc import sign
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user, require_module_tier
from app.core.enums import AuditStatus, ReviewLevel, Role, utcnow
from app.core.history import log_record_history
from app.core.permissions import has_perm
from app.core.schemas import ESignRequest
from app.modules.audits.models import Audit
from app.modules.memos.models import PlanningMemo
from app.modules.notifications.service import notify, notify_many, user_ids_with_level
from app.modules.users.models import User

router = APIRouter(tags=["planning memo"])
Staff = Depends(require_module_tier("planning memo", Role.Admin, Role.Auditor))

_TEXT_FIELDS = ("background", "objectives", "scope", "key_risks", "approach", "team")


class MemoIn(BaseModel):
    background: str = Field("", max_length=20000)
    objectives: str = Field("", max_length=20000)
    scope: str = Field("", max_length=20000)
    key_risks: str = Field("", max_length=20000)
    approach: str = Field("", max_length=20000)
    team: str = Field("", max_length=5000)
    start_date: datetime | None = None
    end_date: datetime | None = None
    budget_hours: int = Field(0, ge=0, le=20000)

    @model_validator(mode="after")
    def _dates(self) -> MemoIn:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("End date must be on or after the start date")
        return self


class MemoOut(MemoIn):
    id: int | None = None
    audit_id: int
    status: str = "Draft"
    review_comment: str = ""
    prepared_by: int | None = None
    prepared_by_name: str | None = None
    submitted_at: datetime | None = None
    approved_by: int | None = None
    approved_by_name: str | None = None
    approved_at: datetime | None = None
    can_edit: bool = False
    can_approve: bool = False
    missing: list[str] = []


def _name(db: DBSession, uid: int | None) -> str | None:
    u = db.get(User, uid) if uid else None
    return (u.full_name or u.username) if u else None


def _audit(db: DBSession, audit_id: int, user: User) -> Audit:
    audit = db.get(Audit, audit_id)
    ensure_can_view(db, user, "audit", audit)
    return audit


def _memo(db: DBSession, audit_id: int) -> PlanningMemo | None:
    return db.execute(select(PlanningMemo).where(PlanningMemo.audit_id == audit_id)).scalar_one_or_none()


def missing_sections(memo: PlanningMemo) -> list[str]:
    need = {
        "objectives": "Objectives",
        "scope": "Scope",
        "key_risks": "Key risks",
        "approach": "Approach",
        "team": "Team",
    }
    out = [label for key, label in need.items() if not (getattr(memo, key) or "").strip()]
    if not memo.start_date or not memo.end_date:
        out.append("Timeline")
    if not memo.budget_hours:
        out.append("Budget hours")
    return out


def memo_approved(db: DBSession, audit_id: int) -> bool:
    memo = _memo(db, audit_id)
    return memo is not None and memo.status == "Approved"


def _out(db: DBSession, audit: Audit, memo: PlanningMemo | None, user: User) -> MemoOut:
    staff = user.role in (Role.Admin, Role.Auditor)
    if memo is None:
        from app.modules.planning.models import PlanEngagement

        eng = db.execute(select(PlanEngagement).where(PlanEngagement.audit_id == audit.id)).scalars().first()
        return MemoOut(
            audit_id=audit.id,
            scope=audit.scope or "",
            background=audit.description or "",
            budget_hours=eng.budget_hours if eng else 0,
            can_edit=staff and audit.status != AuditStatus.Closed,
            missing=["Objectives", "Key risks", "Approach", "Team", "Timeline", "Budget hours"],
        )
    data = {k: getattr(memo, k) for k in (*_TEXT_FIELDS, "start_date", "end_date", "budget_hours")}
    return MemoOut(
        id=memo.id,
        audit_id=audit.id,
        status=memo.status,
        review_comment=memo.review_comment,
        **data,
        prepared_by=memo.prepared_by,
        prepared_by_name=_name(db, memo.prepared_by),
        submitted_at=memo.submitted_at,
        approved_by=memo.approved_by,
        approved_by_name=_name(db, memo.approved_by),
        approved_at=memo.approved_at,
        can_edit=staff and memo.status in ("Draft", "Returned") and audit.status != AuditStatus.Closed,
        can_approve=staff
        and memo.status == "Submitted"
        and has_perm(user, "audit.memo_approve")
        and memo.prepared_by != user.id,
        missing=missing_sections(memo),
    )


@router.get("/api/audits/{audit_id}/planning-memo", response_model=MemoOut)
def get_memo(audit_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> MemoOut:
    audit = _audit(db, audit_id, user)
    return _out(db, audit, _memo(db, audit_id), user)


@router.put("/api/audits/{audit_id}/planning-memo", response_model=MemoOut)
def save_memo(
    audit_id: int, payload: MemoIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> MemoOut:
    from app.core.deps import ensure_perm

    ensure_perm(user, "audit.plan")
    audit = _audit(db, audit_id, user)
    if audit.status == AuditStatus.Closed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The audit is closed")
    memo = _memo(db, audit_id)
    if memo is None:
        memo = PlanningMemo(audit_id=audit_id, prepared_by=user.id, review_comment="")
        db.add(memo)
    elif memo.status not in ("Draft", "Returned"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"The memo is {memo.status.lower()} and can no longer be edited",
        )
    for key, value in payload.model_dump().items():
        setattr(memo, key, value)
    db.flush()
    log_action(db, user_id=user.id, action=f"MEMO_SAVE audit={audit_id}", request=request)
    db.commit()
    db.refresh(memo)
    return _out(db, audit, memo, user)


@router.post("/api/audits/{audit_id}/planning-memo/submit", response_model=MemoOut)
def submit_memo(audit_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> MemoOut:
    audit = _audit(db, audit_id, user)
    memo = _memo(db, audit_id)
    if memo is None or memo.status not in ("Draft", "Returned"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Save the memo as a draft first")
    gaps = missing_sections(memo)
    if gaps:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"Complete these sections before submitting: {', '.join(gaps)}"
        )
    memo.status = "Submitted"
    memo.submitted_at = utcnow()
    memo.prepared_by = memo.prepared_by or user.id
    notify_many(
        db,
        [u for u in user_ids_with_level(db, ReviewLevel.Manager, ReviewLevel.CAE) if u != user.id],
        f"Planning memo awaiting approval: {audit.title}",
        "Review and approve the engagement plan.",
        link_type="audit",
        link_id=audit.id,
    )
    log_record_history(
        db, record_type="audit", record_id=audit.id, user_id=user.id, action="PLANNING MEMO SUBMITTED", request=request
    )
    db.commit()
    return _out(db, audit, memo, user)


@router.post("/api/audits/{audit_id}/planning-memo/approve", response_model=MemoOut)
def approve_memo(
    audit_id: int, payload: ESignRequest, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> MemoOut:
    audit = _audit(db, audit_id, user)
    memo = _memo(db, audit_id)
    if memo is None or memo.status != "Submitted":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The memo is not awaiting approval")

    if not has_perm(user, "audit.memo_approve"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Only an Audit Manager, PIA or the GM Audit can approve a planning memo")
    decision = payload.decision.value

    def _approve(_: DBSession) -> None:
        memo.status = "Approved"
        memo.approved_by = user.id
        memo.approved_at = utcnow()
        memo.review_comment = payload.comment or ""

    sign(
        db,
        record_type="planning_memo",
        record_id=memo.id,
        user=user,
        password=payload.password,
        decision=decision,
        comment=payload.comment,
        request=request,
        on_approve=_approve,
        preparer_id=memo.prepared_by,
    )
    if decision == "Approve":
        notify(
            db,
            memo.prepared_by,
            f"Planning memo approved: {audit.title}",
            "Fieldwork can start.",
            link_type="audit",
            link_id=audit.id,
        )
    else:
        memo.status = "Returned"
        memo.review_comment = payload.comment or ""
        notify(
            db,
            memo.prepared_by,
            f"Planning memo returned: {audit.title}",
            payload.comment or "The reviewer returned the memo for changes.",
            link_type="audit",
            link_id=audit.id,
        )
    log_record_history(
        db,
        record_type="audit",
        record_id=audit.id,
        user_id=user.id,
        action=f"PLANNING MEMO {'APPROVED' if decision == 'Approve' else 'RETURNED'}",
        request=request,
    )
    db.commit()
    return _out(db, audit, memo, user)


def ensure_fieldwork_can_start(db: DBSession, audit: Audit) -> None:
    if cfg("require_memo_approval_for_fieldwork") and not memo_approved(db, audit.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Fieldwork cannot start until the planning memo is approved by an Audit Manager or the CAE",
        )


@router.get("/api/audits/{audit_id}/planning-memo.docx")
def memo_docx(audit_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> Response:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    audit = _audit(db, audit_id, user)
    memo = _memo(db, audit_id)
    if memo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No planning memo yet")
    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)
    head = doc.add_paragraph()
    head.alignment = WD_ALIGN_PARAGRAPH.CENTER
    head.add_run(f"{cfg('org_name').upper()}\n{cfg('department_name').upper()}").bold = True
    doc.add_heading(f"PLANNING MEMORANDUM: {audit.title.upper()}", level=1)
    doc.add_paragraph(f"Ref: AUD-{audit.id:04d}/PM    Status: {memo.status}")
    sections = [
        ("1. Background", memo.background),
        ("2. Objectives", memo.objectives),
        ("3. Scope", memo.scope),
        ("4. Key risks", memo.key_risks),
        ("5. Approach and work programme", memo.approach),
        ("6. Engagement team", memo.team),
    ]
    for title, body in sections:
        doc.add_heading(title, level=2)
        doc.add_paragraph(body or "-")
    doc.add_heading("7. Timeline and budget", level=2)
    def fmt(d: datetime | None) -> str:
        return f"{d:%d %B %Y}" if d else "-"

    doc.add_paragraph(f"Fieldwork: {fmt(memo.start_date)} to {fmt(memo.end_date)}\nBudget: {memo.budget_hours} hours")
    doc.add_heading("Approval", level=2)
    doc.add_paragraph(
        f"Prepared by: {_name(db, memo.prepared_by) or '-'}\n"
        f"Approved by: {_name(db, memo.approved_by) or '-'}"
        + (f" on {memo.approved_at:%d %B %Y}" if memo.approved_at else "")
    )
    buf = io.BytesIO()
    doc.save(buf)
    log_action(db, user_id=user.id, action=f"MEMO_EXPORT audit={audit.id}", request=request)
    db.commit()
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="AUD-{audit.id:04d}-planning-memo.docx"'},
    )
