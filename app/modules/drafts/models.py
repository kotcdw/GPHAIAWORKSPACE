"""Autosaved form drafts.

Every form in the UI continuously saves what the user has typed so far as a
draft, keyed by the form (``form_key``, e.g. ``capa:new`` or ``risk:edit:12``).
A draft survives validation errors, closed tabs, crashes and network drops,
and is restored the next time the user opens the same form - on any device.
Submitting the form successfully deletes the draft. Drafts are private to
their author.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import utcnow


class FormDraft(Base):
    __tablename__ = "form_drafts"
    __table_args__ = (UniqueConstraint("user_id", "form_key", name="uq_form_drafts_user_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    form_key: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    record_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    record_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
