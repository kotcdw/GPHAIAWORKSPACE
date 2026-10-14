"""Annual planning cycle for the Assurance Plan.

Planning preparation -> Risk / universe review -> Audit Managers' planning meeting -> Draft plan
-> Internal review (CAE e-signature) -> Submission to the approving authority -> Audit Committee decision
-> Approved version (numbered snapshot) -> GM Audit controlled distribution (acknowledged) -> PIA / Manager execution.

``AssurancePlan.cycle_stage`` holds the stage awaiting completion; every step is a ``PlanCycleEvent``.
"""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.appconfig import cfg
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import ensure_perm, require_role
from app.core.enums import EngagementStatus, PlanStatus, Role, risk_level, utcnow
from app.core.errors import field_error
from app.core.history import log_record_history
from app.core.permissions import has_perm
from app.domains.assurance.plancycle.models import PlanCycleEvent, PlanDistribution, PlanVersion
from app.domains.assurance.plancycle.status import mark_returned
from app.domains.assurance.planning.models import AssurancePlan, EntityUnit
from app.platform.notifications.service import notify, notify_many
from app.platform.users.models import User
from app.services.documents import docx_response, new_document

router = APIRouter(tags=["planning cycle"])
Staff = Depends(require_role(Role.Admin, Role.Auditor))

STAGES: list[tuple[str, str]] = [
    ("preparation", "Planning preparation"),
    ("universe_review", "Risk / universe review"),
    ("managers_meeting", "Audit Managers' planning meeting"),
    ("drafting", "Draft Annual Assurance Plan"),
    ("internal_review", "Internal review"),
    ("submission", "Submission to the approving authority"),
    ("committee", "Audit Committee review / decision"),
    ("approved", "Approved version"),
    ("distribution", "GM Audit controlled distribution"),
    ("execution", "PIA / Manager execution"),
]
ORDER = [s for s, _ in STAGES]
LABEL = dict(STAGES)
PREPARATION_CHECKS = [
    ("strategy", "Internal Audit strategy and objectives reviewed"),
    ("prior_year", "Prior-year plan results and open findings reviewed"),
    ("stakeholders", "Management and stakeholder concerns gathered"),
    ("resources", "Staff, skills and available hours confirmed"),
    ("regulatory", "Regulatory and Board requirements noted"),
]
COMMITTEE_DECISIONS = ("Approved", "Approved with amendments", "Deferred", "Returned for revision")


def _idx(stage: str) -> int:
    return ORDER.index(stage) if stage in ORDER else 0


def _plan(db: DBSession, plan_id: int) -> AssurancePlan:
    plan = db.get(AssurancePlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assurance Plan not found")
    return plan


def _at(plan: AssurancePlan, *stages: str) -> None:
    if plan.cycle_stage not in stages:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"The plan is at '{LABEL.get(plan.cycle_stage, plan.cycle_stage)}'; this step "
                                   f"belongs to '{LABEL[stages[0]]}'")


def _event(db: DBSession, plan: AssurancePlan, user: User | None, stage: str, action: str,
           request: Request | None = None,
           **kw) -> PlanCycleEvent:
    ev = PlanCycleEvent(plan_id=plan.id, stage=stage, action=action, user_id=user.id if user else None, **kw)
    db.add(ev)
    label = f"PLAN CYCLE {LABEL.get(stage, stage)}: {action}" + (f" ({kw['decision']})" if kw.get("decision") else "")
    if user is not None:
        log_record_history(db, record_type="assurance_plan", record_id=plan.id, user_id=user.id, action=label[:490],
                           request=request)
    return ev


def _past(value: datetime, name: str) -> datetime:
    value = value.replace(tzinfo=None)
    if value > utcnow():
        raise field_error(name, "cannot be in the future")
    return value


# ------------------------------------------------------------------ hooks used by the planning / methodology routers


def ready_for_approval(plan: AssurancePlan) -> None:
    """Called before the CAE e-signs: with the cycle enforced, the plan must have been submitted for review."""
    if cfg("plan_cycle_enforced") and plan.cycle_stage != "internal_review":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Complete the planning cycle first: preparation, risk / universe review, the Audit "
                                   "Managers' planning meeting, then submit the draft for internal review")


def on_internal_decision(db: DBSession, plan: AssurancePlan, user: User, approved: bool, comment: str | None,
                         request: Request | None) -> None:
    """The CAE's e-signature is the internal review decision."""
    _event(db, plan, user, "internal_review", "Endorsed" if approved else "Returned",
           decision="Endorsed (CAE e-signature)" if approved else "Returned for revision", notes=comment or None)
    plan.cycle_stage = "submission" if approved else "drafting"
    if not approved:
        mark_returned(plan)
        notify(db, plan.created_by, f"Assurance Plan FY{plan.fiscal_year} returned for revision", comment or "",
               link_type="assurance_plan", link_id=plan.id)


