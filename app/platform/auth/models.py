"""Authentication sessions (server-side HttpOnly cookie backing).

Owns the ``sessions`` table. References ``users`` by FK string and a lazy
relationship target so no import cycle is created with the users module.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.enums import utcnow

if TYPE_CHECKING:  # pragma: no cover - resolved by the mapper registry at runtime
    from app.platform.users.models import User


class Session(Base):
    """Server-side session backing an HttpOnly cookie."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Last request the person made (background refreshes excluded); drives the idle sign-out.
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[User] = relationship("User", back_populates="sessions")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Session id={self.id} user_id={self.user_id} revoked={self.revoked}>"
