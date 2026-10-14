"""Compliance Maps: obligations (laws, regulations, standards, contracts), their requirements, and the standard
controls that meet each requirement. A requirement with no control is a coverage gap."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import utcnow

COMPLIANCE_STATUSES = ("Not assessed", "Compliant", "Partially compliant", "Non-compliant", "Not applicable")


class Regulation(Base):
    __tablename__ = "regulations"

    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    reg_type: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    issuer: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    @property
    def status(self) -> str:
        return "Active" if self.active else "Retired"


class Requirement(Base):
    __tablename__ = "requirements"
    __table_args__ = (UniqueConstraint("regulation_id", "ref", name="uq_requirements_regulation_ref"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    regulation_id: Mapped[int] = mapped_column(ForeignKey("regulations.id", ondelete="CASCADE"), nullable=False,
                                               index=True)
    ref: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
                                                 index=True)
    entity_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="Not assessed")
    # Set when the obligation changes (new version): the mapping and status need a fresh look.
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_assessed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    assessed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assessment_comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
