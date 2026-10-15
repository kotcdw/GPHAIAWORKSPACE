"""Admin-defined extra fields for a module's records (stored as JSON on the record)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import utcnow

FIELD_TYPES = ("text", "longtext", "number", "date", "select", "yesno")


class CustomField(Base):
    __tablename__ = "custom_fields"
    __table_args__ = (UniqueConstraint("module", "field_key", name="uq_custom_fields_module_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    module: Mapped[str] = mapped_column(String(50), nullable=False)
    field_key: Mapped[str] = mapped_column(String(60), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    field_type: Mapped[str] = mapped_column(String(20), nullable=False, default="text")
    options: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON list for "select"
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    help: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    audit_type: Mapped[str | None] = mapped_column(String(60), nullable=True)  # None = every audit type
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
