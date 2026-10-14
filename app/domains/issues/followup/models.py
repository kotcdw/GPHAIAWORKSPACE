"""Register of follow-up reports submitted (quarterly reports and annual statements)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import utcnow


class FollowupSubmission(Base):
    __tablename__ = "followup_submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # quarterly | annual
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    quarter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    period_label: Mapped[str] = mapped_column(String(60), nullable=False)
    recipients: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON list
    submitted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    snapshot: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"), nullable=False)
    counts: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
