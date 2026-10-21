"""Next-cycle planning signals (PROJECTBLUEPRINT 4.5 and the Risk-Based Assurance Planning walkthrough).

At cycle close, planners review what the finished cycle leaves behind: strategic risks with high residual
exposure and weak or missing assurance, high-risk entities the plan did not cover, open and overdue actions, and
engagements that were deferred or cancelled. This is the input to a management decision. Nothing is created
automatically; planners choose what to carry into the next Assurance Plan.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.database import get_db
from app.core.deps import ensure_perm, require_role
from app.core.enums import CapaStatus, EngagementStatus, FindingStatus, RiskRating, Role
from app.domains.assurance.planning.models import AssurancePlan
from app.platform.users.models import User

router = APIRouter(tags=["planning"])
Staff = Depends(require_role(Role.Admin, Role.Auditor))


def _signal(a: dict) -> str:
    c = a["controls"]
    if not a["objectives"]:
        return "No linked assurance"
    if c["failing"]:
        return "Failing controls"
    if c["total"] and not c["passing"]:
        return "Not yet tested"
    if a["issues"]["open"]:
        return "Open issues"
    if c["not_tested"]:
        return "Partly tested"
    return "Covered"


@router.get("/api/assurance-plans/next-cycle-signals")
def next_cycle_signals(fiscal_year: int | None = Query(None, ge=2000, le=2100), db: DBSession = Depends(get_db),
                       user: User = Staff) -> dict:
    from app.core.access import staff_audit_scope
    from app.domains.assurance.planning.router import _summary
    from app.domains.audit.audits.models import Audit, Finding
    from app.domains.grc.common import band
    from app.domains.grc.risk.assurance import risk_assurance
    from app.domains.grc.risk.models import EnterpriseRisk
    from app.domains.issues.capa.models import Capa

    ensure_perm(user, "plan.prepare", "plan.amend", "plan.approve", "oversight.portfolio", "governance.view")
    target = fiscal_year or date.today().year + 1
    scope = staff_audit_scope(db, user)
    basis = db.execute(select(AssurancePlan).where(AssurancePlan.fiscal_year < target)
                       .order_by(AssurancePlan.fiscal_year.desc())).scalars().first()

    risks = []
    for r in db.execute(select(EnterpriseRisk).where(EnterpriseRisk.status == "Active")).scalars():
        appetite = (r.target_likelihood or 0) * (r.target_impact or 0)
        above = bool(appetite and r.residual_score > appetite)
        level = band(r.residual_score)
        if level != "High" and not above:
            continue
        a = risk_assurance(db, r.id, scope)
        risks.append({"id": r.id, "ref": r.ref, "title": r.title, "category": r.category, "residual_level": level,
                      "residual_score": r.residual_score, "above_target": above,
                      "overall_assurance": a["overall_assurance"], "controls": {k: a["controls"][k] for k in (
                          "passing", "failing", "not_tested", "total")},
                      "open_issues": a["issues"]["open"], "linked_objectives": len(a["objectives"]),
                      "signal": _signal(a)})
    order = {"No linked assurance": 0, "Failing controls": 1, "Not yet tested": 2, "Open issues": 3,
             "Partly tested": 4, "Covered": 5}
    risks.sort(key=lambda x: (order[x["signal"]], -x["residual_score"]))

    uncovered = []
    deferred = []
    if basis is not None:
        uncovered = [u.model_dump() for u in _summary(db, basis).uncovered_high_risk]
        deferred = [{"id": e.id, "title": e.title, "quarter": e.planned_quarter, "status": e.status.value,
                     "hours": e.budget_hours} for e in basis.engagements
                    if e.status in (EngagementStatus.Planned, EngagementStatus.Cancelled)]

    visible = None if scope is None else scope
    today = date.today()
    capas = []
    for c in db.execute(select(Capa).where(Capa.status != CapaStatus.Closed)).scalars():
        audit_id = None
        if c.source_type == "finding" and c.source_id:
            f = db.get(Finding, c.source_id)
            audit_id = f.audit_id if f else None
        if visible is not None and (audit_id is None or audit_id not in visible):
            continue
        overdue = bool(c.due_date and c.due_date.date() < today)
        capas.append({"id": c.id, "ref": c.capa_ref, "title": c.title, "severity": c.severity.value,
                      "due_date": c.due_date, "overdue": overdue, "status": c.status.value})
    high_open = 0
    for f in db.execute(select(Finding).where(Finding.status != FindingStatus.Closed,
                                              Finding.risk_rating == RiskRating.High)).scalars():
        if visible is None or f.audit_id in visible:
            high_open += 1
    open_audits = 0
    if basis is not None:
        ids = [e.audit_id for e in basis.engagements if e.audit_id]
        open_audits = sum(1 for a in db.execute(select(Audit).where(Audit.id.in_(ids or [0]))).scalars()
                          if a.status.value != "Closed" and (visible is None or a.id in visible))
    return {
        "target_fiscal_year": target,
        "basis_plan": {"id": basis.id, "ref": basis.plan_ref, "fiscal_year": basis.fiscal_year,
                       "status": basis.status.value} if basis else None,
        "risks": risks,
        "uncovered_entities": uncovered,
        "deferred_engagements": deferred,
        "carry_forward": {"open_actions": len(capas), "overdue_actions": sum(1 for c in capas if c["overdue"]),
                          "open_high_findings": high_open, "open_audits": open_audits,
                          "overdue": [c for c in capas if c["overdue"]][:50]},
        "note": "Planning signals support a management decision. Nothing is added to a plan automatically.",
    }
