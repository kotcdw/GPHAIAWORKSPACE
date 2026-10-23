"""IIA Topical Requirements per engagement (GIAS 2024 Topical Requirements, e.g. Cybersecurity).

The engagement team decides, for every active topical requirement, whether its topic is in scope and why. When it
is, each requirement is either assessed (with a conclusion, the work done and any issue raised) or excluded with a
documented rationale. Closing an assurance engagement waits for both (rule ``topical_requirements_to_close``).
The conformance view lists every engagement's status for quality assessments.

The catalogue is maintained in Configuration > Topical requirements by holders of ``method.library``. Once an
engagement has decided on a requirement its checklist is fixed; changes go into a new version, and the earlier
version stays on the engagements that used it. A requirement blocks closure only from its effective date.
"""

from __future__ import annotations

import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.access import ensure_can_view, visible
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import ensure_perm, require_module_tier
from app.core.enums import AuditStatus, Role, utcnow
from app.domains.audit.audits.models import Audit, Finding
from app.domains.audit.audits.nature import is_advisory
from app.domains.audit.topical import service as svc
from app.domains.audit.topical.models import (
    EngagementTopical,
    EngagementTopicalItem,
    TopicalRequirement,
    TopicalRequirementItem,
)
from app.platform.users.models import User

router = APIRouter(tags=["topical requirements"])
Staff = Depends(require_module_tier("topical requirements", Role.Admin, Role.Auditor))


class DecisionIn(BaseModel):
    in_scope: bool
    trigger: str | None = Field(default=None, max_length=60)
    rationale: str = Field(default="", max_length=5000)


class ItemIn(BaseModel):
    outcome: str | None = Field(default=None, max_length=20)
    conclusion: str | None = Field(default=None, max_length=30)
    notes: str = Field(default="", max_length=10000)
    finding_id: int | None = None


class RequirementIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    version: str = Field(default="", max_length=40)
    effective_on: date | None = None
    description: str = Field(default="", max_length=5000)
    source_url: str = Field(default="", max_length=500, pattern=r"^(https://\S+)?$")
    is_active: bool = True


class RequirementPatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    version: str | None = Field(default=None, max_length=40)
    effective_on: date | None = None
    description: str | None = Field(default=None, max_length=5000)
    source_url: str | None = Field(default=None, max_length=500, pattern=r"^(https://\S+)?$")
    is_active: bool | None = None


class ItemDefIn(BaseModel):
    area: str = Field(max_length=40)
    ref: str = Field(min_length=1, max_length=10)
    text: str = Field(min_length=10, max_length=2000)


class VersionIn(BaseModel):
    version: str = Field(min_length=1, max_length=40)
    effective_on: date | None = None


def _req_out(r: TopicalRequirement) -> dict:
    return {"id": r.id, "code": r.code, "title": r.title, "version": r.version,
            "effective_on": r.effective_on.isoformat() if r.effective_on else None, "description": r.description,
            "source_url": r.source_url, "is_active": r.is_active, "in_force": svc.in_force(r)}


def _name(db: DBSession, uid: int | None) -> str | None:
    u = db.get(User, uid) if uid else None
    return (u.full_name or u.username) if u else None


def _audit(db: DBSession, audit_id: int, user: User) -> Audit:
    audit = db.get(Audit, audit_id)
    ensure_can_view(db, user, "audit", audit)
    return audit


def _writable(audit: Audit) -> None:
    if audit.status == AuditStatus.Closed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The audit is closed")


def _items(db: DBSession, requirement_id: int) -> list[TopicalRequirementItem]:
    return list(db.execute(select(TopicalRequirementItem).where(TopicalRequirementItem.requirement_id == requirement_id)
                           .order_by(TopicalRequirementItem.sort, TopicalRequirementItem.id)).scalars())


def _full(db: DBSession, r: TopicalRequirement) -> dict:
    return {**_req_out(r), "used_on": svc.use_count(db, r.id),
            "items": [{"id": i.id, "area": i.area, "ref": i.ref, "text": i.text} for i in _items(db, r.id)]}


@router.get("/api/topical-requirements")
def catalogue(include_inactive: bool = False, db: DBSession = Depends(get_db), _: User = Staff) -> list[dict]:
    stmt = select(TopicalRequirement).order_by(TopicalRequirement.id)
    if not include_inactive:
        stmt = stmt.where(TopicalRequirement.is_active.is_(True))
    return [_full(db, r) for r in db.execute(stmt).scalars()]


