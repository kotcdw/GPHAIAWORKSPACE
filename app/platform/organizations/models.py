"""Organizations / entities: GPHA ports, offices, departments and units, and external parties."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import OrganizationStatus, _enum, utcnow


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_ref: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[OrganizationStatus] = mapped_column(
        _enum(OrganizationStatus), nullable=False, default=OrganizationStatus.Pending
    )
    evaluation_end_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Hierarchy (Port -> Department -> Unit) and address.
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set up by administrators: this entity receives a copy of the approved Assurance Plan, under this label
    # (e.g. "HQ", "PIA Tema"), and engagements can name it as their responsible site.
    plan_destination: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    destination_label: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # Administration: who heads the unit, and whether it is still in use. A unit that is no longer used is
    # deactivated (never deleted once approved), so the audits, plans and history that name it stay intact.
    head_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL", use_alter=True, name="fk_organizations_head_user"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deactivated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL", use_alter=True, name="fk_organizations_deactivated_by"),
        nullable=True)
    deactivation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Values of admin-defined custom fields, JSON {field_key: value}.
    custom_fields: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Organization id={self.id} ref={self.org_ref!r} status={self.status.value}>"