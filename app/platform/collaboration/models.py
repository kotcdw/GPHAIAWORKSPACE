"""Comments on any record and the people they mention.

A mention notifies the person and puts the comment in their Projects until they mark it done or reply on the record.
Comments are never edited after posting; the author may withdraw one (the text is kept for the audit trail).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import utcnow


class Comment(Base):
    __tablename__ = "record_comments"
    __table_args__ = (Index("ix_record_comments_record", "record_type", "record_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    record_type: Mapped[str] = mapped_column(String(40), nullable=False)
    record_id: Mapped[int] = mapped_column(Integer, nullable=False)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CommentMention(Base):
    __tablename__ = "comment_mentions"

    id: Mapped[int] = mapped_column(primary_key=True)
    comment_id: Mapped[int] = mapped_column(ForeignKey("record_comments.id", ondelete="CASCADE"), nullable=False,
                                            index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    done_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
