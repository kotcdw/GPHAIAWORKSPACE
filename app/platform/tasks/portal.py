"""Task Manager items: open tasks assigned to the signed-in person."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.enums import TaskStatus
from app.platform.users.models import User


def items(db: DBSession, user: User) -> list[dict]:
    from app.platform.apps.registry import enabled
    from app.platform.tasks.models import Task

    if not enabled("tasks"):
        return []
    rows = db.execute(select(Task).where(Task.assignee_id == user.id,
                                         Task.status.in_((TaskStatus.Open, TaskStatus.InProgress)))).scalars()
    return [{"section": "Tasks", "kind": "task", "id": t.id, "ref": f"T-{t.id}", "title": t.title,
             "detail": (t.description or "")[:160], "due": t.due_date, "status": t.status.value, "action": "Open",
             "open": {"type": "task", "id": t.id}} for t in rows]
