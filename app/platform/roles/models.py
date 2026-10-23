"""Overrides of the default job-role permissions, edited by the Platform Administrator."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import utcnow


class RolePermission(Base):
    __tablename__ = "role_permissions"

    job_role: Mapped[str] = mapped_column(String(40), primary_key=True)
    permission: Mapped[str] = mapped_column(String(60), primary_key=True)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class RoleModuleAccess(Base):
    """A module action the Super Administrator has refused a role in Access by module (View, Create, Edit or Delete
    rights that are not a single permission). Only refusals are stored; no row means the role design applies."""

    __tablename__ = "role_module_access"

    job_role: Mapped[str] = mapped_column(String(40), primary_key=True)
    module: Mapped[str] = mapped_column(String(80), primary_key=True)
    action: Mapped[str] = mapped_column(String(20), primary_key=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
