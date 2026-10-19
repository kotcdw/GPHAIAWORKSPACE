"""Professional practice: annual and engagement declarations (independence, objectivity, ethics,
confidentiality), conflict review, CPD records and certifications (IIA GIAS Domain II; Act 658 ss.18-20)."""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.appconfig import cfg
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user, require_perm
from app.core.enums import Role, utcnow
from app.core.permissions import has_perm
from app.domains.audit.proficiency.models import (
    CPD_CATEGORIES,
    AuditorPriorRole,
    Certification,
    CpdRecord,
    Declaration,
)
from app.domains.audit.proficiency.service import (
    annual_declared,
    cpd_hours,
    declaration_blockers,
    engagement_declaration,
)
from app.platform.users.models import User

router = APIRouter(prefix="/api/proficiency", tags=["professional practice"])
Staff = Depends(require_active_user)
Reviewer = Depends(require_perm("proficiency.manage"))


def _staff_only(user: User) -> None:
    if user.role not in (Role.Admin, Role.Auditor):
        raise HTTPException(status_code=403, detail="Declarations and CPD are for internal audit staff")


class DeclarationIn(BaseModel):
    kind: str
    audit_id: int | None = None
    independence_confirmed: bool
    ethics_confirmed: bool
    confidentiality_confirmed: bool
    has_conflict: bool = False
    conflict_details: str = Field(default="", max_length=5000)


class ReviewIn(BaseModel):
    decision: str  # Cleared | Reassigned
    notes: str = Field(min_length=5, max_length=5000)


class CpdIn(BaseModel):
    activity_date: datetime
    activity: str = Field(min_length=3, max_length=255)
    provider: str = Field(default="", max_length=160)
    category: str
    hours: float = Field(gt=0, le=200)
    ethics_hours: float = Field(default=0, ge=0, le=200)
    evidence_ref: str = Field(default="", max_length=255)


class CertIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    issuer: str = Field(default="", max_length=160)
    number: str = Field(default="", max_length=80)
    obtained_on: datetime | None = None
    expires_on: datetime | None = None


def _decl_out(db: DBSession, d: Declaration) -> dict:
    user = db.get(User, d.user_id)
    audit_title = ""
    if d.audit_id:
        from app.domains.audit.audits.models import Audit

        a = db.get(Audit, d.audit_id)
        audit_title = a.title if a else ""
    return {"id": d.id, "user_id": d.user_id, "user": (user.full_name or user.username) if user else "",
            "kind": d.kind, "year": d.year, "audit_id": d.audit_id, "audit_title": audit_title,
            "statement": d.statement, "independence_confirmed": d.independence_confirmed,
            "ethics_confirmed": d.ethics_confirmed, "confidentiality_confirmed": d.confidentiality_confirmed,
            "has_conflict": d.has_conflict, "conflict_details": d.conflict_details, "signed_at": d.signed_at,
            "review_status": d.review_status, "reviewed_by": d.reviewed_by, "reviewed_at": d.reviewed_at,
            "review_notes": d.review_notes}


@router.get("/declarations/texts")
def texts(_: User = Staff) -> dict:
    return {"annual": cfg("declaration_text_annual"), "engagement": cfg("declaration_text_engagement"),
            "required_before_fieldwork": bool(cfg("require_engagement_declaration"))}


@router.get("/declarations")
def list_declarations(mine: bool = True, audit_id: int | None = None, pending: bool = False,
                      db: DBSession = Depends(get_db), user: User = Staff) -> list[dict]:
    q = select(Declaration).order_by(Declaration.signed_at.desc())
    if audit_id is not None:
        q = q.where(Declaration.audit_id == audit_id)
        _staff_only(user)
    elif pending:
        if not has_perm(user, "proficiency.manage"):
            raise HTTPException(status_code=403, detail="Your role does not review declarations")
        q = q.where(Declaration.review_status == "Pending review")
    elif mine or not has_perm(user, "proficiency.manage"):
        q = q.where(Declaration.user_id == user.id)
    return [_decl_out(db, d) for d in db.execute(q.limit(500)).scalars()]


