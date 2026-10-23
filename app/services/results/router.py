"""Results, Storyboards and Robots (GPHA INTERNAL AUDIT WORKSPACE analytics apps) over workspace data.

* **Results**: Collections hold tables; a table's records carry Priority (Low, Medium, High, Critical), Status
  (New, Open, Under Review, Closed, False Positive), Assignee and Published date. Interpretations are saved
  filters with a chart; Triggers act on records (assign, notify, set status / priority).
* **Robots**: a robot has tasks; a task runs one analytic from a fixed catalogue (no free-form scripts), now or
  on a schedule (daily, weekly, monthly), and publishes its rows into a Results table. Task runs keep their
  status (Queued, Running, Success, Failed, Skipped, Cancelled), method, user, duration and record count.
* **Storyboards**: text, charts and metrics from interpretations, shared read-only with chosen users or all staff.

Viewing needs audit staff; building collections, interpretations, triggers and storyboards needs
"Analytics and reporting"; robots need "Automation rules".
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user, require_perm, require_role
from app.core.enums import Role, utcnow
from app.core.errors import field_error
from app.core.schemas import MessageOut
from app.platform.users.models import User
from app.services.results.analytics import CATALOG, clean_params, next_run
from app.services.results.models import (
    FREQUENCIES,
    PRIORITIES,
    STATUSES,
    ResultsCollection,
    ResultsInterpretation,
    ResultsRecord,
    ResultsTable,
    ResultsTrigger,
    Robot,
    RobotRun,
    RobotTask,
    Storyboard,
)

router = APIRouter(tags=["results"])
Staff = Depends(require_role(Role.Admin, Role.Auditor))
Builder = Depends(require_perm("oversight.reporting", "system.automation"))
RobotAdmin = Depends(require_perm("system.automation"))


def _404(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


def _get(db: DBSession, model, rid: int, what: str):  # noqa: ANN001, ANN202
    row = db.get(model, rid)
    if row is None:
        raise _404(what)
    return row


def _names(db: DBSession, ids) -> dict[int, str]:  # noqa: ANN001
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return {u.id: u.full_name or u.username for u in db.execute(select(User).where(User.id.in_(wanted))).scalars()}


@router.get("/api/results/people")
def people(db: DBSession = Depends(get_db), _: User = Staff) -> list[dict]:
    """Active staff and committee members, for assignee, notify and share pickers."""
    rows = db.execute(select(User).where(User.is_active.is_(True),
                                         User.role.in_((Role.Admin, Role.Auditor, Role.Committee)))
                      .order_by(User.full_name, User.username)).scalars()
    return [{"id": u.id, "name": u.full_name or u.username, "role": u.role.value} for u in rows]


# ------------------------------------------------------------------ collections and tables

class CollectionIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field("", max_length=5000)


class CollectionPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=5000)
    archived: bool | None = None


class TableIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field("", max_length=5000)


@router.get("/api/results/collections")
def list_collections(archived: bool = False, db: DBSession = Depends(get_db), _: User = Staff) -> list[dict]:
    cols = list(db.execute(select(ResultsCollection).where(ResultsCollection.archived.is_(archived))
                           .order_by(ResultsCollection.name)).scalars())
    tables = list(db.execute(select(ResultsTable).where(ResultsTable.collection_id.in_([c.id for c in cols] or [0]))
                             .order_by(ResultsTable.name)).scalars())
    counts = dict(db.execute(select(ResultsRecord.table_id, func.count()).where(
        ResultsRecord.table_id.in_([t.id for t in tables] or [0]),
        ResultsRecord.status.notin_(("Closed", "False Positive"))).group_by(ResultsRecord.table_id)).all())
    return [{"id": c.id, "name": c.name, "description": c.description, "archived": c.archived,
             "tables": [{"id": t.id, "name": t.name, "description": t.description, "analytic": t.analytic,
                         "open_records": counts.get(t.id, 0)} for t in tables if t.collection_id == c.id]}
            for c in cols]


@router.post("/api/results/collections", status_code=status.HTTP_201_CREATED)
def create_collection(payload: CollectionIn, request: Request, db: DBSession = Depends(get_db),
                      user: User = Builder) -> dict:
    name = payload.name.strip()
    if db.execute(select(ResultsCollection.id).where(ResultsCollection.name == name)).first():
        raise field_error("name", "a collection with this name already exists")
    c = ResultsCollection(name=name, description=payload.description.strip(), created_by=user.id)
    db.add(c)
    log_action(db, user_id=user.id, action=f"RESULTS_COLLECTION_CREATE {name}", request=request)
    db.commit()
    return {"id": c.id, "name": c.name}


@router.patch("/api/results/collections/{collection_id}")
def update_collection(collection_id: int, payload: CollectionPatch, request: Request, db: DBSession = Depends(get_db),
                      user: User = Builder) -> dict:
    c = _get(db, ResultsCollection, collection_id, "Collection")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(c, key, value.strip() if isinstance(value, str) else value)
    log_action(db, user_id=user.id, action=f"RESULTS_COLLECTION_UPDATE id={collection_id}", request=request)
    db.commit()
    return {"id": c.id, "name": c.name, "archived": c.archived}


@router.delete("/api/results/collections/{collection_id}", response_model=MessageOut)
def delete_collection(collection_id: int, request: Request, db: DBSession = Depends(get_db),
                      user: User = Builder) -> MessageOut:
    c = _get(db, ResultsCollection, collection_id, "Collection")
    db.delete(c)
    log_action(db, user_id=user.id, action=f"RESULTS_COLLECTION_DELETE {collection_id}", request=request)
    db.commit()
    return MessageOut(message="Collection deleted")


@router.post("/api/results/collections/{collection_id}/tables", status_code=status.HTTP_201_CREATED)
def create_table(collection_id: int, payload: TableIn, request: Request,
                 db: DBSession = Depends(get_db), user: User = Builder) -> dict:
    _get(db, ResultsCollection, collection_id, "Collection")
    t = ResultsTable(collection_id=collection_id, name=payload.name.strip(), description=payload.description.strip(),
                     created_by=user.id)
    db.add(t)
    log_action(db, user_id=user.id, action=f"RESULTS_TABLE_CREATE collection={collection_id}", request=request)
    db.commit()
    return {"id": t.id, "name": t.name}


@router.delete("/api/results/tables/{table_id}", response_model=MessageOut)
def delete_table(table_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Builder) -> MessageOut:
    db.delete(_get(db, ResultsTable, table_id, "Table"))
    log_action(db, user_id=user.id, action=f"RESULTS_TABLE_DELETE id={table_id}", request=request)
    db.commit()
    return MessageOut(message="Table deleted")


def _columns(db: DBSession, t: ResultsTable, records: list[ResultsRecord]) -> list[str]:
    if t.analytic in CATALOG:
        return CATALOG[t.analytic].columns
    seen: list[str] = []
    for r in records:
        for k in json.loads(r.data or "{}"):
            if k not in seen:
                seen.append(k)
    return seen


def _record_out(r: ResultsRecord, names: dict[int, str]) -> dict:
    return {"id": r.id, "key": r.record_key, "data": json.loads(r.data or "{}"), "priority": r.priority,
            "status": r.status, "assignee_id": r.assignee_id, "assignee": names.get(r.assignee_id),
            "published_at": r.published_at.isoformat(), "updated_at": r.updated_at.isoformat(),
            "closed_at": r.closed_at.isoformat() if r.closed_at else None}


def _filtered(db: DBSession, table_id: int, filters: list[dict] | None) -> list[ResultsRecord]:
    rows = list(db.execute(select(ResultsRecord).where(ResultsRecord.table_id == table_id)
                           .order_by(ResultsRecord.id.desc())).scalars())
    for f in filters or []:
        field_, op, value = f.get("field"), f.get("op", "is"), str(f.get("value", ""))

        def get(r: ResultsRecord, field_: str = field_) -> str:
            if field_ in ("priority", "status"):
                return getattr(r, field_)
            return str(json.loads(r.data or "{}").get(field_, ""))

        if op == "is":
            rows = [r for r in rows if get(r) == value]
        elif op == "is not":
            rows = [r for r in rows if get(r) != value]
        elif op == "contains":
            rows = [r for r in rows if value.lower() in get(r).lower()]
    return rows


@router.get("/api/results/tables/{table_id}")
def get_table(table_id: int, status_: str | None = Query(None, alias="status"),
              priority: str | None = None, q: str | None = Query(None, max_length=100),
              db: DBSession = Depends(get_db), _: User = Staff) -> dict:
    t = _get(db, ResultsTable, table_id, "Table")
    filters = ([{"field": "status", "value": status_}] if status_ else []) + (
        [{"field": "priority", "value": priority}] if priority else [])
    rows = _filtered(db, table_id, filters)
    if q:
        rows = [r for r in rows if q.lower() in r.data.lower()]
    names = _names(db, [r.assignee_id for r in rows])
    c = db.get(ResultsCollection, t.collection_id)
    return {"id": t.id, "name": t.name, "description": t.description, "collection": c.name,
            "collection_id": c.id, "analytic": t.analytic, "columns": _columns(db, t, rows),
            "priorities": PRIORITIES, "statuses": STATUSES,
            "records": [_record_out(r, names) for r in rows],
            "interpretations": [{"id": i.id, "name": i.name, "config": json.loads(i.config)} for i in db.execute(
                select(ResultsInterpretation).where(ResultsInterpretation.table_id == t.id)).scalars()],
            "triggers": [{"id": g.id, "name": g.name, "enabled": g.enabled, "config": json.loads(g.config),
                          "last_run_at": g.last_run_at.isoformat() if g.last_run_at else None}
                         for g in db.execute(select(ResultsTrigger).where(ResultsTrigger.table_id == t.id)).scalars()]}


class RecordPatch(BaseModel):
    priority: str | None = None
    status: str | None = None
    assignee_id: int | None = None
    clear_assignee: bool = False


@router.patch("/api/results/records/{record_id}")
def update_record(record_id: int, payload: RecordPatch, request: Request, db: DBSession = Depends(get_db),
                  user: User = Staff) -> dict:
    r = _get(db, ResultsRecord, record_id, "Record")
    if payload.priority is not None:
        if payload.priority not in PRIORITIES:
            raise field_error("priority", f"choose one of {', '.join(PRIORITIES)}")
        r.priority = payload.priority
    if payload.status is not None:
        if payload.status not in STATUSES:
            raise field_error("status", f"choose one of {', '.join(STATUSES)}")
        r.status = payload.status
        r.closed_at = utcnow() if payload.status in ("Closed", "False Positive") else None
    if payload.clear_assignee:
        r.assignee_id = None
    elif payload.assignee_id is not None:
        a = db.get(User, payload.assignee_id)
        if a is None or not a.is_active:
            raise field_error("assignee_id", "choose an active user")
        r.assignee_id = a.id
    r.updated_at = utcnow()
    log_action(db, user_id=user.id, action=f"RESULTS_RECORD_UPDATE {record_id}", request=request)
    db.commit()
    return _record_out(r, _names(db, [r.assignee_id]))


# ------------------------------------------------------------------ interpretations

class InterpretationIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    filters: list[dict] = Field(default_factory=list, max_length=10)
    chart: str = Field("bar", pattern="^(bar|donut|metric|table)$")
    group_by: str = Field("priority", max_length=100)


@router.post("/api/results/tables/{table_id}/interpretations", status_code=status.HTTP_201_CREATED)
def create_interpretation(table_id: int, payload: InterpretationIn, request: Request, db: DBSession = Depends(get_db),
                          user: User = Builder) -> dict:
    _get(db, ResultsTable, table_id, "Table")
    i = ResultsInterpretation(table_id=table_id, name=payload.name.strip(), created_by=user.id,
                              config=json.dumps({"filters": payload.filters, "chart": payload.chart,
                                                 "group_by": payload.group_by}))
    db.add(i)
    log_action(db, user_id=user.id, action=f"RESULTS_INTERPRETATION_CREATE table={table_id}", request=request)
    db.commit()
    return {"id": i.id, "name": i.name}


@router.delete("/api/results/interpretations/{interpretation_id}", response_model=MessageOut)
def delete_interpretation(interpretation_id: int, request: Request,
                          db: DBSession = Depends(get_db), user: User = Builder) -> MessageOut:
    db.delete(_get(db, ResultsInterpretation, interpretation_id, "Interpretation"))
    log_action(db, user_id=user.id, action=f"RESULTS_INTERPRETATION_DELETE id={interpretation_id}", request=request)
    db.commit()
    return MessageOut(message="Interpretation deleted")


def interpretation_data(db: DBSession, i: ResultsInterpretation) -> dict:
    cfg = json.loads(i.config or "{}")
    rows = _filtered(db, i.table_id, cfg.get("filters"))
    group = cfg.get("group_by", "priority")

    def key(r: ResultsRecord) -> str:
        if group in ("priority", "status"):
            return getattr(r, group)
        return str(json.loads(r.data or "{}").get(group, "")) or "(blank)"

    counts = Counter(key(r) for r in rows)
    order = list(PRIORITIES) if group == "priority" else list(STATUSES) if group == "status" else sorted(counts)
    t = db.get(ResultsTable, i.table_id)
    return {"id": i.id, "name": i.name, "table": t.name if t else "", "table_id": i.table_id,
            "chart": cfg.get("chart", "bar"), "group_by": group, "total": len(rows),
            "series": [{"label": k, "count": counts[k]} for k in order if counts.get(k)]}


@router.get("/api/results/interpretations/{interpretation_id}")
def get_interpretation(interpretation_id: int, db: DBSession = Depends(get_db), _: User = Staff) -> dict:
    return interpretation_data(db, _get(db, ResultsInterpretation, interpretation_id, "Interpretation"))


@router.get("/api/results/interpretations")
def list_interpretations(db: DBSession = Depends(get_db), _: User = Staff) -> list[dict]:
    tables = {t.id: t.name for t in db.execute(select(ResultsTable)).scalars()}
    return [{"id": i.id, "name": i.name, "table": tables.get(i.table_id, "")}
            for i in db.execute(select(ResultsInterpretation).order_by(ResultsInterpretation.name)).scalars()]


# ------------------------------------------------------------------ triggers

class TriggerIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    match: str = Field("ALL", pattern="^(ALL|ANY)$")
    conditions: list[dict] = Field(default_factory=list, max_length=10)
    actions: list[dict] = Field(..., min_length=1, max_length=10)
    only_new: bool = True
    enabled: bool = True


def _check_trigger(db: DBSession, p: TriggerIn) -> None:
    for c in p.conditions:
        if c.get("field") not in ("priority", "status"):
            raise field_error("conditions", "conditions use Priority or Status")
        allowed = PRIORITIES if c["field"] == "priority" else STATUSES
        if c.get("value") not in allowed:
            raise field_error("conditions", f"{c['field']} must be one of {', '.join(allowed)}")
    for a in p.actions:
        kind = a.get("type")
        if kind == "assign":
            if db.get(User, int(a.get("user_id") or 0)) is None:
                raise field_error("actions", "choose the assignee")
        elif kind == "notify":
            if not a.get("user_ids"):
                raise field_error("actions", "choose who to notify")
        elif kind == "status":
            if a.get("value") not in STATUSES:
                raise field_error("actions", "choose a status")
        elif kind == "priority":
            if a.get("value") not in PRIORITIES:
                raise field_error("actions", "choose a priority")
        else:
            raise field_error("actions", "actions are Assign, Notify, Status or Priority")


@router.post("/api/results/tables/{table_id}/triggers", status_code=status.HTTP_201_CREATED)
def create_trigger(table_id: int, payload: TriggerIn, request: Request,
                   db: DBSession = Depends(get_db), user: User = Builder) -> dict:
    _get(db, ResultsTable, table_id, "Table")
    _check_trigger(db, payload)
    g = ResultsTrigger(table_id=table_id, name=payload.name.strip(), enabled=payload.enabled, created_by=user.id,
                       config=json.dumps({"match": payload.match, "conditions": payload.conditions,
                                          "actions": payload.actions, "only_new": payload.only_new}))
    db.add(g)
    log_action(db, user_id=user.id, action=f"RESULTS_TRIGGER_CREATE table={table_id}", request=request)
    db.commit()
    return {"id": g.id, "name": g.name}


@router.delete("/api/results/triggers/{trigger_id}", response_model=MessageOut)
def delete_trigger(trigger_id: int, request: Request,
                   db: DBSession = Depends(get_db), user: User = Builder) -> MessageOut:
    db.delete(_get(db, ResultsTrigger, trigger_id, "Trigger"))
    log_action(db, user_id=user.id, action=f"RESULTS_TRIGGER_DELETE id={trigger_id}", request=request)
    db.commit()
    return MessageOut(message="Trigger deleted")


def _matches(cfg: dict, r: ResultsRecord) -> bool:
    checks = [getattr(r, c["field"]) == c["value"] for c in cfg.get("conditions", [])]
    if not checks:
        return True
    return all(checks) if cfg.get("match", "ALL") == "ALL" else any(checks)


@router.post("/api/results/triggers/{trigger_id}/run")
def run_trigger(trigger_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Builder) -> dict:
    g = _get(db, ResultsTrigger, trigger_id, "Trigger")
    records = _filtered(db, g.table_id, None)
    hits = apply_triggers_one(db, g, records)
    log_action(db, user_id=user.id, action=f"RESULTS_TRIGGER_RUN id={trigger_id}", request=request)
    db.commit()
    return {"matched": hits}


def apply_triggers_one(db: DBSession, g: ResultsTrigger, records: list[ResultsRecord]) -> int:
    """Apply one trigger's actions to the records that meet its conditions; returns how many matched."""
    from app.platform.notifications.service import notify

    cfg = json.loads(g.config or "{}")
    matched = [r for r in records if _matches(cfg, r)]
    for r in matched:
        for a in cfg.get("actions", []):
            if a["type"] == "assign":
                r.assignee_id = int(a["user_id"])
            elif a["type"] == "status":
                r.status = a["value"]
            elif a["type"] == "priority":
                r.priority = a["value"]
        r.updated_at = utcnow()
    if matched:
        for a in cfg.get("actions", []):
            if a["type"] == "notify":
                for uid in a.get("user_ids", []):
                    notify(db, int(uid), f"Results: {g.name}", f"{len(matched)} record(s) matched the trigger.",
                           link_type="results_table", link_id=g.table_id)
    g.last_run_at = utcnow()
    return len(matched)


