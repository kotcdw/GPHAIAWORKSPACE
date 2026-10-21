"""Import Objective and Clone Objective (PROJECTBLUEPRINT 5.5 and 6.7).

* **Import** copies one or more objectives into this audit from another audit or from a framework (an audit
  programme in the Project Library). Optionally the source audit's results come too.
* **Clone** copies a single objective from this audit to one target audit, one at a time.

Both keep risks, controls with their test plan, narratives (Internal Control audits only) and procedures. Sign-offs
and reviews never travel: copied work is reviewed again in the target audit. Each audit holds at most the
configured number of objectives (Configuration › Audit methodology, default 500).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.appconfig import cfg
from app.core.audit import log_action
from app.core.database import get_db
from app.domains.audit.audits.models import Audit
from app.domains.audit.rcm.models import Objective
from app.domains.audit.rcm.router import Staff, _audit_or_404, _ensure_open, _history, _objective
from app.platform.users.models import User

router = APIRouter(tags=["risk & control matrix"])


class ImportIn(BaseModel):
    source: Literal["audit", "programme"]
    source_id: int
    objective_ids: list[int] = Field(default_factory=list, max_length=500)  # source = audit
    objective_titles: list[str] = Field(default_factory=list, max_length=500)  # source = programme
    include_results: bool = False

    @model_validator(mode="after")
    def _chosen(self) -> ImportIn:
        if self.source == "audit" and not self.objective_ids:
            raise ValueError("choose at least one objective to import")
        if self.source == "programme" and not self.objective_titles:
            raise ValueError("choose at least one objective to import")
        if self.source == "programme" and self.include_results:
            raise ValueError("a framework (programme) has no results to include")
        return self


class CloneIn(BaseModel):
    target_audit_id: int
    include_results: bool = False


def _scope(db: DBSession, user: User) -> set[int] | None:
    from app.core.access import staff_audit_scope

    return staff_audit_scope(db, user)


def _visible_audit(db: DBSession, user: User, audit_id: int, label: str) -> Audit:
    a = db.get(Audit, audit_id)
    scope = _scope(db, user)
    if a is None or (scope is not None and a.id not in scope):
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return a


def _room(db: DBSession, audit: Audit, adding: int) -> None:
    limit = int(cfg("audit_max_objectives"))
    have = db.execute(select(func.count()).select_from(Objective).where(Objective.audit_id == audit.id)).scalar_one()
    if have + adding > limit:
        raise HTTPException(status_code=409, detail=f"An audit holds at most {limit} objectives "
                                                    f"(it has {have}; this would add {adding})")


@router.get("/api/audits/{audit_id}/objective-sources")
def objective_sources(audit_id: int, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    """Where objectives can be imported from: other audits the user can see, and active audit programmes."""
    from app.domains.audit.programs.models import AuditProgram

    _audit_or_404(db, audit_id)
    scope = _scope(db, user)
    counts = dict(db.execute(select(Objective.audit_id, func.count()).group_by(Objective.audit_id)).all())
    audits = [{"id": a.id, "ref": f"AUD-{a.id:04d}", "title": a.title, "status": a.status.value,
               "objectives": counts.get(a.id, 0)}
              for a in db.execute(select(Audit).where(Audit.id != audit_id).order_by(Audit.id.desc())).scalars()
              if counts.get(a.id) and (scope is None or a.id in scope)]
    programmes = []
    active = select(AuditProgram).where(AuditProgram.status == "Active").order_by(AuditProgram.name)
    for p in db.execute(active).scalars():
        titles = list(dict.fromkeys(s.get("objective", "").strip() for s in p.step_list if s.get("objective")))
        if titles:
            programmes.append({"id": p.id, "ref": p.prog_ref, "name": p.name, "objectives": titles})
    return {"audits": audits, "programmes": programmes}


@router.get("/api/audits/{audit_id}/objective-sources/{source_audit_id}")
def source_objectives(audit_id: int, source_audit_id: int, db: DBSession = Depends(get_db),
                      user: User = Staff) -> list[dict]:
    _audit_or_404(db, audit_id)
    src = _visible_audit(db, user, source_audit_id, "Source audit")
    return [{"id": o.id, "ref": o.ref, "title": o.title, "risks": len(o.risks), "controls": len(o.controls)}
            for o in db.execute(select(Objective).where(Objective.audit_id == src.id).order_by(Objective.id)).scalars()]


@router.post("/api/audits/{audit_id}/objectives/import", status_code=201)
def import_objectives(audit_id: int, payload: ImportIn, request: Request, db: DBSession = Depends(get_db),
                      user: User = Staff) -> dict:
    from app.domains.assurance.planning.projects import copy_objective

    audit = _audit_or_404(db, audit_id)
    _ensure_open(audit)
    if payload.source == "audit":
        if payload.source_id == audit.id:
            raise HTTPException(status_code=422, detail="Import from another audit; to copy within an audit, clone")
        src = _visible_audit(db, user, payload.source_id, "Source audit")
        objs = list(db.execute(select(Objective).where(Objective.audit_id == src.id,
                                                       Objective.id.in_(payload.objective_ids))
                               .order_by(Objective.id)).scalars())
        if len(objs) != len(set(payload.objective_ids)):
            raise HTTPException(status_code=422, detail="Some objectives are not in the source audit")
        _room(db, audit, len(objs))
        counts = {"objectives": 0, "risks": 0, "controls": 0, "narratives": 0, "procedures": 0, "tests": 0}
        for o in objs:
            copy_objective(db, o, audit, user, include_results=payload.include_results, counts=counts)
        source = f"AUD-{src.id:04d}"
    else:
        from app.domains.audit.programs.models import AuditProgram
        from app.domains.audit.programs.router import copy_program

        prog = db.get(AuditProgram, payload.source_id)
        if prog is None or prog.status != "Active":
            raise HTTPException(status_code=404, detail="Programme not found")
        known = {s.get("objective", "").strip().lower() for s in prog.step_list}
        if any(t.strip().lower() not in known for t in payload.objective_titles):
            raise HTTPException(status_code=422, detail="Some objectives are not in the programme")
        have = {o.title.lower() for o in db.execute(select(Objective).where(Objective.audit_id == audit.id)).scalars()}
        _room(db, audit, sum(1 for t in set(payload.objective_titles) if t.strip().lower() not in have))
        counts = copy_program(db, audit, prog, user, only_objectives=set(payload.objective_titles))
        source = prog.prog_ref
    _history(db, audit.id, user, f"OBJECTIVES IMPORTED from {source}: {counts}", request)
    log_action(db, user_id=user.id, request=request,
               action=f"OBJECTIVE_IMPORT audit={audit.id} from={source} results={payload.include_results} {counts}")
    db.commit()
    return {"imported": counts.get("objectives", 0), "counts": counts, "source": source}


@router.post("/api/objectives/{objective_id}/clone", status_code=201)
def clone_objective(objective_id: int, payload: CloneIn, request: Request, db: DBSession = Depends(get_db),
                    user: User = Staff) -> dict:
    """Clone one objective to one target audit (the user must be able to work on both)."""
    from app.core.access import staff_audit_scope
    from app.domains.assurance.planning.projects import copy_objective

    obj = _objective(db, objective_id)
    scope = staff_audit_scope(db, user)
    if scope is not None and obj.audit_id not in scope:
        raise HTTPException(status_code=404, detail="Objective not found")
    target = _visible_audit(db, user, payload.target_audit_id, "Target audit")
    _ensure_open(target)
    _room(db, target, 1)
    counts = {"objectives": 0, "risks": 0, "controls": 0, "narratives": 0, "procedures": 0, "tests": 0}
    new = copy_objective(db, obj, target, user, include_results=payload.include_results, counts=counts)
    _history(db, target.id, user, f"OBJECTIVE CLONED {obj.ref} -> {new.ref} from AUD-{obj.audit_id:04d}", request)
    log_action(db, user_id=user.id, request=request,
               action=f"OBJECTIVE_CLONE {obj.ref} audit={obj.audit_id} -> {new.ref} audit={target.id}")
    db.commit()
    return {"id": new.id, "ref": new.ref, "audit_id": target.id, "counts": counts}


def _progress(states: list[str]) -> str:
    """Not Started / In Process / Completed from the work under an objective."""
    if not states or all(s == "Not Started" for s in states):
        return "Not Started"
    if all(s in ("Completed", "Reviewed", "Prepared") for s in states):
        return "Completed"
    return "In Process"


@router.get("/api/audits/{audit_id}/objective-list")
def objective_list(audit_id: int, db: DBSession = Depends(get_db), user: User = Staff) -> list[dict]:
    """Fieldwork › objective list: each objective with its assigned users and progress (from its tests or
    procedures: Not Started, In Process, Completed)."""
    from app.core.access import staff_audit_scope
    from app.domains.audit.rcm.models import Control, ControlTest, Narrative, Procedure

    audit = _audit_or_404(db, audit_id)
    scope = staff_audit_scope(db, user)
    if scope is not None and audit.id not in scope:
        raise HTTPException(status_code=404, detail="Audit not found")
    names = {u.id: (u.full_name or u.username) for u in db.execute(select(User)).scalars()}
    out = []
    for o in db.execute(select(Objective).where(Objective.audit_id == audit.id).order_by(Objective.id)).scalars():
        controls = list(db.execute(select(Control).where(Control.objective_id == o.id)).scalars())
        tests = list(db.execute(select(ControlTest).where(ControlTest.control_id.in_([c.id for c in controls] or [0])))
                     .scalars())
        procs = list(db.execute(select(Procedure).where(Procedure.objective_id == o.id)).scalars())
        narratives = db.execute(select(func.count()).select_from(Narrative)
                                .where(Narrative.objective_id == o.id)).scalar_one()
        who = [*(t.assigned_to for t in tests), *(p.assigned_to for p in procs)]
        assigned = list(dict.fromkeys(names[x] for x in who if x in names))
        states = [t.status.value for t in tests] + [p.status for p in procs]
        out.append({"id": o.id, "ref": o.ref, "title": o.title, "description": o.description,
                    "assigned": assigned, "progress": _progress(states), "risks": len(o.risks),
                    "controls": len(controls),
                    "tests": len(tests), "procedures": len(procs), "narratives": narratives,
                    "framework_id": o.source_program_id})
    return out
