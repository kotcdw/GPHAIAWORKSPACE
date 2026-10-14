"""Admin-defined automation rules: when <trigger> and <conditions>, do <actions>."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import utcnow


class AutomationRule(Base):
    __tablename__ = "automation_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    trigger: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    offset_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conditions: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON
    actions: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    builtin_key: Mapped[str | None] = mapped_column(String(60), nullable=True, unique=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class AutomationRun(Base):
    __tablename__ = "automation_runs"
    __table_args__ = (UniqueConstraint("rule_id", "record_type", "record_id", "period_key",
                                       name="uq_automation_runs_once"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("automation_rules.id", ondelete="CASCADE"), nullable=False,
                                         index=True)
    record_type: Mapped[str] = mapped_column(String(40), nullable=False)
    record_id: Mapped[int] = mapped_column(Integer, nullable=False)
    period_key: Mapped[str] = mapped_column(String(40), nullable=False, default="once")
    outcome: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    fired_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, index=True)
