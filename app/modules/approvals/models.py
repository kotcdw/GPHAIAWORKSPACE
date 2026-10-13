"""Electronic-signature approval cycles (password attestation only).

Each row records one approver's decision within a numbered cycle for a record
(identified by ``record_type`` + ``record_id``). The approver's password is
verified at signing time and **never** stored.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import ApprovalDecision, _enum, utcnow


class ApprovalCycle(Base):
    __tablename__ = "approval_cycles"
    __table_args__ = (Index("ix_approval_cycles_record", "record_type", "record_id", "cycle_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    record_type: Mapped[str] = mapped_column(String(50), nullable=False)
    record_id: Mapped[int] = mapped_column(nullable=False)
    cycle_no: Mapped[int] = mapped_column(nullable=False, default=1)
    approver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decision: Mapped[ApprovalDecision] = mapped_column(_enum(ApprovalDecision), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<ApprovalCycle {self.record_type}#{self.record_id} "
            f"cycle={self.cycle_no} decision={self.decision.value}>"
        )