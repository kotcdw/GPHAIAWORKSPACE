"""Risk Manager & Strategy API: strategic objectives, the enterprise risk register with dated assessments,
heat maps, and key risk indicators with readings.

Risk owners (business users) may assess their own risks and record readings for their KRIs; everything else
needs the Risk Manager permission.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session as DBSession

from app.core.appconfig import cfg
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user
from app.core.enums import utcnow
from app.core.refs import next_reference
from app.domains.grc import links
from app.domains.grc.common import (
    GRC_PERMS,
    Viewer,
    add_months,
    band,
    can,
    check_entity,
    check_user,
    editor,
    entity_name,
    in_list,
    name_of,
)
from app.domains.grc.risk.models import (
    KRI_FREQUENCIES,
    EnterpriseRisk,
    KeyRiskIndicator,
    KriReading,
    RiskAssessment,
    StrategicObjective,
)
from app.platform.users.models import User

router = APIRouter(prefix="/api/grc", tags=["risk & compliance"])
RiskEditor = editor("grc.risk")
Score = Field(ge=1, le=5)


class ObjectiveIn(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(default="", max_length=10000)
    period: str = Field(default="", max_length=40)
    owner_id: int | None = None
    entity_id: int | None = None
    status: Literal["Active", "Achieved", "Retired"] = "Active"


class RiskIn(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(default="", max_length=20000)
    cause: str = Field(default="", max_length=10000)
    consequence: str = Field(default="", max_length=10000)
    category: str = Field(default="", max_length=100)
    objective_id: int | None = None
    entity_id: int | None = None
    owner_id: int | None = None
    inherent_likelihood: int = Score
    inherent_impact: int = Score
    residual_likelihood: int = Score
    residual_impact: int = Score
    target_likelihood: int | None = Field(default=None, ge=1, le=5)
    target_impact: int | None = Field(default=None, ge=1, le=5)
    appetite: str = Field(default="", max_length=40)
    treatment: str = Field(default="", max_length=40)
    treatment_plan: str = Field(default="", max_length=20000)
    status: Literal["Draft", "Active", "Closed"] = "Active"
    control_ids: list[int] | None = Field(default=None, max_length=200)
    unit_ids: list[int] | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _residual_not_above_inherent(self) -> RiskIn:
        if self.residual_likelihood * self.residual_impact > self.inherent_likelihood * self.inherent_impact:
            raise ValueError("Residual risk cannot be higher than inherent risk")
        return self


class AssessIn(BaseModel):
    inherent_likelihood: int = Score
    inherent_impact: int = Score
    residual_likelihood: int = Score
    residual_impact: int = Score
    control_effectiveness: Literal["", "Effective", "Partially effective", "Ineffective", "Not tested"] = ""
    comment: str = Field(default="", max_length=10000)

    @model_validator(mode="after")
    def _residual_not_above_inherent(self) -> AssessIn:
        if self.residual_likelihood * self.residual_impact > self.inherent_likelihood * self.inherent_impact:
            raise ValueError("Residual risk cannot be higher than inherent risk")
        return self


class KriIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    unit: str = Field(default="", max_length=40)
    higher_is_worse: bool = True
    amber_at: float
    red_at: float
    frequency: str = "Monthly"
    owner_id: int | None = None
    active: bool = True

    @model_validator(mode="after")
    def _thresholds(self) -> KriIn:
        if self.frequency not in KRI_FREQUENCIES:
            raise ValueError(f"Frequency must be one of {', '.join(KRI_FREQUENCIES)}")
        if self.higher_is_worse and self.red_at < self.amber_at:
            raise ValueError("When higher is worse, the red threshold must be at or above the amber threshold")
        if not self.higher_is_worse and self.red_at > self.amber_at:
            raise ValueError("When lower is worse, the red threshold must be at or below the amber threshold")
        return self


class ReadingIn(BaseModel):
    period_date: date
    value: float
    comment: str = Field(default="", max_length=5000)


# ---------------------------------------------------------------- helpers

def _objective_out(db: DBSession, o: StrategicObjective) -> dict:
    risks = list(db.execute(select(EnterpriseRisk).where(EnterpriseRisk.objective_id == o.id,
                                                         EnterpriseRisk.status != "Closed")).scalars())
    return {"id": o.id, "ref": o.ref, "title": o.title, "description": o.description, "period": o.period,
            "owner_id": o.owner_id, "owner": name_of(db, o.owner_id), "entity_id": o.entity_id,
            "entity": entity_name(db, o.entity_id), "status": o.status, "risks": len(risks),
            "high_risks": sum(1 for r in risks if band(r.residual_score) == "High"),
            "worst_residual": max((r.residual_score for r in risks), default=0)}


def _latest(db: DBSession, kri_id: int) -> KriReading | None:
    return db.execute(select(KriReading).where(KriReading.kri_id == kri_id)
                      .order_by(KriReading.period_date.desc(), KriReading.id.desc()).limit(1)).scalar_one_or_none()


def _kri_out(db: DBSession, k: KeyRiskIndicator, history: bool = False) -> dict:
    last = _latest(db, k.id)
    out = {"id": k.id, "risk_id": k.risk_id, "name": k.name, "unit": k.unit, "higher_is_worse": k.higher_is_worse,
           "amber_at": k.amber_at, "red_at": k.red_at, "frequency": k.frequency, "owner_id": k.owner_id,
           "owner": name_of(db, k.owner_id), "active": k.active, "drives": k.drives,
           "amber_step": k.amber_step, "red_step": k.red_step,
           "latest": {"period_date": last.period_date, "value": last.value} if last else None,
           "rag": k.rag(last.value if last else None)}
    if history:
        rows = db.execute(select(KriReading).where(KriReading.kri_id == k.id)
                          .order_by(KriReading.period_date.desc()).limit(24)).scalars()
        out["readings"] = [{"id": r.id, "period_date": r.period_date, "value": r.value, "comment": r.comment,
                            "rag": k.rag(r.value), "by": name_of(db, r.recorded_by)} for r in rows]
    return out


def _overdue(r: EnterpriseRisk) -> bool:
    return r.status == "Active" and (r.next_review_date is None or r.next_review_date < date.today())


def _risk_out(db: DBSession, r: EnterpriseRisk, full: bool = False) -> dict:
    obj = db.get(StrategicObjective, r.objective_id) if r.objective_id else None
    out = {"id": r.id, "ref": r.ref, "title": r.title, "category": r.category, "status": r.status,
           "objective_id": r.objective_id, "objective": f"{obj.ref} {obj.title}" if obj else None,
           "entity_id": r.entity_id, "entity": entity_name(db, r.entity_id), "owner_id": r.owner_id,
           "owner": name_of(db, r.owner_id),
           "inherent_likelihood": r.inherent_likelihood, "inherent_impact": r.inherent_impact,
           "residual_likelihood": r.residual_likelihood, "residual_impact": r.residual_impact,
           "target_likelihood": r.target_likelihood, "target_impact": r.target_impact,
           "inherent_score": r.inherent_score, "residual_score": r.residual_score,
           "inherent_level": band(r.inherent_score), "residual_level": band(r.residual_score),
           "appetite": r.appetite, "treatment": r.treatment, "last_assessed_at": r.last_assessed_at,
           "next_review_date": r.next_review_date, "review_overdue": _overdue(r),
           "above_target": bool(r.target_likelihood and r.target_impact
                                and r.residual_score > r.target_likelihood * r.target_impact)}
    if full:
        out.update({"description": r.description, "cause": r.cause, "consequence": r.consequence,
                    "treatment_plan": r.treatment_plan, "created_at": r.created_at, "updated_at": r.updated_at})
        rows = db.execute(select(RiskAssessment).where(RiskAssessment.risk_id == r.id)
                          .order_by(RiskAssessment.assessed_at.desc(), RiskAssessment.id.desc())).scalars()
        out["assessments"] = [{"id": a.id, "inherent_score": a.inherent_likelihood * a.inherent_impact,
                               "residual_score": a.residual_likelihood * a.residual_impact,
                               "inherent_likelihood": a.inherent_likelihood, "inherent_impact": a.inherent_impact,
                               "residual_likelihood": a.residual_likelihood, "residual_impact": a.residual_impact,
                               "control_effectiveness": a.control_effectiveness, "comment": a.comment,
                               "origin": a.origin,
                               "by": name_of(db, a.assessed_by), "at": a.assessed_at} for a in rows]
        out["kris"] = [_kri_out(db, k, history=True) for k in db.execute(
            select(KeyRiskIndicator).where(KeyRiskIndicator.risk_id == r.id).order_by(KeyRiskIndicator.name))
            .scalars()]
        out["links"] = links.linked(db, "risk", r.id)
    return out


def _risk(db: DBSession, risk_id: int) -> EnterpriseRisk:
    r = db.get(EnterpriseRisk, risk_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Risk not found")
    return r


def _validate(db: DBSession, p: RiskIn | ObjectiveIn) -> None:
    check_user(db, p.owner_id)
    check_entity(db, p.entity_id)
    if isinstance(p, RiskIn) and p.objective_id is not None and db.get(StrategicObjective, p.objective_id) is None:
        raise HTTPException(status_code=422, detail="Unknown strategic objective")


def _apply(db: DBSession, r: EnterpriseRisk, p: RiskIn) -> None:
    r.title, r.description, r.cause, r.consequence = p.title.strip(), p.description, p.cause, p.consequence
    r.category = in_list(p.category, "erm_risk_categories", "Category")
    r.appetite = in_list(p.appetite, "erm_appetite_levels", "Appetite")
    r.treatment = in_list(p.treatment, "erm_treatments", "Treatment")
    r.objective_id, r.entity_id, r.owner_id = p.objective_id, p.entity_id, p.owner_id
    r.inherent_likelihood, r.inherent_impact = p.inherent_likelihood, p.inherent_impact
    r.residual_likelihood, r.residual_impact = p.residual_likelihood, p.residual_impact
    r.target_likelihood, r.target_impact = p.target_likelihood, p.target_impact
    r.treatment_plan, r.status = p.treatment_plan, p.status


def _can_assess(user: User, r: EnterpriseRisk) -> bool:
    return can(user, "grc.risk") or (r.owner_id == user.id)


# ---------------------------------------------------------------- objectives (Strategy)

@router.get("/objectives")
def list_objectives(db: DBSession = Depends(get_db), _: User = Viewer) -> list[dict]:
    rows = db.execute(select(StrategicObjective).order_by(StrategicObjective.status, StrategicObjective.ref)).scalars()
    return [_objective_out(db, o) for o in rows]


@router.post("/objectives", status_code=201)
def create_objective(payload: ObjectiveIn, request: Request, db: DBSession = Depends(get_db),
                     user: User = RiskEditor) -> dict:
    _validate(db, payload)
    o = StrategicObjective(ref=next_reference(db, "OBJ"), created_by=user.id, **payload.model_dump())
    o.title = o.title.strip()
    db.add(o)
    db.flush()
    log_action(db, user_id=user.id, action=f"OBJECTIVE_CREATE {o.ref}", request=request)
    db.commit()
    return _objective_out(db, o)


@router.put("/objectives/{objective_id}")
def update_objective(objective_id: int, payload: ObjectiveIn, request: Request, db: DBSession = Depends(get_db),
                     user: User = RiskEditor) -> dict:
    o = db.get(StrategicObjective, objective_id)
    if o is None:
        raise HTTPException(status_code=404, detail="Objective not found")
    _validate(db, payload)
    for k, v in payload.model_dump().items():
        setattr(o, k, v)
    log_action(db, user_id=user.id, action=f"OBJECTIVE_UPDATE {o.ref}", request=request)
    db.commit()
    return _objective_out(db, o)


# ---------------------------------------------------------------- register

@router.get("/risks")
def list_risks(q: str | None = None, category: str | None = None, status: str | None = None,
               owner_id: int | None = None, objective_id: int | None = None, level: str | None = None,
               mine: bool = False, overdue: bool = False, unassigned: bool = False, my_unit: bool = False,
               db: DBSession = Depends(get_db), user: User = Viewer) -> dict:
    stmt = select(EnterpriseRisk)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(EnterpriseRisk.title.like(like), EnterpriseRisk.ref.like(like),
                              EnterpriseRisk.description.like(like)))
    if category:
        stmt = stmt.where(EnterpriseRisk.category == category)
    if status:
        stmt = stmt.where(EnterpriseRisk.status == status)
    if owner_id or mine:
        stmt = stmt.where(EnterpriseRisk.owner_id == (user.id if mine else owner_id))
    if objective_id:
        stmt = stmt.where(EnterpriseRisk.objective_id == objective_id)
    if unassigned:
        stmt = stmt.where(EnterpriseRisk.owner_id.is_(None))
    if my_unit:
        from app.platform.organizations.router import Index

        scope = (set(Index(db).descendants(user.work_entity_id)) | {user.work_entity_id}) if user.work_entity_id \
            else {-1}
        stmt = stmt.where(EnterpriseRisk.entity_id.in_(scope))
    rows = list(db.execute(stmt.order_by(EnterpriseRisk.ref)).scalars())
    if overdue:
        rows = [r for r in rows if _overdue(r)]
    items = [_risk_out(db, r) for r in rows]
    if level:
        items = [i for i in items if i["residual_level"] == level]
    items.sort(key=lambda i: (-i["residual_score"], i["ref"]))
    return {"items": items, "categories": cfg("erm_risk_categories"), "appetites": cfg("erm_appetite_levels"),
            "treatments": cfg("erm_treatments"), "can_edit": can(user, "grc.risk")}


@router.get("/risks/summary")
def risk_summary(db: DBSession = Depends(get_db), _: User = Viewer) -> dict:
    risks = list(db.execute(select(EnterpriseRisk).where(EnterpriseRisk.status == "Active")).scalars())

    def grid(kind: str) -> list[list[list[int]]]:
        g = [[[] for _ in range(5)] for _ in range(5)]  # [impact-1][likelihood-1] -> risk ids
        for r in risks:
            g[getattr(r, f"{kind}_impact") - 1][getattr(r, f"{kind}_likelihood") - 1].append(r.id)
        return g

    kris = list(db.execute(select(KeyRiskIndicator).where(KeyRiskIndicator.active.is_(True))).scalars())
    rag = {"Red": 0, "Amber": 0, "Green": 0, "No data": 0}
    for k in kris:
        last = _latest(db, k.id)
        rag[k.rag(last.value if last else None)] += 1
    by_cat: dict[str, dict[str, int]] = {}
    for r in risks:
        row = by_cat.setdefault(r.category or "Uncategorised", {"High": 0, "Medium": 0, "Low": 0})
        row[band(r.residual_score)] += 1
    return {
        "active": len(risks),
        "by_level": {lvl: sum(1 for r in risks if band(r.residual_score) == lvl) for lvl in ("High", "Medium", "Low")},
        "by_category": by_cat,
        "review_overdue": sum(1 for r in risks if _overdue(r)),
        "above_target": sum(1 for r in risks if r.target_likelihood and r.target_impact
                            and r.residual_score > r.target_likelihood * r.target_impact),
        "inherent_grid": grid("inherent"), "residual_grid": grid("residual"),
        "titles": {r.id: f"{r.ref} {r.title}" for r in risks},
        "kri_rag": rag,
        "thresholds": {"high": cfg("risk_high_threshold"), "medium": cfg("risk_medium_threshold")},
    }


_PERIOD_DAYS = {"Weekly": 7, "Monthly": 31, "Quarterly": 92, "Half-yearly": 183, "Annually": 366, "Annual": 366}


@router.get("/risks/dashboard")
def risk_dashboard(category: str | None = None, db: DBSession = Depends(get_db), user: User = Viewer) -> dict:
    """Risk Manager overview: key figures, risk breakdown by category, inherent / residual heat maps, the user's
    tasks (risks they own, reviews due, indicators to record) and their unit's risks, optionally for one category."""
    from datetime import timedelta

    from app.domains.grc import links
    from app.platform.organizations.models import Organization
    from app.platform.organizations.router import Index

    stmt = select(EnterpriseRisk).where(EnterpriseRisk.status == "Active")
    if category:
        stmt = stmt.where(EnterpriseRisk.category == category)
    risks = list(db.execute(stmt).scalars())
    ids = {r.id for r in risks}

    def grid(kind: str) -> list[list[list[int]]]:
        g = [[[] for _ in range(5)] for _ in range(5)]
        for r in risks:
            g[getattr(r, f"{kind}_impact") - 1][getattr(r, f"{kind}_likelihood") - 1].append(r.id)
        return g

    high = [r for r in risks if band(r.residual_score) == "High"]
    entities: dict[str, set[int]] = {}
    for r in high:
        if r.entity_id:
            o = db.get(Organization, r.entity_id)
            if o is not None:
                entities.setdefault(o.name, set()).add(r.id)
        for unit in links.linked(db, "risk", r.id, "unit"):
            entities.setdefault(unit.get("title") or unit.get("name") or f"Unit {unit['id']}", set()).add(r.id)
    kris = [k for k in db.execute(select(KeyRiskIndicator).where(KeyRiskIndicator.active.is_(True))).scalars()
            if k.risk_id in ids]
    today = date.today()
    soon = today + timedelta(days=30)
    kri_rows = []
    for k in kris:
        last = _latest(db, k.id)
        stale = last is None or (today - last.period_date).days > _PERIOD_DAYS.get(k.frequency, 31)
        kri_rows.append((k, k.rag(last.value if last else None), stale))
    by_cat: dict[str, dict[str, int]] = {}
    for r in risks:
        row = by_cat.setdefault(r.category or "Uncategorised", {"High": 0, "Medium": 0, "Low": 0})
        row[band(r.residual_score)] += 1
    mine = [r for r in risks if r.owner_id == user.id]
    my_kris = [x for x in kri_rows if x[0].owner_id == user.id]
    group = None
    if user.work_entity_id:
        scope = set(Index(db).descendants(user.work_entity_id)) | {user.work_entity_id}
        unit_risks = [r for r in risks if r.entity_id in scope]
        group = {"open": len(unit_risks), "unassigned": sum(1 for r in unit_risks if not r.owner_id),
                 "overdue": sum(1 for r in unit_risks if _overdue(r)),
                 "unit": (db.get(Organization, user.work_entity_id).name
                          if db.get(Organization, user.work_entity_id) else "")}
    return {
        "category": category, "categories": cfg("erm_risk_categories"), "can_edit": can(user, "grc.risk"),
        "active": len(risks),
        "entities_high": len(entities),
        "entities": sorted(({"name": n, "risks": len(v)} for n, v in entities.items()), key=lambda x: -x["risks"])[:8],
        "above_target": sum(1 for r in risks if r.target_likelihood and r.target_impact
                            and r.residual_score > r.target_likelihood * r.target_impact),
        "kri_breaches": sum(1 for _, rag, _ in kri_rows if rag == "Red"),
        "kri_amber": sum(1 for _, rag, _ in kri_rows if rag == "Amber"),
        "by_level": {lvl: sum(1 for r in risks if band(r.residual_score) == lvl) for lvl in ("High", "Medium", "Low")},
        "by_category": by_cat,
        "inherent_grid": grid("inherent"), "residual_grid": grid("residual"),
        "titles": {r.id: f"{r.ref} {r.title}" for r in risks},
        "my": {"owned": len(mine),
               "review_due": sum(1 for r in mine if r.next_review_date and today <= r.next_review_date <= soon),
               "overdue": sum(1 for r in mine if _overdue(r)), "kris": len(my_kris),
               "kris_to_record": sum(1 for _, _, stale in my_kris if stale),
               "kri_breaches": sum(1 for _, rag, _ in my_kris if rag == "Red")},
        "group": group,
        "thresholds": {"high": cfg("risk_high_threshold"), "medium": cfg("risk_medium_threshold")},
    }


