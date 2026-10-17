"""Follow-up timeline of a remediation action and the rules for changing its target date.

Every step of follow-up is appended to ``capa_events`` (append-only), so progress notes, evidence and the
auditor's validation are never lost when they are updated, and every revised target date keeps the old
date, the new date, the reason and who agreed it.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.audit import client_ip, log_action
from app.core.enums import utcnow
from app.core.history import log_record_history
from app.domains.issues.capa.models import Capa, CapaEvent

KINDS = ("created", "progress", "implementation", "evidence_file", "validation", "extension", "escalation",
         "reopened", "risk_accepted", "withdrawal", "closed", "note")


def add_event(db: DBSession, capa: Capa, kind: str, *, user_id: int | None, text: str | None = None,
              request: Request | None = None, old_due: datetime | None = None,
              new_due: datetime | None = None) -> CapaEvent:
    event = CapaEvent(capa_id=capa.id, kind=kind, user_id=user_id, text=(text or None), old_due_date=old_due,
                      new_due_date=new_due, created_at=utcnow(), ip_address=client_ip(request))
    db.add(event)
    return event


def events(db: DBSession, capa_id: int) -> list[CapaEvent]:
    return list(db.execute(select(CapaEvent).where(CapaEvent.capa_id == capa_id)
                           .order_by(CapaEvent.created_at, CapaEvent.id)).scalars())


def change_due_date(db: DBSession, capa: Capa, new_due: datetime, *, reason: str, user_id: int | None,
                    request: Request | None = None, source: str = "") -> bool:
    """Revise the target date. Keeps the first agreed date, counts extensions, records old/new/reason and
    restarts escalation when the new date is in the future. Returns False when the date is unchanged."""
    old_due = capa.due_date
    if old_due is not None and new_due is not None and old_due.date() == new_due.date():
        return False
    reason = (reason or "").strip()
    if old_due is not None and len(reason) < 10:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Give the reason for revising the target date (at least 10 characters)")
    if capa.original_due_date is None:
        capa.original_due_date = old_due or new_due
    if old_due is not None and new_due is not None and new_due > old_due:
        capa.extension_count = (capa.extension_count or 0) + 1
    capa.due_date = new_due
    if new_due is not None and new_due > utcnow():
        capa.escalation_level = 0
    text = f"{source}: {reason}" if source and reason else (reason or source or None)
    add_event(db, capa, "extension", user_id=user_id, text=text, request=request, old_due=old_due, new_due=new_due)
    old_txt = f"{old_due:%d %b %Y}" if old_due else "none"
    new_txt = f"{new_due:%d %b %Y}" if new_due else "none"
    log_record_history(db, record_type="capa", record_id=capa.id, user_id=user_id, request=request,
                       action=f"TARGET DATE {old_txt} -> {new_txt}" + (f" ({reason[:300]})" if reason else ""))
    log_action(db, user_id=user_id, request=request,
               action=f"REMEDIATION_DUE_DATE_CHANGE id={capa.id} {old_txt} -> {new_txt}")
    return True