def on_reopen(db: DBSession, plan: AssurancePlan, user: User, request: Request | None) -> None:
    _event(db, plan, user, "drafting", "Reopened", notes="Approved plan reopened for changes; re-approval required")
    plan.cycle_stage = "drafting"


def _site_names(plan: AssurancePlan) -> dict[int, str]:
    from sqlalchemy.orm import object_session

    from app.platform.organizations.models import Organization

    db = object_session(plan)
    ids = {e.site_entity_id for e in plan.engagements if e.site_entity_id}
    return {o.id: o.name for o in db.execute(select(Organization).where(Organization.id.in_(ids))).scalars()} if ids \
        else {}


def _snapshot(plan: AssurancePlan) -> dict:
    sites = _site_names(plan)
    return {
        "plan_ref": plan.plan_ref, "fiscal_year": plan.fiscal_year, "title": plan.title,
        "description": plan.description, "total_budget_hours": plan.total_budget_hours,
        "approved_at": plan.approved_at.isoformat() if plan.approved_at else None,
        "committee_meeting_date": plan.committee_meeting_date.isoformat() if plan.committee_meeting_date else None,
        "committee_reference": plan.committee_reference,
        "engagements": [{
            "title": e.title, "entity": (f"{e.entity_unit.location.name} / {e.entity_unit.name}"
                                         if e.entity_unit else None),
            "risk": risk_level(e.entity_unit.risk_score) if e.entity_unit else None,
            "planned_quarter": e.planned_quarter, "budget_hours": e.budget_hours,
            "lead_auditor_id": e.lead_auditor_id, "rationale": e.rationale,
            "site_entity_id": e.site_entity_id, "site": sites.get(e.site_entity_id),
        } for e in plan.engagements if e.status != EngagementStatus.Cancelled],
    }


def record_committee_decision(db: DBSession, plan: AssurancePlan, user: User, decision: str, meeting_date: datetime,
                              reference: str, notes: str, request: Request | None) -> PlanVersion | None:
    """Audit Committee decision. Approval freezes a numbered version; a return sends the plan back to drafting."""
    _event(db, plan, user, "committee", "Decision", decision=decision, meeting_date=meeting_date,
           reference=reference, notes=notes or None)
    if decision == "Deferred":
        plan.cycle_stage = "committee"
        return None
    if decision == "Returned for revision":
        plan.status = PlanStatus.Draft
        plan.approved_by = None
        plan.approved_at = None
        plan.cycle_stage = "drafting"
        mark_returned(plan)
        notify(db, plan.created_by, f"Assurance Plan FY{plan.fiscal_year} returned by the Audit Committee",
               notes or reference, link_type="assurance_plan", link_id=plan.id)
        return None
    plan.committee_meeting_date = meeting_date
    plan.committee_reference = reference
    plan.committee_notes = notes
    plan.committee_recorded_by = user.id
    plan.committee_recorded_at = utcnow()
    plan.current_version += 1
    db.flush()
    version = PlanVersion(plan_id=plan.id, version=plan.current_version, snapshot=json.dumps(_snapshot(plan)),
                          decision=decision, committee_reference=reference, approved_at=meeting_date,
                          created_by=user.id)
    db.add(version)
    _event(db, plan, user, "approved", f"Version {plan.current_version} frozen", reference=reference)
    plan.cycle_stage = "distribution"
    return version


# ------------------------------------------------------------------ read


class StageOut(BaseModel):
    code: str
    label: str
    state: str  # done | current | pending
    completed_at: datetime | None = None
    completed_by: str | None = None
    summary: str | None = None


class EventOut(BaseModel):
    id: int
    stage: str
    stage_label: str
    action: str
    decision: str | None
    meeting_date: datetime | None
    reference: str | None
    attendees: str | None
    notes: str | None
    data: dict | None
    by: str | None
    at: datetime


class VersionOut(BaseModel):
    version: int
    decision: str
    committee_reference: str | None
    approved_at: datetime
    engagements: int
    iaa_submitted_at: datetime | None = None
    iaa_reference: str | None = None


class DistributionOut(BaseModel):
    user_id: int
    site_entity_id: int | None = None
    site: str | None = None
    name: str
    job_role: str | None
    version: int
    sent_at: datetime
    acknowledged_at: datetime | None


