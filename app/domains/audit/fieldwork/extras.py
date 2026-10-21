"""HighBond project features around fieldwork.

* **Narratives** (Internal Control workflow): Title (60), Description, linked controls (up to 100), sign-off.
* **Favourites** on the audit list ("Show favorites first").
* **Terms** per audit type (HighBond project type settings rename Objective, Risk, Control, ...).
* **Custom attributes** values on objectives, narratives, risks, controls, procedures and tests.
* **Progress** of an audit ("Audit Procedures Completed", "Time to Deadline") and the **Project Status Tracker**
  across audits (Project Name, Time Expired, Work Completed, Budget, Time Spent).
"""

from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as DBSession

from app.core.access import visible
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user, require_perm
from app.core.enums import AuditStatus, TestStatus, utcnow
from app.core.errors import field_error
from app.core.refs import next_reference
from app.core.schemas import MessageOut
from app.domains.audit.audits.models import Audit
from app.domains.audit.fieldwork.signoffs import dots_for, ensure_editable
from app.domains.audit.rcm.models import (
    AuditFavorite,
    AuditTypeTerm,
    Control,
    ControlTest,
    Narrative,
    NarrativeControl,
    Objective,
    Procedure,
    Risk,
)
from app.domains.audit.rcm.router import Staff, _audit_or_404, _conflict, _ensure_open, _history, _objective
from app.platform.users.models import User

router = APIRouter(tags=["fieldwork extras"])
Reference = Depends(require_perm("system.reference"))

# ------------------------------------------------------------------ terms

TERMS: dict[str, str] = {
    "project": "Audit", "planning": "Planning", "fieldwork": "Fieldwork", "objective": "Objective",
    "narrative": "Narrative", "rcm": "Risk & control matrix", "risk": "Risk", "control": "Control",
    "walkthrough": "Walkthrough", "test_plan": "Test plan", "testing": "Testing", "procedure": "Procedure",
    "work_program": "Work programme", "execute": "Execute procedures", "issue": "Issue",
    "request": "Request", "results": "Results", "reviews": "Supervision & review",
}


def terms_for(db: DBSession, audit_type: str | None) -> dict[str, str]:
    out = dict(TERMS)
    if audit_type:
        for t in db.execute(select(AuditTypeTerm).where(AuditTypeTerm.audit_type == audit_type)).scalars():
            if t.term_key in out:
                out[t.term_key] = t.label
    return out


class TermsIn(BaseModel):
    terms: dict[str, str] = Field(default_factory=dict)


@router.get("/api/audit-types/settings")
def audit_type_settings(db: DBSession = Depends(get_db), _: User = Depends(require_active_user)) -> dict:
    from app.core.appconfig import cfg
    from app.domains.audit.fieldwork.router import default_workflow

    types = list(cfg("audit_types") or [])
    stored: dict[str, dict[str, str]] = {}
    for t in db.execute(select(AuditTypeTerm)).scalars():
        stored.setdefault(t.audit_type, {})[t.term_key] = t.label
    return {"defaults": TERMS, "types": [{"name": t, "workflow": default_workflow(t), "terms": stored.get(t, {})}
                                        for t in types]}


@router.put("/api/audit-types/{audit_type}/terms")
def save_terms(audit_type: str, payload: TermsIn, request: Request, db: DBSession = Depends(get_db),
               user: User = Reference) -> dict:
    from app.core.appconfig import cfg

    if audit_type not in (cfg("audit_types") or []):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown audit type")
    errors = [k for k in payload.terms if k not in TERMS]
    if errors:
        raise field_error("terms", f"unknown term(s): {', '.join(errors)}")
    db.execute(delete(AuditTypeTerm).where(AuditTypeTerm.audit_type == audit_type))
    for key, label in payload.terms.items():
        label = (label or "").strip()
        if len(label) > 60:
            raise field_error(f"term_{key}", "must be 60 characters or fewer")
        if label and label != TERMS[key]:
            db.add(AuditTypeTerm(audit_type=audit_type, term_key=key, label=label))
    log_action(db, user_id=user.id, action=f"AUDIT_TYPE_TERMS {audit_type}", request=request)
    db.commit()
    return {"audit_type": audit_type, "terms": terms_for(db, audit_type)}


@router.get("/api/audits/{audit_id}/terms")
def audit_terms(audit_id: int, db: DBSession = Depends(get_db), _: User = Depends(require_active_user)) -> dict:
    audit = _audit_or_404(db, audit_id)
    return terms_for(db, audit.audit_type)


# ------------------------------------------------------------------ custom attribute values

_VALUE_MODELS = {"objectives": Objective, "narratives": Narrative, "risks": Risk, "controls": Control,
                 "procedures": Procedure, "control_tests": ControlTest}
_SIGNOFF_TYPE = {"narratives": "narrative", "procedures": "procedure", "control_tests": "test"}


