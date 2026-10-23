"""Assurance plan coverage grid (HighBond Assurance Plan > Entities tab).

Rows are the plan's engagements (Project | Status | Hours | Progress), columns are the auditable entities, with a tick
where an engagement covers an entity. Filters: entity category (location), parent entity, and "Entities not covered".
Overall progress is the average of the engagements' progress; planned hours are compared with the hours available
(the plan's total budget): the bar is green up to the available hours and red above.

Progress of an engagement is counted from its phases, the way GPHA INTERNAL AUDIT WORKSPACE counts project
progress: each phase scores
Not started 0, In process 1, Completed 2, and progress = total / (2 x number of phases). The phases are the planning
memo, each fieldwork step (process narratives, risk & control matrix, walkthroughs, test plan and testing; or work
programme and execute procedures) and the report. A closed audit is 100 %; an engagement not yet started is 0 %.
Cancelled engagements are listed but left out of the averages and hours.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.database import get_db
from app.core.deps import require_role
from app.core.enums import AuditStatus, EngagementStatus, Role
from app.domains.assurance.planning.models import AssurancePlan, EntityUnit, Location
from app.domains.audit.audits.models import Audit
from app.platform.users.models import User

router = APIRouter(tags=["planning"])
Staff = Depends(require_role(Role.Admin, Role.Auditor))

def _score(done: int, total: int) -> int:
    """0 not started, 1 in process, 2 completed."""
    if not total or not done:
        return 0
    return 2 if done >= total else 1


def phase_scores(db: DBSession, audit: Audit) -> list[tuple[str, int]]:
    """The phases of an audit with their scores (0, 1 or 2)."""
    from app.domains.audit.fieldwork.router import WORKPLAN, _steps
    from app.domains.audit.memos.models import PlanningMemo
    from app.domains.audit.reports.models import AuditReport

    memo = db.execute(select(PlanningMemo.status).where(PlanningMemo.audit_id == audit.id)).scalar()
    report = db.execute(select(AuditReport.status).where(AuditReport.audit_id == audit.id)).scalar()
    st = _steps(db, audit.id)
    phases = [("Planning memo", 0 if memo is None else 2 if memo == "Approved" else 1)]
    if audit.workflow == WORKPLAN:
        phases += [("Work programme", 2 if st["procedures"] else 1 if st["objectives"] else 0),
                   ("Execute procedures", _score(st["procedures_done"], st["procedures"]))]
    else:
        phases += [("Process narratives", 2 if st["narratives"] else 0),
                   ("Risk & control matrix", 0 if not st["controls"] else 1 if st["risks_without_controls"] else 2),
                   ("Walkthroughs", _score(st["walked"], st["controls"])),
                   ("Test plan", _score(st["key_planned"], st["key_controls"])),
                   ("Testing", _score(st["tests_done"], st["tests"]))]
    status_value = getattr(report, "value", report)
    phases.append(("Report", 0 if report is None else 2 if status_value == "Issued" else 1))
    return phases


def engagement_progress(db: DBSession, audit: Audit | None) -> int:
    if audit is None:
        return 0
    if audit.status == AuditStatus.Closed:
        return 100
    phases = phase_scores(db, audit)
    return round(100 * sum(v for _, v in phases) / (2 * len(phases)))


@router.get("/api/assurance-plans/{plan_id}/coverage")
def plan_coverage(
    plan_id: int,
    category: int | None = Query(None, description="Entity category (location) id"),
    not_covered: bool = False,
    db: DBSession = Depends(get_db),
    _: User = Staff,
) -> dict:
    plan = db.get(AssurancePlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assurance plan not found")
    from app.domains.audit.capacity.models import TimeEntry

    engagements = list(plan.engagements)
    audit_ids = [e.audit_id for e in engagements if e.audit_id]
    audits = {a.id: a for a in db.execute(select(Audit).where(Audit.id.in_(audit_ids or [0]))).scalars()}
    actual = dict(db.execute(select(TimeEntry.audit_id, func.sum(TimeEntry.hours))
                             .where(TimeEntry.audit_id.in_(audit_ids or [0])).group_by(TimeEntry.audit_id)).all())
    leads = {u.id: u.full_name or u.username for u in db.execute(select(User).where(User.id.in_(
        [e.lead_auditor_id for e in engagements if e.lead_auditor_id] or [0]))).scalars()}

    units = list(db.execute(select(EntityUnit).join(Location, Location.id == EntityUnit.location_id)
                            .where(EntityUnit.is_active.is_(True)).order_by(Location.name, EntityUnit.code)).scalars())
    from app.domains.assurance.planning.projects import engagement_entity_ids

    covers = {e.id: engagement_entity_ids(db, e) for e in engagements}
    live = [e for e in engagements if e.status != EngagementStatus.Cancelled]
    covered_ids = set().union(*(covers[e.id] for e in live)) if live else set()
    uncovered = [u for u in units if u.id not in covered_ids]
    shown = [u for u in units if (category is None or u.location_id == category)
             and (not not_covered or u.id not in covered_ids)]

    rows = []
    for e in engagements:
        audit = audits.get(e.audit_id) if e.audit_id else None
        progress = engagement_progress(db, audit)
        rows.append({
            "engagement_id": e.id, "title": e.title, "quarter": e.planned_quarter,
            "status": audit.status.value if audit else e.status.value, "engagement_status": e.status.value,
            "audit_id": audit.id if audit else None, "lead": leads.get(e.lead_auditor_id),
            "hours": e.budget_hours, "actual_hours": round(float(actual.get(e.audit_id, 0) or 0), 1),
            "progress": progress, "cancelled": e.status == EngagementStatus.Cancelled,
            "entity_unit_id": e.entity_unit_id, "entity_ids": sorted(covers[e.id]),
        })
    counted = [r for r in rows if not r["cancelled"]]
    planned_hours = sum(r["hours"] for r in counted)
    available = plan.total_budget_hours or 0
    return {
        "plan_id": plan.id, "plan_ref": plan.plan_ref, "fiscal_year": plan.fiscal_year,
        "overall_progress": round(sum(r["progress"] for r in counted) / len(counted)) if counted else 0,
        "hours": {"planned": planned_hours, "available": available,
                  "actual": round(sum(r["actual_hours"] for r in counted), 1),
                  "over": max(0, planned_hours - available) if available else 0},
        "entities": [{"id": u.id, "code": u.code, "name": u.name, "location_id": u.location_id,
                      "location": u.location.name, "risk_score": u.risk_score, "risk": u.effective_rating,
                      "covered": u.id in covered_ids} for u in shown],
        "categories": [{"id": loc.id, "name": loc.name} for loc in
                       db.execute(select(Location).where(Location.is_active.is_(True)).order_by(Location.name))
                       .scalars()],
        "not_covered": len(uncovered),
        "not_covered_high": sum(1 for u in uncovered if u.effective_rating == "High"),
        "engagements": rows,
    }
