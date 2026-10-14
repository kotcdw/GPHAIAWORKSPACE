"""Notification routes: the signed-in user's bell."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session as DBSession

from app.core.database import get_db
from app.core.deps import require_active_user
from app.core.schemas import MessageOut
from app.platform.notifications.models import Notification
from app.platform.users.models import User

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str
    link_type: str | None
    link_id: int | None
    is_read: bool
    created_at: datetime


class NotificationList(BaseModel):
    unread: int
    items: list[NotificationOut]


@router.get("", response_model=NotificationList)
def my_notifications(
    unread_only: bool = False,
    limit: int = 30,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_active_user),
) -> NotificationList:
    limit = max(1, min(limit, 100))
    query = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        query = query.where(Notification.is_read.is_(False))
    items = db.execute(query.order_by(Notification.id.desc()).limit(limit)).scalars().all()
    unread = db.execute(
        select(func.count()).select_from(Notification).where(
            Notification.user_id == user.id, Notification.is_read.is_(False)
        )
    ).scalar_one()
    return NotificationList(unread=unread, items=[NotificationOut.model_validate(n) for n in items])


@router.post("/{notification_id}/read", response_model=MessageOut)
def mark_read(
    notification_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)
) -> MessageOut:
    note = db.get(Notification, notification_id)
    if note is None or note.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    note.is_read = True
    db.commit()
    return MessageOut(message="Marked as read")


@router.post("/read-all", response_model=MessageOut)
def mark_all_read(db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> MessageOut:
    db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    db.commit()
    return MessageOut(message="All notifications marked as read")
