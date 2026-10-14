"""GIAS completion features.

* Audit Committee approval of the Assurance Plan and a documented log of plan changes (GIAS 9.4).
* Criteria library used when writing findings (GIAS 13.4 / 14.3).
* Supervisory review notes on engagement work, working-paper cross-references and reviewer
  sign-off (GIAS 12.3, 14.6).
* Exit meeting record on the audit report (GIAS 15.1).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DBSession

from app.core import review_chain
from app.core.access import ensure_can_view
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user, require_module_tier, require_perm
from app.core.enums import AuditStatus, EngagementStatus, PlanStatus, ReportStatus, ReviewLevel, Role, utcnow
from app.core.errors import field_error
from app.core.history import log_record_history
from app.core.permissions import has_perm, job_role_of
from app.core.refs import next_reference
from app.domains.assurance.planning.models import AssurancePlan, PlanChange, PlanEngagement
from app.domains.audit.audits.models import Audit, Finding, WorkingPaper
from app.domains.audit.methodology.models import CRITERIA_SOURCES, Criterion, ReviewNote
from app.platform.notifications.service import notify
from app.platform.users.models import User

router = APIRouter(tags=["methodology"])
Staff = Depends(require_module_tier("audit work", Role.Admin, Role.Auditor))
AdminOnly = Depends(require_perm("plan.amend"))


def _name(db: DBSession, uid: int | None) -> str | None:
    u = db.get(User, uid) if uid else None
    return (u.full_name or u.username) if u else None


def _reason(text: str) -> str:
    text = (text or "").strip()
    if len(text) < 10:
        raise field_error("reason", "explain the change (at least 10 characters)")
    return text


# ==================================================================== plan: committee approval + changes


class CommitteeIn(BaseModel):
    meeting_date: datetime
    reference: str = Field(..., min_length=1, max_length=100)
    notes: str = Field("", max_length=5000)


class ChangeOut(BaseModel):
    id: int
    change_type: str
    engagement_id: int | None
    description: str
    reason: str
    changed_by: str | None
    changed_at: datetime


def _plan(db: DBSession, plan_id: int) -> AssurancePlan:
    plan = db.get(AssurancePlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assurance Plan not found")
    return plan


def _log_change(
    db: DBSession,
    plan: AssurancePlan,
    user: User,
    kind: str,
    description: str,
    reason: str,
    request: Request,
    engagement_id: int | None = None,
) -> None:
    db.add(
        PlanChange(
            plan_id=plan.id,
            engagement_id=engagement_id,
            change_type=kind,
            description=description,
            reason=reason,
            changed_by=user.id,
        )
    )
    log_record_history(
        db,
        record_type="assurance_plan",
        record_id=plan.id,
        user_id=user.id,
        action=f"PLAN {kind.upper()}: {description}"[:490],
        request=request,
    )


@router.post("/api/assurance-plans/{plan_id}/committee-approval")
def record_committee_approval(
    plan_id: int, payload: CommitteeIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> dict:
    """Record that the Audit Committee approved the (CAE-approved) plan at a meeting."""
    from app.core.deps import ensure_perm

    ensure_perm(user, "plan.amend")
    plan = _plan(db, plan_id)
    if plan.status != PlanStatus.Approved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The CAE approves the plan first; then record the Audit Committee's approval",
        )
    if payload.meeting_date.replace(tzinfo=None) > utcnow():
        raise field_error("meeting_date", "cannot be in the future")
    if plan.approved_at and payload.meeting_date.replace(tzinfo=None).date() < plan.approved_at.date():
        raise field_error("meeting_date", "is before the CAE approved the plan")
    if plan.cycle_stage in (
        "preparation",
        "universe_review",
        "managers_meeting",
        "drafting",
        "internal_review",
        "submission",
        "committee",
    ):
        # First Committee approval of this CAE-approved draft: freeze a numbered version (planning cycle).
        from app.domains.assurance.plancycle.router import record_committee_decision

        record_committee_decision(
            db,
            plan,
            user,
            "Approved",
            payload.meeting_date.replace(tzinfo=None),
            payload.reference.strip(),
            payload.notes.strip(),
            request,
        )
    else:
        plan.committee_meeting_date = payload.meeting_date.replace(tzinfo=None)
        plan.committee_reference = payload.reference.strip()
        plan.committee_notes = payload.notes.strip()
        plan.committee_recorded_by = user.id
        plan.committee_recorded_at = utcnow()
    _log_change(
        db,
        plan,
        user,
        "Committee",
        f"Approved by the Audit Committee on {plan.committee_meeting_date:%d %b %Y} (ref {plan.committee_reference})",
        payload.notes.strip(),
        request,
    )
    log_action(db, user_id=user.id, action=f"PLAN_COMMITTEE_APPROVAL id={plan.id}", request=request)
    db.commit()
    return {"message": "Audit Committee approval recorded", "committee_reference": plan.committee_reference}


class AmendAddIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    entity_unit_id: int | None = None
    rationale: str = Field("", max_length=5000)
    planned_quarter: str = Field("Q1", pattern=r"^Q[1-4]$")
    budget_hours: int = Field(0, ge=0, le=10000)
    lead_auditor_id: int | None = None
    reason: str = Field(..., max_length=2000)


@router.post("/api/assurance-plans/{plan_id}/amendments", status_code=status.HTTP_201_CREATED)
def amend_add(
    plan_id: int, payload: AmendAddIn, request: Request, db: DBSession = Depends(get_db), user: User = AdminOnly
) -> dict:
    """Superseded by plan change requests (app.domains.assurance.plancycle.changes); answers old clients clearly."""
    plan = _plan(db, plan_id)
    if plan.status != PlanStatus.Approved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Use the normal Add engagement while the plan is a draft"
        )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Approved plans are changed through a plan change request (reason, impact, review and approval)",
    )
    reason = _reason(payload.reason)
    data = payload.model_dump(exclude={"reason"})
    eng = PlanEngagement(plan_id=plan.id, created_by=user.id, **data)
    db.add(eng)
    db.flush()
    _log_change(
        db,
        plan,
        user,
        "Added",
        f"{eng.title} ({eng.planned_quarter}, {eng.budget_hours}h) added",
        reason,
        request,
        eng.id,
    )
    log_action(db, user_id=user.id, action=f"PLAN_AMEND_ADD plan={plan.id} eng={eng.id}", request=request)
    db.commit()
    return {"id": eng.id, "message": "Engagement added to the approved plan"}


class AmendChangeIn(BaseModel):
    planned_quarter: str | None = Field(None, pattern=r"^Q[1-4]$")
    budget_hours: int | None = Field(None, ge=0, le=10000)
    lead_auditor_id: int | None = None
    reason: str = Field(..., max_length=2000)


@router.post("/api/plan-engagements/{eng_id}/amend")
def amend_change(
    eng_id: int, payload: AmendChangeIn, request: Request, db: DBSession = Depends(get_db), user: User = AdminOnly
) -> dict:
    """Re-time, re-budget or re-assign an engagement of an approved plan, with a documented reason."""
    eng = db.get(PlanEngagement, eng_id)
    if eng is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engagement not found")
    plan = _plan(db, eng.plan_id)
    if plan.status != PlanStatus.Approved:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Edit the engagement directly in a draft plan")
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Approved plans are changed through a plan change request (reason, impact, review and approval)",
    )
    if eng.status == EngagementStatus.Cancelled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The engagement is cancelled")
    reason = _reason(payload.reason)
    parts = []
    if payload.planned_quarter and payload.planned_quarter != eng.planned_quarter:
        parts.append(f"quarter {eng.planned_quarter} -> {payload.planned_quarter}")
        eng.planned_quarter = payload.planned_quarter
    if payload.budget_hours is not None and payload.budget_hours != eng.budget_hours:
        parts.append(f"budget {eng.budget_hours}h -> {payload.budget_hours}h")
        eng.budget_hours = payload.budget_hours
    if "lead_auditor_id" in payload.model_fields_set and payload.lead_auditor_id != eng.lead_auditor_id:
        if payload.lead_auditor_id is not None and db.get(User, payload.lead_auditor_id) is None:
            raise field_error("lead_auditor_id", "is not a known user")
        old, new = _name(db, eng.lead_auditor_id) or "none", _name(db, payload.lead_auditor_id) or "none"
        parts.append(f"lead {old} -> {new}")
        eng.lead_auditor_id = payload.lead_auditor_id
    if not parts:
        raise field_error("form", "nothing changed")
    _log_change(db, plan, user, "Changed", f"{eng.title}: {', '.join(parts)}", reason, request, eng.id)
    log_action(db, user_id=user.id, action=f"PLAN_AMEND_CHANGE eng={eng.id}", request=request)
    db.commit()
    return {"message": "Engagement changed", "changes": parts}


@router.get("/api/assurance-plans/{plan_id}/changes", response_model=list[ChangeOut])
def plan_changes(plan_id: int, db: DBSession = Depends(get_db), user: User = Staff) -> list[ChangeOut]:
    _plan(db, plan_id)
    rows = db.execute(
        select(PlanChange)
        .where(PlanChange.plan_id == plan_id)
        .order_by(PlanChange.changed_at.desc(), PlanChange.id.desc())
    ).scalars()
    return [
        ChangeOut(
            id=c.id,
            change_type=c.change_type,
            engagement_id=c.engagement_id,
            description=c.description,
            reason=c.reason,
            changed_by=_name(db, c.changed_by),
            changed_at=c.changed_at,
        )
        for c in rows
    ]


# ==================================================================== criteria library


class CriterionIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    source_type: str = "GPHA Policy"
    reference: str = Field("", max_length=255)
    body: str = Field(..., min_length=1, max_length=20000)

    @field_validator("source_type")
    @classmethod
    def _src(cls, v: str) -> str:
        if v not in CRITERIA_SOURCES:
            raise ValueError(f"must be one of: {', '.join(CRITERIA_SOURCES)}")
        return v


class CriterionPatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    source_type: str | None = None
    reference: str | None = Field(None, max_length=255)
    body: str | None = Field(None, min_length=1, max_length=20000)
    status: str | None = Field(None, pattern="^(Active|Retired)$")

    @field_validator("source_type")
    @classmethod
    def _src(cls, v: str | None) -> str | None:
        if v is not None and v not in CRITERIA_SOURCES:
            raise ValueError(f"must be one of: {', '.join(CRITERIA_SOURCES)}")
        return v


class CriterionOut(BaseModel):
    id: int
    crit_ref: str
    title: str
    source_type: str
    reference: str
    body: str
    status: str
    used_in: int = 0
    created_by: int | None
    created_at: datetime
    updated_at: datetime


class CriterionList(BaseModel):
    total: int
    items: list[CriterionOut]


def _crit_out(db: DBSession, c: Criterion, counts: dict[int, int] | None = None) -> CriterionOut:
    used = (
        counts.get(c.id, 0)
        if counts is not None
        else db.execute(select(func.count()).select_from(Finding).where(Finding.criterion_id == c.id)).scalar_one()
    )
    return CriterionOut(
        id=c.id,
        crit_ref=c.crit_ref,
        title=c.title,
        source_type=c.source_type,
        reference=c.reference,
        body=c.body,
        status=c.status,
        used_in=used,
        created_by=c.created_by,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


@router.get("/api/criteria/sources")
def criteria_sources(user: User = Staff) -> list[str]:
    return list(CRITERIA_SOURCES)


@router.get("/api/criteria", response_model=CriterionList)
def list_criteria(
    q: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    source_type: str | None = None,
    db: DBSession = Depends(get_db),
    user: User = Staff,
) -> CriterionList:
    stmt = select(Criterion).order_by(Criterion.title)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Criterion.title).like(like),
                func.lower(Criterion.reference).like(like),
                func.lower(Criterion.crit_ref).like(like),
                func.lower(Criterion.body).like(like),
            )
        )
    if status_filter:
        stmt = stmt.where(Criterion.status == status_filter)
    if source_type:
        stmt = stmt.where(Criterion.source_type == source_type)
    rows = list(db.execute(stmt).scalars())
    counts = dict(
        db.execute(
            select(Finding.criterion_id, func.count())
            .where(Finding.criterion_id.is_not(None))
            .group_by(Finding.criterion_id)
        ).all()
    )
    return CriterionList(total=len(rows), items=[_crit_out(db, c, counts) for c in rows])


@router.post("/api/criteria", response_model=CriterionOut, status_code=status.HTTP_201_CREATED)
def create_criterion(
    payload: CriterionIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> CriterionOut:
    if not has_perm(user, "method.library", "audit.findings"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your role does not maintain criteria")
    c = Criterion(
        crit_ref=next_reference(db, "CR"),
        title=payload.title.strip(),
        source_type=payload.source_type,
        reference=payload.reference.strip(),
        body=payload.body.strip(),
        created_by=user.id,
    )
    db.add(c)
    db.flush()
    log_action(db, user_id=user.id, action=f"CRITERION_CREATE id={c.id} ref={c.crit_ref}", request=request)
    log_record_history(db, record_type="criterion", record_id=c.id, user_id=user.id, action="CREATED", request=request)
    db.commit()
    return _crit_out(db, c)


def _crit(db: DBSession, crit_id: int) -> Criterion:
    c = db.get(Criterion, crit_id)
    if c is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Criterion not found")
    return c


@router.get("/api/criteria/{crit_id}", response_model=CriterionOut)
def get_criterion(crit_id: int, db: DBSession = Depends(get_db), user: User = Staff) -> CriterionOut:
    return _crit_out(db, _crit(db, crit_id))


@router.patch("/api/criteria/{crit_id}", response_model=CriterionOut)
def update_criterion(
    crit_id: int, payload: CriterionPatch, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> CriterionOut:
    if not has_perm(user, "method.library", "audit.findings"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your role does not maintain criteria")
    c = _crit(db, crit_id)
    changed = []
    for field in ("title", "source_type", "reference", "body", "status"):
        value = getattr(payload, field)
        if value is not None:
            setattr(c, field, value.strip() if isinstance(value, str) else value)
            changed.append(field)
    log_action(db, user_id=user.id, action=f"CRITERION_UPDATE id={c.id} [{', '.join(changed)}]", request=request)
    log_record_history(
        db,
        record_type="criterion",
        record_id=c.id,
        user_id=user.id,
        action=f"UPDATED [{', '.join(changed)}]",
        request=request,
    )
    db.commit()
    return _crit_out(db, c)


# ==================================================================== review notes

TARGETS = ("audit", "working_paper", "control_test", "finding")


class NoteIn(BaseModel):
    target_type: str = "audit"
    target_id: int | None = None
    note: str = Field(..., min_length=3, max_length=5000)

    @field_validator("target_type")
    @classmethod
    def _t(cls, v: str) -> str:
        if v not in TARGETS:
            raise ValueError(f"must be one of: {', '.join(TARGETS)}")
        return v


class NoteText(BaseModel):
    response: str = Field(..., min_length=3, max_length=5000)


class NoteOut(BaseModel):
    id: int
    audit_id: int
    target_type: str
    target_id: int | None
    target_label: str
    note: str
    status: str
    response: str | None
    raised_by: int | None
    raised_by_name: str | None
    raised_at: datetime
    responded_by_name: str | None
    responded_at: datetime | None
    cleared_by_name: str | None
    cleared_at: datetime | None
    can_respond: bool = False
    can_clear: bool = False


def _is_reviewer(user: User) -> bool:
    return (
        user.role == Role.Admin
        or user.review_level is not None
        or job_role_of(user) == "manager"
    )


def _note_out(db: DBSession, n: ReviewNote, user: User) -> NoteOut:
    staff = user.role in (Role.Admin, Role.Auditor)
    return NoteOut(
        id=n.id,
        audit_id=n.audit_id,
        target_type=n.target_type,
        target_id=n.target_id,
        target_label=n.target_label,
        note=n.note,
        status=n.status,
        response=n.response,
        raised_by=n.raised_by,
        raised_by_name=_name(db, n.raised_by),
        raised_at=n.raised_at,
        responded_by_name=_name(db, n.responded_by),
        responded_at=n.responded_at,
        cleared_by_name=_name(db, n.cleared_by),
        cleared_at=n.cleared_at,
        can_respond=staff and n.status in ("Open", "Responded") and n.raised_by != user.id,
        can_clear=staff
        and n.status == "Responded"
        and (n.raised_by == user.id or _is_reviewer(user))
        and n.responded_by != user.id,
    )


def _target_label(db: DBSession, audit: Audit, kind: str, target_id: int | None) -> str:
    if kind == "audit":
        return f"Audit: {audit.title}"
    if target_id is None:
        raise field_error("target_id", "choose the item the note is about")
    if kind == "working_paper":
        wp = db.get(WorkingPaper, target_id)
        if wp is None or wp.audit_id != audit.id:
            raise field_error("target_id", "is not a working paper of this audit")
        return f"Working paper {wp.wp_ref + ' ' if wp.wp_ref else ''}{wp.title} v{wp.version_number}"
    if kind == "finding":
        f = db.get(Finding, target_id)
        if f is None or f.audit_id != audit.id:
            raise field_error("target_id", "is not a finding of this audit")
        return f"Finding #{f.id}: {f.title}"
    from app.domains.audit.rcm.models import Control, ControlTest, Objective

    t = db.get(ControlTest, target_id)
    ok = (
        t is not None
        and db.execute(
            select(Objective.audit_id)
            .join(Control, Control.objective_id == Objective.id)
            .where(Control.id == t.control_id)
        ).scalar_one_or_none()
        == audit.id
    )
    if not ok:
        raise field_error("target_id", "is not a control test of this audit")
    return f"Test {t.ref}"


def open_notes(db: DBSession, audit_id: int) -> int:
    return db.execute(
        select(func.count())
        .select_from(ReviewNote)
        .where(ReviewNote.audit_id == audit_id, ReviewNote.status != "Cleared")
    ).scalar_one()


@router.get("/api/audits/{audit_id}/review-notes", response_model=list[NoteOut])
def list_notes(audit_id: int, db: DBSession = Depends(get_db), user: User = Staff) -> list[NoteOut]:
    ensure_can_view(db, user, "audit", db.get(Audit, audit_id))
    rows = db.execute(
        select(ReviewNote)
        .where(ReviewNote.audit_id == audit_id)
        .order_by(ReviewNote.status != "Open", ReviewNote.raised_at.desc())
    ).scalars()
    return [_note_out(db, n, user) for n in rows]


@router.post("/api/audits/{audit_id}/review-notes", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
def raise_note(
    audit_id: int, payload: NoteIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> NoteOut:
    audit = db.get(Audit, audit_id)
    ensure_can_view(db, user, "audit", audit)
    if audit.status == AuditStatus.Closed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The audit is closed")
    if not has_perm(user, "review.notes"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your role does not raise review notes")
    if audit.created_by == user.id and not _is_reviewer(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Review notes are raised by a reviewer, not by the audit's preparer",
        )
    label = _target_label(db, audit, payload.target_type, payload.target_id)
    n = ReviewNote(
        audit_id=audit_id,
        target_type=payload.target_type,
        target_id=payload.target_id,
        target_label=label[:255],
        note=payload.note.strip(),
        raised_by=user.id,
    )
    db.add(n)
    db.flush()
    if audit.created_by != user.id:
        notify(
            db,
            audit.created_by,
            f"Review note on {audit.title}",
            f"{label}\n{n.note}",
            link_type="audit",
            link_id=audit.id,
        )
    log_record_history(
        db,
        record_type="audit",
        record_id=audit.id,
        user_id=user.id,
        action=f"REVIEW NOTE RAISED #{n.id} on {label}"[:490],
        request=request,
    )
    db.commit()
    return _note_out(db, n, user)


def _note(db: DBSession, note_id: int, user: User) -> ReviewNote:
    n = db.get(ReviewNote, note_id)
    if n is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review note not found")
    ensure_can_view(db, user, "audit", db.get(Audit, n.audit_id))
    return n


@router.post("/api/review-notes/{note_id}/respond", response_model=NoteOut)
def respond_note(
    note_id: int, payload: NoteText, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> NoteOut:
    n = _note(db, note_id, user)
    if n.status == "Cleared":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The note is already cleared")
    if n.raised_by == user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="The reviewer cannot answer their own note")
    n.response = payload.response.strip()
    n.status = "Responded"
    n.responded_by = user.id
    n.responded_at = utcnow()
    notify(
        db,
        n.raised_by,
        "Review note answered",
        f"{n.target_label}\n{n.response}",
        link_type="audit",
        link_id=n.audit_id,
    )
    log_record_history(
        db,
        record_type="audit",
        record_id=n.audit_id,
        user_id=user.id,
        action=f"REVIEW NOTE ANSWERED #{n.id}",
        request=request,
    )
    db.commit()
    return _note_out(db, n, user)


@router.post("/api/review-notes/{note_id}/clear", response_model=NoteOut)
def clear_note(note_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> NoteOut:
    n = _note(db, note_id, user)
    if n.status != "Responded":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The preparer must answer the note first")
    if not (n.raised_by == user.id or _is_reviewer(user)) or n.responded_by == user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the reviewer (or an Audit Manager / CAE) who did not answer it can clear it",
        )
    n.status = "Cleared"
    n.cleared_by = user.id
    n.cleared_at = utcnow()
    log_record_history(
        db,
        record_type="audit",
        record_id=n.audit_id,
        user_id=user.id,
        action=f"REVIEW NOTE CLEARED #{n.id}",
        request=request,
    )
    db.commit()
    return _note_out(db, n, user)


# ==================================================================== working-paper cross-references + sign-off


class XrefIn(BaseModel):
    wp_ref: str | None = Field(None, max_length=30, pattern=r"^[A-Za-z0-9 ._/\-]*$")
    test_id: int | None = None
    finding_id: int | None = None


def _paper(db: DBSession, paper_id: int, user: User) -> WorkingPaper:
    wp = db.get(WorkingPaper, paper_id)
    if wp is None or wp.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Working paper not found")
    ensure_can_view(db, user, "audit", db.get(Audit, wp.audit_id))
    return wp


@router.patch("/api/working-papers/{paper_id}/xref")
def set_xref(
    paper_id: int, payload: XrefIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> dict:
    wp = _paper(db, paper_id, user)
    audit = db.get(Audit, wp.audit_id)
    if audit.status == AuditStatus.Closed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The audit is closed")
    sent = payload.model_fields_set
    if "wp_ref" in sent:
        ref = (payload.wp_ref or "").strip() or None
        if (
            ref
            and db.execute(
                select(WorkingPaper.id).where(
                    WorkingPaper.audit_id == wp.audit_id,
                    WorkingPaper.wp_ref == ref,
                    WorkingPaper.title != wp.title,
                    WorkingPaper.is_deleted.is_(False),
                )
            ).first()
        ):
            raise field_error("wp_ref", "is already used by another working paper in this audit")
        wp.wp_ref = ref
    if "test_id" in sent:
        if payload.test_id is not None:
            _target_label(db, audit, "control_test", payload.test_id)
        wp.test_id = payload.test_id
    if "finding_id" in sent:
        if payload.finding_id is not None:
            _target_label(db, audit, "finding", payload.finding_id)
        wp.finding_id = payload.finding_id
    log_action(db, user_id=user.id, action=f"WP_XREF id={wp.id} ref={wp.wp_ref}", request=request)
    db.commit()
    return {"id": wp.id, "wp_ref": wp.wp_ref, "test_id": wp.test_id, "finding_id": wp.finding_id}


@router.post("/api/working-papers/{paper_id}/review")
def review_paper(paper_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    wp = _paper(db, paper_id, user)
    if not has_perm(user, "review.workpapers"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your role does not sign off working papers")
    if wp.uploaded_by == user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A working paper is signed off by someone other than its preparer",
        )
    if wp.reviewed_at:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already signed off")
    levels = review_chain.chain("workpaper")
    if not levels:  # no chain configured: one sign-off by any reviewer
        wp.reviewed_by = user.id
        wp.reviewed_at = utcnow()
        what = "REVIEWED"
    else:
        try:
            stage = ReviewLevel(wp.review_stage) if wp.review_stage else levels[0]
        except ValueError:
            stage = levels[0]
        allowed, why = review_chain.may_sign(user, stage, wp.review_trail, wp.uploaded_by)
        if not allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=why)
        wp.review_trail = review_chain.sign(wp.review_trail, user, stage)
        following = review_chain.next_stage("workpaper", stage)
        if following is None:
            wp.review_stage, wp.reviewed_by, wp.reviewed_at = None, user.id, utcnow()
            what = f"REVIEWED ({review_chain.label(stage)}, final)"
        else:
            wp.review_stage = following.value
            what = f"SIGNED OFF by {review_chain.label(stage)}; next {review_chain.label(following)}"
            from app.platform.notifications.service import notify_many

            notify_many(db, [u for u in review_chain.reviewers_for(db, following) if u != user.id],
                        f"Working paper to review: {wp.wp_ref or wp.title}",
                        f"{wp.title} v{wp.version_number} is ready for {review_chain.label(following)} review.",
                        link_type="audit", link_id=wp.audit_id)
    log_record_history(
        db,
        record_type="audit",
        record_id=wp.audit_id,
        user_id=user.id,
        action=f"WORKING PAPER {what} {wp.wp_ref or ''} {wp.title} v{wp.version_number}".strip(),
        request=request,
    )
    db.commit()
    return {"id": wp.id, "reviewed_by": _name(db, wp.reviewed_by) if wp.reviewed_by else None,
            "reviewed_at": wp.reviewed_at.isoformat() if wp.reviewed_at else None,
            "review_stage": review_chain.label(wp.review_stage) if wp.review_stage else None,
            "review_trail": review_chain.trail(wp.review_trail)}


# ==================================================================== exit meeting


class ExitMeetingIn(BaseModel):
    meeting_date: datetime
    attendees: str = Field(..., min_length=3, max_length=5000)
    notes: str = Field("", max_length=20000)


@router.put("/api/reports/{report_id}/exit-meeting")
def save_exit_meeting(
    report_id: int, payload: ExitMeetingIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> dict:
    from app.domains.audit.reports.models import AuditReport

    report = db.get(AuditReport, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    ensure_can_view(db, user, "audit", db.get(Audit, report.audit_id))
    if report.status == ReportStatus.Issued:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The report is already issued")
    if payload.meeting_date.replace(tzinfo=None) > utcnow():
        raise field_error("meeting_date", "cannot be in the future")
    report.exit_meeting_date = payload.meeting_date.replace(tzinfo=None)
    report.exit_meeting_attendees = payload.attendees.strip()
    report.exit_meeting_notes = payload.notes.strip()
    log_record_history(
        db,
        record_type="audit_report",
        record_id=report.id,
        user_id=user.id,
        action=f"EXIT MEETING RECORDED {report.exit_meeting_date:%Y-%m-%d}",
        request=request,
    )
    db.commit()
    return {"message": "Exit meeting recorded"}


@router.get("/api/audits/{audit_id}/xref-options")
def xref_options(audit_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> dict:
    """Tests and findings of an audit, for cross-reference and review-note pickers."""
    from app.domains.audit.rcm.models import Control, ControlTest, Objective

    ensure_can_view(db, user, "audit", db.get(Audit, audit_id))
    tests = db.execute(
        select(ControlTest.id, ControlTest.ref)
        .join(Control, Control.id == ControlTest.control_id)
        .join(Objective, Objective.id == Control.objective_id)
        .where(Objective.audit_id == audit_id)
        .order_by(ControlTest.ref)
    ).all()
    findings = db.execute(
        select(Finding.id, Finding.title).where(Finding.audit_id == audit_id).order_by(Finding.id)
    ).all()
    papers = (
        db.execute(
            select(WorkingPaper)
            .where(WorkingPaper.audit_id == audit_id, WorkingPaper.is_deleted.is_(False))
            .order_by(WorkingPaper.title, WorkingPaper.version_number.desc())
        )
        .scalars()
        .all()
    )
    return {
        "tests": [{"id": t.id, "label": t.ref} for t in tests],
        "findings": [{"id": f.id, "label": f"#{f.id} {f.title}"} for f in findings],
        "working_papers": [
            {"id": p.id, "label": f"{p.wp_ref + ' ' if p.wp_ref else ''}{p.title} v{p.version_number}"} for p in papers
        ],
    }
