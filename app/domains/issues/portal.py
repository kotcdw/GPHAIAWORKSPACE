"""Task Manager items from follow-up: agreed actions (remediation) owned by the signed-in person."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.enums import CapaStatus
from app.platform.users.models import User


def items(db: DBSession, user: User) -> list[dict]:
    from app.domains.issues.capa.models import Capa

    if not user.email:
        return []
    rows = db.execute(select(Capa).where(func.lower(Capa.owner_email) == user.email.lower(),
                                         Capa.status.in_((CapaStatus.Open, CapaStatus.InProgress)))).scalars()
    return [{"section": "Agreed actions", "kind": "capa", "id": c.id, "ref": c.capa_ref, "title": c.title,
             "detail": f"{c.severity.value} · {c.implementation_status}", "due": c.due_date,
             "status": c.status.value, "action": "Update progress", "open": {"type": "capa", "id": c.id}} for c in rows]
