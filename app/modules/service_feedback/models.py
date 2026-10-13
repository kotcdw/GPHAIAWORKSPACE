"""Service feedback (complaints)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import FeedbackStatus, _enum, utcnow


class ServiceFeedback(Base):
    __tablename__ = "service_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    sf_ref: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    received_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    status: Mapped[FeedbackStatus] = mapped_column(
        _enum(FeedbackStatus), nullable=False, default=FeedbackStatus.Open
    )
    owner_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linked_nc_id: Mapped[int | None] = mapped_column(
        ForeignKey("nonconformances.id", ondelete="SET NULL"), nullable=True
    )
    linked_capa_id: Mapped[int | None] = mapped_column(ForeignKey("capa.id", ondelete="SET NULL"), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)