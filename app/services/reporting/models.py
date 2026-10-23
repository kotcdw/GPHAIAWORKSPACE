"""Saved reports, dashboards and presentations (one table, by kind) and AI Reporting workstreams.

Definitions are JSON. Nothing is hard-deleted: items and workstreams are archived so past sharing and
publishing decisions stay explainable.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import utcnow

KINDS = ("report", "dashboard", "presentation")
ITEM_STATUSES = ("Draft", "Active")
BROADCAST_FREQUENCIES = ("Daily", "Weekly", "Monthly")
WORKSTREAM_STATUSES = ("Draft", "In review", "Approved", "Published")


class ReportItem(Base):
    __tablename__ = "report_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    definition: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # JSON
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Draft")
    access: Mapped[str] = mapped_column(String(20), nullable=False, default="Private")
    group_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON list
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    folder: Mapped[str] = mapped_column(String(120), nullable=False, default="My Reports")
    settings: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: show_on_browse, allow_dashboards
    user_ids: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list: Private access for these users
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class AiWorkstream(Base):
    __tablename__ = "ai_report_workstreams"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sources: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON list of report specs
    facts: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: the stored facts, never generated
    facts_generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    narrative: Mapped[str] = mapped_column(Text, nullable=False, default="")
    narrative_origin: Mapped[str] = mapped_column(String(20), nullable=False, default="none")  # none|ai|edited
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Draft")
    review_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    access: Mapped[str] = mapped_column(String(20), nullable=False, default="Private")
    group_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    user_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class ReportBroadcast(Base):
    """Broadcast schedule: send an active report, dashboard or presentation to chosen people on a timer. Each
    recipient opens it with their own access; people it is not shared with are skipped."""

    __tablename__ = "report_broadcasts"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("report_items.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False, default="Weekly")
    weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0 = Monday (Weekly)
    day_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-28 (Monthly)
    hour: Mapped[int] = mapped_column(Integer, nullable=False, default=8)  # workspace time zone
    user_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    group_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_result: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class ReportMedia(Base):
    """A video uploaded for a presentation slide (MP4 or WebM), served from this application."""

    __tablename__ = "report_media"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    filename: Mapped[str] = mapped_column(String(200), nullable=False)
    content_type: Mapped[str] = mapped_column(String(40), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    stored_name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
