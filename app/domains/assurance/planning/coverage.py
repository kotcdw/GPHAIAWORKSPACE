"""Assurance plan coverage grid (HighBond Assurance Plan > Entities tab).

Rows are the plan's engagements (Project | Status | Hours | Progress), columns are the auditable entities, with a tick
where an engagement covers an entity. Filters: entity category (location), parent entity, and "Entities not covered".
Overall progress is the average of the engagements' progress; planned hours are compared with the hours available
(the plan's total budget): the bar is green up to the available hours and red above.

Progress of an engagement (recorded decision, see mainBLUEPRINT.md): Not started 0 %, audit Planned 10 %, In Progress
25 % plus up to 50 % for the share of fieldwork (procedures or key-control tests) signed off as prepared or reviewed,
Review 85 %, Closed 100 %. Cancelled engagements are listed but left out of the averages and hours.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.appconfig import cfg
from app.core.database import get_db
from app.core.deps import require_role
from app.core.enums import AuditStatus, EngagementStatus, Role, TestStatus, TestType
from app.domains.assurance.planning.models import AssurancePlan, EntityUnit, Location
from app.domains.audit.audits.models import Audit
from app.platform.users.models import User

router = APIRouter(tags=["planning"])
Staff = Depends(require_role(Role.Admin, Role.Auditor))

_PHASE = {AuditStatus.Planned: 10, AuditStatus.Review: 85, AuditStatus.Closed: 100}


def _fieldwork_share(db: DBSession, audit: Audit) -> float:
    from app.domains.audit.rcm.models import Control, ControlTest, Objective, Procedure

    objs = select(Objective.id).where(Objective.audit_id == audit.id)
    if audit.workflow == "Workplan":
        rows = db.execute(select(Procedure.status).where(Procedure.objective_id.in_(objs))).scalars().all()
        done = sum(1 for s in rows if s in ("Prepared", "Reviewed"))
    else:
        ctls = select(Control.id).where(Control.objective_id.in_(objs), Control.is_key.is_(True))
        rows = db.execute(select(ControlTest.status).where(
            ControlTest.control_id.in_(ctls), ControlTest.in_scope.is_(True),
            ControlTest.test_type == TestType.OperatingEffectiveness)).scalars().all()
        done = sum(1 for s in rows if s in (TestStatus.Completed, TestStatus.Reviewed))
    return done / len(rows) if rows else 0.0


def engagement_progress(db: DBSession, audit: Audit | None) -> int:
    if audit is None:
        return 0
    if audit.status == AuditStatus.InProgress:
        return round(25 + 50 * _fieldwork_share(db, audit))
    return _PHASE.get(audit.status, 0)


def _rating(score: int) -> str:
    if score >= int(cfg("risk_high_threshold")):
        return "High"
    if score >= int(cfg("risk_medium_threshold")):
        return "Medium"
    return "Low"


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
    live = [e for e in engagements if e.status != EngagementStatus.Cancelled]
    covered_ids = {e.entity_unit_id for e in live if e.entity_unit_id}
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
            "entity_unit_id": e.entity_unit_id,
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
                      "location": u.location.name, "risk_score": u.risk_score, "risk": _rating(u.risk_score),
                      "covered": u.id in covered_ids} for u in shown],
        "categories": [{"id": loc.id, "name": loc.name} for loc in
                       db.execute(select(Location).where(Location.is_active.is_(True)).order_by(Location.name))
                       .scalars()],
        "not_covered": len(uncovered),
        "not_covered_high": sum(1 for u in uncovered if _rating(u.risk_score) == "High"),
        "engagements": rows,
    }
