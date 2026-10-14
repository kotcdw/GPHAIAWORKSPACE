"""Task Center routes: assigned to me / by me / closed."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session as DBSession

from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user
from app.core.enums import Role, TaskStatus
from app.core.tasksvc import create_task
from app.platform.tasks.models import Task
from app.platform.tasks.schemas import TaskCreate, TaskList, TaskOut, TaskUpdate
from app.platform.users.models import User

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _get_or_404(db: DBSession, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.get("", response_model=TaskList)
def list_tasks(
    db: DBSession = Depends(get_db),
    user: User = Depends(require_active_user),
    assigned_to_me: bool = Query(default=False),
    by_me: bool = Query(default=False),
    status_filter: TaskStatus | None = Query(default=None, alias="status"),
) -> TaskList:
    stmt = select(Task).order_by(Task.created_at.desc())
    if user.role != Role.Admin:
        # Non-admins only ever see tasks they are assigned to or assigned.
        stmt = stmt.where(or_(Task.assignee_id == user.id, Task.assignor_id == user.id))
    if assigned_to_me:
        stmt = stmt.where(Task.assignee_id == user.id)
    if by_me:
        stmt = stmt.where(Task.assignor_id == user.id)
    if status_filter is not None:
        stmt = stmt.where(Task.status == status_filter)
    items = list(db.execute(stmt).scalars().all())
    return TaskList(total=len(items), items=[TaskOut.model_validate(t) for t in items])


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_new_task(
    payload: TaskCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_active_user),
) -> Task:
    task = create_task(
        db,
        title=payload.title,
        description=payload.description,
        assignee_id=payload.assignee_id,
        assignor_id=user.id,
        due_date=payload.due_date,
        source_type=payload.source_type,
        source_id=payload.source_id,
    )
    log_action(db, user_id=user.id, action=f"TASK_CREATE id={task.id} assignee={payload.assignee_id}", request=request)
    db.commit()
    db.refresh(task)
    return task


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> Task:
    task = _get_or_404(db, task_id)
    if user.role != Role.Admin and user.id not in (task.assignee_id, task.assignor_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_active_user),
) -> Task:
    task = _get_or_404(db, task_id)
    if user.role != Role.Admin and user.id not in (task.assignee_id, task.assignor_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your task")

    changes: list[str] = []
    if payload.title is not None:
        task.title = payload.title
        changes.append("title")
    if payload.description is not None:
        task.description = payload.description
        changes.append("description")
    if payload.due_date is not None:
        task.due_date = payload.due_date
        changes.append("due_date")
    if payload.assignee_id is not None:
        task.assignee_id = payload.assignee_id
        changes.append("assignee_id")
    if payload.status is not None and payload.status != task.status:
        task.status = payload.status
        changes.append(f"status={payload.status.value}")
        task.completed_at = datetime.now(UTC).replace(tzinfo=None) if payload.status == TaskStatus.Closed else None

    log_action(db, user_id=user.id, action=f"TASK_UPDATE id={task.id} [{', '.join(changes)}]", request=request)
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}", response_model=TaskOut)
def close_task(
    task_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)
) -> Task:
    task = _get_or_404(db, task_id)
    if user.role != Role.Admin and user.id not in (task.assignee_id, task.assignor_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your task")
    task.status = TaskStatus.Closed
    task.completed_at = datetime.now(UTC).replace(tzinfo=None)
    log_action(db, user_id=user.id, action=f"TASK_CLOSE id={task.id}", request=request)
    db.commit()
    db.refresh(task)
    return task