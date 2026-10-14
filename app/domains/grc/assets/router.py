"""Asset Inventory API: systems, infrastructure, data, facilities, equipment and third parties, with owners,
criticality, links to risks, controls and requirements, and due-diligence assessments of third parties."""

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
from app.core.refs import next_reference
from app.domains.grc import links
from app.domains.grc.assets.models import CRITICALITY, DUE_DILIGENCE, Asset, ThirdPartyAssessment
from app.domains.grc.common import (
    GRC_PERMS,
    Viewer,
    add_months,
    can,
    check_entity,
    check_user,
    editor,
    entity_name,
    in_list,
    name_of,
)
from app.platform.users.models import User

router = APIRouter(prefix="/api/grc", tags=["risk & compliance"])
Editor = editor("grc.assets")
Level = Literal["Low", "Medium", "High", "Critical"]


class AssetIn(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    asset_type: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=20000)
    owner_id: int | None = None
    entity_id: int | None = None
    location: str = Field(default="", max_length=160)
    criticality: Level = "Medium"
    classification: str = Field(default="", max_length=40)
    status: Literal["Planned", "Active", "Retired"] = "Active"
    vendor_contact: str = Field(default="", max_length=255)
    services: str = Field(default="", max_length=10000)
    contract_ref: str = Field(default="", max_length=80)
    contract_start: date | None = None
    contract_end: date | None = None
    risk_ids: list[int] | None = Field(default=None, max_length=200)
    control_ids: list[int] | None = Field(default=None, max_length=200)
    requirement_ids: list[int] | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _contract_dates(self) -> AssetIn:
        if self.contract_start and self.contract_end and self.contract_end < self.contract_start:
            raise ValueError("The contract cannot end before it starts")
        return self


class TpAssessmentIn(BaseModel):
    assessed_on: date
    rating: Level
    outcome: str
    areas: str = Field(default="", max_length=5000)
    findings: str = Field(default="", max_length=20000)

    @model_validator(mode="after")
    def _outcome(self) -> TpAssessmentIn:
        if self.outcome not in DUE_DILIGENCE or self.outcome == "Not started":
            raise ValueError("Outcome must be In progress, Approved, Approved with conditions or Rejected")
        if self.assessed_on > date.today():
            raise ValueError("The assessment date cannot be in the future")
        return self


def _asset(db: DBSession, asset_id: int) -> Asset:
    a = db.get(Asset, asset_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return a


def _asset_out(db: DBSession, a: Asset, full: bool = False) -> dict:
    today = date.today()
    out = {"id": a.id, "ref": a.ref, "name": a.name, "asset_type": a.asset_type, "is_third_party": a.is_third_party,
           "owner_id": a.owner_id, "owner": name_of(db, a.owner_id), "entity_id": a.entity_id,
           "entity": entity_name(db, a.entity_id), "location": a.location, "criticality": a.criticality,
           "classification": a.classification, "status": a.status, "contract_ref": a.contract_ref,
           "contract_end": a.contract_end, "due_diligence": a.due_diligence, "risk_rating": a.risk_rating,
           "last_assessed_at": a.last_assessed_at, "next_assessment_date": a.next_assessment_date,
           "assessment_due": bool(a.is_third_party and a.status == "Active"
                                  and (a.next_assessment_date is None or a.next_assessment_date <= today)),
           "contract_expiring": bool(a.contract_end and today <= a.contract_end <= today + timedelta(days=90)),
           "contract_expired": bool(a.contract_end and a.contract_end < today and a.status == "Active")}
    if full:
        out.update({"description": a.description, "vendor_contact": a.vendor_contact, "services": a.services,
                    "contract_start": a.contract_start, "links": links.linked(db, "asset", a.id),
                    "assessments": [{"id": t.id, "assessed_on": t.assessed_on, "rating": t.rating,
                                     "outcome": t.outcome, "areas": t.areas, "findings": t.findings,
                                     "assessor": name_of(db, t.assessor_id)} for t in db.execute(
                        select(ThirdPartyAssessment).where(ThirdPartyAssessment.asset_id == a.id)
                        .order_by(ThirdPartyAssessment.assessed_on.desc())).scalars()]})
    return out


def _apply(db: DBSession, a: Asset, p: AssetIn, user: User) -> None:
    check_user(db, p.owner_id)
    check_entity(db, p.entity_id)
    a.asset_type = in_list(p.asset_type, "asset_types", "Type", allow_empty=False)
    a.classification = in_list(p.classification, "data_classifications", "Classification")
    for f in ("name", "description", "owner_id", "entity_id", "location", "criticality", "status", "vendor_contact",
              "services", "contract_ref", "contract_start", "contract_end"):
        setattr(a, f, getattr(p, f))
    a.name = a.name.strip()
    db.flush()
    for kind, ids in (("risk", p.risk_ids), ("control", p.control_ids), ("requirement", p.requirement_ids)):
        if ids is not None:
            links.set_links(db, "asset", a.id, kind, ids, user.id)


@router.get("/assets")
def list_assets(q: str | None = None, asset_type: str | None = None, criticality: str | None = None,
                status: str | None = None, third_party: bool | None = None, db: DBSession = Depends(get_db),
                user: User = Viewer) -> dict:
    stmt = select(Asset)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Asset.name.like(like), Asset.ref.like(like), Asset.description.like(like),
                              Asset.contract_ref.like(like)))
    if asset_type:
        stmt = stmt.where(Asset.asset_type == asset_type)
    if criticality:
        stmt = stmt.where(Asset.criticality == criticality)
    if status:
        stmt = stmt.where(Asset.status == status)
    items = [_asset_out(db, a) for a in db.execute(stmt.order_by(Asset.ref)).scalars()]
    if third_party is not None:
        items = [i for i in items if i["is_third_party"] == third_party]
    rank = {c: n for n, c in enumerate(reversed(CRITICALITY))}
    items.sort(key=lambda i: (rank.get(i["criticality"], 9), i["ref"]))
    every = [_asset_out(db, a) for a in db.execute(select(Asset).where(Asset.status == "Active")).scalars()]
    return {"items": items, "types": cfg("asset_types"), "classifications": cfg("data_classifications"),
            "criticality": list(CRITICALITY), "due_diligence": list(DUE_DILIGENCE), "can_edit": can(user, "grc.assets"),
            "summary": {"active": len(every), "critical": sum(1 for i in every if i["criticality"] == "Critical"),
                        "third_parties": sum(1 for i in every if i["is_third_party"]),
                        "assessments_due": sum(1 for i in every if i["assessment_due"]),
                        "contracts_expiring": sum(1 for i in every if i["contract_expiring"]),
                        "contracts_expired": sum(1 for i in every if i["contract_expired"]),
                        "by_type": {t: sum(1 for i in every if i["asset_type"] == t) for t in cfg("asset_types")}}}