@router.post("/risks", status_code=201)
def create_risk(payload: RiskIn, request: Request, db: DBSession = Depends(get_db), user: User = RiskEditor) -> dict:
    _validate(db, payload)
    r = EnterpriseRisk(ref=next_reference(db, "ERM"), created_by=user.id)
    _apply(db, r, payload)
    r.last_assessed_at = utcnow()
    r.next_review_date = add_months(date.today(), cfg("erm_review_months"))
    db.add(r)
    db.flush()
    db.add(RiskAssessment(risk_id=r.id, inherent_likelihood=r.inherent_likelihood, inherent_impact=r.inherent_impact,
                          residual_likelihood=r.residual_likelihood, residual_impact=r.residual_impact,
                          comment="Initial assessment", assessed_by=user.id))
    if payload.control_ids is not None:
        links.set_links(db, "risk", r.id, "control", payload.control_ids, user.id)
    if payload.unit_ids is not None:
        links.set_links(db, "risk", r.id, "unit", payload.unit_ids, user.id)
    log_action(db, user_id=user.id, action=f"ERM_RISK_CREATE {r.ref}", request=request)
    if r.owner_id and r.owner_id != user.id:
        from app.platform.notifications.service import notify

        notify(db, r.owner_id, f"You own risk {r.ref}", f"{r.title}. Keep its assessment and indicators current.",
               link_type="erm_risk", link_id=r.id)
    db.commit()
    return _risk_out(db, r, full=True)


