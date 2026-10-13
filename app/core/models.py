"""Cross-cutting ORM models owned by the core layer."""

from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ReferenceSequence(Base):
    """Monotonic counter backing human-readable record references.

    One row per prefix (``NC``, ``CAPA``, ``ORG``, ``SH``, ``SF``). Incremented
    under a row lock so concurrent writers get unique references.
    """

    __tablename__ = "reference_sequences"

    prefix: Mapped[str] = mapped_column(String(20), primary_key=True)
    next_value: Mapped[int] = mapped_column(Integer, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<ReferenceSequence prefix={self.prefix!r} next_value={self.next_value}>"