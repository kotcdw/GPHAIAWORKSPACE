"""Frameworks and the standard controls library.

A framework is any source of expected controls GPHA wants to audit against: a control framework (COSO), a risk
standard (ISO 31000), an IT framework (COBIT), a law or regulation (PFM Regulations), or a GPHA policy. Each holds
standard controls with a suggested test; auditors copy them into an engagement's risk and control matrix.
Everything is set up by the Audit Administrator - nothing is built in.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import ControlFrequency, ControlNature, ControlType, _enum, utcnow


class Framework(Base):
    __tablename__ = "frameworks"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    framework_type: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    issuer: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class LibraryControl(Base):
    __tablename__ = "library_controls"
    __table_args__ = (UniqueConstraint("framework_id", "ref", name="uq_library_controls_framework_ref"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    framework_id: Mapped[int] = mapped_column(ForeignKey("frameworks.id", ondelete="CASCADE"), nullable=False,
                                              index=True)
    ref: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    process_area: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    risk_statement: Mapped[str] = mapped_column(Text, nullable=False, default="")
    control_type: Mapped[ControlType] = mapped_column(_enum(ControlType), nullable=False,
                                                      default=ControlType.Preventive)
    nature: Mapped[ControlNature] = mapped_column(_enum(ControlNature), nullable=False, default=ControlNature.Manual)
    frequency: Mapped[ControlFrequency] = mapped_column(_enum(ControlFrequency), nullable=False,
                                                        default=ControlFrequency.Monthly)
    is_key: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    test_procedure: Mapped[str] = mapped_column(Text, nullable=False, default="")
    criterion_id: Mapped[int | None] = mapped_column(ForeignKey("criteria.id", ondelete="SET NULL"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
