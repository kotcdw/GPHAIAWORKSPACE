"""IIA Topical Requirements (GIAS 2024): the requirement catalogue and each engagement's assessment of it.

A Topical Requirement is mandatory for assurance engagements and recommended for advisory ones when its topic is
the subject of a planned engagement, is identified during an engagement, or is the subject of an engagement request.
Each requirement is assessed for applicability; an exclusion keeps its rationale. Conformance is evaluated in
quality assessments.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import utcnow


class TopicalRequirement(Base):
    __tablename__ = "topical_requirements"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    effective_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class TopicalRequirementItem(Base):
    __tablename__ = "topical_requirement_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    requirement_id: Mapped[int] = mapped_column(ForeignKey("topical_requirements.id", ondelete="CASCADE"),
                                                nullable=False, index=True)
    area: Mapped[str] = mapped_column(String(40), nullable=False)  # Governance | Risk management | Control processes
    ref: Mapped[str] = mapped_column(String(10), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class EngagementTopical(Base):
    """Whether a topical requirement applies to an engagement, why, and who decided."""

    __tablename__ = "engagement_topicals"
    __table_args__ = (UniqueConstraint("audit_id", "requirement_id", name="uq_engagement_topical"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    audit_id: Mapped[int] = mapped_column(ForeignKey("audits.id", ondelete="CASCADE"), nullable=False, index=True)
    requirement_id: Mapped[int] = mapped_column(ForeignKey("topical_requirements.id", ondelete="CASCADE"),
                                                nullable=False)
    in_scope: Mapped[bool] = mapped_column(Boolean, nullable=False)
    trigger: Mapped[str | None] = mapped_column(String(60), nullable=True)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class EngagementTopicalItem(Base):
    """One requirement of the checklist on one engagement: assessed (with the conclusion) or excluded (with why)."""

    __tablename__ = "engagement_topical_items"
    __table_args__ = (UniqueConstraint("engagement_topical_id", "item_id", name="uq_engagement_topical_item"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    engagement_topical_id: Mapped[int] = mapped_column(ForeignKey("engagement_topicals.id", ondelete="CASCADE"),
                                                       nullable=False, index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("topical_requirement_items.id", ondelete="CASCADE"), nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)  # Assessed | Excluded
    conclusion: Mapped[str | None] = mapped_column(String(30), nullable=True)  # No exceptions | Exceptions noted
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    finding_id: Mapped[int | None] = mapped_column(ForeignKey("findings.id", ondelete="SET NULL"), nullable=True)
    assessed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
