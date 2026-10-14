"""Saved list views: a user's named search + filter combinations per module."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import utcnow


class SavedView(Base):
    __tablename__ = "saved_views"
    __table_args__ = (UniqueConstraint("user_id", "module", "name", name="uq_saved_view"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    params: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # JSON {param: value}
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
