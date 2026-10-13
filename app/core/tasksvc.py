"""Task Center service: create tasks and auto-generate system tasks."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.enums import TaskStatus
from app.modules.tasks.models import Task
from app.modules.users.models import User


def _user_id_by_email(db: DBSession, email: str | None) -> int | None:
    if not email:
        return None
    return db.execute(
        select(User.id).where(func.lower(User.email) == email.lower()).order_by(User.id).limit(1)
    ).scalar_one_or_none()


def create_task(
    db: DBSession,
    *,
    title: str,
    description: str = "",
    assignee_id: int | None = None,
    assignor_id: int | None = None,
    due_date: datetime | None = None,
    source_type: str | None = None,
    source_id: int | None = None,
    system_generated: bool = False,
) -> Task:
    """Create a task in the current transaction."""
    task = Task(
        title=title[:255],
        description=description,
        assignee_id=assignee_id,
        assignor_id=assignor_id,
        status=TaskStatus.Open,
        due_date=due_date,
        source_type=source_type,
        source_id=source_id,
        system_generated=system_generated,
    )
    db.add(task)
    db.flush()
    return task


def auto_task_for_record(
    db: DBSession,
    *,
    record_type: str,
    record,  # noqa: ANN001 - module record instance with id + optional owner_email
    action: str,
    assignor_id: int | None = None,
) -> Task:
    """Create the system task raised when a record is created or reassigned.

    The task is assigned to the record owner (matched by ``owner_email``) when
    that email belongs to a known user; otherwise it is left unassigned so an
    administrator can triage it.
    """
    owner_email = getattr(record, "owner_email", None)
    assignee_id = _user_id_by_email(db, owner_email)
    record_id = getattr(record, "id", None)
    title = f"{action} {record_type} #{record_id}" if record_id is not None else f"{action} {record_type}"
    return create_task(
        db,
        title=title,
        description=f"System task generated for {record_type} #{record_id}",
        assignee_id=assignee_id,
        assignor_id=assignor_id,
        source_type=record_type,
        source_id=record_id,
        system_generated=True,
    )