def _value_record(db: DBSession, module: str, record_id: int):  # noqa: ANN202
    model = _VALUE_MODELS.get(module)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown page")
    rec = db.get(model, record_id)
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")
    if module == "control_tests":
        obj = db.get(Objective, db.get(Control, rec.control_id).objective_id)
    elif module == "objectives":
        obj = rec
    else:
        obj = db.get(Objective, rec.objective_id)
    return rec, _audit_or_404(db, obj.audit_id)


class ValuesIn(BaseModel):
    values: dict = Field(default_factory=dict)


@router.get("/api/custom-values/{module}/{record_id}")
def get_values(module: str, record_id: int, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    from app.domains.audit.fieldwork.signoffs import _in_scope
    from app.platform.customfields.router import _out, definitions

    rec, audit = _value_record(db, module, record_id)
    _in_scope(db, user, audit.id)
    return {"fields": [_out(d) for d in definitions(db, module, audit_type=audit.audit_type or "")],
            "values": json.loads(rec.custom_fields or "{}")}


@router.put("/api/custom-values/{module}/{record_id}")
def put_values(module: str, record_id: int, payload: ValuesIn, request: Request, db: DBSession = Depends(get_db),
               user: User = Staff) -> dict:
    from app.domains.audit.fieldwork.signoffs import _in_scope
    from app.platform.customfields.router import clean_values

    rec, audit = _value_record(db, module, record_id)
    _in_scope(db, user, audit.id)
    _ensure_open(audit)
    if module in _SIGNOFF_TYPE:
        ensure_editable(db, _SIGNOFF_TYPE[module], record_id)
    rec.custom_fields = json.dumps(clean_values(db, module, payload.values, json.loads(rec.custom_fields or "{}"),
                                                audit_type=audit.audit_type or ""))
    log_action(db, user_id=user.id, action=f"CUSTOM_VALUES {module}={record_id}", request=request)
    db.commit()
    return {"values": json.loads(rec.custom_fields)}


# ------------------------------------------------------------------ narratives

class NarrativeIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=60)
    description: str = Field("", max_length=524_288)
    control_ids: list[int] = Field(default_factory=list, max_length=100)


class NarrativeUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=60)
    description: str | None = Field(None, max_length=524_288)
    control_ids: list[int] | None = Field(None, max_length=100)
    position: int | None = Field(None, ge=0, le=10_000)


def _narrative(db: DBSession, narrative_id: int) -> Narrative:
    n = db.get(Narrative, narrative_id)
    if n is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Narrative not found")
    return n


def _set_controls(db: DBSession, n: Narrative, audit_id: int, ids: list[int]) -> None:
    ids = list(dict.fromkeys(ids))
    if ids:
        ok = set(db.execute(select(Control.id).join(Objective, Objective.id == Control.objective_id)
                            .where(Control.id.in_(ids), Objective.audit_id == audit_id)).scalars())
        bad = [i for i in ids if i not in ok]
        if bad:
            raise field_error("control_ids", "every control must belong to this audit")
    db.execute(delete(NarrativeControl).where(NarrativeControl.narrative_id == n.id))
    for cid in ids:
        db.add(NarrativeControl(narrative_id=n.id, control_id=cid))


def _narrative_out(n: Narrative, dots: list[dict], objective: Objective) -> dict:
    return {"id": n.id, "ref": n.ref, "objective_id": n.objective_id, "objective": objective.title,
            "title": n.title, "description": n.description, "position": n.position,
            "controls": [{"id": c.id, "ref": c.ref, "title": c.title} for c in n.controls],
            "custom_fields": json.loads(n.custom_fields or "{}"), "signoffs": dots,
            "read_only": any(d["done"] for d in dots), "updated_at": n.updated_at.isoformat()}


@router.get("/api/audits/{audit_id}/narratives")
def list_narratives(audit_id: int, db: DBSession = Depends(get_db), _: User = Staff) -> list[dict]:
    _audit_or_404(db, audit_id)
    objectives = {o.id: o for o in db.execute(select(Objective).where(Objective.audit_id == audit_id)).scalars()}
    items = list(db.execute(select(Narrative).where(Narrative.objective_id.in_(list(objectives) or [0]))
                            .order_by(Narrative.objective_id, Narrative.position, Narrative.id)).scalars())
    dots = dots_for(db, "narrative", [n.id for n in items])
    return [_narrative_out(n, dots[n.id], objectives[n.objective_id]) for n in items]


def ensure_narratives_allowed(audit) -> None:  # noqa: ANN001
    """Process narratives belong to the Internal Control workflow (PROJECTBLUEPRINT 5.5)."""
    from app.domains.audit.fieldwork.router import INTERNAL_CONTROL, default_workflow

    if (audit.workflow or default_workflow(audit.audit_type)) != INTERNAL_CONTROL:
        raise HTTPException(status_code=409, detail="Process narratives are part of the Internal Control workflow; "
                                                    "this audit uses the Workplan workflow")


