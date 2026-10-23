"""Broadcast schedules (Reports › report › Broadcast schedule › Set schedule).

The owner of an active report, dashboard or presentation sends it to chosen users and groups Daily, Weekly or
Monthly at an hour in the workspace time zone. Each delivery goes only to people the item is shared with, and each
of them opens it with their own access. A schedule pauses itself when its item is archived or set back to draft.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user
from app.core.enums import utcnow
from app.platform.users.models import User
from app.services.reporting.models import ReportBroadcast, ReportItem
from app.services.reporting.router import _owned, deliver
from app.services.reporting.sharing import check_audience, ensure_staff, ids

router = APIRouter(prefix="/api/reporting", tags=["reporting"])
MAX_PER_ITEM = 10


class BroadcastIn(BaseModel):
    frequency: Literal["Daily", "Weekly", "Monthly"] = "Weekly"
    weekday: int | None = Field(default=None, ge=0, le=6)
    day_of_month: int | None = Field(default=None, ge=1, le=28)
    hour: int = Field(default=8, ge=0, le=23)
    user_ids: list[int] = Field(default_factory=list, max_length=200)
    group_ids: list[int] = Field(default_factory=list, max_length=50)
    message: str = Field(default="", max_length=2000)
    active: bool = True

    @model_validator(mode="after")
    def _when(self) -> BroadcastIn:
        if self.frequency == "Weekly" and self.weekday is None:
            raise ValueError("Choose the day of the week")
        if self.frequency == "Monthly" and self.day_of_month is None:
            raise ValueError("Choose the day of the month (1-28)")
        if not self.user_ids and not self.group_ids:
            raise ValueError("Choose who receives it")
        return self


def next_run(b: ReportBroadcast | BroadcastIn, after: datetime) -> datetime:
    """The next send time after ``after`` (naive UTC), computed in the workspace time zone."""
    from app.core.regional import zone

    tz = zone()
    local = after.replace(tzinfo=UTC).astimezone(tz)
    candidate = local.replace(hour=b.hour, minute=0, second=0, microsecond=0)
    for _ in range(400):
        ok = candidate > local and (
            b.frequency == "Daily"
            or (b.frequency == "Weekly" and candidate.weekday() == b.weekday)
            or (b.frequency == "Monthly" and candidate.day == b.day_of_month))
        if ok:
            return candidate.astimezone(UTC).replace(tzinfo=None)
        candidate = (candidate + timedelta(days=1)).replace(hour=b.hour)
    raise HTTPException(status_code=422, detail="The schedule never runs")  # pragma: no cover - guarded above


def _out(b: ReportBroadcast) -> dict:
    return {"id": b.id, "item_id": b.item_id, "frequency": b.frequency, "weekday": b.weekday,
            "day_of_month": b.day_of_month, "hour": b.hour, "user_ids": ids(b.user_ids), "group_ids": ids(b.group_ids),
            "message": b.message, "active": b.active, "next_run_at": b.next_run_at, "last_run_at": b.last_run_at,
            "last_result": b.last_result}


def _own_broadcast(db: DBSession, user: User, bid: int) -> tuple[ReportBroadcast, ReportItem]:
    b = db.get(ReportBroadcast, bid)
    if b is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return b, _owned(db, user, b.item_id)


def _apply(db: DBSession, b: ReportBroadcast, it: ReportItem, p: BroadcastIn) -> None:
    if p.active and it.status != "Active":
        raise HTTPException(status_code=409, detail="Activate it before scheduling it")
    groups, users = check_audience(db, "Private", p.group_ids, p.user_ids)
    b.frequency, b.hour, b.message, b.active = p.frequency, p.hour, p.message.strip(), p.active
    b.weekday = p.weekday if p.frequency == "Weekly" else None
    b.day_of_month = p.day_of_month if p.frequency == "Monthly" else None
    b.user_ids, b.group_ids = json.dumps(users), json.dumps(groups)
    b.next_run_at = next_run(b, utcnow()) if p.active else None


@router.get("/items/{item_id}/broadcasts")
def list_broadcasts(item_id: int, db: DBSession = Depends(get_db),
                    user: User = Depends(require_active_user)) -> list[dict]:
    ensure_staff(user)
    it = _owned(db, user, item_id)
    rows = db.execute(select(ReportBroadcast).where(ReportBroadcast.item_id == it.id)
                      .order_by(ReportBroadcast.id)).scalars()
    return [_out(b) for b in rows]


@router.post("/items/{item_id}/broadcasts", status_code=201)
def create_broadcast(item_id: int, payload: BroadcastIn, request: Request, db: DBSession = Depends(get_db),
                     user: User = Depends(require_active_user)) -> dict:
    ensure_staff(user)
    it = _owned(db, user, item_id)
    count = len(list(db.execute(select(ReportBroadcast.id).where(ReportBroadcast.item_id == it.id)).scalars()))
    if count >= MAX_PER_ITEM:
        raise HTTPException(status_code=409, detail=f"An item can have at most {MAX_PER_ITEM} schedules")
    b = ReportBroadcast(item_id=it.id, owner_id=user.id)
    _apply(db, b, it, payload)
    db.add(b)
    db.flush()
    log_action(db, user_id=user.id, request=request,
               action=f"REPORTING_BROADCAST_CREATE {it.kind} id={it.id} schedule={b.id} {b.frequency} {b.hour}h")
    db.commit()
    return _out(b)


@router.put("/broadcasts/{bid}")
def update_broadcast(bid: int, payload: BroadcastIn, request: Request, db: DBSession = Depends(get_db),
                     user: User = Depends(require_active_user)) -> dict:
    ensure_staff(user)
    b, it = _own_broadcast(db, user, bid)
    _apply(db, b, it, payload)
    log_action(db, user_id=user.id, request=request,
               action=f"REPORTING_BROADCAST_UPDATE schedule={b.id} {b.frequency} {b.hour}h active={b.active}")
    db.commit()
    return _out(b)


@router.delete("/broadcasts/{bid}")
def delete_broadcast(bid: int, request: Request, db: DBSession = Depends(get_db),
                     user: User = Depends(require_active_user)) -> dict:
    ensure_staff(user)
    b, it = _own_broadcast(db, user, bid)
    log_action(db, user_id=user.id, request=request, action=f"REPORTING_BROADCAST_DELETE schedule={b.id} item={it.id}")
    db.delete(b)
    db.commit()
    return {"ok": True}


def run_broadcasts(db: DBSession, now: datetime | None = None) -> int:
    """Send every schedule that is due. Returns how many schedules ran. Called by the server's timer."""
    now = now or utcnow()
    due = list(db.execute(select(ReportBroadcast).where(ReportBroadcast.active.is_(True),
                                                        ReportBroadcast.next_run_at.is_not(None),
                                                        ReportBroadcast.next_run_at <= now)).scalars())
    ran = 0
    for b in due:
        it = db.get(ReportItem, b.item_id)
        owner = db.get(User, b.owner_id) if b.owner_id else None
        if it is None or it.archived or it.status != "Active" or owner is None or not owner.is_active:
            b.active, b.next_run_at, b.last_result = False, None, "Paused: the item is no longer active"
            continue
        sent, blocked = deliver(db, owner, it, ids(b.user_ids), ids(b.group_ids), b.message)
        b.last_run_at, b.next_run_at = now, next_run(b, now)
        b.last_result = f"Sent to {sent}" + (f"; {blocked} not shared with it" if blocked else "")
        log_action(db, user_id=b.owner_id, action=f"REPORTING_BROADCAST_SEND schedule={b.id} item={it.id} sent={sent} "
                                                  f"not_shared={blocked}")
        ran += 1
    db.commit()
    return ran