# ------------------------------------------------------------------ catalogue maintenance (Configuration)
def _editor(user: User) -> None:
    ensure_perm(user, "method.library")


def _requirement(db: DBSession, requirement_id: int) -> TopicalRequirement:
    r = db.get(TopicalRequirement, requirement_id)
    if r is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topical requirement not found")
    return r


def _unused(db: DBSession, r: TopicalRequirement) -> None:
    n = svc.use_count(db, r.id)
    if n:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Used on {n} engagement(s): its checklist is fixed. Make a new version instead.")


def _code(db: DBSession, title: str, version: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", f"{title} {version}".lower()).strip("_")[:34] or "topical"
    code, n = base, 1
    while db.execute(select(TopicalRequirement.id).where(TopicalRequirement.code == code)).first():
        n += 1
        code = f"{base[:34]}_{n}"
    return code


def _check_item(payload: ItemDefIn) -> None:
    if payload.area not in svc.AREAS:
        raise HTTPException(status_code=422, detail=f"Area: {', '.join(svc.AREAS)}")


@router.post("/api/topical-requirements", status_code=201)
def create_requirement(payload: RequirementIn, request: Request, db: DBSession = Depends(get_db),
                       user: User = Staff) -> dict:
    _editor(user)
    r = TopicalRequirement(code=_code(db, payload.title, payload.version), title=payload.title.strip(),
                           version=payload.version.strip(), effective_on=payload.effective_on,
                           description=payload.description.strip(), source_url=payload.source_url.strip(),
                           is_active=payload.is_active)
    db.add(r)
    db.flush()
    log_action(db, user_id=user.id, request=request, action=f"TOPICAL_REQUIREMENT_CREATED code={r.code}")
    db.commit()
    return _full(db, r)


@router.patch("/api/topical-requirements/{requirement_id}")
def update_requirement(requirement_id: int, payload: RequirementPatch, request: Request,
                       db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    _editor(user)
    r = _requirement(db, requirement_id)
    changes = payload.model_dump(exclude_unset=True)
    for k, v in changes.items():
        if k in ("title", "version", "description", "source_url") and v is not None:
            v = v.strip()
        if k == "title" and not v:
            continue
        setattr(r, k, v)
    log_action(db, user_id=user.id, request=request,
               action=f"TOPICAL_REQUIREMENT_UPDATED code={r.code} fields={','.join(sorted(changes)) or '-'}")
    db.commit()
    return _full(db, r)


@router.post("/api/topical-requirements/{requirement_id}/new-version", status_code=201)
def new_version(requirement_id: int, payload: VersionIn, request: Request, db: DBSession = Depends(get_db),
                user: User = Staff) -> dict:
    """Copy the requirement and its checklist as a new, inactive version to edit; activate it when it is ready."""
    _editor(user)
    old = _requirement(db, requirement_id)
    r = TopicalRequirement(code=_code(db, old.title, payload.version), title=old.title, version=payload.version.strip(),
                           effective_on=payload.effective_on, description=old.description, source_url=old.source_url,
                           is_active=False)
    db.add(r)
    db.flush()
    for i in _items(db, old.id):
        db.add(TopicalRequirementItem(requirement_id=r.id, area=i.area, ref=i.ref, text=i.text, sort=i.sort))
    log_action(db, user_id=user.id, request=request,
               action=f"TOPICAL_REQUIREMENT_VERSIONED from={old.code} to={r.code}")
    db.commit()
    return _full(db, r)


@router.post("/api/topical-requirements/{requirement_id}/items", status_code=201)
def add_item(requirement_id: int, payload: ItemDefIn, request: Request, db: DBSession = Depends(get_db),
             user: User = Staff) -> dict:
    _editor(user)
    r = _requirement(db, requirement_id)
    _unused(db, r)
    _check_item(payload)
    top = db.execute(select(func.max(TopicalRequirementItem.sort))
                     .where(TopicalRequirementItem.requirement_id == r.id)).scalar()
    db.add(TopicalRequirementItem(requirement_id=r.id, area=payload.area, ref=payload.ref.strip(),
                                  text=payload.text.strip(), sort=(top or 0) + 1))
    log_action(db, user_id=user.id, request=request, action=f"TOPICAL_ITEM_ADDED code={r.code} ref={payload.ref}")
    db.commit()
    return _full(db, r)


def _item(db: DBSession, item_id: int) -> tuple[TopicalRequirementItem, TopicalRequirement]:
    i = db.get(TopicalRequirementItem, item_id)
    if i is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requirement item not found")
    r = _requirement(db, i.requirement_id)
    _unused(db, r)
    return i, r


@router.put("/api/topical-requirement-items/{item_id}")
def update_item(item_id: int, payload: ItemDefIn, request: Request, db: DBSession = Depends(get_db),
                user: User = Staff) -> dict:
    _editor(user)
    i, r = _item(db, item_id)
    _check_item(payload)
    i.area, i.ref, i.text = payload.area, payload.ref.strip(), payload.text.strip()
    log_action(db, user_id=user.id, request=request, action=f"TOPICAL_ITEM_UPDATED code={r.code} ref={i.ref}")
    db.commit()
    return _full(db, r)


@router.delete("/api/topical-requirement-items/{item_id}")
def delete_item(item_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    _editor(user)
    i, r = _item(db, item_id)
    db.delete(i)
    log_action(db, user_id=user.id, request=request, action=f"TOPICAL_ITEM_DELETED code={r.code} ref={i.ref}")
    db.commit()
    return _full(db, r)


@router.get("/api/audits/{audit_id}/topical")
def engagement_topicals(audit_id: int, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    audit = _audit(db, audit_id, user)
    advisory = is_advisory(audit)
    reqs = []
    for r in svc.requirements_for(db, audit.id):
        et = svc.decision(db, audit.id, r.id)
        items = []
        if et is not None and et.in_scope:
            q = select(EngagementTopicalItem).where(EngagementTopicalItem.engagement_topical_id == et.id)
            rows = {x.item_id: x for x in db.execute(q).scalars()}
            for i in db.execute(select(TopicalRequirementItem).where(TopicalRequirementItem.requirement_id == r.id)
                                .order_by(TopicalRequirementItem.sort)).scalars():
                x = rows.get(i.id)
                items.append({"item_id": i.id, "area": i.area, "ref": i.ref, "text": i.text,
                              "outcome": x.outcome if x else None, "conclusion": x.conclusion if x else None,
                              "notes": x.notes if x else "", "finding_id": x.finding_id if x else None,
                              "assessed_by": _name(db, x.assessed_by) if x else None,
                              "assessed_at": x.assessed_at.isoformat() if x and x.assessed_at else None})
        reqs.append({**_req_out(r),
                     "decision": None if et is None else {
                         "in_scope": et.in_scope, "trigger": et.trigger, "rationale": et.rationale,
                         "decided_by": _name(db, et.decided_by), "decided_at": et.decided_at.isoformat()},
                     "progress": svc.progress(db, et), "items": items})
    findings = db.execute(select(Finding.id, Finding.title).where(Finding.audit_id == audit.id)).all()
    return {"audit_id": audit.id, "nature": "Advisory" if advisory else "Assurance",
            "mandatory": not advisory, "closed": audit.status == AuditStatus.Closed,
            "triggers": svc.TRIGGERS, "conclusions": svc.CONCLUSIONS, "requirements": reqs,
            "findings": [{"id": f.id, "title": f.title} for f in findings],
            "open_points": svc.open_points(db, audit)}


@router.put("/api/audits/{audit_id}/topical/{requirement_id}")
def decide(audit_id: int, requirement_id: int, payload: DecisionIn, request: Request,
           db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    ensure_perm(user, "audit.plan")
    audit = _audit(db, audit_id, user)
    _writable(audit)
    req = db.get(TopicalRequirement, requirement_id)
    if req is None or not req.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topical requirement not found")
    if payload.in_scope and payload.trigger not in svc.TRIGGERS:
        raise HTTPException(status_code=422, detail=f"Say how the topic came into scope: {', '.join(svc.TRIGGERS)}")
    if not payload.in_scope and len(payload.rationale.strip()) < 10:
        raise HTTPException(status_code=422, detail="Explain why the topic is not in scope (at least 10 characters)")
    et = svc.decision(db, audit.id, req.id)
    if et is None:
        et = EngagementTopical(audit_id=audit.id, requirement_id=req.id, in_scope=payload.in_scope, rationale="")
        db.add(et)
    et.in_scope = payload.in_scope
    et.trigger = payload.trigger if payload.in_scope else None
    et.rationale = payload.rationale.strip()
    et.decided_by = user.id
    et.decided_at = utcnow()
    db.flush()
    if et.in_scope:
        svc.ensure_items(db, et)
    log_action(db, user_id=user.id, request=request,
               action=f"TOPICAL_DECISION audit={audit.id} requirement={req.code} in_scope={et.in_scope}")
    db.commit()
    return engagement_topicals(audit_id, db, user)


@router.put("/api/audits/{audit_id}/topical/{requirement_id}/items/{item_id}")
def assess_item(audit_id: int, requirement_id: int, item_id: int, payload: ItemIn, request: Request,
                db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    ensure_perm(user, "audit.fieldwork")
    audit = _audit(db, audit_id, user)
    _writable(audit)
    et = svc.decision(db, audit.id, requirement_id)
    if et is None or not et.in_scope:
        raise HTTPException(status_code=409, detail="Decide first that the topic is in scope of this engagement")
    svc.ensure_items(db, et)
    row = db.execute(select(EngagementTopicalItem).where(EngagementTopicalItem.engagement_topical_id == et.id,
                                                         EngagementTopicalItem.item_id == item_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Requirement not found on this engagement")
    notes = payload.notes.strip()
    if payload.outcome not in (None, *svc.OUTCOMES):
        raise HTTPException(status_code=422, detail="Outcome: Assessed or Excluded")
    if payload.outcome == "Excluded" and len(notes) < 10:
        raise HTTPException(status_code=422, detail="Document the rationale for the exclusion (at least 10 characters)")
    if payload.outcome == "Assessed" and payload.conclusion not in svc.CONCLUSIONS:
        raise HTTPException(status_code=422, detail=f"Conclusion: {' or '.join(svc.CONCLUSIONS)}")
    if payload.finding_id is not None:
        f = db.get(Finding, payload.finding_id)
        if f is None or f.audit_id != audit.id:
            raise HTTPException(status_code=422, detail="Link an issue of this engagement")
    if payload.outcome == "Assessed" and payload.conclusion == "Exceptions noted" and payload.finding_id is None \
            and not notes:
        raise HTTPException(status_code=422, detail="Describe the exceptions or link the issue raised")
    row.outcome = payload.outcome
    row.conclusion = payload.conclusion if payload.outcome == "Assessed" else None
    row.notes = notes
    row.finding_id = payload.finding_id if payload.outcome == "Assessed" else None
    row.assessed_by = user.id if payload.outcome else None
    row.assessed_at = utcnow() if payload.outcome else None
    ref = db.get(TopicalRequirementItem, item_id).ref
    log_action(db, user_id=user.id, request=request,
               action=f"TOPICAL_ITEM audit={audit.id} item={ref} outcome={row.outcome or '-'}")
    db.commit()
    return engagement_topicals(audit_id, db, user)


@router.get("/api/topical-requirements/conformance")
def conformance(status_filter: str = Query(default="all", alias="status", pattern="^(all|open|closed)$"),
                db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    """Quality assessment view: every engagement's topical-requirement status (GIAS: conformance is evaluated in
    quality assessments)."""
    stmt = select(Audit).order_by(Audit.id.desc())
    if status_filter == "open":
        stmt = stmt.where(Audit.status != AuditStatus.Closed)
    elif status_filter == "closed":
        stmt = stmt.where(Audit.status == AuditStatus.Closed)
    audits = visible(db, user, "audit", list(db.execute(stmt.limit(1000)).scalars()))
    reqs = svc.active_requirements(db)
    rows = []
    for a in audits:
        per = []
        for r in reqs:
            et = svc.decision(db, a.id, r.id)
            p = svc.progress(db, et)
            per.append({"code": r.code, "title": r.title,
                        "state": ("Not decided" if svc.in_force(r) else "Not yet in force") if et is None
                        else "Not in scope" if not et.in_scope
                        else "Complete" if p["done"] == p["total"] else "In progress",
                        **p})
        rows.append({"audit_id": a.id, "title": a.title,
                     "status": a.status.value, "nature": "Advisory" if is_advisory(a) else "Assurance",
                     "requirements": per})
    gaps = sum(1 for r in rows for q in r["requirements"]
               if r["nature"] == "Assurance" and q["state"] in ("Not decided", "In progress"))
    return {"requirements": [_req_out(r) for r in reqs], "engagements": rows, "gaps": gaps}
