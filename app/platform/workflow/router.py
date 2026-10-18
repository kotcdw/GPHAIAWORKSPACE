"""Workflow API: the "My work" inbox, record transition history and actions, SLA policies."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user, require_perm
from app.core.enums import Role, TaskStatus, utcnow
from app.platform.users.models import User
from app.platform.workflow import definitions
from app.platform.workflow.engine import mark_action
from app.platform.workflow.models import SlaPolicy, WorkflowTransition, WorkItem
from app.platform.workflow.workitems import KINDS, LINK, SLA_DEFAULTS, desired, ensure_policies, full_resync

router = APIRouter(tags=["workflow"])

# Audit tab that shows each record type (the web app opens the audit on that tab).
TAB = {"procedure": "fieldwork", "control_test": "fieldwork", "test_plan": "fieldwork", "narrative": "fieldwork",
       "rcm": "fieldwork", "evidence_request": "evidence", "review_note": "notes", "working_paper": "fieldwork"}
GROUPS = {"prepare": "To prepare", "review": "To review", "respond": "To respond", "action": "Actions",
          "task": "Tasks"}


def _audits(db: DBSession, ids: set[int]) -> dict[int, dict]:
    from app.domains.audit.audits.models import Audit

    if not ids:
        return {}
    return {a.id: {"title": a.title, "ref": f"AUD-{a.id:04d}"}
            for a in db.execute(select(Audit).where(Audit.id.in_(ids))).scalars()}


def _state(due: datetime | None, sla_state: str, now: datetime, warn_days: int = 1) -> str:
    from app.core.workdays import working_days_between

    if due is None:
        return "none"
    if due < now:
        return "breached"
    if sla_state == "warning" or working_days_between(now, due) <= warn_days:
        return "warning"
    return "ok"


def _my_items(db: DBSession, user: User) -> list[dict]:
    from app.platform.tasks.models import Task

    now = utcnow()
    rows = list(db.execute(select(WorkItem).where(WorkItem.assignee_id == user.id, WorkItem.status == "open"))
                .scalars())
    audits = _audits(db, {r.audit_id for r in rows if r.audit_id})
    warn = {p.key: p.warn_before_days for p in db.execute(select(SlaPolicy)).scalars()}
    out: list[dict] = []
    for r in rows:
        label, _, group = KINDS.get(r.kind, (r.kind, "", "review"))
        link = {"type": LINK[r.record_type], "id": r.record_id} if r.record_type in LINK else \
            {"type": "audit", "id": r.audit_id, "tab": TAB.get(r.record_type)}
        a = audits.get(r.audit_id or 0, {})
        out.append({"id": f"w{r.id}", "source": "work", "kind": r.kind, "label": label, "group": group,
                    "title": r.title, "record_type": r.record_type, "record_id": r.record_id,
                    "audit_id": r.audit_id, "audit_title": a.get("title"), "audit_ref": a.get("ref"),
                    "opened_at": r.opened_at.isoformat(), "due_at": r.due_at.isoformat() if r.due_at else None,
                    "sla_state": _state(r.due_at, r.sla_state, now, warn.get(r.sla_key or "", 1)),
                    "priority": r.priority, "link": link})
    tasks = db.execute(select(Task).where(Task.assignee_id == user.id,
                                          Task.status.in_((TaskStatus.Open, TaskStatus.InProgress)))).scalars()
    for t in tasks:
        state = "none" if t.due_date is None else ("breached" if t.due_date < now else
                                                   "warning" if t.due_date - now <= timedelta(days=2) else "ok")
        out.append({"id": f"t{t.id}", "source": "task", "kind": "task", "label": "To-do", "group": "task",
                    "title": t.title, "record_type": "task", "record_id": t.id, "audit_id": None,
                    "audit_title": None, "audit_ref": None, "opened_at": t.created_at.isoformat(),
                    "due_at": t.due_date.isoformat() if t.due_date else None, "sla_state": state,
                    "priority": "normal", "link": {"type": "task", "id": t.id}})
    far = datetime.max.isoformat()
    out.sort(key=lambda i: (i["due_at"] or far, i["opened_at"]))
    return out


def _counts(items: list[dict]) -> dict:
    week = (utcnow() + timedelta(days=7)).isoformat()
    by_group = {g: 0 for g in GROUPS}
    for i in items:
        by_group[i["group"]] = by_group.get(i["group"], 0) + 1
    return {"total": len(items), "overdue": sum(1 for i in items if i["sla_state"] == "breached"),
            "due_soon": sum(1 for i in items if i["sla_state"] == "warning"),
            "due_week": sum(1 for i in items if i["due_at"] and i["due_at"] <= week), "by_group": by_group}


@router.get("/api/my-work")
def my_work(
    group: str | None = Query(default=None),
    due: str | None = Query(default=None, pattern="^(overdue|week)$"),
    audit_id: int | None = Query(default=None),
    db: DBSession = Depends(get_db),
    user: User = Depends(require_active_user),
) -> dict:
    items = _my_items(db, user)
    counts = _counts(items)
    week = (utcnow() + timedelta(days=7)).isoformat()
    if group:
        items = [i for i in items if i["group"] == group]
    if due == "overdue":
        items = [i for i in items if i["sla_state"] == "breached"]
    elif due == "week":
        items = [i for i in items if i["due_at"] and i["due_at"] <= week]
    if audit_id:
        items = [i for i in items if i["audit_id"] == audit_id]
    return {"items": items, "counts": counts, "groups": GROUPS}


@router.get("/api/my-work/counts")
def my_work_counts(db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> dict:
    return _counts(_my_items(db, user))


# ---------------------------------------------------------------- definitions, history, actions

def _staff(user: User) -> None:
    if user.role not in (Role.Admin, Role.Auditor):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


@router.get("/api/workflows")
def list_workflows(db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> list[dict]:
    _staff(user)
    return [{"record_type": rt, **d} for rt, d in definitions.all_definitions(db).items()]


def _record(db: DBSession, user: User, record_type: str, record_id: int):  # noqa: ANN202
    from app.core.access import can_view
    from app.domains.audit.audits.models import Audit
    from app.platform.workflow.workitems import audit_id_for

    if definitions.definition(record_type, db) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown record type")
    obj, _ = desired(db, record_type, record_id)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")
    aid = audit_id_for(db, record_type, obj)
    if user.role != Role.Admin:
        if aid is not None:
            if not can_view(db, user, "audit", db.get(Audit, aid)):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")
        elif record_type == "capa":
            if not can_view(db, user, "capa", obj):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")
        else:
            _staff(user)
    return obj


def _status_of(obj) -> str | None:  # noqa: ANN001
    st = getattr(obj, "status", None)
    return st.value if hasattr(st, "value") else st


@router.get("/api/workflow/{record_type}/{record_id}/history")
def record_transitions(record_type: str, record_id: int, db: DBSession = Depends(get_db),
                       user: User = Depends(require_active_user)) -> list[dict]:
    _record(db, user, record_type, record_id)
    rows = list(db.execute(select(WorkflowTransition).where(WorkflowTransition.record_type == record_type,
                                                            WorkflowTransition.record_id == record_id)
                           .order_by(WorkflowTransition.created_at, WorkflowTransition.id)).scalars())
    names = {u.id: (u.full_name or u.username) for u in db.execute(
        select(User).where(User.id.in_({r.user_id for r in rows if r.user_id}))).scalars()} if rows else {}
    return [{"id": r.id, "from": r.from_state, "to": r.to_state, "action": r.action, "allowed": r.allowed,
             "user": names.get(r.user_id) or ("System" if r.user_id is None else None), "source": r.source,
             "at": r.created_at.isoformat()} for r in rows]


# Actions the generic endpoint can perform itself (they have no side effects beyond the status change).
# Everything else keeps its own endpoint, which already enforces its checks; it is listed for information.
GENERIC = {("procedure", "start"), ("control_test", "start")}


def _actions(db: DBSession, user: User, record_type: str, obj) -> list[dict]:  # noqa: ANN001
    from app.core.permissions import has_perm

    current = _status_of(obj)
    out = []
    for t in definitions.definition(record_type, db).get("transitions", []):
        if current not in t["from"]:
            continue
        perm_ok = not t.get("permission") or has_perm(user, t["permission"])
        out.append({"action": t["action"], "label": t["label"], "to": t["to"], "allowed": perm_ok,
                    "generic": (record_type, t["action"]) in GENERIC,
                    "reason": "" if perm_ok else "Your role does not allow this"})
    return out


@router.get("/api/workflow/{record_type}/{record_id}/actions")
def record_actions(record_type: str, record_id: int, db: DBSession = Depends(get_db),
                   user: User = Depends(require_active_user)) -> dict:
    obj = _record(db, user, record_type, record_id)
    return {"state": _status_of(obj), "actions": _actions(db, user, record_type, obj)}


class TransitionIn(BaseModel):
    action: str = Field(min_length=1, max_length=60)


@router.post("/api/workflow/{record_type}/{record_id}/transition")
def do_transition(record_type: str, record_id: int, payload: TransitionIn, request: Request,
                  db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> dict:
    """Move a record through its workflow. Only actions without side effects run here (see GENERIC)."""
    obj = _record(db, user, record_type, record_id)
    match = next((a for a in _actions(db, user, record_type, obj) if a["action"] == payload.action), None)
    if match is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"'{payload.action}' is not possible while the record is {_status_of(obj)}")
    if not match["allowed"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=match["reason"])
    if not match["generic"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Use the record's own screen for this step: it has checks of its own")
    if record_type in ("procedure", "control_test"):
        from app.domains.audit.fieldwork.signoffs import is_signed

        target = "test" if record_type == "control_test" else "procedure"
        if is_signed(db, target, record_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Signed-off work is read-only")
        if obj.assigned_to not in (None, user.id) and user.role != Role.Admin:
            from app.core.permissions import has_perm

            if not has_perm(user, "review.workpapers"):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This work is assigned to "
                                                                                  "someone else")
    old = _status_of(obj)
    status_attr = type(obj).__table__.c.status.type
    new = match["to"]
    enum_cls = getattr(status_attr, "enum_class", None)
    obj.status = enum_cls(new) if enum_cls else new
    mark_action(db, record_type, record_id, payload.action, "api")
    log_action(db, user_id=user.id, request=request,
               action=f"WORKFLOW_TRANSITION {record_type} id={record_id} {old} -> {new} ({payload.action})")
    db.commit()
    db.refresh(obj)
    return {"state": _status_of(obj), "actions": _actions(db, user, record_type, obj)}


# ---------------------------------------------------------------- SLA policies

class SlaIn(BaseModel):
    working_days: int = Field(ge=1, le=365)
    warn_before_days: int = Field(ge=0, le=60)
    escalate_on_breach: bool = True
    active: bool = True


def _sla_out(p: SlaPolicy) -> dict:
    return {"key": p.key, "label": p.label, "working_days": p.working_days, "warn_before_days": p.warn_before_days,
            "escalate_on_breach": p.escalate_on_breach, "active": p.active}


@router.get("/api/sla-policies")
def list_sla(db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> list[dict]:
    _staff(user)
    ensure_policies(db)
    db.commit()
    order = list(SLA_DEFAULTS)
    rows = sorted(db.execute(select(SlaPolicy)).scalars(), key=lambda p: order.index(p.key) if p.key in order else 99)
    return [_sla_out(p) for p in rows]


@router.put("/api/sla-policies/{key}")
def update_sla(key: str, payload: SlaIn, request: Request, db: DBSession = Depends(get_db),
               user: User = Depends(require_perm("system.workflow"))) -> dict:
    ensure_policies(db)
    p = db.get(SlaPolicy, key)
    if p is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown SLA policy")
    if payload.warn_before_days >= payload.working_days:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="The warning must come before the due date (fewer days than allowed)")
    before = f"{p.working_days}d/warn {p.warn_before_days}d"
    p.working_days, p.warn_before_days = payload.working_days, payload.warn_before_days
    p.escalate_on_breach, p.active, p.updated_by = payload.escalate_on_breach, payload.active, user.id
    log_action(db, user_id=user.id, request=request,
               action=f"SLA_POLICY_UPDATE {key} {before} -> {p.working_days}d/warn {p.warn_before_days}d")
    db.commit()
    return _sla_out(p)


@router.post("/api/workflow/resync")
def resync(request: Request, db: DBSession = Depends(get_db),
           user: User = Depends(require_perm("system.workflow"))) -> dict:
    """Rebuild every open work item from the records (normally done at start-up and nightly)."""
    n = full_resync(db)
    log_action(db, user_id=user.id, request=request, action=f"WORKFLOW_RESYNC records={n}")
    db.commit()
    return {"records": n}