class CycleOut(BaseModel):
    plan_id: int
    stage: str
    stage_label: str
    status: str
    current_version: int
    enforced: bool
    stages: list[StageOut]
    events: list[EventOut]
    versions: list[VersionOut]
    distribution: list[DistributionOut]
    execution: dict
    can: dict[str, bool]
    preparation_checks: list[dict]
    committee_decisions: list[str]


def _name(db: DBSession, uid: int | None) -> str | None:
    u = db.get(User, uid) if uid else None
    return (u.full_name or u.username) if u else None


def _cycle(db: DBSession, plan: AssurancePlan, user: User) -> CycleOut:
    events = list(db.execute(select(PlanCycleEvent).where(PlanCycleEvent.plan_id == plan.id)
                             .order_by(PlanCycleEvent.id)).scalars())
    last_by_stage: dict[str, PlanCycleEvent] = {}
    for ev in events:
        last_by_stage[ev.stage] = ev
    current = _idx(plan.cycle_stage)
    closed = plan.status == PlanStatus.Closed
    stages = []
    for i, (code, label) in enumerate(STAGES):
        ev = last_by_stage.get(code)
        state = "done" if i < current or (closed and code == "execution") else ("current" if i == current
                                                                                 else "pending")
        summary = None
        if ev is not None:
            summary = ev.decision or ev.action
            if ev.reference:
                summary += f" · ref {ev.reference}"
        stages.append(StageOut(code=code, label=label, state=state, completed_at=ev.created_at if ev else None,
                               completed_by=_name(db, ev.user_id) if ev else None, summary=summary))
    versions = list(db.execute(select(PlanVersion).where(PlanVersion.plan_id == plan.id)
                               .order_by(PlanVersion.version.desc())).scalars())
    dist = list(db.execute(select(PlanDistribution).where(PlanDistribution.plan_id == plan.id)
                           .order_by(PlanDistribution.version.desc(), PlanDistribution.id)).scalars())
    live = [e for e in plan.engagements if e.status != EngagementStatus.Cancelled]
    site_list = sites(db)
    site_dest = {x["id"]: x["destination"] for x in site_list}
    by_site: dict[str, dict[str, int]] = {}
    for e in live:
        row = by_site.setdefault(site_dest.get(e.site_entity_id, "No responsible site"), {"planned": 0, "started": 0})
        row["started" if e.status == EngagementStatus.Started else "planned"] += 1
    by_lead: dict[str, dict[str, int]] = {}
    for e in live:
        row = by_lead.setdefault(_name(db, e.lead_auditor_id) or "Unassigned", {"planned": 0, "started": 0})
        row["started" if e.status == EngagementStatus.Started else "planned"] += 1
    prepare = has_perm(user, "plan.prepare")
    gm = has_perm(user, "plan.amend")
    mine = next((d for d in dist if d.user_id == user.id and d.version == plan.current_version), None)
    can = {
        "preparation": prepare and plan.cycle_stage == "preparation",
        "universe_review": prepare and plan.cycle_stage == "universe_review",
        "managers_meeting": prepare and plan.cycle_stage == "managers_meeting",
        "submit_review": prepare and plan.cycle_stage == "drafting" and plan.status == PlanStatus.Draft,
        "internal_review": has_perm(user, "plan.approve") and plan.status == PlanStatus.Draft
        and plan.created_by != user.id
        and (plan.cycle_stage == "internal_review" or not cfg("plan_cycle_enforced")),
        "submit_authority": has_perm(user, "plan.approve") and plan.cycle_stage == "submission",
        "committee": gm and plan.cycle_stage == "committee",
        "distribute": has_perm(user, "oversight.portfolio") and plan.status == PlanStatus.Approved
        and plan.current_version > 0 and plan.cycle_stage in ("distribution", "execution"),
        "acknowledge": mine is not None and mine.acknowledged_at is None,
    }
    return CycleOut(
        plan_id=plan.id, stage=plan.cycle_stage, stage_label=LABEL.get(plan.cycle_stage, plan.cycle_stage),
        status=plan.status.value, current_version=plan.current_version, enforced=bool(cfg("plan_cycle_enforced")),
        stages=stages,
        events=[EventOut(id=e.id, stage=e.stage, stage_label=LABEL.get(e.stage, e.stage), action=e.action,
                         decision=e.decision, meeting_date=e.meeting_date, reference=e.reference,
                         attendees=e.attendees, notes=e.notes, data=json.loads(e.data) if e.data else None,
                         by=_name(db, e.user_id), at=e.created_at) for e in reversed(events)],
        versions=[VersionOut(version=v.version, decision=v.decision, committee_reference=v.committee_reference,
                             approved_at=v.approved_at, engagements=len(json.loads(v.snapshot)["engagements"]),
                             iaa_submitted_at=v.iaa_submitted_at, iaa_reference=v.iaa_reference)
                  for v in versions],
        distribution=[DistributionOut(user_id=d.user_id, site_entity_id=d.site_entity_id,
                                      site=site_dest.get(d.site_entity_id), name=_name(db, d.user_id) or "?",
                                      job_role=_job_name(db, d.user_id), version=d.version, sent_at=d.sent_at,
                                      acknowledged_at=d.acknowledged_at) for d in dist],
        execution={"engagements": len(live), "started": sum(1 for e in live if e.status == EngagementStatus.Started),
                   "by_lead": by_lead, "by_site": by_site},
        can=can, preparation_checks=[{"key": k, "label": label} for k, label in PREPARATION_CHECKS],
        committee_decisions=list(COMMITTEE_DECISIONS),
    )


