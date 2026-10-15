"""Audit plan Timeline view, Include audits and Exclude from audit plan (Diligent One Audit app).

* **Timeline**: one bar per engagement from its planned start to end (or its planned quarter), in colour-coded
  swimlanes by category (port / site), quarter or lead, with milestones (Audit Committee meetings, plan approval).
* **Include audits**: audits that are not on any plan can be included; a draft plan takes them directly, an
  approved plan records each inclusion as a plan change (Plan changes log, Committee pack).
* **Exclude from audit plan**: takes an included audit off the plan again.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.access import visible
from app.core.audit import log_action
from app.core.database import get_db
from app.core.enums import AuditStatus, EngagementStatus, PlanStatus
from app.core.errors import field_error
from app.core.permissions import has_perm
from app.domains.assurance.planning.models import AssurancePlan, PlanChange, PlanEngagement
from app.domains.assurance.planning.router import Staff, _conflict, _engagement_or_404, _history, _plan_or_404
from app.domains.assurance.scheduler.router import _quarter_bounds
from app.domains.audit.audits.models import Audit, AuditTeamMember
from app.platform.users.models import User

router = APIRouter(tags=["assurance planning"])

GROUPS = ("category", "quarter", "lead", "status")


def _span(plan: AssurancePlan, e: PlanEngagement) -> tuple[date, date]:
    if e.planned_start and e.planned_end:
        return e.planned_start, e.planned_end
    start, end = _quarter_bounds(plan.fiscal_year, e.planned_quarter or "Q1")
    return e.planned_start or start, e.planned_end or end


def _lane(db: DBSession, e: PlanEngagement, group: str, leads: dict[int, str], sites: dict[int, str]) -> str:
    if group == "quarter":
        return e.planned_quarter or "Unscheduled"
    if group == "lead":
        return leads.get(e.lead_auditor_id) or "Unassigned"
    if group == "status":
        return e.status.value
    if e.site_entity_id and e.site_entity_id in sites:
        return sites[e.site_entity_id]
    unit = e.entity_unit
    if unit is not None and getattr(unit, "location", None) is not None:
        return unit.location.name
    return "No category"


@router.get("/api/assurance-plans/{plan_id}/timeline")
def plan_timeline(plan_id: int, group: str = Query("category", pattern="^(category|quarter|lead|status)$"),
                  db: DBSession = Depends(get_db), _: User = Staff) -> dict:
    from app.domains.assurance.committee.models import CommitteeMeeting
    from app.domains.assurance.planning.coverage import engagement_progress
    from app.platform.organizations.models import Organization

    plan = _plan_or_404(db, plan_id)
    engagements = [e for e in plan.engagements]
    leads = {u.id: u.full_name or u.username for u in db.execute(select(User).where(User.id.in_(
        [e.lead_auditor_id for e in engagements if e.lead_auditor_id] or [0]))).scalars()}
    sites = {o.id: o.name for o in db.execute(select(Organization).where(Organization.id.in_(
        [e.site_entity_id for e in engagements if e.site_entity_id] or [0]))).scalars()}
    audits = {a.id: a for a in db.execute(select(Audit).where(Audit.id.in_(
        [e.audit_id for e in engagements if e.audit_id] or [0]))).scalars()}
    lanes: dict[str, list[dict]] = {}
    fy_start, fy_end = date(plan.fiscal_year, 1, 1), date(plan.fiscal_year, 12, 31)
    lo, hi = fy_start, fy_end
    for e in engagements:
        start, end = _span(plan, e)
        lo, hi = min(lo, start), max(hi, end)
        audit = audits.get(e.audit_id) if e.audit_id else None
        lanes.setdefault(_lane(db, e, group, leads, sites), []).append({
            "engagement_id": e.id, "audit_id": e.audit_id, "title": e.title, "start": start.isoformat(),
            "end": end.isoformat(), "quarter": e.planned_quarter, "status": e.status.value,
            "audit_status": audit.status.value if audit else None, "budget_hours": e.budget_hours,
            "lead": leads.get(e.lead_auditor_id), "progress": engagement_progress(db, audit) if audit else 0,
            "dated": bool(e.planned_start and e.planned_end)})
    milestones = [{"date": m.meeting_date.date().isoformat(), "label": f"Audit Committee ({m.meeting_type})",
                   "kind": "committee"}
                  for m in db.execute(select(CommitteeMeeting).where(
                      CommitteeMeeting.meeting_date >= lo, CommitteeMeeting.meeting_date <= hi)).scalars()]
    if plan.approved_at:
        milestones.append({"date": plan.approved_at.date().isoformat(), "label": "Plan approved", "kind": "plan"})
    ordered = sorted(lanes.items(), key=lambda kv: (kv[0] in ("No category", "Unassigned", "Unscheduled"), kv[0]))
    return {"start": lo.isoformat(), "end": hi.isoformat(), "group": group,
            "lanes": [{"label": k, "items": sorted(v, key=lambda i: i["start"])} for k, v in ordered],
            "milestones": sorted(milestones, key=lambda m: m["date"])}


@router.get("/api/assurance-plans/{plan_id}/includable-audits")
def includable_audits(plan_id: int, q: str | None = Query(None, max_length=100), db: DBSession = Depends(get_db),
                      user: User = Staff) -> list[dict]:
    """Audits not on any plan (and not closed), for the Include audits dialog."""
    _plan_or_404(db, plan_id)
    linked = set(db.execute(select(PlanEngagement.audit_id).where(PlanEngagement.audit_id.is_not(None))).scalars())
    audits = visible(db, user, "audit", list(db.execute(select(Audit).where(Audit.status != AuditStatus.Closed)
                                                         .order_by(Audit.id.desc())).scalars()))
    leads = dict(db.execute(select(AuditTeamMember.audit_id, AuditTeamMember.user_id).where(
        AuditTeamMember.team_role == "Lead auditor")).all())
    names = {u.id: u.full_name or u.username for u in db.execute(select(User).where(User.id.in_(
        list(leads.values()) or [0]))).scalars()}
    out = []
    for a in audits:
        if a.id in linked:
            continue
        ref = f"AUD-{a.id:04d}"
        if q and q.lower() not in f"{ref} {a.title} {a.audit_type or ''}".lower():
            continue
        out.append({"id": a.id, "ref": ref, "title": a.title, "audit_type": a.audit_type, "status": a.status.value,
                    "lead": names.get(leads.get(a.id))})
    return out


class IncludeIn(BaseModel):
    audit_ids: list[int] = Field(..., min_length=1, max_length=100)
    quarter: str = Field("Q1", pattern="^Q[1-4]$")
    reason: str = Field("", max_length=2000)


class ExcludeIn(BaseModel):
    reason: str = Field("", max_length=2000)


def _may_change(plan: AssurancePlan, user: User, reason: str) -> bool:
    """True when the change must be logged as a plan change (approved plan)."""
    if plan.status == PlanStatus.Closed:
        raise _conflict(f"The {plan.fiscal_year} Assurance Plan is closed")
    if plan.status == PlanStatus.Approved:
        if not has_perm(user, "plan.amend"):
            raise _conflict("The plan is approved; only the GM Audit can include or exclude audits")
        if not reason.strip():
            raise field_error("reason", "give the reason for changing the approved plan")
        return True
    return False


@router.post("/api/assurance-plans/{plan_id}/include")
def include_audits(plan_id: int, payload: IncludeIn, request: Request, db: DBSession = Depends(get_db),
                   user: User = Staff) -> dict:
    plan = _plan_or_404(db, plan_id)
    logged = _may_change(plan, user, payload.reason)
    allowed = {a["id"] for a in includable_audits(plan_id, None, db, user)}
    bad = [i for i in payload.audit_ids if i not in allowed]
    if bad:
        raise field_error("audit_ids", "some audits are already on a plan, closed or outside your scope")
    added = []
    for aid in dict.fromkeys(payload.audit_ids):
        a = db.get(Audit, aid)
        lead = db.execute(select(AuditTeamMember.user_id).where(AuditTeamMember.audit_id == aid,
                                                                 AuditTeamMember.team_role == "Lead auditor")).first()
        e = PlanEngagement(plan_id=plan.id, entity_unit_id=a.entity_unit_id, title=a.title,
                           rationale="Included existing audit", planned_quarter=payload.quarter, budget_hours=0,
                           lead_auditor_id=lead[0] if lead else None, site_entity_id=a.port_entity_id,
                           status=EngagementStatus.Started, audit_id=a.id, created_by=user.id)
        db.add(e)
        db.flush()
        a.plan_id = plan.id
        added.append(e.id)
        if logged:
            db.add(PlanChange(plan_id=plan.id, engagement_id=e.id, change_type="Added",
                              description=f"Existing audit AUD-{a.id:04d} {a.title} included", reason=payload.reason,
                              changed_by=user.id))
        _history(db, plan.id, user, f"AUDIT INCLUDED AUD-{a.id:04d} {a.title}", request)
    log_action(db, user_id=user.id, action=f"PLAN_INCLUDE plan={plan.id} audits={payload.audit_ids}", request=request)
    db.commit()
    return {"included": len(added), "engagement_ids": added}


@router.post("/api/plan-engagements/{eng_id}/exclude")
def exclude_audit(eng_id: int, payload: ExcludeIn, request: Request, db: DBSession = Depends(get_db),
                  user: User = Staff) -> dict:
    eng = _engagement_or_404(db, eng_id)
    plan = eng.plan
    logged = _may_change(plan, user, payload.reason)
    if eng.audit_id is None:
        raise _conflict("Only an engagement with an audit can be excluded; remove or cancel a planned one instead")
    audit = db.get(Audit, eng.audit_id)
    if audit is not None and audit.plan_id == plan.id:
        audit.plan_id = None
    title = eng.title
    if logged:
        db.add(PlanChange(plan_id=plan.id, engagement_id=eng.id, change_type="Removed",
                          description=f"Audit {title} excluded from the plan", reason=payload.reason,
                          changed_by=user.id))
        eng.status, eng.audit_id = EngagementStatus.Cancelled, None
    else:
        db.delete(eng)
    _history(db, plan.id, user, f"AUDIT EXCLUDED {title}", request)
    log_action(db, user_id=user.id, action=f"PLAN_EXCLUDE engagement={eng_id}", request=request)
    db.commit()
    return {"excluded": title}
