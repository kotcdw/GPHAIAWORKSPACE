"""In-app notifications (the bell) - one row per recipient."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import utcnow


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Soft link to the record the notification is about (opened from the bell).
    link_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    link_id: Mapped[int | None] = mapped_column(nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    emailed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
