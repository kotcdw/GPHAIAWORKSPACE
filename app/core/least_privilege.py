"""Least privilege for Auditors (the field role): enforced where the data is written, whatever the route.

An Auditor works only on engagements they are assigned to (the audit team) and never overwrites work a reviewer has
signed off:

* every insert, change or delete of engagement records (findings, working papers, the risk & control matrix, tests,
  procedures, narratives, review notes, evidence requests, the report, sign-offs) must belong to an audit whose team
  the Auditor is on;
* fieldwork pages and findings that another person has signed off are read-only to them, and they cannot remove
  someone else's sign-off;
* the report is theirs to draft and edit only while it is in Draft; once it is sent on for review it is read-only;
* the engagement team is allocated by whoever holds "Create audits and allocate the team" (a Manager by default).

The checks run in a ``before_flush`` hook on the database session, so a route that forgets a check still cannot
write past them. The acting user is the one the authentication dependency records on the session
(``session.info["actor_id"]``). Configuration > Security > "Auditors work only on their assigned engagements"
switches the assignment rule off for small teams; the sign-off rules always apply.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

# Records that belong to one engagement, and how to find it.
_DIRECT = {"findings", "working_papers", "audit_reports", "objectives", "review_notes", "evidence_requests",
           "procedures", "narratives"}
_VIA_OBJECTIVE = {"risks", "controls"}
_VIA_CONTROL = {"control_tests"}
# Sign-off targets: table -> the target type the sign-off table uses.
_SIGNOFF_TARGET = {"findings": "finding", "control_tests": "test", "controls": "test_plan", "procedures": "procedure",
                   "narratives": "narrative", "objectives": "rcm"}


def _deny(detail: str, code: int = status.HTTP_403_FORBIDDEN) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def is_field_auditor(user) -> bool:  # noqa: ANN001
    from app.core import permissions as perms

    return user is not None and perms.job_role_of(user) == "auditor"


def assignment_enforced() -> bool:
    from app.core.appconfig import cfg

    return bool(cfg("auditor_assigned_only"))


def _audit_of(session: Session, table: str, obj) -> int | None:  # noqa: ANN001
    from app.domains.audit.rcm.models import Control, Objective

    if table in _DIRECT:
        aid = getattr(obj, "audit_id", None)
        if aid is None and getattr(obj, "objective_id", None):
            o = session.get(Objective, obj.objective_id)
            aid = o.audit_id if o else None
        return aid
    if table in _VIA_OBJECTIVE and obj.objective_id:
        o = session.get(Objective, obj.objective_id)
        return o.audit_id if o else None
    if table in _VIA_CONTROL and obj.control_id:
        c = session.get(Control, obj.control_id)
        o = session.get(Objective, c.objective_id) if c else None
        return o.audit_id if o else None
    return None


def _signoff_target_audit(session: Session, target_type: str, target_id: int) -> int | None:
    from app.domains.audit.audits.models import Finding
    from app.domains.audit.rcm.models import Control, ControlTest, Narrative, Objective, Procedure

    model = {"finding": Finding, "test": ControlTest, "test_plan": Control, "procedure": Procedure,
             "narrative": Narrative, "rcm": Objective}.get(target_type)
    rec = session.get(model, target_id) if model else None
    if rec is None:
        return None
    table = {Finding: "findings", ControlTest: "control_tests", Control: "controls", Procedure: "procedures",
             Narrative: "narratives", Objective: "objectives"}[model]
    return _audit_of(session, table, rec)


def _signed_by_others(session: Session, target_type: str, target_id: int, actor_id: int) -> bool:
    from app.domains.audit.rcm.models import Signoff

    return session.execute(select(Signoff.id).where(
        Signoff.target_type == target_type, Signoff.target_id == target_id,
        Signoff.user_id.is_not(None), Signoff.user_id != actor_id).limit(1)).first() is not None


# Report fields the review workflow moves (submitting a report changes these, not its content).
_REPORT_WORKFLOW = {"status", "review_stage", "review_trail", "manager_reviewed_by", "manager_reviewed_at",
                    "draft_sent_at", "response_due_at", "response_received_at", "updated_at"}


def _changed(obj) -> set[str]:  # noqa: ANN001
    state = inspect(obj)
    return {a.key for a in state.attrs if a.history.has_changes()}


def _old(obj, attr: str):  # noqa: ANN001, ANN202
    """The value an attribute had when it was loaded (before this request changed it)."""
    hist = inspect(obj).attrs[attr].history
    if hist.deleted:
        return hist.deleted[0]
    return getattr(obj, attr)


def _check(session: Session, user, obj, op: str, team: set[int]) -> None:  # noqa: ANN001, C901
    table = getattr(obj, "__tablename__", None)
    if table is None:
        return
    if table == "audit_team_members":
        from app.core.permissions import has_perm

        if not has_perm(user, "audit.create"):  # "Create audits and allocate the team"
            raise _deny("The engagement team is allocated by a Manager")
        aid = obj.audit_id
        if op != "insert" and team is not None and aid not in team:
            raise _deny("You can only work on engagements you are assigned to")
        return
    if table == "signoffs":
        if op == "delete" and obj.user_id not in (None, user.id):
            raise _deny("You cannot remove a sign-off made by someone else")
        aid = _signoff_target_audit(session, obj.target_type, obj.target_id)
        if team is not None and aid is not None and aid not in team:
            raise _deny("You can only sign work on engagements you are assigned to")
        return
    if table == "audits":
        if op != "insert" and team is not None and obj.id not in team:
            raise _deny("You can only work on engagements you are assigned to")
        return
    if table not in _DIRECT | _VIA_OBJECTIVE | _VIA_CONTROL:
        return
    aid = _audit_of(session, table, obj)
    if team is not None and aid is not None and aid not in team:
        raise _deny("You can only work on engagements you are assigned to")
    if op == "insert":
        return
    target = _SIGNOFF_TARGET.get(table)
    if target and obj.id and _signed_by_others(session, target, obj.id, user.id):
        raise _deny("This work has been signed off by a reviewer and is read-only to you",
                    status.HTTP_409_CONFLICT)
    if table == "audit_reports":
        was = _old(obj, "status")
        if getattr(was, "value", was) != "Draft" and _changed(obj) - _REPORT_WORKFLOW:
            raise _deny("The report has left Draft: it is read-only to you", status.HTTP_409_CONFLICT)
    if table == "working_papers" and (_old(obj, "reviewed_by") or _old(obj, "reviewed_at")):
        raise _deny("This working paper has been reviewed and is read-only to you", status.HTTP_409_CONFLICT)


def _before_flush(session: Session, _ctx, _instances) -> None:  # noqa: ANN001
    actor_id = session.info.get("actor_id")
    if not actor_id:
        return
    from app.platform.users.models import User

    with session.no_autoflush:
        user = session.get(User, actor_id)
        if not is_field_auditor(user):
            return
        team = None
        if assignment_enforced():
            from app.core.access import staff_audit_scope

            team = staff_audit_scope(session, user)
        for op, objs in (("insert", session.new), ("update", session.dirty), ("delete", session.deleted)):
            for obj in list(objs):
                if op == "update" and not session.is_modified(obj, include_collections=False):
                    continue
                _check(session, user, obj, op, team)


_installed = False


def install() -> None:
    """Register the hook once for every database session."""
    global _installed
    if not _installed:
        event.listen(Session, "before_flush", _before_flush)
        _installed = True
