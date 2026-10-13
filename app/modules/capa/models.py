"""Corrective and preventive actions (CAPA)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.enums import CapaStatus, Severity, _enum, utcnow

if TYPE_CHECKING:
    from app.modules.nonconformances.models import Nonconformance


class Capa(Base):
    __tablename__ = "capa"

    id: Mapped[int] = mapped_column(primary_key=True)
    capa_ref: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    root_cause: Mapped[str] = mapped_column(Text, nullable=False, default="")
    corrective_action: Mapped[str] = mapped_column(Text, nullable=False, default="")
    preventive_action: Mapped[str] = mapped_column(Text, nullable=False, default="")
    effectiveness_check: Mapped[str] = mapped_column(Text, nullable=False, default="")
    severity: Mapped[Severity] = mapped_column(_enum(Severity), nullable=False, default=Severity.Medium)
    disposition: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[CapaStatus] = mapped_column(_enum(CapaStatus), nullable=False, default=CapaStatus.Open)
    owner_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_id: Mapped[int | None] = mapped_column(nullable=True)
    linked_nc_id: Mapped[int | None] = mapped_column(
        ForeignKey("nonconformances.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    linked_nc: Mapped[Nonconformance | None] = relationship(
        "Nonconformance", foreign_keys=[linked_nc_id], lazy="selectin"
    )