def _job_name(db: DBSession, uid: int) -> str | None:
    from app.core.permissions import JOB_ROLES_BY_CODE, job_role_of

    u = db.get(User, uid)
    return JOB_ROLES_BY_CODE[job_role_of(u)].name if u else None


@router.get("/api/assurance-plans/{plan_id}/cycle", response_model=CycleOut)
def get_cycle(plan_id: int, db: DBSession = Depends(get_db), user: User = Staff) -> CycleOut:
    return _cycle(db, _plan(db, plan_id), user)


# ------------------------------------------------------------------ stages 1-4


class PreparationIn(BaseModel):
    checks: list[str] = Field(default_factory=list)
    notes: str = Field("", max_length=8000)


@router.post("/api/assurance-plans/{plan_id}/cycle/preparation", response_model=CycleOut)
def preparation(plan_id: int, payload: PreparationIn, request: Request, db: DBSession = Depends(get_db),
                user: User = Staff) -> CycleOut:
    ensure_perm(user, "plan.prepare")
    plan = _plan(db, plan_id)
    _at(plan, "preparation")
    missing = [label for k, label in PREPARATION_CHECKS if k not in payload.checks]
    if missing:
        raise field_error("checks", f"confirm every preparation item (missing: {', '.join(missing)})")
    _event(db, plan, user, "preparation", "Completed", notes=payload.notes.strip() or None,
           data=json.dumps({"checks": payload.checks}))
    plan.cycle_stage = "universe_review"
    db.commit()
    return _cycle(db, plan, user)


def universe_snapshot(db: DBSession) -> dict:
    now = utcnow()
    cycle_years = {"High": cfg("audit_cycle_high_years"), "Medium": cfg("audit_cycle_medium_years"),
                   "Low": cfg("audit_cycle_low_years")}
    units = list(db.execute(select(EntityUnit).where(EntityUnit.is_active.is_(True))).scalars())
    by_rating = {"High": 0, "Medium": 0, "Low": 0}
    due = []
    for u in units:
        rating = risk_level(u.risk_score)
        by_rating[rating] = by_rating.get(rating, 0) + 1
        years = cycle_years.get(rating, 3)
        if u.last_audited_at is None or (now - u.last_audited_at).days > 365 * years:
            due.append({"id": u.id, "name": f"{u.location.name} / {u.name}", "risk": rating, "score": u.risk_score,
                        "last_audited": u.last_audited_at.date().isoformat() if u.last_audited_at else None})
    due.sort(key=lambda d: -d["score"])
    return {"units": len(units), "by_rating": by_rating, "due_count": len(due), "due": due[:50]}


