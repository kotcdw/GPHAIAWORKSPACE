"""Workflow definitions, the transition log, work items and SLA policies."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import utcnow


class WorkflowDefinition(Base):
    """A versioned workflow for one record type (states, transitions, who may act). JSON in ``definition``."""

    __tablename__ = "workflow_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    audit_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class WorkflowTransition(Base):
    """One status change of a record (append-only)."""

    __tablename__ = "workflow_transitions"
    __table_args__ = (Index("ix_workflow_transitions_record", "record_type", "record_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    record_type: Mapped[str] = mapped_column(String(40), nullable=False)
    record_id: Mapped[int] = mapped_column(Integer, nullable=False)
    audit_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    from_state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_state: Mapped[str] = mapped_column(String(40), nullable=False)
    action: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # False when the change is not in the record type's workflow definition (recorded, flagged, never blocked).
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="app")  # app | api | system
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, index=True)


class WorkItem(Base):
    """A task in someone's inbox: prepare, review, respond, validate... Derived from the records."""

    __tablename__ = "work_items"
    __table_args__ = (
        Index("ix_work_items_assignee_status", "assignee_id", "status"),
        Index("ix_work_items_record", "record_type", "record_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    record_type: Mapped[str] = mapped_column(String(40), nullable=False)
    record_id: Mapped[int] = mapped_column(Integer, nullable=False)
    audit_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    assignee_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="open")  # open | done | cancelled
    sla_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # True when the due date comes from the record itself (target date, response deadline), not the SLA policy.
    due_from_record: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sla_state: Mapped[str] = mapped_column(String(10), nullable=False, default="ok")  # ok | warning | breached
    warned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    breached_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="normal")  # normal | high
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SlaPolicy(Base):
    """Time allowed for one kind of task, in working days (public holidays from Configuration are skipped)."""

    __tablename__ = "sla_policies"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    working_days: Mapped[int] = mapped_column(Integer, nullable=False)
    warn_before_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    escalate_on_breach: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
