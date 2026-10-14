"""User accounts.

Owns the ``users`` table. Cross-module relationships use string targets so the
mapper registry resolves them once all model modules are imported (no import
cycles).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.enums import ReviewLevel, Role, _enum, utcnow

if TYPE_CHECKING:  # pragma: no cover - resolved by the mapper registry at runtime
    from app.domains.audit.audits.models import Audit
    from app.platform.auth.models import Session


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(_enum(Role), nullable=False, default=Role.Auditee)
    email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    first_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    last_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    company: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Supervisory level for the report review chain (None = preparer only).
    review_level: Mapped[ReviewLevel | None] = mapped_column(_enum(ReviewLevel), nullable=True)
    # Optional TOTP multi-factor authentication; the secret is stored encrypted.
    mfa_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    # Job role (see app.core.permissions.JOB_ROLES); empty = derived from role / review level.
    job_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # The entity (normally a port or office) where the user is based.
    work_entity_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL", use_alter=True, name="fk_users_work_entity"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    audits: Mapped[list[Audit]] = relationship("Audit", back_populates="creator")
    sessions: Mapped[list[Session]] = relationship(
        "Session",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<User id={self.id} username={self.username!r} role={self.role.value}>"
