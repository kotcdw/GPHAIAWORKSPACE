"""Automated risk assessment from key risk indicators, and per-segment risk assessment.

**KRI drivers.** An indicator can drive the risk's residual likelihood or impact: when its latest reading is Amber
or Red, the dimension rises by the indicator's Amber or Red step above the last assessment made by a person (or by
the segment roll-up). Several drivers on one dimension take the largest step; residual never rises above inherent.
The proposal is applied by the risk owner or the risk team, or automatically when a reading is recorded if the
administrator turns on ``erm_kri_auto_assess``. Every applied proposal is a dated assessment marked "kri".

**Segments.** A risk can be assessed separately for segments of the organisation (ports, divisions,
departments). The latest assessment of each segment rolls up to the risk as the worst segment or the average, per
the ``erm_segment_rollup`` setting, and is recorded as an assessment marked "segments".
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.appconfig import cfg
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user
from app.core.enums import utcnow
from app.domains.grc.common import GRC_PERMS, add_months, band, can, check_entity, editor, entity_name, name_of
from app.domains.grc.risk.models import (
    EnterpriseRisk,
    KeyRiskIndicator,
    KriReading,
    RiskAssessment,
    RiskSegmentAssessment,
)
from app.platform.users.models import User

router = APIRouter(prefix="/api/grc", tags=["risk & compliance"])
RiskEditor = editor("grc.risk")
Score = Field(ge=1, le=5)


class DriverIn(BaseModel):
    drives: Literal["", "likelihood", "impact"] = ""
    amber_step: int = Field(default=1, ge=0, le=4)
    red_step: int = Field(default=2, ge=0, le=4)

    @model_validator(mode="after")
    def _order(self) -> DriverIn:
        if self.red_step < self.amber_step:
            raise ValueError("The Red step must be at least the Amber step")
        return self


class SegmentIn(BaseModel):
    org_id: int
    inherent_likelihood: int = Score
    inherent_impact: int = Score
    residual_likelihood: int = Score
    residual_impact: int = Score
    comment: str = Field(default="", max_length=5000)

    @model_validator(mode="after")
    def _residual_not_above_inherent(self) -> SegmentIn:
        if self.residual_likelihood * self.residual_impact > self.inherent_likelihood * self.inherent_impact:
            raise ValueError("Residual risk cannot be higher than inherent risk")
        return self


def _risk(db: DBSession, user: User, risk_id: int) -> EnterpriseRisk:
    r = db.get(EnterpriseRisk, risk_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Risk not found")
    if not (can(user, *GRC_PERMS) or r.owner_id == user.id):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return r


def _can_assess(user: User, r: EnterpriseRisk) -> bool:
    return can(user, "grc.risk") or r.owner_id == user.id


def _record(db: DBSession, r: EnterpriseRisk, scores: tuple[int, int, int, int], origin: str, comment: str,
            user_id: int | None) -> None:
    il, ii, rl, ri = scores
    db.add(RiskAssessment(risk_id=r.id, inherent_likelihood=il, inherent_impact=ii, residual_likelihood=rl,
                          residual_impact=ri, comment=comment, origin=origin, assessed_by=user_id))
    r.inherent_likelihood, r.inherent_impact, r.residual_likelihood, r.residual_impact = il, ii, rl, ri
    r.last_assessed_at = utcnow()
    r.next_review_date = add_months(date.today(), cfg("erm_review_months"))


# ------------------------------------------------------------------ KRI drivers

def _latest_value(db: DBSession, kri_id: int) -> float | None:
    row = db.execute(select(KriReading.value).where(KriReading.kri_id == kri_id)
                     .order_by(KriReading.period_date.desc(), KriReading.id.desc()).limit(1)).scalar_one_or_none()
    return row


def proposal(db: DBSession, r: EnterpriseRisk) -> dict:
    """The KRI-driven residual scores for this risk now, and why."""
    base = db.execute(select(RiskAssessment).where(RiskAssessment.risk_id == r.id, RiskAssessment.origin != "kri")
                      .order_by(RiskAssessment.assessed_at.desc(), RiskAssessment.id.desc())
                      .limit(1)).scalar_one_or_none()
    base_l, base_i = (base.residual_likelihood, base.residual_impact) if base else (r.residual_likelihood,
                                                                                    r.residual_impact)
    drivers, steps = [], {"likelihood": 0, "impact": 0}
    for k in db.execute(select(KeyRiskIndicator).where(KeyRiskIndicator.risk_id == r.id,
                                                       KeyRiskIndicator.active.is_(True),
                                                       KeyRiskIndicator.drives != "")
                        .order_by(KeyRiskIndicator.name)).scalars():
        value = _latest_value(db, k.id)
        rag = k.rag(value)
        step = k.red_step if rag == "Red" else k.amber_step if rag == "Amber" else 0
        steps[k.drives] = max(steps[k.drives], step)
        drivers.append({"kri_id": k.id, "name": k.name, "drives": k.drives, "rag": rag, "value": value, "step": step})

    def raise_(base_v: int, inherent_v: int, step: int) -> int:
        return base_v if not step else max(base_v, min(5, base_v + step, max(inherent_v, base_v)))

    new_l = raise_(base_l, r.inherent_likelihood, steps["likelihood"])
    new_i = raise_(base_i, r.inherent_impact, steps["impact"])
    if new_l * new_i > r.inherent_score:  # never above inherent: keep the base on the dimension that broke it
        new_l, new_i = (base_l, new_i) if base_l * new_i <= r.inherent_score else (new_l, base_i)
        if new_l * new_i > r.inherent_score:
            new_l, new_i = base_l, base_i
    return {"base": {"residual_likelihood": base_l, "residual_impact": base_i, "residual_score": base_l * base_i,
                     "from": "last assessment" if base else "current scores"},
            "drivers": drivers,
            "proposed": {"residual_likelihood": new_l, "residual_impact": new_i, "residual_score": new_l * new_i,
                         "residual_level": band(new_l * new_i)},
            "current": {"residual_likelihood": r.residual_likelihood, "residual_impact": r.residual_impact,
                        "residual_score": r.residual_score},
            "changes": (new_l, new_i) != (r.residual_likelihood, r.residual_impact),
            "auto": bool(cfg("erm_kri_auto_assess"))}


def apply_proposal(db: DBSession, r: EnterpriseRisk, user_id: int | None) -> dict | None:
    """Record the KRI-driven assessment when it changes the residual scores. Returns the proposal, or None."""
    p = proposal(db, r)
    if not p["changes"] or r.status == "Closed":
        return None
    moved = [f"{d['name']} {d['rag']} (+{d['step']} {d['drives']})" for d in p["drivers"] if d["step"]]
    comment = "KRI-driven: " + ("; ".join(moved) if moved else "no indicator is Amber or Red; back to the last "
                                                              "assessment")
    _record(db, r, (r.inherent_likelihood, r.inherent_impact, p["proposed"]["residual_likelihood"],
                    p["proposed"]["residual_impact"]), "kri", comment[:5000], user_id)
    return p


def on_reading(db: DBSession, k: KeyRiskIndicator, user_id: int) -> None:
    """Called after a reading is recorded: apply the KRI-driven assessment when the setting is on."""
    if not k.drives or not cfg("erm_kri_auto_assess"):
        return
    r = db.get(EnterpriseRisk, k.risk_id)
    if r is None:
        return
    p = apply_proposal(db, r, user_id)
    if p:
        from app.platform.notifications.service import notify

        notify(db, r.owner_id, f"Risk reassessed from indicators: {r.ref}",
               f"Residual score is now {p['proposed']['residual_score']} ({p['proposed']['residual_level']}).",
               link_type="erm_risk", link_id=r.id)
        log_action(db, user_id=user_id, action=f"ERM_RISK_ASSESS {r.ref} kri residual {r.residual_score}")


@router.put("/kris/{kri_id}/driver")
def set_driver(kri_id: int, payload: DriverIn, request: Request, db: DBSession = Depends(get_db),
               user: User = RiskEditor) -> dict:
    k = db.get(KeyRiskIndicator, kri_id)
    if k is None:
        raise HTTPException(status_code=404, detail="Indicator not found")
    k.drives, k.amber_step, k.red_step = payload.drives, payload.amber_step, payload.red_step
    log_action(db, user_id=user.id, request=request,
               action=f"KRI_DRIVER {k.id} drives={k.drives or 'none'} amber+{k.amber_step} red+{k.red_step}")
    db.commit()
    return {"id": k.id, "drives": k.drives, "amber_step": k.amber_step, "red_step": k.red_step}


@router.get("/risks/{risk_id}/kri-assessment")
def get_kri_assessment(risk_id: int, db: DBSession = Depends(get_db),
                       user: User = Depends(require_active_user)) -> dict:
    r = _risk(db, user, risk_id)
    return {**proposal(db, r), "can_apply": _can_assess(user, r) and r.status != "Closed"}


@router.post("/risks/{risk_id}/kri-assessment")
def apply_kri_assessment(risk_id: int, request: Request, db: DBSession = Depends(get_db),
                         user: User = Depends(require_active_user)) -> dict:
    r = _risk(db, user, risk_id)
    if not _can_assess(user, r):
        raise HTTPException(status_code=403, detail="Only the risk owner or the risk team can assess this risk")
    if r.status == "Closed":
        raise HTTPException(status_code=422, detail="This risk is closed")
    p = apply_proposal(db, r, user.id)
    if p is None:
        raise HTTPException(status_code=409, detail="The indicators do not change the residual scores")
    log_action(db, user_id=user.id, request=request, action=f"ERM_RISK_ASSESS {r.ref} kri residual {r.residual_score}")
    db.commit()
    return {**proposal(db, r), "can_apply": True}


# ------------------------------------------------------------------ segments

def latest_segments(db: DBSession, risk_id: int) -> list[RiskSegmentAssessment]:
    latest: dict[int, RiskSegmentAssessment] = {}
    for s in db.execute(select(RiskSegmentAssessment).where(RiskSegmentAssessment.risk_id == risk_id)
                        .order_by(RiskSegmentAssessment.assessed_at, RiskSegmentAssessment.id)).scalars():
        latest[s.org_id] = s
    return list(latest.values())


def rollup(segments: list[RiskSegmentAssessment], method: str) -> tuple[int, int, int, int] | None:
    if not segments:
        return None
    if method == "Average":
        n = len(segments)
        avg = [int(sum(getattr(s, f) for s in segments) / n + 0.5) for f in
               ("inherent_likelihood", "inherent_impact", "residual_likelihood", "residual_impact")]
        il, ii, rl, ri = avg
        if rl * ri > il * ii:
            rl, ri = min(rl, il), min(ri, ii)
        return il, ii, rl, ri
    worst_in = max(segments, key=lambda s: (s.inherent_likelihood * s.inherent_impact, s.inherent_impact))
    worst_res = max(segments, key=lambda s: (s.residual_likelihood * s.residual_impact, s.residual_impact))
    return (worst_in.inherent_likelihood, worst_in.inherent_impact, worst_res.residual_likelihood,
            worst_res.residual_impact)


def _segments_out(db: DBSession, r: EnterpriseRisk) -> dict:
    method = cfg("erm_segment_rollup")
    segs = latest_segments(db, r.id)
    rolled = rollup(segs, method)
    history = db.execute(select(RiskSegmentAssessment).where(RiskSegmentAssessment.risk_id == r.id)
                         .order_by(RiskSegmentAssessment.assessed_at.desc(), RiskSegmentAssessment.id.desc())
                         .limit(50)).scalars()
    row = lambda s: {"id": s.id, "org_id": s.org_id, "segment": entity_name(db, s.org_id),  # noqa: E731
                     "inherent_likelihood": s.inherent_likelihood, "inherent_impact": s.inherent_impact,
                     "residual_likelihood": s.residual_likelihood, "residual_impact": s.residual_impact,
                     "inherent_score": s.inherent_likelihood * s.inherent_impact,
                     "residual_score": s.residual_likelihood * s.residual_impact,
                     "residual_level": band(s.residual_likelihood * s.residual_impact), "comment": s.comment,
                     "by": name_of(db, s.assessed_by), "at": s.assessed_at}
    return {"method": method,
            "segments": sorted((row(s) for s in segs), key=lambda x: (-x["residual_score"], x["segment"] or "")),
            "history": [row(s) for s in history],
            "rollup": None if rolled is None else {
                "inherent_likelihood": rolled[0], "inherent_impact": rolled[1], "residual_likelihood": rolled[2],
                "residual_impact": rolled[3], "inherent_score": rolled[0] * rolled[1],
                "residual_score": rolled[2] * rolled[3], "residual_level": band(rolled[2] * rolled[3]),
                "differs": rolled != (r.inherent_likelihood, r.inherent_impact, r.residual_likelihood,
                                      r.residual_impact)}}


@router.get("/risks/{risk_id}/segments")
def get_segments(risk_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> dict:
    r = _risk(db, user, risk_id)
    return {**_segments_out(db, r), "can_assess": _can_assess(user, r) and r.status != "Closed"}


@router.post("/risks/{risk_id}/segments", status_code=201)
def assess_segment(risk_id: int, payload: SegmentIn, request: Request, db: DBSession = Depends(get_db),
                   user: User = Depends(require_active_user)) -> dict:
    r = _risk(db, user, risk_id)
    if not _can_assess(user, r):
        raise HTTPException(status_code=403, detail="Only the risk owner or the risk team can assess this risk")
    if r.status == "Closed":
        raise HTTPException(status_code=422, detail="This risk is closed")
    check_entity(db, payload.org_id)
    db.add(RiskSegmentAssessment(risk_id=r.id, assessed_by=user.id, **payload.model_dump()))
    log_action(db, user_id=user.id, request=request,
               action=f"ERM_SEGMENT_ASSESS {r.ref} org={payload.org_id} "
                      f"residual {payload.residual_likelihood * payload.residual_impact}")
    db.commit()
    return {**_segments_out(db, r), "can_assess": True}


@router.post("/risks/{risk_id}/segments/rollup")
def apply_rollup(risk_id: int, request: Request, db: DBSession = Depends(get_db),
                 user: User = Depends(require_active_user)) -> dict:
    r = _risk(db, user, risk_id)
    if not _can_assess(user, r):
        raise HTTPException(status_code=403, detail="Only the risk owner or the risk team can assess this risk")
    if r.status == "Closed":
        raise HTTPException(status_code=422, detail="This risk is closed")
    segs = latest_segments(db, r.id)
    rolled = rollup(segs, cfg("erm_segment_rollup"))
    if rolled is None:
        raise HTTPException(status_code=422, detail="Assess at least one segment first")
    _record(db, r, rolled, "segments",
            f"Roll-up ({cfg('erm_segment_rollup').lower()}) of {len(segs)} segment assessment"
            f"{'' if len(segs) == 1 else 's'}", user.id)
    log_action(db, user_id=user.id, request=request,
               action=f"ERM_RISK_ASSESS {r.ref} segments residual {r.residual_score}")
    db.commit()
    return {**_segments_out(db, r), "can_assess": True}