@router.post("/api/objectives/{objective_id}/narratives", status_code=status.HTTP_201_CREATED)
def create_narrative(objective_id: int, payload: NarrativeIn, request: Request, db: DBSession = Depends(get_db),
                     user: User = Staff) -> dict:
    obj = _objective(db, objective_id)
    audit = _audit_or_404(db, obj.audit_id)
    _ensure_open(audit)
    ensure_narratives_allowed(audit)
    count = db.execute(select(func.count()).select_from(Narrative)
                       .where(Narrative.objective_id == obj.id)).scalar_one()
    n = Narrative(objective_id=obj.id, ref=next_reference(db, "NAR"), title=payload.title.strip(),
                  description=payload.description, position=count, custom_fields="{}", created_by=user.id)
    db.add(n)
    db.flush()
    _set_controls(db, n, audit.id, payload.control_ids)
    _history(db, audit.id, user, f"NARRATIVE {n.ref} ADDED: {n.title}", request)
    log_action(db, user_id=user.id, request=request, action=f"NARRATIVE_CREATE id={n.id} {n.ref} audit={audit.id}")
    db.commit()
    db.refresh(n)
    return _narrative_out(n, dots_for(db, "narrative", [n.id])[n.id], obj)


@router.patch("/api/narratives/{narrative_id}")
def update_narrative(narrative_id: int, payload: NarrativeUpdate, request: Request, db: DBSession = Depends(get_db),
                     user: User = Staff) -> dict:
    n = _narrative(db, narrative_id)
    obj = _objective(db, n.objective_id)
    audit = _audit_or_404(db, obj.audit_id)
    _ensure_open(audit)
    ensure_editable(db, "narrative", n.id)
    sent = payload.model_dump(exclude_unset=True)
    if sent.get("title") is not None:
        n.title = sent["title"].strip()
    if sent.get("description") is not None:
        n.description = sent["description"]
    if sent.get("position") is not None:
        n.position = sent["position"]
    if sent.get("control_ids") is not None:
        _set_controls(db, n, audit.id, sent["control_ids"])
    n.updated_at = utcnow()
    _history(db, audit.id, user, f"NARRATIVE {n.ref} UPDATED [{', '.join(sent)}]", request)
    log_action(db, user_id=user.id, request=request,
               action=f"NARRATIVE_UPDATE id={n.id} {n.ref} audit={audit.id} [{', '.join(sent)}]")
    db.commit()
    db.refresh(n)
    return _narrative_out(n, dots_for(db, "narrative", [n.id])[n.id], obj)


@router.delete("/api/narratives/{narrative_id}", response_model=MessageOut)
def delete_narrative(narrative_id: int, request: Request, db: DBSession = Depends(get_db),
                     user: User = Staff) -> MessageOut:
    n = _narrative(db, narrative_id)
    audit = _audit_or_404(db, _objective(db, n.objective_id).audit_id)
    _ensure_open(audit)
    ensure_editable(db, "narrative", n.id)
    ref = n.ref
    db.delete(n)
    _history(db, audit.id, user, f"NARRATIVE {ref} DELETED", request)
    log_action(db, user_id=user.id, request=request,
               action=f"NARRATIVE_DELETE id={narrative_id} {ref} audit={audit.id}")
    db.commit()
    return MessageOut(message=f"Narrative {ref} deleted")


# ------------------------------------------------------------------ favourites