@router.get("/risks/{risk_id}")
def get_risk(risk_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> dict:
    r = _risk(db, risk_id)
    if not (can(user, *GRC_PERMS) or r.owner_id == user.id):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return {**_risk_out(db, r, full=True), "can_edit": can(user, "grc.risk"), "can_assess": _can_assess(user, r)}


@router.put("/risks/{risk_id}")
def update_risk(risk_id: int, payload: RiskIn, request: Request, db: DBSession = Depends(get_db),
                user: User = RiskEditor) -> dict:
    r = _risk(db, risk_id)
    _validate(db, payload)
    scores_before = (r.inherent_likelihood, r.inherent_impact, r.residual_likelihood, r.residual_impact)
    _apply(db, r, payload)
    if scores_before != (r.inherent_likelihood, r.inherent_impact, r.residual_likelihood, r.residual_impact):
        db.add(RiskAssessment(risk_id=r.id, inherent_likelihood=r.inherent_likelihood,
                              inherent_impact=r.inherent_impact, residual_likelihood=r.residual_likelihood,
                              residual_impact=r.residual_impact, comment="Scores changed on the risk record",
                              assessed_by=user.id))
        r.last_assessed_at = utcnow()
        r.next_review_date = add_months(date.today(), cfg("erm_review_months"))
    if payload.control_ids is not None:
        links.set_links(db, "risk", r.id, "control", payload.control_ids, user.id)
    if payload.unit_ids is not None:
        links.set_links(db, "risk", r.id, "unit", payload.unit_ids, user.id)
    log_action(db, user_id=user.id, action=f"ERM_RISK_UPDATE {r.ref}", request=request)
    db.commit()
    return _risk_out(db, r, full=True)


@router.post("/risks/{risk_id}/assess")
def assess_risk(risk_id: int, payload: AssessIn, request: Request, db: DBSession = Depends(get_db),
                user: User = Depends(require_active_user)) -> dict:
    r = _risk(db, risk_id)
    if not _can_assess(user, r):
        raise HTTPException(status_code=403, detail="Only the risk owner or the risk team can assess this risk")
    if r.status == "Closed":
        raise HTTPException(status_code=422, detail="This risk is closed")
    db.add(RiskAssessment(risk_id=r.id, assessed_by=user.id, **payload.model_dump()))
    r.inherent_likelihood, r.inherent_impact = payload.inherent_likelihood, payload.inherent_impact
    r.residual_likelihood, r.residual_impact = payload.residual_likelihood, payload.residual_impact
    r.last_assessed_at = utcnow()
    r.next_review_date = add_months(date.today(), cfg("erm_review_months"))
    log_action(db, user_id=user.id, action=f"ERM_RISK_ASSESS {r.ref} residual {r.residual_score}", request=request)
    db.commit()
    return _risk_out(db, r, full=True)


class StateIn(BaseModel):
    treatment: str = Field(default="", max_length=40)


@router.patch("/risks/{risk_id}/state")
def move_risk_state(risk_id: int, payload: StateIn, request: Request, db: DBSession = Depends(get_db),
                    user: User = RiskEditor) -> dict:
    """Move a risk to another mitigation state on the Risk Profile (its treatment response)."""
    r = _risk(db, risk_id)
    before = r.treatment or "Not set"
    r.treatment = in_list(payload.treatment, "erm_treatments", "Treatment")
    log_action(db, user_id=user.id, request=request,
               action=f"ERM_RISK_STATE {r.ref} {before} -> {r.treatment or 'Not set'}")
    db.commit()
    return _risk_out(db, r)


@router.delete("/risks/{risk_id}")
def delete_risk(risk_id: int, request: Request, db: DBSession = Depends(get_db), user: User = RiskEditor) -> dict:
    r = _risk(db, risk_id)
    if r.status != "Draft":
        raise HTTPException(status_code=422, detail="Only draft risks can be deleted; close an active risk instead")
    links.drop_links(db, "risk", r.id)
    log_action(db, user_id=user.id, action=f"ERM_RISK_DELETE {r.ref}", request=request)
    db.delete(r)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- KRIs

@router.get("/kris")
def list_kris(db: DBSession = Depends(get_db), _: User = Viewer) -> list[dict]:
    out = []
    for k in db.execute(select(KeyRiskIndicator).where(KeyRiskIndicator.active.is_(True))
                        .order_by(KeyRiskIndicator.name)).scalars():
        r = db.get(EnterpriseRisk, k.risk_id)
        out.append({**_kri_out(db, k), "risk": f"{r.ref} {r.title}" if r else None})
    order = {"Red": 0, "Amber": 1, "No data": 2, "Green": 3}
    return sorted(out, key=lambda k: (order[k["rag"]], k["name"]))


@router.post("/risks/{risk_id}/kris", status_code=201)
def create_kri(risk_id: int, payload: KriIn, request: Request, db: DBSession = Depends(get_db),
               user: User = RiskEditor) -> dict:
    r = _risk(db, risk_id)
    check_user(db, payload.owner_id)
    k = KeyRiskIndicator(risk_id=r.id, **payload.model_dump())
    db.add(k)
    db.flush()
    log_action(db, user_id=user.id, action=f"KRI_CREATE {r.ref} {k.name}", request=request)
    db.commit()
    return _kri_out(db, k, history=True)


@router.put("/kris/{kri_id}")
def update_kri(kri_id: int, payload: KriIn, request: Request, db: DBSession = Depends(get_db),
               user: User = RiskEditor) -> dict:
    k = db.get(KeyRiskIndicator, kri_id)
    if k is None:
        raise HTTPException(status_code=404, detail="Indicator not found")
    check_user(db, payload.owner_id)
    for f, v in payload.model_dump().items():
        setattr(k, f, v)
    log_action(db, user_id=user.id, action=f"KRI_UPDATE {k.id}", request=request)
    db.commit()
    return _kri_out(db, k, history=True)


@router.post("/kris/{kri_id}/readings", status_code=201)
def add_reading(kri_id: int, payload: ReadingIn, request: Request, db: DBSession = Depends(get_db),
                user: User = Depends(require_active_user)) -> dict:
    k = db.get(KeyRiskIndicator, kri_id)
    if k is None:
        raise HTTPException(status_code=404, detail="Indicator not found")
    r = db.get(EnterpriseRisk, k.risk_id)
    if not (can(user, "grc.risk") or user.id in (k.owner_id, r.owner_id if r else None)):
        raise HTTPException(status_code=403, detail="Only the indicator owner, the risk owner or the risk team can "
                                                    "record readings")
    if payload.period_date > date.today() + timedelta(days=31):
        raise HTTPException(status_code=422, detail="The reading period cannot be more than a month ahead")
    before = _latest(db, k.id)
    db.add(KriReading(kri_id=k.id, recorded_by=user.id, **payload.model_dump()))
    db.flush()
    status = k.rag(payload.value)
    if status == "Red" and (before is None or k.rag(before.value) != "Red"):
        from app.platform.notifications.service import notify_many

        notify_many(db, [r.owner_id if r else None, k.owner_id],
                    f"KRI breached: {k.name}", f"{payload.value:g} {k.unit} is past the red threshold "
                    f"({k.red_at:g}) for risk {r.ref if r else ''}.", link_type="erm_risk", link_id=k.risk_id)
    log_action(db, user_id=user.id, action=f"KRI_READING {k.id} {payload.value:g}", request=request)
    from app.domains.grc.risk.drivers import on_reading

    on_reading(db, k, user.id)
    db.commit()
    return _kri_out(db, k, history=True)

