"""Sign-offs on fieldwork pages (HighBond: Preparer, Detail Reviewer, General Reviewer, Supplemental Reviewer,
Specialty Reviewer).

* The levels and their names come from Configuration > Audit methodology > "Sign-off levels" (up to five).
* The preparer signs first (level 1). A reviewer signs the next level only when set as the **Next Reviewer**;
  an Audit Manager (someone who reviews working papers and holds an approval level) may **override** that.
* Nobody signs two levels of the same page. A signed-off page is read-only.
* Removing a sign-off removes every later sign-off too.
* The first sign-off marks a procedure Prepared / a test Completed; the last configured level marks it Reviewed
  (an issue: reviewed). Removing them reverses that.

Pages: ``procedure``, ``test`` (walkthroughs and tests), ``test_plan`` (a control's test plan), ``narrative``,
``rcm`` (an objective's risk control matrix) and ``finding`` (Issue Information).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DBSession

from app.core.access import staff_audit_scope
from app.core.appconfig import cfg
from app.core.audit import log_action
from app.core.database import get_db
from app.core.enums import Role, TestConclusion, TestStatus, utcnow
from app.core.errors import field_error
from app.core.permissions import has_perm
from app.domains.audit.audits.models import Audit, Finding
from app.domains.audit.rcm.models import Control, ControlTest, Narrative, Objective, Procedure, Signoff, SignoffReviewer
from app.domains.audit.rcm.router import Staff, _conflict, _ensure_open, _history
from app.platform.users.models import User

router = APIRouter(tags=["sign-offs"])

TARGETS = ("procedure", "test", "test_plan", "narrative", "rcm", "finding")
DEFAULT_LEVELS = ["Preparer", "Detail Reviewer", "General Reviewer", "Supplemental Reviewer", "Specialty Reviewer"]


def levels() -> list[str]:
    names = [n.strip() for n in (cfg("signoff_levels") or []) if str(n).strip()][:5]
    return names or DEFAULT_LEVELS[:2]


def _record(db: DBSession, target_type: str, target_id: int):  # noqa: ANN202
    model = {"procedure": Procedure, "test": ControlTest, "test_plan": Control, "narrative": Narrative,
             "rcm": Objective, "finding": Finding}.get(target_type)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown page type")
    rec = db.get(model, target_id)
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
    return rec


def audit_id_of(db: DBSession, target_type: str, rec) -> int:  # noqa: ANN001
    if target_type == "finding":
        return rec.audit_id
    if target_type == "rcm":
        return rec.audit_id
    if target_type in ("procedure", "narrative"):
        return db.get(Objective, rec.objective_id).audit_id
    control = db.get(Control, rec.control_id) if target_type == "test" else rec
    return db.get(Objective, control.objective_id).audit_id


def _in_scope(db: DBSession, user: User, audit_id: int) -> None:
    if user.role == Role.Auditor:
        scope = staff_audit_scope(db, user)
        if scope is not None and audit_id not in scope:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")


def is_manager(user: User) -> bool:
    return user.review_level is not None and has_perm(user, "review.workpapers")


def rows(db: DBSession, target_type: str, target_id: int) -> list[Signoff]:
    return list(db.execute(select(Signoff).where(Signoff.target_type == target_type, Signoff.target_id == target_id)
                           .order_by(Signoff.level)).scalars())


def is_signed(db: DBSession, target_type: str, target_id: int) -> bool:
    return db.execute(select(Signoff.id).where(Signoff.target_type == target_type,
                                               Signoff.target_id == target_id).limit(1)).first() is not None


def ensure_editable(db: DBSession, target_type: str, target_id: int) -> None:
    if is_signed(db, target_type, target_id):
        raise _conflict("This page is signed off and read-only; remove the sign-off to change it")


def _names(db: DBSession, ids) -> dict[int, str]:  # noqa: ANN001
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return {u.id: u.full_name or u.username for u in db.execute(select(User).where(User.id.in_(wanted))).scalars()}


def dots_for(db: DBSession, target_type: str, ids: list[int]) -> dict[int, list[dict]]:
    """Sign-off dots for many pages at once: {target_id: [{label, done, by, at, override}]}."""
    names_ = levels()
    found: dict[int, dict[int, Signoff]] = {}
    for s in db.execute(select(Signoff).where(Signoff.target_type == target_type,
                                              Signoff.target_id.in_(ids or [0]))).scalars():
        found.setdefault(s.target_id, {})[s.level] = s
    who = _names(db, [s.user_id for d in found.values() for s in d.values()])
    out = {}
    for tid in ids:
        signed = found.get(tid, {})
        out[tid] = [{"label": n, "done": lvl in signed, "by": who.get(signed[lvl].user_id) if lvl in signed else None,
                     "at": signed[lvl].signed_at.isoformat() if lvl in signed else None,
                     "override": bool(signed[lvl].override) if lvl in signed else False}
                    for lvl, n in enumerate(names_, start=1)]
    return out


def state(db: DBSession, target_type: str, target_id: int, user: User | None = None) -> dict:
    names_ = levels()
    signed = {s.level: s for s in rows(db, target_type, target_id)}
    who = _names(db, [s.user_id for s in signed.values()])
    nxt = db.get(SignoffReviewer, (target_type, target_id))
    next_level = next((lvl for lvl in range(1, len(names_) + 1) if lvl not in signed), None)
    out = {
        "levels": [{"level": lvl, "label": n, "done": lvl in signed,
                    "by": who.get(signed[lvl].user_id) if lvl in signed else None,
                    "by_id": signed[lvl].user_id if lvl in signed else None,
                    "at": signed[lvl].signed_at.isoformat() if lvl in signed else None,
                    "override": bool(signed[lvl].override) if lvl in signed else False}
                   for lvl, n in enumerate(names_, start=1)],
        "next_level": next_level,
        "next_label": names_[next_level - 1] if next_level else None,
        "next_reviewer": ({"id": nxt.reviewer_id, "name": _names(db, [nxt.reviewer_id]).get(nxt.reviewer_id),
                           "level": nxt.level} if nxt else None),
        "complete": next_level is None,
        "read_only": bool(signed),
        "requires_password": bool(cfg("signoff_requires_password")),
    }
    if user is not None:
        out["can_sign"], out["why_not"] = _may_sign(db, user, target_type, target_id, signed, nxt, next_level)
        out["can_override"] = bool(next_level and next_level > 1 and is_manager(user)
                                   and user.id not in {s.user_id for s in signed.values()})
    return out


def _may_sign(db: DBSession, user: User, target_type: str, target_id: int, signed: dict, nxt,  # noqa: ANN001
              next_level: int | None) -> tuple[bool, str]:
    if next_level is None:
        return False, "Every sign-off level is complete"
    if user.id in {s.user_id for s in signed.values()}:
        return False, "You have already signed this page at another level"
    if next_level == 1:
        return True, ""
    if nxt and nxt.reviewer_id == user.id and nxt.level == next_level:
        return True, ""
    if is_manager(user):
        return False, "You are not the Next Reviewer; use Override sign-off"
    return False, f"Waiting for the {levels()[next_level - 1]} (set as Next Reviewer)"


def record_legacy(db: DBSession, target_type: str, target_id: int, audit_id: int, user_id: int | None,
                  reset: bool = False) -> None:
    """Keep the sign-off table in step with the older status buttons (Prepared / review e-sign / reopen)."""
    if reset:
        db.execute(delete(Signoff).where(Signoff.target_type == target_type, Signoff.target_id == target_id))
        return
    done = {s.level for s in rows(db, target_type, target_id)}
    level = next((lvl for lvl in range(1, len(levels()) + 1) if lvl not in done), None)
    if level is not None:
        db.add(Signoff(target_type=target_type, target_id=target_id, audit_id=audit_id, level=level,
                       user_id=user_id, signed_at=utcnow()))


# ---- effects on the underlying record

def _on_first(db: DBSession, target_type: str, rec, user: User) -> None:  # noqa: ANN001
    from app.domains.audit.fieldwork.router import ISSUES_NOTED, NO_ISSUES, P_PREPARED

    if target_type == "procedure":
        if not (rec.results or "").strip():
            raise field_error("results", "record the procedure results before signing off")
        if rec.outcome not in (NO_ISSUES, ISSUES_NOTED):
            raise field_error("outcome", "answer 'Were issues identified?' before signing off")
        rec.status, rec.performed_by, rec.performed_at = P_PREPARED, user.id, utcnow()
    elif target_type == "test":
        if rec.conclusion == TestConclusion.NotTested:
            raise field_error("conclusion", "record a conclusion before signing off")
        if rec.status in (TestStatus.NotStarted, TestStatus.InProgress):
            rec.status = TestStatus.Completed
        rec.performed_by, rec.performed_at = user.id, utcnow()


def _on_complete(db: DBSession, target_type: str, rec, user: User) -> None:  # noqa: ANN001
    from app.domains.audit.fieldwork.router import P_REVIEWED

    if target_type == "procedure":
        rec.status, rec.reviewed_by, rec.reviewed_at = P_REVIEWED, user.id, utcnow()
    elif target_type == "test":
        rec.status, rec.reviewed_by, rec.reviewed_at = TestStatus.Reviewed, user.id, utcnow()
    elif target_type == "finding":
        rec.reviewed_at, rec.review_stage = utcnow(), None


def _on_removed(db: DBSession, target_type: str, rec, from_level: int) -> None:  # noqa: ANN001
    from app.domains.audit.fieldwork.router import P_IN_PROGRESS, P_PREPARED

    if target_type == "procedure":
        rec.reviewed_by = rec.reviewed_at = None
        if from_level == 1:
            rec.status, rec.performed_by, rec.performed_at = P_IN_PROGRESS, None, None
        else:
            rec.status = P_PREPARED
    elif target_type == "test":
        rec.reviewed_by = rec.reviewed_at = None
        if from_level == 1:
            rec.status, rec.performed_by, rec.performed_at = TestStatus.InProgress, None, None
        else:
            rec.status = TestStatus.Completed
    elif target_type == "finding":
        rec.reviewed_at = None


# ---- routes

class SignIn(BaseModel):
    password: str | None = Field(None, max_length=200)
    override: bool = False


class NextReviewerIn(BaseModel):
    reviewer_id: int


def _load(db: DBSession, user: User, target_type: str, target_id: int):  # noqa: ANN202
    if target_type not in TARGETS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown page type")
    rec = _record(db, target_type, target_id)
    audit_id = audit_id_of(db, target_type, rec)
    _in_scope(db, user, audit_id)
    return rec, db.get(Audit, audit_id)


@router.get("/api/signoffs/{target_type}/{target_id}")
def get_signoffs(target_type: str, target_id: int, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    _load(db, user, target_type, target_id)
    return state(db, target_type, target_id, user)


@router.post("/api/signoffs/{target_type}/{target_id}")
def sign_off(target_type: str, target_id: int, payload: SignIn, request: Request, db: DBSession = Depends(get_db),
             user: User = Staff) -> dict:
    """Sign the next level: the preparer, the Next Reviewer, or an Audit Manager with ``override``."""
    from app.core.security import verify_password

    rec, audit = _load(db, user, target_type, target_id)
    _ensure_open(audit)
    if cfg("signoff_requires_password") and not (payload.password and verify_password(payload.password,
                                                                                      user.password_hash)):
        raise field_error("password", "enter your password to sign")
    names_ = levels()
    signed = {s.level: s for s in rows(db, target_type, target_id)}
    nxt = db.get(SignoffReviewer, (target_type, target_id))
    level = next((lvl for lvl in range(1, len(names_) + 1) if lvl not in signed), None)
    allowed, why = _may_sign(db, user, target_type, target_id, signed, nxt, level)
    override = False
    if not allowed:
        if payload.override and level and level > 1 and is_manager(user) and \
                user.id not in {s.user_id for s in signed.values()}:
            override = True
        else:
            raise _conflict(why)
    if level and level > 1 and 1 not in signed and cfg("signoff_preparer_required"):
        raise _conflict("The preparer has not signed off yet")
    if level == 1:
        _on_first(db, target_type, rec, user)
    db.add(Signoff(target_type=target_type, target_id=target_id, audit_id=audit.id, level=level, user_id=user.id,
                   signed_at=utcnow(), override=override))
    if nxt is not None:
        db.delete(nxt)
    if level == len(names_):
        _on_complete(db, target_type, rec, user)
    label = names_[level - 1]
    log_action(db, user_id=user.id, action=f"SIGNOFF {target_type}={target_id} level={level}"
               + (" override" if override else ""), request=request)
    _history(db, audit.id, user, f"SIGN-OFF {label} on {target_type} #{target_id}" + (" (override)" if override
                                                                                       else ""), request)
    db.commit()
    return state(db, target_type, target_id, user)


@router.put("/api/signoffs/{target_type}/{target_id}/next-reviewer")
def set_next_reviewer(target_type: str, target_id: int, payload: NextReviewerIn, request: Request,
                      db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    """Set and Notify Reviewer: the person asked to sign the next level."""
    from app.platform.notifications.service import notify

    rec, audit = _load(db, user, target_type, target_id)
    _ensure_open(audit)
    names_ = levels()
    signed = {s.level: s for s in rows(db, target_type, target_id)}
    level = next((lvl for lvl in range(1, len(names_) + 1) if lvl not in signed), None)
    if level is None or level == 1:
        raise _conflict("The preparer signs first; set the Next Reviewer after the first sign-off"
                        if level == 1 else "Every sign-off level is complete")
    reviewer = db.get(User, payload.reviewer_id)
    if reviewer is None or not reviewer.is_active or reviewer.role not in (Role.Admin, Role.Auditor):
        raise field_error("reviewer_id", "choose an active member of the audit staff")
    if reviewer.id in {s.user_id for s in signed.values()}:
        raise field_error("reviewer_id", "this person has already signed this page")
    row = db.get(SignoffReviewer, (target_type, target_id))
    if row is None:
        row = SignoffReviewer(target_type=target_type, target_id=target_id, reviewer_id=reviewer.id, level=level,
                              set_by=user.id, set_at=utcnow())
        db.add(row)
    else:
        row.reviewer_id, row.level, row.set_by, row.set_at = reviewer.id, level, user.id, utcnow()
    notify(db, reviewer.id, f"Sign-off requested: {names_[level - 1]}",
           f"{user.full_name or user.username} asked you to review a {target_type.replace('_', ' ')} on "
           f"{audit.title}.", link_type="audit", link_id=audit.id)
    log_action(db, user_id=user.id, action=f"SIGNOFF_NEXT {target_type}={target_id} reviewer={reviewer.id}",
               request=request)
    db.commit()
    return state(db, target_type, target_id, user)


@router.delete("/api/signoffs/{target_type}/{target_id}/{level}")
def remove_signoff(target_type: str, target_id: int, level: int, request: Request, db: DBSession = Depends(get_db),
                   user: User = Staff) -> dict:
    """Remove a sign-off and every later one (the signer, or an Audit Manager)."""
    rec, audit = _load(db, user, target_type, target_id)
    _ensure_open(audit)
    signed = {s.level: s for s in rows(db, target_type, target_id)}
    if level not in signed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No sign-off at this level")
    if signed[level].user_id != user.id and not is_manager(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Only the person who signed, or an Audit Manager, can remove this sign-off")
    from app.core.least_privilege import is_field_auditor

    if is_field_auditor(user) and any(lv > level and s.user_id not in (None, user.id) for lv, s in signed.items()):
        # Least privilege: an Auditor cannot undo a reviewer's sign-off by removing their own earlier one.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="A reviewer has signed after you; only an Audit Manager can reopen this work")
    was_complete = max(signed) == len(levels())
    db.execute(delete(Signoff).where(Signoff.target_type == target_type, Signoff.target_id == target_id,
                                     Signoff.level >= level))
    if level == 1 or was_complete:
        _on_removed(db, target_type, rec, level)
    log_action(db, user_id=user.id, action=f"SIGNOFF_REMOVE {target_type}={target_id} from level={level}",
               request=request)
    _history(db, audit.id, user, f"SIGN-OFF REMOVED from level {level} on {target_type} #{target_id}", request)
    db.commit()
    return state(db, target_type, target_id, user)


@router.get("/api/audits/{audit_id}/signoff-status")
def audit_signoff_status(audit_id: int, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    """Fieldwork status (HighBond "My work status"): every page of the audit with one column per sign-off level."""
    from app.domains.audit.fieldwork.router import WORKPLAN

    audit = db.get(Audit, audit_id)
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit not found")
    names_ = levels()
    objectives = list(db.execute(select(Objective).where(Objective.audit_id == audit_id)
                                 .order_by(Objective.id)).scalars())
    obj_ids = [o.id for o in objectives] or [0]
    pages: list[tuple[str, int, int, str, str, bool]] = []  # type, id, objective, phase, title, applicable
    workplan = (audit.workflow or "") == WORKPLAN
    for o in objectives:
        if not workplan:
            pages.append(("rcm", o.id, o.id, "Risk control matrix", o.title, True))
    if workplan:
        for p in db.execute(select(Procedure).where(Procedure.objective_id.in_(obj_ids))
                            .order_by(Procedure.id)).scalars():
            pages.append(("procedure", p.id, p.objective_id, "Procedures", f"{p.ref} {p.title}", True))
    else:
        for n in db.execute(select(Narrative).where(Narrative.objective_id.in_(obj_ids))
                            .order_by(Narrative.position, Narrative.id)).scalars():
            pages.append(("narrative", n.id, n.objective_id, "Narratives", f"{n.ref} {n.title}", True))
        controls = list(db.execute(select(Control).where(Control.objective_id.in_(obj_ids))
                                   .order_by(Control.id)).scalars())
        for c in controls:
            pages.append(("test_plan", c.id, c.objective_id, "Test plan", f"{c.ref} {c.title}", c.is_key))
        for c in controls:
            for t in c.tests:
                phase = "Walkthroughs" if t.test_type.value == "Walkthrough" else (
                    f"Testing round {t.round_no}" if t.round_no else "Testing")
                pages.append(("test", t.id, c.objective_id, phase, f"{t.ref} {c.title}", t.in_scope))
    for f in db.execute(select(Finding).where(Finding.audit_id == audit_id).order_by(Finding.id)).scalars():
        pages.append(("finding", f.id, 0, "Issues", f.title, True))
    by_type: dict[str, list[int]] = {}
    for t, i, *_ in pages:
        by_type.setdefault(t, []).append(i)
    dots = {t: dots_for(db, t, ids) for t, ids in by_type.items()}
    titles = {o.id: o.title for o in objectives}
    out_rows = []
    for t, i, obj, phase, title, applicable in pages:
        d = dots[t][i]
        statuses = []
        for n, dot in enumerate(d):
            if not applicable:
                statuses.append("Not applicable")
            elif dot["done"]:
                statuses.append("Completed")
            elif n > 0 and d[n - 1]["done"]:
                statuses.append("In progress")
            else:
                statuses.append("Not started")
        out_rows.append({"type": t, "id": i, "objective": titles.get(obj, "Issues"), "phase": phase, "title": title,
                         "signoffs": d, "statuses": statuses})
    summary = {lbl: {"Completed": 0, "In progress": 0, "Not started": 0, "Not applicable": 0} for lbl in names_}
    for r in out_rows:
        for lbl, st in zip(names_, r["statuses"], strict=True):
            summary[lbl][st] += 1
    return {"levels": names_, "rows": out_rows, "summary": summary}


@router.get("/api/audits/{audit_id}/signoff-reviewers")
def signoff_reviewers(audit_id: int, db: DBSession = Depends(get_db), _: User = Staff) -> list[dict]:
    """People who can be set as Next Reviewer: the engagement team and staff holding an approval level."""
    from app.domains.audit.audits.models import AuditTeamMember

    team = set(db.execute(select(AuditTeamMember.user_id).where(AuditTeamMember.audit_id == audit_id)).scalars())
    rows = db.execute(select(User).where(User.is_active.is_(True), User.role.in_((Role.Admin, Role.Auditor)))
                      .order_by(User.full_name, User.username)).scalars()
    return [{"id": u.id, "name": u.full_name or u.username,
             "level": u.review_level.value if u.review_level else None, "team": u.id in team}
            for u in rows if u.id in team or u.review_level is not None]
