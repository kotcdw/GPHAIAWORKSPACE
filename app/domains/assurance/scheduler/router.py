"""Scheduler: engagement dates and auditor bookings on one timeline, with double-booking warnings.

Bookings never block: a manager may deliberately overlap two engagements. Every overlap is shown, returned as a
warning when the booking is saved, and sent to resource managers through the automation rules.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.appconfig import cfg
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_perm, staff_or_perm
from app.core.enums import EngagementStatus, Role
from app.core.permissions import job_role_of
from app.domains.assurance.planning.models import AssurancePlan, PlanEngagement
from app.domains.assurance.scheduler.models import BOOKING_KINDS, ENGAGEMENT_ROLES, ScheduleBooking
from app.platform.users.models import User

router = APIRouter(prefix="/api/schedule", tags=["scheduler"])
Viewer = Depends(staff_or_perm("oversight.resources", "governance.view"))
Manager = Depends(require_perm("oversight.resources", "plan.prepare"))


class BookingIn(BaseModel):
    user_id: int
    kind: str = "Engagement"
    plan_engagement_id: int | None = None
    role: str = "Team member"
    title: str = Field(default="", max_length=200)
    start_date: date
    end_date: date
    hours: int | None = Field(default=None, ge=0, le=5000)
    notes: str = Field(default="", max_length=2000)


class DatesIn(BaseModel):
    planned_start: date
    planned_end: date
    book_lead: bool = True


def _quarter_bounds(year: int, quarter: str) -> tuple[date, date]:
    q = int(quarter[1]) if quarter and quarter[1:].isdigit() else 1
    start = date(year, q * 3 - 2, 1)
    end = (date(year + (q == 4), 1 if q == 4 else q * 3 + 1, 1)) - timedelta(days=1)
    return start, end


def working_days(start: date, end: date) -> int:
    from app.core.workdays import holidays

    hols, n, d = holidays(), 0, start
    while d <= end:
        if d.weekday() < 5 and d not in hols:
            n += 1
        d += timedelta(days=1)
    return n


def _overlaps(a: ScheduleBooking, b: ScheduleBooking) -> bool:
    return a.start_date <= b.end_date and b.start_date <= a.end_date


def conflicts_for(db: DBSession, user_id: int, start: date | None = None, end: date | None = None,
                  only: ScheduleBooking | None = None) -> list[dict]:
    """Pairs of bookings of one person that overlap where at least one is an engagement."""
    q = select(ScheduleBooking).where(ScheduleBooking.user_id == user_id)
    if start and end:
        q = q.where(ScheduleBooking.start_date <= end, ScheduleBooking.end_date >= start)
    rows = list(db.execute(q.order_by(ScheduleBooking.start_date)).scalars())
    out = []
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if only is not None and only.id not in (a.id, b.id):
                continue
            if not _overlaps(a, b) or (a.kind != "Engagement" and b.kind != "Engagement"):
                continue
            if a.plan_engagement_id and a.plan_engagement_id == b.plan_engagement_id:
                continue
            ov_start, ov_end = max(a.start_date, b.start_date), min(a.end_date, b.end_date)
            out.append({"user_id": user_id, "a": a.id, "b": b.id, "from": ov_start, "to": ov_end,
                        "days": working_days(ov_start, ov_end),
                        "what": f"{_label(db, a)} and {_label(db, b)}"})
    return out


def _label(db: DBSession, b: ScheduleBooking) -> str:
    if b.plan_engagement_id:
        eng = db.get(PlanEngagement, b.plan_engagement_id)
        return eng.title if eng else "an engagement"
    return f"{b.kind.lower()}{f' ({b.title})' if b.title else ''}"


def _booking_out(db: DBSession, b: ScheduleBooking) -> dict:
    return {"id": b.id, "user_id": b.user_id, "kind": b.kind, "plan_engagement_id": b.plan_engagement_id,
            "role": b.role, "title": b.title or _label(db, b), "start_date": b.start_date, "end_date": b.end_date,
            "hours": b.hours, "notes": b.notes, "working_days": working_days(b.start_date, b.end_date)}


def _staff(db: DBSession) -> list[User]:
    return list(db.execute(select(User).where(User.is_active.is_(True), User.role.in_((Role.Admin, Role.Auditor)))
                           .order_by(User.full_name, User.username)).scalars())


@router.get("")
def timeline(start: date = Query(...), end: date = Query(...), site_id: int | None = None,
             db: DBSession = Depends(get_db), _: User = Viewer) -> dict:
    if end < start or (end - start).days > 400:
        raise HTTPException(status_code=422, detail="Choose a range of up to about a year")
    bookings = list(db.execute(select(ScheduleBooking).where(ScheduleBooking.start_date <= end,
                                                             ScheduleBooking.end_date >= start)).scalars())
    by_user: dict[int, list[ScheduleBooking]] = {}
    for b in bookings:
        by_user.setdefault(b.user_id, []).append(b)
    daily = int(cfg("schedule_daily_hours"))
    people, conflicts = [], []
    for u in _staff(db):
        mine = by_user.get(u.id, [])
        c = conflicts_for(db, u.id, start, end)
        conflicts += c
        eng_days = sum(working_days(max(b.start_date, start), min(b.end_date, end))
                       for b in mine if b.kind == "Engagement")
        people.append({"user_id": u.id, "name": u.full_name or u.username, "job_role": job_role_of(u),
                       "work_entity_id": u.work_entity_id,
                       "bookings": [_booking_out(db, b) for b in sorted(mine, key=lambda x: x.start_date)],
                       "conflicts": c, "engagement_days": eng_days,
                       "available_days": working_days(start, end), "hours_per_day": daily})
    if site_id:
        people = [p for p in people if p["work_entity_id"] == site_id or p["bookings"]]
    # Engagements of the plans that cover the range.
    years = list(range(start.year, end.year + 1))
    rows = db.execute(select(PlanEngagement, AssurancePlan).join(AssurancePlan,
                                                                 AssurancePlan.id == PlanEngagement.plan_id)
                      .where(AssurancePlan.fiscal_year.in_(years),
                             PlanEngagement.status != EngagementStatus.Cancelled)).all()
    engagements, unscheduled = [], []
    booked = {}
    for b in bookings:
        if b.plan_engagement_id:
            booked.setdefault(b.plan_engagement_id, []).append(b.user_id)
    for eng, plan in rows:
        if site_id and eng.site_entity_id not in (None, site_id):
            continue
        q_start, q_end = _quarter_bounds(plan.fiscal_year, eng.planned_quarter)
        item = {"id": eng.id, "title": eng.title, "plan_id": plan.id, "plan_ref": plan.plan_ref,
                "fiscal_year": plan.fiscal_year, "planned_quarter": eng.planned_quarter,
                "quarter_start": q_start, "quarter_end": q_end, "planned_start": eng.planned_start,
                "planned_end": eng.planned_end, "budget_hours": eng.budget_hours,
                "lead_auditor_id": eng.lead_auditor_id, "site_entity_id": eng.site_entity_id,
                "status": eng.status.value, "audit_id": eng.audit_id,
                "booked_user_ids": sorted(set(booked.get(eng.id, [])))}
        if eng.planned_start and eng.planned_end:
            if eng.planned_start <= end and eng.planned_end >= start:
                engagements.append(item)
        elif q_start <= end and q_end >= start:
            unscheduled.append(item)
    return {"start": start, "end": end, "working_days": working_days(start, end), "kinds": BOOKING_KINDS,
            "roles": ENGAGEMENT_ROLES, "people": people, "engagements": engagements, "unscheduled": unscheduled,
            "conflicts": conflicts}


def _validate(db: DBSession, payload: BookingIn) -> PlanEngagement | None:
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=422, detail="The end date is before the start date")
    if (payload.end_date - payload.start_date).days > 366:
        raise HTTPException(status_code=422, detail="A booking cannot be longer than a year")
    if payload.kind not in BOOKING_KINDS:
        raise HTTPException(status_code=422, detail=f"Kind must be one of: {', '.join(BOOKING_KINDS)}")
    user = db.get(User, payload.user_id)
    if user is None or not user.is_active or user.role not in (Role.Admin, Role.Auditor):
        raise HTTPException(status_code=422, detail="Choose an active member of the audit staff")
    eng = None
    if payload.kind == "Engagement":
        if payload.role not in ENGAGEMENT_ROLES:
            raise HTTPException(status_code=422, detail=f"Role must be one of: {', '.join(ENGAGEMENT_ROLES)}")
        eng = db.get(PlanEngagement, payload.plan_engagement_id or 0)
        if eng is None or eng.status == EngagementStatus.Cancelled:
            raise HTTPException(status_code=422, detail="Choose an engagement from the plan")
    elif len(payload.title.strip()) < 2 and payload.kind == "Other work":
        raise HTTPException(status_code=422, detail="Describe the other work")
    return eng


def _notify_conflicts(db: DBSession, booking: ScheduleBooking, found: list[dict]) -> None:
    if not found:
        return
    from app.platform.automations.engine import emit

    user = db.get(User, booking.user_id)
    emit(db, "schedule.conflict", "schedule_booking", booking.id,
         {"user": (user.full_name or user.username) if user else "", "what": found[0]["what"],
          "from": f"{found[0]['from']:%d %b %Y}", "to": f"{found[0]['to']:%d %b %Y}",
          "_people": {"subject_user": [booking.user_id]}},
         period=f"{booking.start_date:%Y%m%d}-{booking.end_date:%Y%m%d}")


@router.post("/bookings", status_code=201)
def create_booking(payload: BookingIn, request: Request, db: DBSession = Depends(get_db), user: User = Manager) -> dict:
    eng = _validate(db, payload)
    b = ScheduleBooking(user_id=payload.user_id, kind=payload.kind, plan_engagement_id=eng.id if eng else None,
                        role=payload.role if eng else "", title=payload.title.strip(), start_date=payload.start_date,
                        end_date=payload.end_date, hours=payload.hours, notes=payload.notes, created_by=user.id)
    db.add(b)
    db.flush()
    found = conflicts_for(db, b.user_id, only=b)
    _notify_conflicts(db, b, found)
    log_action(db, user_id=user.id, request=request,
               action=f"SCHEDULE_BOOK user={b.user_id} {b.kind} {b.start_date}..{b.end_date} conflicts={len(found)}")
    db.commit()
    return {"booking": _booking_out(db, b), "conflicts": found}


@router.put("/bookings/{booking_id}")
def update_booking(booking_id: int, payload: BookingIn, request: Request, db: DBSession = Depends(get_db),
                   user: User = Manager) -> dict:
    b = db.get(ScheduleBooking, booking_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    eng = _validate(db, payload)
    b.user_id, b.kind, b.plan_engagement_id = payload.user_id, payload.kind, eng.id if eng else None
    b.role, b.title, b.start_date, b.end_date = payload.role if eng else "", payload.title.strip(), \
        payload.start_date, payload.end_date
    b.hours, b.notes = payload.hours, payload.notes
    db.flush()
    found = conflicts_for(db, b.user_id, only=b)
    _notify_conflicts(db, b, found)
    log_action(db, user_id=user.id, request=request,
               action=f"SCHEDULE_UPDATE id={b.id} {b.start_date}..{b.end_date} conflicts={len(found)}")
    db.commit()
    return {"booking": _booking_out(db, b), "conflicts": found}


@router.delete("/bookings/{booking_id}")
def delete_booking(booking_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Manager) -> dict:
    b = db.get(ScheduleBooking, booking_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    db.delete(b)
    log_action(db, user_id=user.id, action=f"SCHEDULE_DELETE id={booking_id}", request=request)
    db.commit()
    return {"message": "Booking removed"}


@router.put("/engagements/{engagement_id}/dates")
def set_engagement_dates(engagement_id: int, payload: DatesIn, request: Request, db: DBSession = Depends(get_db),
                         user: User = Manager) -> dict:
    """Plan the fieldwork window. Moving outside the planned quarter is a plan change (change request), so the
    dates must stay inside it; the lead auditor is booked for the window unless asked not to."""
    eng = db.get(PlanEngagement, engagement_id)
    if eng is None:
        raise HTTPException(status_code=404, detail="Engagement not found")
    if eng.status == EngagementStatus.Cancelled:
        raise HTTPException(status_code=409, detail="The engagement is cancelled")
    if payload.planned_end < payload.planned_start:
        raise HTTPException(status_code=422, detail="The end date is before the start date")
    plan = db.get(AssurancePlan, eng.plan_id)
    q_start, q_end = _quarter_bounds(plan.fiscal_year, eng.planned_quarter)
    if payload.planned_start < q_start or payload.planned_end > q_end:
        raise HTTPException(status_code=422, detail=(
            f"The engagement is planned for {eng.planned_quarter} {plan.fiscal_year} "
            f"({q_start:%d %b} - {q_end:%d %b}). To move it to another quarter, raise a plan change request."))
    old_start, old_end = eng.planned_start, eng.planned_end
    eng.planned_start, eng.planned_end = payload.planned_start, payload.planned_end
    found: list[dict] = []
    # Keep existing bookings that matched the old window in step with the new one.
    for b in db.execute(select(ScheduleBooking).where(ScheduleBooking.plan_engagement_id == eng.id)).scalars():
        if old_start and b.start_date == old_start and b.end_date == old_end:
            b.start_date, b.end_date = payload.planned_start, payload.planned_end
    if payload.book_lead and eng.lead_auditor_id:
        exists = db.execute(select(ScheduleBooking).where(ScheduleBooking.plan_engagement_id == eng.id,
                                                          ScheduleBooking.user_id == eng.lead_auditor_id)).first()
        if not exists:
            b = ScheduleBooking(user_id=eng.lead_auditor_id, kind="Engagement", plan_engagement_id=eng.id,
                                role="Lead auditor", start_date=payload.planned_start, end_date=payload.planned_end,
                                hours=eng.budget_hours or None, created_by=user.id)
            db.add(b)
            db.flush()
            found = conflicts_for(db, b.user_id, only=b)
            _notify_conflicts(db, b, found)
    log_action(db, user_id=user.id, request=request,
               action=f"ENGAGEMENT_DATES id={eng.id} {payload.planned_start}..{payload.planned_end}")
    db.commit()
    return {"id": eng.id, "planned_start": eng.planned_start, "planned_end": eng.planned_end, "conflicts": found}


@router.get("/people/{user_id}/conflicts")
def person_conflicts(user_id: int, db: DBSession = Depends(get_db), _: User = Viewer) -> list[dict]:
    return conflicts_for(db, user_id)