@router.post("/declarations", status_code=201)
def sign_declaration(payload: DeclarationIn, request: Request, db: DBSession = Depends(get_db),
                     user: User = Staff) -> dict:
    _staff_only(user)
    year = utcnow().year
    if payload.kind not in ("annual", "engagement"):
        raise HTTPException(status_code=422, detail="Kind must be annual or engagement")
    if not (payload.independence_confirmed and payload.ethics_confirmed and payload.confidentiality_confirmed):
        raise HTTPException(status_code=422, detail="Confirm each statement. If you cannot, declare the conflict "
                                                    "below and tick the confirmations that do apply.")
    if payload.has_conflict and len(payload.conflict_details.strip()) < 10:
        raise HTTPException(status_code=422, detail="Describe the conflict or impairment")
    if payload.kind == "engagement":
        from app.domains.audit.audits.models import Audit

        if payload.audit_id is None or db.get(Audit, payload.audit_id) is None:
            raise HTTPException(status_code=422, detail="Choose the engagement")
        existing = engagement_declaration(db, user.id, payload.audit_id)
        if existing is not None and existing.review_status != "Reassigned" and not payload.has_conflict:
            raise HTTPException(status_code=409, detail="You have already declared for this engagement")
    elif annual_declared(db, user.id, year):
        raise HTTPException(status_code=409, detail=f"You have already signed the {year} annual declaration")
    d = Declaration(user_id=user.id, kind=payload.kind, year=year,
                    audit_id=payload.audit_id if payload.kind == "engagement" else None,
                    statement=cfg("declaration_text_annual" if payload.kind == "annual"
                                  else "declaration_text_engagement"),
                    independence_confirmed=True, ethics_confirmed=True, confidentiality_confirmed=True,
                    has_conflict=payload.has_conflict, conflict_details=payload.conflict_details.strip(),
                    signed_at=utcnow(), review_status="Pending review" if payload.has_conflict else "Not required")
    db.add(d)
    db.flush()
    log_action(db, user_id=user.id, request=request,
               action=f"DECLARATION_SIGNED {d.kind} year={year} audit={d.audit_id} conflict={d.has_conflict}")
    if d.has_conflict:
        from app.platform.automations.engine import emit

        out = _decl_out(db, d)
        emit(db, "declaration.conflict", "declaration", d.id,
             {"user": out["user"], "audit_title": out["audit_title"] or "the year", "details": d.conflict_details,
              "_link_type": "audit" if d.audit_id else None, "_link_id": d.audit_id,
              "_people": {"subject_user": [d.user_id]}})
    db.commit()
    return _decl_out(db, d)


