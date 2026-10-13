"""Nonconformances."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.enums import NCStatus, Severity, _enum, utcnow

if TYPE_CHECKING:
    from app.modules.capa.models import Capa


class Nonconformance(Base):
    __tablename__ = "nonconformances"

    id: Mapped[int] = mapped_column(primary_key=True)
    nc_ref: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    severity: Mapped[Severity] = mapped_column(_enum(Severity), nullable=False, default=Severity.Medium)
    disposition: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[NCStatus] = mapped_column(_enum(NCStatus), nullable=False, default=NCStatus.Open)
    owner_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    audit_id: Mapped[int | None] = mapped_column(ForeignKey("audits.id", ondelete="SET NULL"), nullable=True)
    linked_capa_id: Mapped[int | None] = mapped_column(ForeignKey("capa.id", ondelete="SET NULL"), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    linked_capa: Mapped[Capa | None] = relationship(
        "Capa", foreign_keys=[linked_capa_id], lazy="selectin"
    )