@router.post("/assets", status_code=201)
def create_asset(payload: AssetIn, request: Request, db: DBSession = Depends(get_db), user: User = Editor) -> dict:
    a = Asset(ref=next_reference(db, "AST"), name=payload.name.strip(), asset_type="", created_by=user.id)
    db.add(a)
    _apply(db, a, payload, user)
    if a.is_third_party:
        a.next_assessment_date = date.today()
    log_action(db, user_id=user.id, action=f"ASSET_CREATE {a.ref} {a.asset_type}", request=request)
    db.commit()
    return _asset_out(db, a, full=True)


@router.get("/assets/{asset_id}")
def get_asset(asset_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> dict:
    a = _asset(db, asset_id)
    if not (can(user, *GRC_PERMS) or a.owner_id == user.id):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return {**_asset_out(db, a, full=True), "can_edit": can(user, "grc.assets"),
            "can_assess": can(user, "grc.assets") or a.owner_id == user.id}


@router.put("/assets/{asset_id}")
def update_asset(asset_id: int, payload: AssetIn, request: Request, db: DBSession = Depends(get_db),
                 user: User = Editor) -> dict:
    a = _asset(db, asset_id)
    _apply(db, a, payload, user)
    log_action(db, user_id=user.id, action=f"ASSET_UPDATE {a.ref}", request=request)
    db.commit()
    return _asset_out(db, a, full=True)


@router.post("/assets/{asset_id}/assessments", status_code=201)
def add_assessment(asset_id: int, payload: TpAssessmentIn, request: Request, db: DBSession = Depends(get_db),
                   user: User = Depends(require_active_user)) -> dict:
    a = _asset(db, asset_id)
    if not (can(user, "grc.assets") or a.owner_id == user.id):
        raise HTTPException(status_code=403, detail="Only the owner or the asset team can record due diligence")
    if not a.is_third_party:
        raise HTTPException(status_code=422, detail="Due-diligence assessments are for third parties")
    db.add(ThirdPartyAssessment(asset_id=a.id, assessor_id=user.id, **payload.model_dump()))
    a.last_assessed_at, a.risk_rating, a.due_diligence = payload.assessed_on, payload.rating, payload.outcome
    months = cfg("third_party_review_months")
    if payload.rating in ("Low", "Medium"):
        months *= 2
    if payload.outcome == "In progress":
        months = 1
    a.next_assessment_date = add_months(payload.assessed_on, months)
    log_action(db, user_id=user.id, action=f"TP_ASSESS {a.ref} {payload.rating} {payload.outcome}", request=request)
    db.commit()
    return _asset_out(db, a, full=True)