# ------------------------------------------------------------------ robots

class RobotIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field("", max_length=5000)


class TaskIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    analytic: str
    params: dict = Field(default_factory=dict)
    table_id: int | None = None
    frequency: str | None = None
    starting_at: str = Field("06:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    beginning_on: date | None = None
    notify_on_failure: bool = True
    enabled: bool = True


@router.get("/api/robots/analytics")
def analytics_catalog(_: User = Staff) -> list[dict]:
    return [{"key": a.key, "name": a.name, "description": a.description, "columns": a.columns,
             "params": [{"key": p.key, "label": p.label, "default": p.default, "min": p.min, "max": p.max}
                        for p in a.params]} for a in CATALOG.values()]


def _run_out(r: RobotRun, names: dict[int, str]) -> dict:
    dur = (r.finished_at - r.started_at).total_seconds() if r.finished_at else None
    return {"id": r.id, "task_id": r.task_id, "method": r.method, "user": names.get(r.user_id), "status": r.status,
            "started_at": r.started_at.isoformat(), "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "duration_s": round(dur, 1) if dur is not None else None, "records": r.records, "message": r.message}


def _task_out(db: DBSession, t: RobotTask) -> dict:
    last = db.execute(select(RobotRun).where(RobotRun.task_id == t.id).order_by(RobotRun.id.desc())).scalars().first()
    a = CATALOG.get(t.analytic)
    table = db.get(ResultsTable, t.table_id) if t.table_id else None
    return {"id": t.id, "robot_id": t.robot_id, "name": t.name, "analytic": t.analytic,
            "analytic_name": a.name if a else t.analytic, "params": json.loads(t.params or "{}"),
            "table_id": t.table_id, "table": table.name if table else None, "frequency": t.frequency,
            "starting_at": t.starting_at, "beginning_on": t.beginning_on.isoformat() if t.beginning_on else None,
            "next_run_at": t.next_run_at.isoformat() if t.next_run_at else None,
            "notify_on_failure": t.notify_on_failure, "enabled": t.enabled,
            "last_run": _run_out(last, _names(db, [last.user_id])) if last else None}


@router.get("/api/robots")
def list_robots(db: DBSession = Depends(get_db), _: User = Staff) -> list[dict]:
    robots = list(db.execute(select(Robot).order_by(Robot.name)).scalars())
    tasks = list(db.execute(select(RobotTask).order_by(RobotTask.id)).scalars())
    return [{"id": r.id, "name": r.name, "description": r.description,
             "tasks": [_task_out(db, t) for t in tasks if t.robot_id == r.id]} for r in robots]


@router.post("/api/robots", status_code=status.HTTP_201_CREATED)
def create_robot(payload: RobotIn, request: Request, db: DBSession = Depends(get_db), user: User = RobotAdmin) -> dict:
    name = payload.name.strip()
    if db.execute(select(Robot.id).where(Robot.name == name)).first():
        raise field_error("name", "a robot with this name already exists")
    r = Robot(name=name, description=payload.description.strip(), created_by=user.id)
    db.add(r)
    log_action(db, user_id=user.id, action=f"ROBOT_CREATE {name}", request=request)
    db.commit()
    return {"id": r.id, "name": r.name}


@router.delete("/api/robots/{robot_id}", response_model=MessageOut)
def delete_robot(robot_id: int, request: Request, db: DBSession = Depends(get_db),
                 user: User = RobotAdmin) -> MessageOut:
    db.delete(_get(db, Robot, robot_id, "Robot"))
    log_action(db, user_id=user.id, action=f"ROBOT_DELETE {robot_id}", request=request)
    db.commit()
    return MessageOut(message="Robot deleted")


def _results_table_for(db: DBSession, task: RobotTask, user_id: int | None) -> ResultsTable:
    if task.table_id and db.get(ResultsTable, task.table_id):
        return db.get(ResultsTable, task.table_id)
    col = db.execute(select(ResultsCollection).where(ResultsCollection.name == "Robots")).scalars().first()
    if col is None:
        col = ResultsCollection(name="Robots", description="Tables published by robot tasks", created_by=user_id)
        db.add(col)
        db.flush()
    a = CATALOG[task.analytic]
    t = ResultsTable(collection_id=col.id, name=task.name, description=a.description, analytic=a.key,
                     created_by=user_id)
    db.add(t)
    db.flush()
    task.table_id = t.id
    return t


@router.post("/api/robots/{robot_id}/tasks", status_code=status.HTTP_201_CREATED)
def create_task(robot_id: int, payload: TaskIn, request: Request, db: DBSession = Depends(get_db),
                user: User = RobotAdmin) -> dict:
    _get(db, Robot, robot_id, "Robot")
    a = CATALOG.get(payload.analytic)
    if a is None:
        raise field_error("analytic", "choose an analytic from the list")
    if payload.frequency not in (None, "", *FREQUENCIES):
        raise field_error("frequency", "choose daily, weekly or monthly, or no schedule")
    if payload.table_id is not None:
        _get(db, ResultsTable, payload.table_id, "Table")
    t = RobotTask(robot_id=robot_id, name=payload.name.strip(), analytic=a.key,
                  params=json.dumps(clean_params(a, payload.params)), table_id=payload.table_id,
                  frequency=payload.frequency or None, starting_at=payload.starting_at,
                  beginning_on=payload.beginning_on, notify_on_failure=payload.notify_on_failure,
                  enabled=payload.enabled, created_by=user.id)
    t.next_run_at = next_run(t.frequency, t.starting_at, t.beginning_on)
    db.add(t)
    db.flush()
    _results_table_for(db, t, user.id)
    log_action(db, user_id=user.id, action=f"ROBOT_TASK_CREATE robot={robot_id} {a.key}", request=request)
    db.commit()
    return _task_out(db, t)


class TaskPatch(BaseModel):
    enabled: bool | None = None
    frequency: str | None = None
    starting_at: str | None = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    params: dict | None = None


@router.patch("/api/robot-tasks/{task_id}")
def update_task(task_id: int, payload: TaskPatch, request: Request,
                db: DBSession = Depends(get_db), user: User = RobotAdmin) -> dict:
    t = _get(db, RobotTask, task_id, "Task")
    sent = payload.model_dump(exclude_unset=True)
    if "frequency" in sent:
        if sent["frequency"] not in (None, "", *FREQUENCIES):
            raise field_error("frequency", "choose daily, weekly or monthly, or no schedule")
        t.frequency = sent["frequency"] or None
    if sent.get("starting_at"):
        t.starting_at = sent["starting_at"]
    if sent.get("params") is not None:
        t.params = json.dumps(clean_params(CATALOG[t.analytic], sent["params"]))
    if sent.get("enabled") is not None:
        t.enabled = sent["enabled"]
    t.next_run_at = next_run(t.frequency, t.starting_at, t.beginning_on) if t.enabled else None
    log_action(db, user_id=user.id, action=f"ROBOT_TASK_UPDATE id={task_id}", request=request)
    db.commit()
    return _task_out(db, t)


@router.delete("/api/robot-tasks/{task_id}", response_model=MessageOut)
def delete_task(task_id: int, request: Request, db: DBSession = Depends(get_db), user: User = RobotAdmin) -> MessageOut:
    db.delete(_get(db, RobotTask, task_id, "Task"))
    log_action(db, user_id=user.id, action=f"ROBOT_TASK_DELETE id={task_id}", request=request)
    db.commit()
    return MessageOut(message="Task deleted")


def run_task(db: DBSession, task: RobotTask, method: str, user_id: int | None) -> RobotRun:
    """Run one task: compute the analytic, publish its rows into the task's table, apply real-time triggers."""
    run = RobotRun(task_id=task.id, method=method, user_id=user_id, status="Running", started_at=utcnow())
    db.add(run)
    db.flush()
    try:
        a = CATALOG[task.analytic]
        table = _results_table_for(db, task, user_id)
        rows = a.run(db, json.loads(task.params or "{}"))
        existing = {r.record_key: r for r in db.execute(select(ResultsRecord).where(
            ResultsRecord.table_id == table.id)).scalars()}
        new: list[ResultsRecord] = []
        now = utcnow()
        for key, data, priority in rows:
            rec = existing.get(key)
            if rec is None:
                rec = ResultsRecord(table_id=table.id, record_key=key[:120], data=json.dumps(data, default=str),
                                    priority=priority, status="New", published_at=now, run_id=run.id,
                                    updated_at=now)
                db.add(rec)
                new.append(rec)
            else:
                rec.data, rec.run_id = json.dumps(data, default=str), run.id
                if rec.status == "Closed":  # found again: reopen (a False Positive stays dismissed)
                    rec.status, rec.closed_at, rec.updated_at = "Open", None, now
        db.flush()
        for g in db.execute(select(ResultsTrigger).where(ResultsTrigger.table_id == table.id,
                                                         ResultsTrigger.enabled.is_(True))).scalars():
            apply_triggers_one(db, g, new)
        run.status, run.records = "Success", len(rows)
        run.message = f"{len(rows)} record(s); {len(new)} new"
    except Exception as exc:  # noqa: BLE001 - a failed run is recorded, never raised to the scheduler
        run.status, run.message = "Failed", str(exc).splitlines()[0][:500]
        if task.notify_on_failure and task.created_by:
            from app.platform.notifications.service import notify

            notify(db, task.created_by, f"Robot task failed: {task.name}", run.message)
    run.finished_at = utcnow()
    return run


@router.post("/api/robot-tasks/{task_id}/run")
def run_now(task_id: int, request: Request, db: DBSession = Depends(get_db), user: User = RobotAdmin) -> dict:
    t = _get(db, RobotTask, task_id, "Task")
    run = run_task(db, t, "manual", user.id)
    log_action(db, user_id=user.id, action=f"ROBOT_TASK_RUN {task_id} {run.status}", request=request)
    db.commit()
    return _run_out(run, _names(db, [user.id]))


@router.get("/api/robot-runs")
def list_runs(task_id: int | None = None, limit: int = Query(100, ge=1, le=500), db: DBSession = Depends(get_db),
              _: User = Staff) -> list[dict]:
    q = select(RobotRun).order_by(RobotRun.id.desc()).limit(limit)
    if task_id is not None:
        q = q.where(RobotRun.task_id == task_id)
    runs = list(db.execute(q).scalars())
    tasks = {t.id: t.name for t in db.execute(select(RobotTask)).scalars()}
    names = _names(db, [r.user_id for r in runs])
    return [{**_run_out(r, names), "task": tasks.get(r.task_id)} for r in runs]


def run_scheduled_robots(db: DBSession) -> int:
    """Run every enabled task whose next run time has passed (called by the background watcher)."""
    now = utcnow()
    due = list(db.execute(select(RobotTask).where(RobotTask.enabled.is_(True), RobotTask.next_run_at.is_not(None),
                                                  RobotTask.next_run_at <= now)).scalars())
    for t in due:
        run_task(db, t, "scheduled", None)
        t.next_run_at = next_run(t.frequency, t.starting_at, t.beginning_on, after=now)
    db.commit()
    return len(due)


# ------------------------------------------------------------------ storyboards

class StoryboardIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    blocks: list[dict] = Field(default_factory=list, max_length=40)


class ShareIn(BaseModel):
    user_ids: list[int] = Field(default_factory=list, max_length=500)
    all_staff: bool = False


def _check_blocks(db: DBSession, blocks: list[dict]) -> list[dict]:
    out = []
    for b in blocks:
        kind = b.get("type")
        width = "half" if b.get("width") == "half" else "full"
        if kind == "text":
            out.append({"type": "text", "title": str(b.get("title", ""))[:255], "body": str(b.get("body", ""))[:20000],
                        "width": width})
        elif kind in ("chart", "metric"):
            iid = int(b.get("interpretation_id") or 0)
            if db.get(ResultsInterpretation, iid) is None:
                raise field_error("blocks", "every chart or metric needs a saved interpretation")
            out.append({"type": kind, "interpretation_id": iid, "title": str(b.get("title", ""))[:255],
                        "width": width})
        else:
            raise field_error("blocks", "blocks are Text, Chart or Metric")
    return out


def _may_view(sb: Storyboard, user: User) -> bool:
    share = json.loads(sb.shared_with or "{}")
    if sb.created_by == user.id or user.role == Role.Admin:
        return True
    if share.get("all_staff") and user.role in (Role.Admin, Role.Auditor, Role.Committee):
        return True
    return user.id in share.get("user_ids", [])


def _sb_out(db: DBSession, sb: Storyboard, user: User, data: bool = False) -> dict:
    blocks = json.loads(sb.blocks or "[]")
    if data:
        for b in blocks:
            if b["type"] in ("chart", "metric"):
                i = db.get(ResultsInterpretation, b["interpretation_id"])
                b["data"] = interpretation_data(db, i) if i else None
    share = json.loads(sb.shared_with or "{}")
    return {"id": sb.id, "name": sb.name, "blocks": blocks, "shared_with": share,
            "owner": _names(db, [sb.created_by]).get(sb.created_by), "can_edit": sb.created_by == user.id
            or user.role == Role.Admin, "updated_at": sb.updated_at.isoformat()}


@router.get("/api/storyboards")
def list_storyboards(db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> list[dict]:
    return [_sb_out(db, s, user) for s in db.execute(select(Storyboard).order_by(Storyboard.name)).scalars()
            if _may_view(s, user)]


@router.post("/api/storyboards", status_code=status.HTTP_201_CREATED)
def create_storyboard(payload: StoryboardIn, request: Request,
                      db: DBSession = Depends(get_db), user: User = Builder) -> dict:
    sb = Storyboard(name=payload.name.strip(), blocks=json.dumps(_check_blocks(db, payload.blocks)),
                    shared_with="{}", created_by=user.id, updated_at=utcnow())
    db.add(sb)
    log_action(db, user_id=user.id, action="STORYBOARD_CREATE", request=request)
    db.commit()
    return _sb_out(db, sb, user)


def _own(db: DBSession, sb_id: int, user: User) -> Storyboard:
    sb = _get(db, Storyboard, sb_id, "Storyboard")
    if not _may_view(sb, user):
        raise _404("Storyboard")
    if sb.created_by != user.id and user.role != Role.Admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Read only: shared with you to view")
    return sb


@router.get("/api/storyboards/{storyboard_id}")
def get_storyboard(storyboard_id: int, db: DBSession = Depends(get_db),
                   user: User = Depends(require_active_user)) -> dict:
    sb = _get(db, Storyboard, storyboard_id, "Storyboard")
    if not _may_view(sb, user):
        raise _404("Storyboard")
    return _sb_out(db, sb, user, data=True)


@router.put("/api/storyboards/{storyboard_id}")
def save_storyboard(storyboard_id: int, payload: StoryboardIn, request: Request, db: DBSession = Depends(get_db),
                    user: User = Builder) -> dict:
    sb = _own(db, storyboard_id, user)
    sb.name, sb.blocks, sb.updated_at = payload.name.strip(), json.dumps(_check_blocks(db, payload.blocks)), utcnow()
    log_action(db, user_id=user.id, action=f"STORYBOARD_UPDATE id={storyboard_id}", request=request)
    db.commit()
    return _sb_out(db, sb, user, data=True)


@router.put("/api/storyboards/{storyboard_id}/share")
def share_storyboard(storyboard_id: int, payload: ShareIn, request: Request, db: DBSession = Depends(get_db),
                     user: User = Builder) -> dict:
    sb = _own(db, storyboard_id, user)
    ids = [u.id for u in db.execute(select(User).where(User.id.in_(payload.user_ids or [0]))).scalars()]
    sb.shared_with = json.dumps({"user_ids": ids, "all_staff": payload.all_staff})
    log_action(db, user_id=user.id, action=f"STORYBOARD_SHARE id={storyboard_id}", request=request)
    db.commit()
    return _sb_out(db, sb, user)


@router.delete("/api/storyboards/{storyboard_id}", response_model=MessageOut)
def delete_storyboard(storyboard_id: int, request: Request,
                      db: DBSession = Depends(get_db), user: User = Builder) -> MessageOut:
    db.delete(_own(db, storyboard_id, user))
    log_action(db, user_id=user.id, action=f"STORYBOARD_DELETE id={storyboard_id}", request=request)
    db.commit()
    return MessageOut(message="Storyboard deleted")