@router.post("/declarations/{decl_id}/review")
def review_declaration(decl_id: int, payload: ReviewIn, request: Request, db: DBSession = Depends(get_db),
                       user: User = Reviewer) -> dict:
    d = db.get(Declaration, decl_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Declaration not found")
    if d.review_status != "Pending review":
        raise HTTPException(status_code=409, detail="This declaration is not awaiting review")
    if d.user_id == user.id:
        raise HTTPException(status_code=403, detail="You cannot review your own declaration")
    if payload.decision not in ("Cleared", "Reassigned"):
        raise HTTPException(status_code=422, detail="Decision must be Cleared or Reassigned")
    d.review_status, d.reviewed_by, d.reviewed_at, d.review_notes = payload.decision, user.id, utcnow(), \
        payload.notes.strip()
    log_action(db, user_id=user.id, action=f"DECLARATION_REVIEWED id={d.id} {payload.decision}", request=request)
    from app.platform.notifications.service import notify

    notify(db, d.user_id, f"Your declaration was reviewed: {payload.decision}", payload.notes,
           link_type="audit" if d.audit_id else None, link_id=d.audit_id)
    db.commit()
    return _decl_out(db, d)


@router.get("/audits/{audit_id}/status")
def engagement_status(audit_id: int, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    from app.domains.audit.audits.models import Audit

    _staff_only(user)
    audit = db.get(Audit, audit_id)
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit not found")
    mine = engagement_declaration(db, user.id, audit_id)
    return {"required": bool(cfg("require_engagement_declaration")), "blockers": declaration_blockers(db, audit),
            "mine": _decl_out(db, mine) if mine else None,
            "annual_signed": annual_declared(db, user.id, utcnow().year),
            "declarations": list_declarations(mine=False, audit_id=audit_id, db=db, user=user)}


# ---------------------------------------------------------------- CPD and certifications

def _cpd_out(r: CpdRecord) -> dict:
    return {"id": r.id, "user_id": r.user_id, "activity_date": r.activity_date, "activity": r.activity,
            "provider": r.provider, "category": r.category, "hours": r.hours, "ethics_hours": r.ethics_hours,
            "evidence_ref": r.evidence_ref, "verified_by": r.verified_by, "verified_at": r.verified_at}


def _cert_out(c: Certification) -> dict:
    now = utcnow()
    return {"id": c.id, "user_id": c.user_id, "name": c.name, "issuer": c.issuer, "number": c.number,
            "obtained_on": c.obtained_on, "expires_on": c.expires_on,
            "expired": bool(c.expires_on and c.expires_on < now)}


def _target_user(user: User, user_id: int | None) -> int:
    if user_id is None or user_id == user.id:
        return user.id
    if not has_perm(user, "proficiency.manage"):
        raise HTTPException(status_code=403, detail="You can only see your own records")
    return user_id


@router.get("/cpd")
def my_cpd(year: int | None = None, user_id: int | None = None, db: DBSession = Depends(get_db),
           user: User = Staff) -> dict:
    uid = _target_user(user, user_id)
    year = year or utcnow().year
    rows = db.execute(select(CpdRecord).where(CpdRecord.user_id == uid, CpdRecord.activity_date >= datetime(year, 1, 1),
                                              CpdRecord.activity_date < datetime(year + 1, 1, 1))
                      .order_by(CpdRecord.activity_date.desc())).scalars().all()
    certs = db.execute(select(Certification).where(Certification.user_id == uid)
                       .order_by(Certification.name)).scalars()
    return {"year": year, "categories": CPD_CATEGORIES, "target": cfg("cpd_target_hours"),
            "ethics_target": cfg("cpd_ethics_hours"), "hours": sum(r.hours for r in rows),
            "ethics_hours": sum(r.ethics_hours for r in rows), "records": [_cpd_out(r) for r in rows],
            "certifications": [_cert_out(c) for c in certs]}


@router.post("/cpd", status_code=201)
def add_cpd(payload: CpdIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    _staff_only(user)
    if payload.category not in CPD_CATEGORIES:
        raise HTTPException(status_code=422, detail="Choose a category")
    if payload.ethics_hours > payload.hours:
        raise HTTPException(status_code=422, detail="Ethics hours cannot exceed the total hours")
    when = payload.activity_date.replace(tzinfo=None)
    if when > utcnow():
        raise HTTPException(status_code=422, detail="CPD is recorded after the activity")
    r = CpdRecord(user_id=user.id, activity_date=when, activity=payload.activity.strip(),
                  provider=payload.provider.strip(), category=payload.category, hours=payload.hours,
                  ethics_hours=payload.ethics_hours, evidence_ref=payload.evidence_ref.strip())
    db.add(r)
    db.flush()
    log_action(db, user_id=user.id, action=f"CPD_RECORDED id={r.id} hours={r.hours}", request=request)
    db.commit()
    return _cpd_out(r)


@router.delete("/cpd/{record_id}")
def delete_cpd(record_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    r = db.get(CpdRecord, record_id)
    if r is None or r.user_id != user.id:
        raise HTTPException(status_code=404, detail="Record not found")
    if r.verified_at:
        raise HTTPException(status_code=409, detail="A verified record cannot be deleted")
    db.delete(r)
    log_action(db, user_id=user.id, action=f"CPD_DELETED id={record_id}", request=request)
    db.commit()
    return {"message": "Deleted"}


@router.post("/cpd/{record_id}/verify")
def verify_cpd(record_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Reviewer) -> dict:
    r = db.get(CpdRecord, record_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Record not found")
    if r.user_id == user.id:
        raise HTTPException(status_code=403, detail="You cannot verify your own CPD")
    r.verified_by, r.verified_at = user.id, utcnow()
    log_action(db, user_id=user.id, action=f"CPD_VERIFIED id={r.id}", request=request)
    db.commit()
    return _cpd_out(r)


@router.post("/certifications", status_code=201)
def add_cert(payload: CertIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    _staff_only(user)
    if payload.obtained_on and payload.expires_on and payload.expires_on <= payload.obtained_on:
        raise HTTPException(status_code=422, detail="The expiry date must be after the date obtained")
    c = Certification(user_id=user.id, name=payload.name.strip(), issuer=payload.issuer.strip(),
                      number=payload.number.strip(),
                      obtained_on=payload.obtained_on.replace(tzinfo=None) if payload.obtained_on else None,
                      expires_on=payload.expires_on.replace(tzinfo=None) if payload.expires_on else None)
    db.add(c)
    db.flush()
    log_action(db, user_id=user.id, action=f"CERTIFICATION_ADDED id={c.id}", request=request)
    db.commit()
    return _cert_out(c)


@router.delete("/certifications/{cert_id}")
def delete_cert(cert_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    c = db.get(Certification, cert_id)
    if c is None or c.user_id != user.id:
        raise HTTPException(status_code=404, detail="Certification not found")
    db.delete(c)
    log_action(db, user_id=user.id, action=f"CERTIFICATION_DELETED id={cert_id}", request=request)
    db.commit()
    return {"message": "Deleted"}


@router.get("/team")
def team_summary(year: int | None = Query(default=None), db: DBSession = Depends(get_db),
                 _: User = Reviewer) -> dict:
    """Per auditor: annual declaration, CPD hours against target, certifications expiring."""
    year = year or utcnow().year
    target = int(cfg("cpd_target_hours"))
    staff = db.execute(select(User).where(User.is_active.is_(True), User.role.in_((Role.Admin, Role.Auditor)))
                       .order_by(User.full_name)).scalars()
    now = utcnow()
    out = []
    for u in staff:
        certs = db.execute(select(Certification).where(Certification.user_id == u.id)).scalars().all()
        hours = cpd_hours(db, u.id, year)
        out.append({"user_id": u.id, "name": u.full_name or u.username, "annual_declaration": annual_declared(
            db, u.id, year), "cpd_hours": hours, "cpd_target": target, "on_track": hours >= target,
            "certifications": [c.name for c in certs],
            "expiring": [c.name for c in certs if c.expires_on and (c.expires_on - now).days <= 90]})
    pending = db.execute(select(Declaration).where(Declaration.review_status == "Pending review")).scalars().all()
    return {"year": year, "target": target, "staff": out, "pending_reviews": [_decl_out(db, d) for d in pending]}


# ---------------------------------------------------------------- prior roles (cooling-off, IIA GIAS 2.2)


class PriorRoleIn(BaseModel):
    user_id: int | None = None
    org_unit_id: int
    role: str = Field(min_length=2, max_length=160)
    from_date: date | None = None
    to_date: date | None = None


def _prior_out(db: DBSession, r: AuditorPriorRole) -> dict:
    from app.platform.organizations.models import Organization

    org = db.get(Organization, r.org_unit_id)
    return {"id": r.id, "user_id": r.user_id, "org_unit_id": r.org_unit_id, "unit": org.name if org else None,
            "role": r.role, "from_date": r.from_date, "to_date": r.to_date}


def _subject(user: User, user_id: int | None) -> int:
    if user_id in (None, user.id):
        _staff_only(user)
        return user.id
    if not has_perm(user, "proficiency.manage"):
        raise HTTPException(status_code=403, detail="Only a reviewer can record another auditor's prior roles")
    return user_id


@router.get("/prior-roles")
def list_prior_roles(user_id: int | None = Query(default=None), db: DBSession = Depends(get_db),
                     user: User = Staff) -> dict:
    """Units the auditor worked in before; an audit of these units within the cooling-off period is flagged."""
    from app.platform.organizations.models import Organization

    who = _subject(user, user_id)
    rows = db.execute(select(AuditorPriorRole).where(AuditorPriorRole.user_id == who)
                      .order_by(AuditorPriorRole.to_date.is_(None).desc(), AuditorPriorRole.to_date.desc())).scalars()
    units = db.execute(select(Organization).order_by(Organization.name)).scalars()
    return {"items": [_prior_out(db, r) for r in rows], "cooling_off_months": int(cfg("cooling_off_months") or 0),
            "units": [{"id": o.id, "name": o.name} for o in units]}


@router.post("/prior-roles", status_code=201)
def add_prior_role(payload: PriorRoleIn, request: Request, db: DBSession = Depends(get_db),
                   user: User = Staff) -> dict:
    from app.platform.organizations.models import Organization

    who = _subject(user, payload.user_id)
    if db.get(User, who) is None:
        raise HTTPException(status_code=422, detail="Choose an auditor")
    if db.get(Organization, payload.org_unit_id) is None:
        raise HTTPException(status_code=422, detail="Choose an org unit")
    if payload.from_date and payload.to_date and payload.to_date < payload.from_date:
        raise HTTPException(status_code=422, detail="The end date must be after the start date")
    r = AuditorPriorRole(user_id=who, org_unit_id=payload.org_unit_id, role=payload.role.strip(),
                         from_date=payload.from_date, to_date=payload.to_date, created_by=user.id)
    db.add(r)
    db.flush()
    log_action(db, user_id=user.id, request=request,
               action=f"PRIOR_ROLE_ADDED id={r.id} user={who} unit={payload.org_unit_id}")
    db.commit()
    return _prior_out(db, r)


@router.delete("/prior-roles/{role_id}")
def delete_prior_role(role_id: int, request: Request, db: DBSession = Depends(get_db),
                      user: User = Reviewer) -> dict:
    """Only a reviewer removes a recorded role, so an auditor cannot lift their own cooling-off flag."""
    r = db.get(AuditorPriorRole, role_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(r)
    log_action(db, user_id=user.id, request=request,
               action=f"PRIOR_ROLE_DELETED id={role_id} user={r.user_id} unit={r.org_unit_id} role={r.role}")
    db.commit()
    return {"message": "Deleted"}
