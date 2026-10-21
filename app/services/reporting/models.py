"""Saved reports, dashboards and presentations (one table, by kind) and AI Reporting workstreams.

Definitions are JSON. Nothing is hard-deleted: items and workstreams are archived so past sharing and
publishing decisions stay explainable.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import utcnow

KINDS = ("report", "dashboard", "presentation")
ITEM_STATUSES = ("Draft", "Active")
ACCESS = ("Private", "Staff", "Groups")
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