@router.get("/api/assurance-plans/{plan_id}/cycle/universe")
def universe_preview(plan_id: int, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    _plan(db, plan_id)
    return universe_snapshot(db)


class ReviewIn(BaseModel):
    notes: str = Field(..., min_length=10, max_length=8000)


@router.post("/api/assurance-plans/{plan_id}/cycle/universe-review", response_model=CycleOut)
def universe_review(plan_id: int, payload: ReviewIn, request: Request, db: DBSession = Depends(get_db),
                    user: User = Staff) -> CycleOut:
    ensure_perm(user, "plan.prepare")
    plan = _plan(db, plan_id)
    _at(plan, "universe_review")
    snap = universe_snapshot(db)
    _event(db, plan, user, "universe_review", "Completed", notes=payload.notes.strip(), data=json.dumps(snap))
    plan.cycle_stage = "managers_meeting"
    db.commit()
    return _cycle(db, plan, user)


class MeetingIn(BaseModel):
    meeting_date: datetime
    attendees: str = Field(..., min_length=3, max_length=4000)
    minutes: str = Field(..., min_length=10, max_length=20000)


@router.post("/api/assurance-plans/{plan_id}/cycle/managers-meeting", response_model=CycleOut)
def managers_meeting(plan_id: int, payload: MeetingIn, request: Request, db: DBSession = Depends(get_db),
                     user: User = Staff) -> CycleOut:
    ensure_perm(user, "plan.prepare")
    plan = _plan(db, plan_id)
    _at(plan, "managers_meeting")
    _event(db, plan, user, "managers_meeting", "Held", meeting_date=_past(payload.meeting_date, "meeting_date"),
           attendees=payload.attendees.strip(), notes=payload.minutes.strip())
    plan.cycle_stage = "drafting"
    db.commit()
    return _cycle(db, plan, user)


class NoteIn(BaseModel):
    notes: str = Field("", max_length=8000)


@router.post("/api/assurance-plans/{plan_id}/cycle/submit-review", response_model=CycleOut)
def submit_review(plan_id: int, payload: NoteIn, request: Request, db: DBSession = Depends(get_db),
                  user: User = Staff) -> CycleOut:
    """Draft complete: send it for internal review (the CAE's e-signature)."""
    ensure_perm(user, "plan.prepare")
    plan = _plan(db, plan_id)
    _at(plan, "drafting")
    if plan.status != PlanStatus.Draft:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only a draft plan can be submitted")
    if not any(e.status != EngagementStatus.Cancelled for e in plan.engagements):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Add at least one engagement first")
    _event(db, plan, user, "drafting", "Submitted for internal review", notes=payload.notes.strip() or None)
    plan.cycle_stage = "internal_review"
    reviewers = [u.id for u in db.execute(select(User).where(User.is_active.is_(True))).scalars()
                 if u.id != user.id and has_perm(u, "plan.approve")]
    notify_many(db, reviewers, f"Assurance Plan FY{plan.fiscal_year} ready for internal review",
                f"{_name(db, user.id)} submitted the draft plan for your review and e-signature.",
                link_type="assurance_plan", link_id=plan.id)
    db.commit()
    return _cycle(db, plan, user)


class ReturnIn(BaseModel):
    comment: str = Field(..., min_length=5, max_length=4000)


@router.post("/api/assurance-plans/{plan_id}/cycle/return", response_model=CycleOut)
def return_draft(plan_id: int, payload: ReturnIn, request: Request, db: DBSession = Depends(get_db),
                 user: User = Staff) -> CycleOut:
    """Internal reviewer sends the draft back without signing."""
    ensure_perm(user, "plan.approve")
    plan = _plan(db, plan_id)
    _at(plan, "internal_review")
    on_internal_decision(db, plan, user, False, payload.comment.strip(), request)
    db.commit()
    return _cycle(db, plan, user)


# ------------------------------------------------------------------ stages 6-7


class SubmitAuthorityIn(BaseModel):
    authority: str = Field("Audit Committee", min_length=3, max_length=255)
    submitted_on: datetime
    reference: str = Field("", max_length=100)
    notes: str = Field("", max_length=8000)


@router.post("/api/assurance-plans/{plan_id}/cycle/submit-authority", response_model=CycleOut)
def submit_authority(plan_id: int, payload: SubmitAuthorityIn, request: Request, db: DBSession = Depends(get_db),
                     user: User = Staff) -> CycleOut:
    ensure_perm(user, "plan.approve")
    plan = _plan(db, plan_id)
    _at(plan, "submission")
    _event(db, plan, user, "submission", "Submitted", decision=f"To {payload.authority.strip()}",
           meeting_date=_past(payload.submitted_on, "submitted_on"), reference=payload.reference.strip() or None,
           notes=payload.notes.strip() or None)
    plan.cycle_stage = "committee"
    db.commit()
    return _cycle(db, plan, user)


class DecisionIn(BaseModel):
    decision: str
    meeting_date: datetime
    reference: str = Field(..., min_length=2, max_length=100)
    notes: str = Field("", max_length=8000)


@router.post("/api/assurance-plans/{plan_id}/cycle/committee-decision", response_model=CycleOut)
def committee_decision(plan_id: int, payload: DecisionIn, request: Request, db: DBSession = Depends(get_db),
                       user: User = Staff) -> CycleOut:
    ensure_perm(user, "plan.amend")
    plan = _plan(db, plan_id)
    _at(plan, "committee")
    if payload.decision not in COMMITTEE_DECISIONS:
        raise field_error("decision", f"must be one of {', '.join(COMMITTEE_DECISIONS)}")
    if payload.decision == "Approved with amendments" and len(payload.notes.strip()) < 10:
        raise field_error("notes", "record the amendments the Committee asked for")
    meeting = _past(payload.meeting_date, "meeting_date")
    if plan.approved_at and meeting.date() < plan.approved_at.date():
        raise field_error("meeting_date", "is before the CAE approved the plan")
    version = record_committee_decision(db, plan, user, payload.decision, meeting, payload.reference.strip(),
                                        payload.notes.strip(), request)
    log_action(db, user_id=user.id, request=request,
               action=f"PLAN_COMMITTEE_DECISION id={plan.id} {payload.decision}"
                      + (f" v{version.version}" if version else ""))
    db.commit()
    return _cycle(db, plan, user)


# ------------------------------------------------------------------ versions


@router.get("/api/assurance-plans/{plan_id}/versions/{version}")
def get_version(plan_id: int, version: int, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    v = _version(db, plan_id, version)
    return {"version": v.version, "decision": v.decision, "committee_reference": v.committee_reference,
            "approved_at": v.approved_at, **json.loads(v.snapshot)}


def _version(db: DBSession, plan_id: int, version: int) -> PlanVersion:
    v = db.execute(select(PlanVersion).where(PlanVersion.plan_id == plan_id, PlanVersion.version == version)
                   ).scalar_one_or_none()
    if v is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    return v


@router.get("/api/assurance-plans/{plan_id}/versions/{version}/export.docx")
def export_version(plan_id: int, version: int, request: Request, site_id: int | None = None,
                   db: DBSession = Depends(get_db), user: User = Staff) -> Response:

    v = _version(db, plan_id, version)
    s = json.loads(v.snapshot)
    copy_for = None
    if site_id is not None:  # the copy for one destination (HQ / PIA Tema / PIA Takoradi)
        site = next((x for x in sites(db) if x["id"] == site_id), None)
        if site is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown site")
        copy_for = site["destination"]
        s["engagements"] = [e for e in s["engagements"] if e.get("site_entity_id") == site_id]
    doc = new_document()
    doc.add_heading(f"{s['title']} (FY{s['fiscal_year']})", level=1)
    doc.add_paragraph(f"Approved version {v.version} · {v.decision} by the Audit Committee on "
                      f"{v.approved_at:%d %B %Y} (ref {v.committee_reference or '-'}) · {s['plan_ref']}")
    doc.add_paragraph("CONTROLLED COPY - distributed by the GM Audit. Do not amend; changes go through the plan "
                      "amendment process."
                      + (f" Copy for: {copy_for}." if copy_for else "")).runs[0].bold = True
    if s.get("description"):
        doc.add_heading("Basis of the plan", level=2)
        doc.add_paragraph(s["description"])
    doc.add_heading("Planned engagements", level=2)
    table = doc.add_table(rows=1, cols=6)
    table.style = "Light Grid Accent 1"
    for cell, text in zip(table.rows[0].cells, ("Engagement", "Responsible site", "Entity", "Risk", "Quarter",
                                                "Hours"), strict=True):
        cell.text = text
    for e in s["engagements"]:
        row = table.add_row().cells
        for cell, text in zip(row, (e["title"], e.get("site") or "-", e["entity"] or "-", e["risk"] or "-",
                                    e["planned_quarter"], str(e["budget_hours"])), strict=True):
            cell.text = text
    doc.add_paragraph(f"Total budget: {s['total_budget_hours']} hours · "
                      f"{sum(e['budget_hours'] for e in s['engagements'])} hours planned")
    log_action(db, user_id=user.id, action=f"PLAN_VERSION_EXPORT plan={plan_id} v{version}", request=request)
    db.commit()
    return docx_response(doc, f"Assurance-Plan-FY{s['fiscal_year']}-v{v.version}"
                         + (f"-{copy_for.replace(' ', '-')}" if copy_for else "") + ".docx")


# ------------------------------------------------------------------ stages 9-10


def sites(db: DBSession) -> list[dict]:
    """Distribution destinations, set up by administrators on the Organizations register: every entity marked
    'Receives the approved plan', shown under its destination label (e.g. HQ, PIA Tema, PIA Takoradi).
    Until an administrator marks any, the entities of the configured port / site types are used."""
    from app.platform.organizations.router import Index

    idx = Index(db)
    flagged = [o for o in idx.rows.values() if o.plan_destination]
    rows = flagged or [o for o in idx.rows.values() if idx.is_port(o)]
    out = [{"id": o.id, "name": o.name, "destination": o.destination_label or o.name, "configured": bool(flagged)}
           for o in rows]
    return sorted(out, key=lambda x: x["destination"].lower())


def site_officers(db: DBSession, site_id: int) -> list[User]:
    """Who receives the copy for a site: its PIA (port oversight) and Audit Managers / planners based there.
    The GM Audit (portfolio oversight) distributes and is not a site recipient."""
    from app.domains.audit.audits.router import _home_port

    staff = db.execute(select(User).where(User.is_active.is_(True), User.role.in_((Role.Auditor, Role.Admin))))
    return [u for u in staff.scalars()
            if _home_port(db, u) == site_id and has_perm(u, "oversight.port", "audit.memo_approve", "plan.prepare")
            and not has_perm(u, "oversight.portfolio")]


def default_recipients(db: DBSession) -> list[User]:
    """PIAs and Audit Managers (and anyone else who oversees a port or approves memos)."""
    return [u for u in db.execute(select(User).where(User.is_active.is_(True), User.role == Role.Auditor)).scalars()
            if has_perm(u, "oversight.port", "audit.memo_approve") and not has_perm(u, "oversight.portfolio")]


@router.get("/api/assurance-plans/{plan_id}/cycle/destinations")
def destinations(plan_id: int, db: DBSession = Depends(get_db), user: User = Staff) -> list[dict]:
    """HQ, PIA Tema, PIA Takoradi ...: who receives each copy and what is in it."""
    plan = _plan(db, plan_id)
    live = [e for e in plan.engagements if e.status != EngagementStatus.Cancelled]
    out = []
    for s in sites(db):
        engs = [e for e in live if e.site_entity_id == s["id"]]
        out.append({**s, "engagements": len(engs), "hours": sum(e.budget_hours for e in engs),
                    "recipients": [{"id": u.id, "name": u.full_name or u.username, "job_role": _job_name(db, u.id)}
                                   for u in site_officers(db, s["id"])]})
    unassigned = [e for e in live if e.site_entity_id is None]
    return out + ([{"id": None, "name": "No responsible site", "destination": "Unassigned", "configured": False,
                    "engagements": len(unassigned), "hours": sum(e.budget_hours for e in unassigned),
                    "recipients": []}] if unassigned else [])


@router.get("/api/assurance-plans/{plan_id}/cycle/recipients")
def recipients(plan_id: int, db: DBSession = Depends(get_db), user: User = Staff) -> list[dict]:
    _plan(db, plan_id)
    suggested = {u.id for u in default_recipients(db)}
    staff = db.execute(select(User).where(User.is_active.is_(True), User.role.in_((Role.Auditor, Role.Admin))))
    return [{"id": u.id, "name": u.full_name or u.username, "job_role": _job_name(db, u.id),
             "suggested": u.id in suggested} for u in staff.scalars() if u.id != user.id]


class DistributeIn(BaseModel):
    site_ids: list[int] = Field(default_factory=list, max_length=50)
    user_ids: list[int] = Field(default_factory=list, max_length=200)
    note: str = Field("", max_length=4000)


@router.post("/api/assurance-plans/{plan_id}/cycle/distribute", response_model=CycleOut)
def distribute(plan_id: int, payload: DistributeIn, request: Request, db: DBSession = Depends(get_db),
               user: User = Staff) -> CycleOut:
    """GM Audit sends the approved version to the destinations - HQ and each port's PIA - and, optionally,
    to named individuals. Every recipient acknowledges receipt."""
    ensure_perm(user, "oversight.portfolio")
    plan = _plan(db, plan_id)
    if plan.status != PlanStatus.Approved or plan.current_version == 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Only an Audit Committee-approved version can be distributed")
    _at(plan, "distribution", "execution")
    if not payload.site_ids and not payload.user_ids:
        raise field_error("site_ids", "choose at least one destination (HQ or a port)")
    known = {s["id"]: s for s in sites(db)}
    targets: list[tuple[int, int | None]] = []
    for sid in dict.fromkeys(payload.site_ids):
        if sid not in known:
            raise field_error("site_ids", f"entity {sid} is not set up as a plan destination")
        officers = site_officers(db, sid)
        if not officers:
            raise field_error("site_ids", f"nobody is registered to receive the plan at {known[sid]['name']}: "
                                          "set 'Where I work' for its PIA / Audit Manager")
        targets += [(u.id, sid) for u in officers]
    for uid in payload.user_ids:
        u = db.get(User, uid)
        if u is None or not u.is_active or u.role not in (Role.Auditor, Role.Admin):
            raise field_error("user_ids", f"user {uid} is not an active member of the audit staff")
        targets.append((uid, None))
    existing = {d.user_id for d in db.execute(select(PlanDistribution).where(
        PlanDistribution.plan_id == plan.id, PlanDistribution.version == plan.current_version)).scalars()}
    sent: list[int] = []
    for uid, sid in targets:
        if uid in existing or uid in sent:
            continue
        db.add(PlanDistribution(plan_id=plan.id, version=plan.current_version, user_id=uid, site_entity_id=sid,
                                note=payload.note.strip() or None, sent_by=user.id))
        sent.append(uid)
    notify_many(db, sent, f"Approved Assurance Plan FY{plan.fiscal_year} (version {plan.current_version})",
                (payload.note.strip() + "\n\n" if payload.note.strip() else "")
                + "Please open the plan and acknowledge receipt.", link_type="assurance_plan", link_id=plan.id)
    dests = [known[s]["destination"] for s in dict.fromkeys(payload.site_ids)]
    _event(db, plan, user, "distribution", "Distributed",
           decision=(f"Version {plan.current_version} to " + ", ".join(dests or ["named individuals"]))[:40],
           notes=(", ".join(dests) + (f" + {len(payload.user_ids)} individual(s)" if payload.user_ids else "")
                  + (f". {payload.note.strip()}" if payload.note.strip() else "")),
           data=json.dumps({"site_ids": payload.site_ids, "user_ids": sent}))
    plan.cycle_stage = "execution"
    db.commit()
    return _cycle(db, plan, user)


@router.post("/api/assurance-plans/{plan_id}/cycle/acknowledge", response_model=CycleOut)
def acknowledge(plan_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> CycleOut:
    plan = _plan(db, plan_id)
    d = db.execute(select(PlanDistribution).where(PlanDistribution.plan_id == plan.id,
                                                  PlanDistribution.version == plan.current_version,
                                                  PlanDistribution.user_id == user.id)).scalar_one_or_none()
    if d is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="The plan was not distributed to you")
    if d.acknowledged_at is None:
        d.acknowledged_at = utcnow()
        log_record_history(db, record_type="assurance_plan", record_id=plan.id, user_id=user.id,
                           action=f"PLAN v{plan.current_version} RECEIPT ACKNOWLEDGED", request=request)
        notify(db, d.sent_by, f"{_name(db, user.id)} acknowledged the FY{plan.fiscal_year} plan", "",
               link_type="assurance_plan", link_id=plan.id, email=False)
        db.commit()
    return _cycle(db, plan, user)


def ensure_can_execute(plan: AssurancePlan) -> None:
    """Called before an engagement is started."""
    if cfg("plan_distribution_before_execution") and plan.cycle_stage != "execution":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Engagements start after the Audit Committee-approved plan has been distributed "
                                   "by the GM Audit")


# ------------------------------------------------------------------ archive


@router.post("/api/assurance-plans/{plan_id}/archive", response_model=CycleOut)
def archive(plan_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> CycleOut:
    """Archive a closed plan year: read-only, hidden from the default plan list, kept for the record."""
    ensure_perm(user, "plan.amend")
    plan = _plan(db, plan_id)
    if plan.status != PlanStatus.Closed or plan.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only a closed plan can be archived")
    plan.archived_at = utcnow()
    plan.archived_by = user.id
    _event(db, plan, user, "execution", "Archived", request)
    log_action(db, user_id=user.id, action=f"PLAN_ARCHIVE id={plan.id}", request=request)
    db.commit()
    return _cycle(db, plan, user)


# ------------------------------------------------------------------ Internal Audit Agency (Ghana)


class IaaIn(BaseModel):
    submitted_on: datetime
    reference: str = Field(..., min_length=2, max_length=100)


@router.post("/api/assurance-plans/{plan_id}/versions/{version}/iaa-submission", response_model=CycleOut)
def iaa_submission(plan_id: int, version: int, payload: IaaIn, request: Request, db: DBSession = Depends(get_db),
                   user: User = Staff) -> CycleOut:
    """Record that an approved version was submitted to the Internal Audit Agency (date and letter reference)."""
    ensure_perm(user, "plan.amend")
    plan = _plan(db, plan_id)
    v = _version(db, plan_id, version)
    when = _past(payload.submitted_on, "submitted_on")
    if when.date() < v.approved_at.date():
        raise field_error("submitted_on", "is before this version was approved")
    v.iaa_submitted_at = when
    v.iaa_reference = payload.reference.strip()
    v.iaa_recorded_by = user.id
    _event(db, plan, user, "approved", "Submitted to IAA", request, decision=f"Version {version} to the Internal "
           "Audit Agency", meeting_date=when, reference=v.iaa_reference)
    db.commit()
    return _cycle(db, plan, user)
