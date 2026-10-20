"""Auditor capacity, skills and time sheets (IIA GIAS 10.2 - human resources management)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_module_tier
from app.core.enums import EngagementStatus, Role, utcnow
from app.core.errors import field_error
from app.domains.audit.audits.models import Audit
from app.domains.audit.capacity.models import TIME_CATEGORIES, AuditorProfile, TimeEntry
from app.platform.users.models import User

router = APIRouter(prefix="/api/capacity", tags=["capacity"])
Staff = Depends(require_module_tier("capacity", Role.Admin, Role.Auditor))
AUDIT_WORK = ("Audit", "Follow-up")


def _is_supervisor(user: User) -> bool:
    from app.core.permissions import has_perm

    return user.role == Role.Admin or has_perm(user, "oversight.resources")


def _name(u: User) -> str:
    return u.full_name or u.username


# ------------------------------------------------------------------ profiles


class ProfileIn(BaseModel):
    grade: str = Field("", max_length=100)
    skills: list[str] = Field(default_factory=list, max_length=40)
    certifications: list[str] = Field(default_factory=list, max_length=20)
    annual_hours: int = Field(1600, ge=0, le=3000)

    @field_validator("skills", "certifications")
    @classmethod
    def _clean(cls, v: list[str]) -> list[str]:
        out = []
        for item in v:
            item = item.strip()
            if len(item) > 60:
                raise ValueError("Each entry must be 60 characters or fewer")
            if item and item.lower() not in [o.lower() for o in out]:
                out.append(item)
        return out


class ProfileOut(ProfileIn):
    user_id: int
    name: str
    role: str
    review_level: str | None = None


def _split(text: str) -> list[str]:
    return [s.strip() for s in (text or "").split(",") if s.strip()]


def _profile_out(user: User, p: AuditorProfile | None) -> ProfileOut:
    return ProfileOut(
        user_id=user.id,
        name=_name(user),
        role=user.role.value,
        review_level=user.review_level.value if user.review_level else None,
        grade=p.grade if p else "",
        skills=_split(p.skills) if p else [],
        certifications=_split(p.certifications) if p else [],
        annual_hours=p.annual_hours if p else 1600,
    )


def _staff_users(db: DBSession) -> list[User]:
    return list(
        db.execute(
            select(User)
            .where(User.role.in_([Role.Admin, Role.Auditor]), User.is_active.is_(True))
            .order_by(User.full_name)
        ).scalars()
    )


@router.get("/profiles", response_model=list[ProfileOut])
def list_profiles(skill: str | None = None, db: DBSession = Depends(get_db), user: User = Staff) -> list[ProfileOut]:
    profiles = {p.user_id: p for p in db.execute(select(AuditorProfile)).scalars()}
    out = [_profile_out(u, profiles.get(u.id)) for u in _staff_users(db)]
    if skill:
        needle = skill.strip().lower()
        out = [p for p in out if any(needle in s.lower() for s in p.skills + p.certifications)]
    return out


@router.put("/profiles/{user_id}", response_model=ProfileOut)
def save_profile(
    user_id: int, payload: ProfileIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> ProfileOut:
    if user_id != user.id and not _is_supervisor(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only edit your own profile")
    target = db.get(User, user_id)
    if target is None or target.role not in (Role.Admin, Role.Auditor):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auditor not found")
    p = db.get(AuditorProfile, user_id) or AuditorProfile(user_id=user_id)
    p.grade = payload.grade.strip()
    p.skills = ", ".join(payload.skills)
    p.certifications = ", ".join(payload.certifications)
    if _is_supervisor(user):  # available hours are set by management
        p.annual_hours = payload.annual_hours
    db.add(p)
    log_action(db, user_id=user.id, action=f"PROFILE_SAVE user={user_id}", request=request)
    db.commit()
    return _profile_out(target, p)


# ------------------------------------------------------------------ time sheets


class TimeIn(BaseModel):
    entry_date: datetime
    hours: float = Field(..., gt=0, le=24)
    category: str = "Audit"
    audit_id: int | None = None
    description: str = Field("", max_length=2000)

    @field_validator("category")
    @classmethod
    def _cat(cls, v: str) -> str:
        if v not in TIME_CATEGORIES:
            raise ValueError(f"must be one of: {', '.join(TIME_CATEGORIES)}")
        return v

    @field_validator("hours")
    @classmethod
    def _quarter(cls, v: float) -> float:
        if round(v * 4) != v * 4:
            raise ValueError("must be in quarter hours (e.g. 1.25, 3.5)")
        return v


class TimeOut(BaseModel):
    id: int
    user_id: int
    user_name: str
    entry_date: datetime
    hours: float
    category: str
    audit_id: int | None
    audit_title: str | None
    description: str
    can_delete: bool


def _time_out(db: DBSession, e: TimeEntry, viewer: User) -> TimeOut:
    owner = db.get(User, e.user_id)
    audit = db.get(Audit, e.audit_id) if e.audit_id else None
    return TimeOut(
        id=e.id,
        user_id=e.user_id,
        user_name=_name(owner) if owner else "-",
        entry_date=e.entry_date,
        hours=e.hours,
        category=e.category,
        audit_id=e.audit_id,
        audit_title=audit.title if audit else None,
        description=e.description,
        can_delete=e.user_id == viewer.id or viewer.role == Role.Admin,
    )


@router.get("/time", response_model=list[TimeOut])
def list_time(
    user_id: int | None = None,
    audit_id: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    db: DBSession = Depends(get_db),
    user: User = Staff,
) -> list[TimeOut]:
    q = select(TimeEntry)
    if user_id is not None and user_id != user.id:
        if not _is_supervisor(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only see your own time sheet")
        q = q.where(TimeEntry.user_id == user_id)
    elif audit_id is None or not _is_supervisor(user):
        q = q.where(TimeEntry.user_id == user.id)
    if audit_id is not None:
        q = q.where(TimeEntry.audit_id == audit_id)
    if start:
        q = q.where(TimeEntry.entry_date >= start)
    if end:
        q = q.where(TimeEntry.entry_date < end + timedelta(days=1))
    rows = db.execute(q.order_by(TimeEntry.entry_date.desc(), TimeEntry.id.desc()).limit(1000)).scalars()
    return [_time_out(db, e, user) for e in rows]


@router.post("/time", response_model=TimeOut, status_code=status.HTTP_201_CREATED)
def add_time(payload: TimeIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> TimeOut:
    day = payload.entry_date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    if day > utcnow() + timedelta(days=1):
        raise field_error("entry_date", "cannot be in the future")
    if payload.category in AUDIT_WORK and payload.audit_id is None:
        raise field_error("audit_id", f"is required for {payload.category} time")
    if payload.audit_id is not None and db.get(Audit, payload.audit_id) is None:
        raise field_error("audit_id", "is not a known audit")
    booked = db.execute(
        select(func.coalesce(func.sum(TimeEntry.hours), 0)).where(
            TimeEntry.user_id == user.id, TimeEntry.entry_date >= day, TimeEntry.entry_date < day + timedelta(days=1)
        )
    ).scalar_one()
    if float(booked) + payload.hours > 24:
        raise field_error("hours", f"would take the day over 24 hours ({float(booked):g} already booked)")
    e = TimeEntry(
        user_id=user.id,
        audit_id=payload.audit_id,
        category=payload.category,
        entry_date=day,
        hours=payload.hours,
        description=payload.description.strip(),
    )
    db.add(e)
    db.flush()
    log_action(db, user_id=user.id, action=f"TIME_ADD id={e.id} hours={payload.hours:g}", request=request)
    db.commit()
    return _time_out(db, e, user)


@router.delete("/time/{entry_id}")
def delete_time(entry_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    e = db.get(TimeEntry, entry_id)
    if e is None or (e.user_id != user.id and user.role != Role.Admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time entry not found")
    db.delete(e)
    log_action(db, user_id=user.id, action=f"TIME_DELETE id={entry_id}", request=request)
    db.commit()
    return {"message": "Time entry deleted"}


# ------------------------------------------------------------------ capacity summary


class AuditorLoad(BaseModel):
    user_id: int
    name: str
    grade: str
    skills: list[str]
    certifications: list[str] = []
    available_hours: int
    planned_hours: int
    logged_hours: float
    audit_hours: float
    load_pct: int  # planned / available
    utilisation_pct: int  # audit-work hours / logged hours


class AuditBudget(BaseModel):
    audit_id: int
    title: str
    status: str
    budget_hours: int
    actual_hours: float
    variance_hours: float


class CapacitySummary(BaseModel):
    fiscal_year: int
    auditors: list[AuditorLoad]
    audits: list[AuditBudget]
    totals: dict[str, float]


def year_bounds(fy: int) -> tuple[datetime, datetime]:
    return datetime(fy, 1, 1), datetime(fy + 1, 1, 1)


def audit_budgets(db: DBSession, fy: int | None = None) -> list[AuditBudget]:
    from app.domains.assurance.planning.models import AssurancePlan, PlanEngagement
    from app.domains.audit.memos.models import PlanningMemo

    memos = {m.audit_id: m.budget_hours for m in db.execute(select(PlanningMemo)).scalars()}
    eng = {
        e.audit_id: e.budget_hours
        for e in db.execute(select(PlanEngagement).where(PlanEngagement.audit_id.is_not(None))).scalars()
    }
    actual = dict(
        db.execute(
            select(TimeEntry.audit_id, func.sum(TimeEntry.hours))
            .where(TimeEntry.audit_id.is_not(None))
            .group_by(TimeEntry.audit_id)
        ).all()
    )
    q = select(Audit)
    if fy is not None:
        plan_ids = select(AssurancePlan.id).where(AssurancePlan.fiscal_year == fy)
        start, end = year_bounds(fy)
        q = q.where(
            (Audit.plan_id.in_(plan_ids))
            | ((Audit.plan_id.is_(None)) & (Audit.created_at >= start) & (Audit.created_at < end))
        )
    out = []
    for a in db.execute(q.order_by(Audit.id.desc())).scalars():
        budget = memos.get(a.id) or eng.get(a.id) or 0
        act = float(actual.get(a.id) or 0)
        out.append(
            AuditBudget(
                audit_id=a.id,
                title=a.title,
                status=a.status.value,
                budget_hours=budget,
                actual_hours=act,
                variance_hours=round(budget - act, 2),
            )
        )
    return out


def capacity_summary(db: DBSession, fy: int) -> CapacitySummary:
    from app.domains.assurance.planning.models import AssurancePlan, PlanEngagement

    start, end = year_bounds(fy)
    profiles = {p.user_id: p for p in db.execute(select(AuditorProfile)).scalars()}
    planned: dict[int, int] = defaultdict(int)
    for e in db.execute(
        select(PlanEngagement)
        .join(AssurancePlan, AssurancePlan.id == PlanEngagement.plan_id)
        .where(AssurancePlan.fiscal_year == fy, PlanEngagement.status != EngagementStatus.Cancelled)
    ).scalars():
        if e.lead_auditor_id:
            planned[e.lead_auditor_id] += e.budget_hours or 0
    logged: dict[int, float] = defaultdict(float)
    audit_h: dict[int, float] = defaultdict(float)
    for e in db.execute(select(TimeEntry).where(TimeEntry.entry_date >= start, TimeEntry.entry_date < end)).scalars():
        logged[e.user_id] += e.hours
        if e.category in AUDIT_WORK:
            audit_h[e.user_id] += e.hours
    auditors = []
    for u in _staff_users(db):
        p = profiles.get(u.id)
        avail = p.annual_hours if p else 1600
        auditors.append(
            AuditorLoad(
                user_id=u.id,
                name=_name(u),
                grade=p.grade if p else "",
                skills=_split(p.skills) if p else [],
                certifications=_split(p.certifications) if p else [],
                available_hours=avail,
                planned_hours=planned[u.id],
                logged_hours=round(logged[u.id], 2),
                audit_hours=round(audit_h[u.id], 2),
                load_pct=round(100 * planned[u.id] / avail) if avail else 0,
                utilisation_pct=round(100 * audit_h[u.id] / logged[u.id]) if logged[u.id] else 0,
            )
        )
    budgets = audit_budgets(db, fy)
    total_logged = sum(logged.values())
    totals = {
        "available_hours": sum(a.available_hours for a in auditors),
        "planned_hours": sum(a.planned_hours for a in auditors),
        "logged_hours": round(total_logged, 2),
        "audit_hours": round(sum(audit_h.values()), 2),
        "utilisation_pct": round(100 * sum(audit_h.values()) / total_logged) if total_logged else 0,
    }
    return CapacitySummary(fiscal_year=fy, auditors=auditors, audits=budgets, totals=totals)


@router.get("/summary", response_model=CapacitySummary)
def get_summary(fiscal_year: int | None = None, db: DBSession = Depends(get_db), user: User = Staff) -> CapacitySummary:
    from app.core.regional import current_fiscal_year

    return capacity_summary(db, fiscal_year or current_fiscal_year())