@router.put("/api/audits/{audit_id}/favorite")
def add_favorite(audit_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> dict:
    audit = _audit_or_404(db, audit_id)
    if not visible(db, user, "audit", [audit]):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit not found")
    if db.get(AuditFavorite, (user.id, audit_id)) is None:
        db.add(AuditFavorite(user_id=user.id, audit_id=audit_id, created_at=utcnow()))
        db.commit()
    return {"favorite": True}


@router.delete("/api/audits/{audit_id}/favorite")
def remove_favorite(audit_id: int, db: DBSession = Depends(get_db),
                    user: User = Depends(require_active_user)) -> dict:
    row = db.get(AuditFavorite, (user.id, audit_id))
    if row is not None:
        db.delete(row)
        db.commit()
    return {"favorite": False}


def favorite_ids(db: DBSession, user: User) -> set[int]:
    return set(db.execute(select(AuditFavorite.audit_id).where(AuditFavorite.user_id == user.id)).scalars())


# ------------------------------------------------------------------ progress

def _work_counts(db: DBSession, audit: Audit) -> dict[str, int]:
    """Audit Procedures Completed: Not Started / In Process / Completed (procedures, or tests in the IC workflow)."""
    from app.domains.audit.fieldwork.router import P_IN_PROGRESS, P_NOT_STARTED, WORKPLAN

    objs = select(Objective.id).where(Objective.audit_id == audit.id)
    out = {"Not Started": 0, "In Process": 0, "Completed": 0}
    if (audit.workflow or "") == WORKPLAN:
        for st in db.execute(select(Procedure.status).where(Procedure.objective_id.in_(objs))).scalars():
            out["Not Started" if st == P_NOT_STARTED else "In Process" if st == P_IN_PROGRESS else "Completed"] += 1
    else:
        ctls = select(Control.id).where(Control.objective_id.in_(objs))
        for st in db.execute(select(ControlTest.status).where(ControlTest.control_id.in_(ctls),
                                                              ControlTest.in_scope.is_(True))).scalars():
            out["Not Started" if st == TestStatus.NotStarted else "In Process" if st == TestStatus.InProgress
                else "Completed"] += 1
    return out


def _dates(db: DBSession, audit: Audit) -> tuple[date | None, date | None, int]:
    from app.domains.assurance.planning.models import PlanEngagement

    eng = db.execute(select(PlanEngagement).where(PlanEngagement.audit_id == audit.id)).scalars().first()
    start = (eng.planned_start if eng and eng.planned_start else
             (audit.start_date.date() if getattr(audit, "start_date", None) else None))
    end = (eng.planned_end if eng and eng.planned_end else
           (audit.end_date.date() if getattr(audit, "end_date", None) else None))
    return start, end, (eng.budget_hours if eng else 0)


def _hours(db: DBSession, audit_ids: list[int]) -> dict[int, float]:
    from app.domains.audit.capacity.models import TimeEntry

    return {a: float(h or 0) for a, h in db.execute(
        select(TimeEntry.audit_id, func.sum(TimeEntry.hours)).where(TimeEntry.audit_id.in_(audit_ids or [0]))
        .group_by(TimeEntry.audit_id)).all()}


@router.get("/api/audits/{audit_id}/progress")
def audit_progress(audit_id: int, db: DBSession = Depends(get_db), _: User = Staff) -> dict:
    from app.domains.assurance.planning.coverage import engagement_progress

    audit = _audit_or_404(db, audit_id)
    start, end, budget = _dates(db, audit)
    today = date.today()
    expired = None
    if start and end and end > start:
        expired = max(0, min(100, round(100 * (today - start).days / (end - start).days)))
    return {"work": _work_counts(db, audit), "progress": engagement_progress(db, audit),
            "start": start.isoformat() if start else None, "target": end.isoformat() if end else None,
            "days_to_deadline": (end - today).days if end else None, "time_expired": expired,
            "budget_hours": budget, "time_spent": _hours(db, [audit.id]).get(audit.id, 0.0)}


@router.get("/api/audits/status-tracker")
def status_tracker(db: DBSession = Depends(get_db), user: User = Staff) -> list[dict]:
    """Project Status Tracker: active audits with time expired, work completed, budget and time spent."""
    from app.domains.assurance.planning.coverage import engagement_progress

    audits = visible(db, user, "audit", list(db.execute(select(Audit).where(Audit.status != AuditStatus.Closed)
                                                         .order_by(Audit.id)).scalars()))
    hours = _hours(db, [a.id for a in audits])
    favs = favorite_ids(db, user)
    today = date.today()
    rows = []
    for a in audits:
        start, end, budget = _dates(db, a)
        expired = None
        if start and end and end > start:
            expired = max(0, min(100, round(100 * (today - start).days / (end - start).days)))
        rows.append({"id": a.id, "ref": f"AUD-{a.id:04d}", "name": a.title, "type": a.audit_type,
                     "status": a.status.value, "workflow": a.workflow, "start": start.isoformat() if start else None,
                     "target": end.isoformat() if end else None, "time_expired": expired,
                     "work_completed": engagement_progress(db, a), "budget": budget,
                     "time_spent": hours.get(a.id, 0.0), "favorite": a.id in favs})
    return rows


@router.post("/api/audits/{audit_id}/narratives/reorder", response_model=MessageOut)
def reorder_narratives(audit_id: int, ids: list[int], request: Request, db: DBSession = Depends(get_db),
                       user: User = Staff) -> MessageOut:
    audit = _audit_or_404(db, audit_id)
    _ensure_open(audit)
    objs = select(Objective.id).where(Objective.audit_id == audit_id)
    found = {n.id: n for n in db.execute(select(Narrative).where(Narrative.objective_id.in_(objs))).scalars()}
    if any(i not in found for i in ids):
        raise _conflict("Every narrative must belong to this audit")
    for pos, i in enumerate(ids):
        found[i].position = pos
    log_action(db, user_id=user.id, request=request, action=f"NARRATIVE_REORDER audit={audit_id}")
    db.commit()
    return MessageOut(message="Order saved")

