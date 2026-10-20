"""The workflow engine: records every status change and keeps work items in step with the records.

It hooks the database session, so every status change made anywhere in GIAW (an endpoint, a background job, an
automation) goes through the same place:

* ``before_flush`` notes which tracked records changed status (old -> new) and which records may have changed who
  must act next (an assignee, a next reviewer, a deadline...);
* ``before_commit`` writes one ``workflow_transitions`` row per status change, checked against the record type's
  workflow definition, and re-derives the affected work items.

Nothing here may break the user's action: the engine's own writes run in a savepoint and a failure is logged.
"""

from __future__ import annotations

import enum
import logging
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

logger = logging.getLogger("gpha")

# ORM class name -> workflow record type. Status changes of these are recorded as transitions.
TRACKED = {
    "Audit": "audit",
    "Procedure": "procedure",
    "ControlTest": "control_test",
    "EvidenceRequest": "evidence_request",
    "ReviewNote": "review_note",
    "Finding": "finding",
    "AuditReport": "audit_report",
    "Capa": "capa",
}
# Records whose changes can alter who must act next (work items), without a status of their own to record.
SYNC_ONLY = {"WorkingPaper": "working_paper", "Control": "test_plan", "Narrative": "narrative", "Objective": "rcm"}
# Sign-off page type -> workflow record type.
SIGNOFF_TYPES = {"procedure": "procedure", "test": "control_test", "finding": "finding", "test_plan": "test_plan",
                 "narrative": "narrative", "rcm": "rcm"}

_TRANSITIONS = "wf_transitions"
_SYNC = "wf_sync"
_BUSY = "wf_busy"


def _value(v: Any) -> str | None:
    if v is None:
        return None
    return v.value if isinstance(v, enum.Enum) else str(v)


def set_actor(session: Session, user_id: int | None, ip: str | None = None) -> None:
    """Remember who is acting in this request (set by the authentication dependency)."""
    session.info["actor_id"] = user_id
    session.info["actor_ip"] = ip


def mark_action(session: Session, record_type: str, record_id: int, action: str, source: str = "api") -> None:
    """Name the workflow action behind the next status change of a record (used by ``transition``)."""
    session.info.setdefault("wf_actions", {})[(record_type, record_id)] = (action, source)


# ---------------------------------------------------------------- session hooks

def _before_flush(session: Session, _ctx, _instances) -> None:  # noqa: ANN001, C901
    if session.info.get(_BUSY):
        return
    pending = session.info.setdefault(_TRANSITIONS, [])
    sync_objs = session.info.setdefault("wf_sync_objs", [])
    sync = session.info.setdefault(_SYNC, set())
    for obj in list(session.new) + list(session.dirty):
        name = type(obj).__name__
        if name in TRACKED:
            hist = inspect(obj).attrs.status.history
            if hist.added:
                old = _value(hist.deleted[0]) if hist.deleted else None
                new = _value(hist.added[0])
                if old != new:
                    pending.append((obj, TRACKED[name], old, new))
            sync_objs.append((obj, TRACKED[name]))
        elif name in SYNC_ONLY:
            sync_objs.append((obj, SYNC_ONLY[name]))
        elif name in ("Signoff", "SignoffReviewer") and getattr(obj, "target_type", None) in SIGNOFF_TYPES:
            sync.add((SIGNOFF_TYPES[obj.target_type], obj.target_id))
        elif name == "AuditTeamMember":
            sync.add(("audit_team", obj.audit_id))
    for obj in session.deleted:
        name = type(obj).__name__
        rt = TRACKED.get(name) or SYNC_ONLY.get(name)
        if rt and getattr(obj, "id", None):
            sync.add((rt, obj.id))
        elif name in ("Signoff", "SignoffReviewer") and getattr(obj, "target_type", None) in SIGNOFF_TYPES:
            sync.add((SIGNOFF_TYPES[obj.target_type], obj.target_id))


def _clear(session: Session) -> None:
    for key in (_TRANSITIONS, "wf_sync_objs", _SYNC, "wf_actions"):
        session.info.pop(key, None)


def _before_commit(session: Session) -> None:
    if session.info.get(_BUSY):
        return
    for _ in range(3):  # our own writes never queue more work, so this settles in one or two rounds
        try:
            session.flush()
        except Exception:  # the user's own flush failed: let commit raise it as before
            return
        pending = session.info.pop(_TRANSITIONS, [])
        objs = session.info.pop("wf_sync_objs", [])
        sync = session.info.pop(_SYNC, set())
        actions = session.info.pop("wf_actions", {})
        for obj, rt in objs:
            rid = getattr(obj, "id", None)
            if rid is not None:
                sync.add((rt, rid))
        if not pending and not sync:
            return
        session.info[_BUSY] = True
        try:
            nested = session.begin_nested()
            try:
                _record(session, pending, actions)
                from app.platform.workflow.workitems import sync_records

                sync_records(session, sync)
                session.flush()
                nested.commit()
            except Exception:  # noqa: BLE001 - the engine never blocks the user's change
                nested.rollback()
                logger.exception("Workflow engine could not record transitions / work items")
        finally:
            session.info[_BUSY] = False


def _record(session: Session, pending: list, actions: dict) -> None:
    from app.platform.workflow import definitions
    from app.platform.workflow.models import WorkflowTransition
    from app.platform.workflow.workitems import audit_id_for

    actor = session.info.get("actor_id")
    ip = session.info.get("actor_ip")
    for obj, rt, old, new in pending:
        rid = getattr(obj, "id", None)
        if rid is None or new is None:
            continue
        action, source = actions.get((rt, rid), (None, "app" if actor else "system"))
        if action is None:
            t = definitions.match(rt, old, new, session) if old is not None else None
            action = t["action"] if t else ("create" if old is None else None)
        allowed = definitions.is_allowed(rt, old, new, session)
        if not allowed:
            logger.warning("Workflow: %s #%s moved %s -> %s, which its workflow does not list", rt, rid, old, new)
        session.add(WorkflowTransition(record_type=rt, record_id=rid, audit_id=audit_id_for(session, rt, obj),
                                       from_state=old, to_state=new, action=action, allowed=allowed,
                                       user_id=actor, source=source, ip_address=ip))


_INSTALLED = False


def install() -> None:
    """Attach the engine to every database session (idempotent)."""
    global _INSTALLED  # noqa: PLW0603 - module-level switch so the hooks are attached once
    if _INSTALLED:
        return
    event.listen(Session, "before_flush", _before_flush)
    event.listen(Session, "before_commit", _before_commit)
    event.listen(Session, "after_rollback", _clear)
    _INSTALLED = True
