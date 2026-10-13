"""Per-record history writer.

``record_history`` is the human-facing activity trail for individual records
(distinct from the immutable ``audit_logs`` global trail). Entries may carry an
approval-cycle number so a record's history can be grouped per cycle.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.audit import client_ip
from app.core.enums import utcnow
from app.modules.history.models import RecordHistory


def log_record_history(
    db: DBSession,
    *,
    record_type: str,
    record_id: int,
    user_id: int | None,
    action: str,
    cycle_no: int | None = None,
    request=None,  # noqa: ANN001
    commit: bool = False,
) -> RecordHistory:
    """Append an entry to a record's history (added to the current transaction)."""
    entry = RecordHistory(
        record_type=record_type,
        record_id=record_id,
        user_id=user_id,
        action=action[:500],
        cycle_no=cycle_no,
        timestamp=utcnow(),
        ip_address=client_ip(request),
    )
    db.add(entry)
    if commit:
        db.commit()
    return entry


def list_record_history(
    db: DBSession,
    record_type: str,
    record_id: int,
    *,
    cycle_no: int | None = None,
) -> list[RecordHistory]:
    """Return a record's history, optionally filtered to one approval cycle."""
    stmt = (
        select(RecordHistory)
        .where(RecordHistory.record_type == record_type, RecordHistory.record_id == record_id)
        .order_by(RecordHistory.timestamp, RecordHistory.id)
    )
    if cycle_no is not None:
        stmt = stmt.where(RecordHistory.cycle_no == cycle_no)
    return list(db.execute(stmt).scalars().all())