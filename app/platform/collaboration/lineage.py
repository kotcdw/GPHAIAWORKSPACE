"""Where a record sits in the data flow of the assurance cycle: what it came from and what it feeds.

Risk (Risk Manager) -> auditable entity and risk assessment -> Assurance Plan -> audit -> controls and tests ->
issues -> actions -> report -> quality review. Only records the person may read are listed.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.platform.collaboration.records import LABEL, can_read, name
from app.platform.users.models import User


def _node(record_type: str, obj, *, note: str = "", audit_id: int | None = None, tab: str | None = None,  # noqa: ANN001
          status: str | None = None) -> dict:
    ref, title = name(record_type, obj)
    st = getattr(obj, "status", None) if status is None else status
    return {"type": record_type, "id": obj.id, "kind": LABEL.get(record_type, record_type), "ref": ref,
            "title": title, "note": note, "status": getattr(st, "value", st), "audit_id": audit_id, "tab": tab}


def _audit_flow(db: DBSession, audit) -> tuple[list[dict], list[dict]]:  # noqa: ANN001, C901
    from app.domains.assurance.planning.models import AssurancePlan, EntityUnit
    from app.domains.assurance.qaip.models import QualityReview
    from app.domains.audit.audits.models import Finding
    from app.domains.audit.rcm.models import Objective
    from app.domains.audit.rcm.models import Risk as RcmRisk
    from app.domains.audit.reports.models import AuditReport
    from app.domains.grc.risk.models import EnterpriseRisk, RiskTreatment
    from app.domains.issues.capa.models import Capa

    came, feeds = [], []
    if audit.plan_id and (p := db.get(AssurancePlan, audit.plan_id)):
        came.append(_node("assurance_plan", p))
    if audit.entity_unit_id and (u := db.get(EntityUnit, audit.entity_unit_id)):
        came.append(_node("entity_unit", u, status=None if u.is_active else "Inactive"))
    objective_ids = list(db.execute(select(Objective.id).where(Objective.audit_id == audit.id)).scalars())
    if objective_ids:
        erm = set(db.execute(select(RiskTreatment.risk_id).where(RiskTreatment.objective_id.in_(objective_ids)))
                  .scalars())
        erm |= {r for r in db.execute(select(RcmRisk.enterprise_risk_id).where(
            RcmRisk.objective_id.in_(objective_ids), RcmRisk.enterprise_risk_id.is_not(None))).scalars()}
        for rid in sorted(erm):
            if (r := db.get(EnterpriseRisk, rid)) is not None:
                came.append(_node("erm_risk", r, note="treated by this audit"))
    findings = list(db.execute(select(Finding).where(Finding.audit_id == audit.id).order_by(Finding.id)).scalars())
    for f in findings:
        feeds.append(_node("finding", f, note=f.risk_rating.value))
    fids = [f.id for f in findings]
    if fids:
        for c in db.execute(select(Capa).where(Capa.source_type == "finding", Capa.source_id.in_(fids))).scalars():
            feeds.append(_node("capa", c))
    if (rep := db.execute(select(AuditReport).where(AuditReport.audit_id == audit.id)).scalar_one_or_none()):
        feeds.append(_node("audit_report", rep))
    if (q := db.execute(select(QualityReview).where(QualityReview.audit_id == audit.id)).scalar_one_or_none()):
        feeds.append({"type": "quality_review", "id": q.id, "kind": LABEL["quality_review"], "ref": f"QR-{q.id:04d}",
                      "title": "Quality review", "note": f"{q.score}%" if q.score is not None else "",
                      "status": "Completed" if q.completed_at else "In progress", "audit_id": audit.id,
                      "tab": "quality"})
    return came, feeds


def lineage(db: DBSession, user: User, record_type: str, obj) -> dict:  # noqa: ANN001, C901
    from app.domains.assurance.planning.models import AssurancePlan, EngagementEntity, EntityUnit, PlanEngagement
    from app.domains.audit.audits.models import Audit, Finding
    from app.domains.audit.rcm.models import Control, ControlTest, Objective
    from app.domains.audit.rcm.models import Risk as RcmRisk
    from app.domains.audit.reports.models import AuditReport
    from app.domains.issues.capa.models import Capa

    came: list[dict] = []
    feeds: list[dict] = []
    if record_type == "audit":
        came, feeds = _audit_flow(db, obj)
    elif record_type == "finding":
        audit = db.get(Audit, obj.audit_id)
        if audit:
            came.append(_node("audit", audit))
        if obj.test_id and (t := db.get(ControlTest, obj.test_id)):
            came.append(_node("control_test", t, audit_id=obj.audit_id, tab="fieldwork"))
        elif obj.control_id and (c := db.get(Control, obj.control_id)):
            came.append({**_node("control_test", c, audit_id=obj.audit_id, tab="fieldwork"), "kind": "Control",
                         "title": c.title})
        for c in db.execute(select(Capa).where(Capa.source_type == "finding", Capa.source_id == obj.id)).scalars():
            feeds.append(_node("capa", c))
        if (rep := db.execute(select(AuditReport).where(AuditReport.audit_id == obj.audit_id)).scalar_one_or_none()):
            feeds.append(_node("audit_report", rep))
    elif record_type == "capa":
        if obj.source_type == "finding" and obj.source_id and (f := db.get(Finding, obj.source_id)):
            came.append(_node("finding", f, note=f.risk_rating.value))
            if (a := db.get(Audit, f.audit_id)):
                came.append(_node("audit", a))
            feeds.append({**_node("finding", f), "note": "closes when its actions are validated"})
    elif record_type == "audit_report":
        if (a := db.get(Audit, obj.audit_id)):
            came.append(_node("audit", a))
            for f in db.execute(select(Finding).where(Finding.audit_id == a.id)).scalars():
                came.append(_node("finding", f, note=f.risk_rating.value))
    elif record_type == "assurance_plan":
        unit_ids = set(db.execute(select(PlanEngagement.entity_unit_id).where(
            PlanEngagement.plan_id == obj.id, PlanEngagement.entity_unit_id.is_not(None))).scalars())
        unit_ids |= set(db.execute(select(EngagementEntity.entity_unit_id).join(
            PlanEngagement, PlanEngagement.id == EngagementEntity.engagement_id)
            .where(PlanEngagement.plan_id == obj.id)).scalars())
        for u in db.execute(select(EntityUnit).where(EntityUnit.id.in_(unit_ids or {0})).order_by(EntityUnit.code)
                            ).scalars():
            came.append(_node("entity_unit", u, status=None if u.is_active else "Inactive"))
        aids = set(db.execute(select(Audit.id).where(Audit.plan_id == obj.id)).scalars())
        aids |= set(db.execute(select(PlanEngagement.audit_id).where(
            PlanEngagement.plan_id == obj.id, PlanEngagement.audit_id.is_not(None))).scalars())
        for a in db.execute(select(Audit).where(Audit.id.in_(aids or {0})).order_by(Audit.id)).scalars():
            feeds.append(_node("audit", a))
    elif record_type == "entity_unit":
        from app.domains.assurance.universe.models import AuditRiskAssessment

        if obj.assessment_id and (ra := db.get(AuditRiskAssessment, obj.assessment_id)):
            came.append(_node("risk_assessment", ra, note=obj.assessed_rating or ""))
        plan_ids = set(db.execute(select(PlanEngagement.plan_id).where(PlanEngagement.entity_unit_id == obj.id))
                       .scalars())
        plan_ids |= set(db.execute(select(PlanEngagement.plan_id).join(
            EngagementEntity, EngagementEntity.engagement_id == PlanEngagement.id)
            .where(EngagementEntity.entity_unit_id == obj.id)).scalars())
        for p in db.execute(select(AssurancePlan).where(AssurancePlan.id.in_(plan_ids or {0}))).scalars():
            feeds.append(_node("assurance_plan", p))
        for a in db.execute(select(Audit).where(Audit.entity_unit_id == obj.id).order_by(Audit.id)).scalars():
            feeds.append(_node("audit", a))
    elif record_type == "risk_assessment":
        from app.domains.assurance.planning.models import EntityUnit as EU

        if obj.plan_id and (p := db.get(AssurancePlan, obj.plan_id)):
            feeds.append(_node("assurance_plan", p))
        for u in db.execute(select(EU).where(EU.assessment_id == obj.id).order_by(EU.code)).scalars():
            feeds.append(_node("entity_unit", u, note=u.assessed_rating or ""))
    elif record_type == "erm_risk":
        from app.domains.grc.risk.models import RiskTreatment, StrategicObjective

        if obj.objective_id and (so := db.get(StrategicObjective, obj.objective_id)):
            came.append({"type": "strategic_objective", "id": so.id, "kind": LABEL["strategic_objective"],
                         "ref": f"SO-{so.id:03d}", "title": so.title, "note": "", "status": None, "audit_id": None,
                         "tab": None})
        oids = set(db.execute(select(RiskTreatment.objective_id).where(
            RiskTreatment.risk_id == obj.id, RiskTreatment.objective_id.is_not(None))).scalars())
        oids |= set(db.execute(select(RcmRisk.objective_id).where(RcmRisk.enterprise_risk_id == obj.id)).scalars())
        aids = set(db.execute(select(Objective.audit_id).where(Objective.id.in_(oids or {0}))).scalars())
        for a in db.execute(select(Audit).where(Audit.id.in_(aids or {0})).order_by(Audit.id)).scalars():
            feeds.append(_node("audit", a, note="assurance on this risk"))
    readable = _reader(db, user)
    return {"came_from": [n for n in came if readable(n)], "feeds_into": [n for n in feeds if readable(n)]}


def _reader(db: DBSession, user: User):  # noqa: ANN202
    from app.platform.collaboration.records import model_for

    cache: dict[tuple[str, int], bool] = {}

    def ok(n: dict) -> bool:
        key = (n["type"], n["id"])
        if key not in cache:
            if n["type"] in ("control_test", "quality_review", "strategic_objective"):
                cache[key] = user.role.value in ("Admin", "Auditor")
            else:
                model = model_for(n["type"])
                cache[key] = model is not None and can_read(db, user, n["type"], db.get(model, n["id"]))
        return cache[key]

    return ok
