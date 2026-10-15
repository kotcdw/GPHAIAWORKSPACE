"""Task Tracker priorities from audit work: evidence requests waiting for the signed-in person."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.platform.users.models import User


def items(db: DBSession, user: User) -> list[dict]:
    from app.domains.audit.audits.models import Audit
    from app.domains.audit.evidence.models import EvidenceRequest

    rows = db.execute(select(EvidenceRequest, Audit).join(Audit, Audit.id == EvidenceRequest.audit_id).where(
        EvidenceRequest.assignee_id == user.id, EvidenceRequest.status.in_(("Requested", "Returned")))).all()
    return [{"section": "Evidence requests", "kind": "evidence_request", "id": r.id, "ref": r.request_ref,
             "title": r.title, "detail": f"Audit: {a.title}",
             "due": r.due_date, "status": r.status, "action": "Provide evidence",
             "open": {"type": "evidence_request", "id": r.id}} for r, a in rows]
