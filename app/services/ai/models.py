"""Log of every AI request (who asked, for which record, which provider/model, outcome).

The prompt and the answer are not stored here: the answer is returned to the user as a draft and is only
saved, like any other edit, when the user accepts it.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import utcnow


class AiRequest(Base):
    __tablename__ = "ai_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    feature: Mapped[str] = mapped_column(String(40), nullable=False)
    record_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    record_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    input_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # ok | error
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, index=True)
