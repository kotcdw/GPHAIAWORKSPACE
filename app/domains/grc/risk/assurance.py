"""Strategy › Treatment and Assurance (PROJECTBLUEPRINT 5.4, 6.4; Strategy walkthrough steps 6 and 8).

A strategic (enterprise) risk is *treated* by objectives:

* a **project objective** (an objective inside one audit), or
* a **framework objective** (an objective of a Project Library programme). Linking a framework objective rolls up
  assurance from every project objective that was imported or applied from that framework.

A risk is linked to either the framework objective or the project objectives that came from it, never both, so
nothing is counted twice. Audit risks that name the enterprise risk they test also count ("Tests the risk").

The Assurance view rolls up the controls, tests and published issues of the treated objectives. Only explicit
links count, and figures are limited to the audits the viewer may see.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DBSession

from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user
from app.core.enums import TestConclusion, TestType, utcnow
from app.domains.grc.common import GRC_PERMS, band, can, editor
from app.domains.grc.risk.models import EnterpriseRisk, RiskTreatment
from app.platform.users.models import User

router = APIRouter(prefix="/api/grc", tags=["risk & compliance"])
RiskEditor = editor("grc.risk")


class FrameworkObjectiveIn(BaseModel):
    program_id: int
    title: str = Field(min_length=1, max_length=255)


class TreatmentIn(BaseModel):
    objective_ids: list[int] = Field(default_factory=list, max_length=100)
    framework_objectives: list[FrameworkObjectiveIn] = Field(default_factory=list, max_length=100)
    note: str = Field(default="", max_length=500)


def _risk(db: DBSession, risk_id: int, user: User) -> EnterpriseRisk:
    r = db.get(EnterpriseRisk, risk_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Risk not found")
    if not (can(user, *GRC_PERMS) or r.owner_id == user.id):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return r


def _scope(db: DBSession, user: User) -> set[int] | None:
    from app.core.access import staff_audit_scope

    return staff_audit_scope(db, user)


def _framework_objectives(db: DBSession, program_id: int, title: str) -> list[int]:
    from app.domains.audit.rcm.models import Objective

    return list(db.execute(select(Objective.id).where(Objective.source_program_id == program_id,
                                                      func.lower(Objective.title) == title.strip().lower())).scalars())


def treated_objective_ids(db: DBSession, risk_id: int) -> dict[int, str]:
    """Objective id -> how it is linked ('Treatment', 'Framework treatment' or 'Tests the risk')."""
    from app.domains.audit.rcm.models import Risk

    out: dict[int, str] = {}
    for t in db.execute(select(RiskTreatment).where(RiskTreatment.risk_id == risk_id)).scalars():
        if t.objective_id:
            out[t.objective_id] = "Treatment"
        elif t.program_id and t.program_objective:
            for oid in _framework_objectives(db, t.program_id, t.program_objective):
                out.setdefault(oid, "Framework treatment")
    for (oid,) in db.execute(select(Risk.objective_id).where(Risk.enterprise_risk_id == risk_id)).all():
        out.setdefault(oid, "Tests the risk")
    return out


def _control_result(tests: list) -> str:  # noqa: ANN001
    operating = [t for t in tests if t.test_type == TestType.OperatingEffectiveness]
    design = [t for t in tests if t.test_type in (TestType.Walkthrough, TestType.Design)]
    latest = max(operating, key=lambda t: t.id) if operating else None
    if any(t.conclusion == TestConclusion.Ineffective for t in design) or (
            latest is not None and latest.conclusion == TestConclusion.Ineffective):
        return "Failing"
    if latest is not None and latest.conclusion == TestConclusion.Effective:
        return "Passing"
    return "Not tested"


def _tally(r: dict) -> dict:
    return {"passing": r.get("Passing", 0), "failing": r.get("Failing", 0), "not_tested": r.get("Not tested", 0)}


def risk_assurance(db: DBSession, risk_id: int, scope: set[int] | None) -> dict:
    """Roll-up of the assurance work on one enterprise risk, from its treated objectives only."""
    from app.domains.audit.audits.models import Audit, Finding
    from app.domains.audit.programs.models import AuditProgram
    from app.domains.audit.rcm.models import Control, ControlTest, Objective, Procedure

    links = treated_objective_ids(db, risk_id)
    objs = [o for o in db.execute(select(Objective).where(Objective.id.in_(list(links) or [0]))).scalars()
            if scope is None or o.audit_id in scope]
    obj_ids = [o.id for o in objs]
    audits = {a.id: a for a in db.execute(select(Audit).where(Audit.id.in_([o.audit_id for o in objs] or [0])))
              .scalars()}
    controls = list(db.execute(select(Control).where(Control.objective_id.in_(obj_ids or [0]))).scalars())
    tests: dict[int, list] = {}
    control_ids = [c.id for c in controls]
    for t in db.execute(select(ControlTest).where(ControlTest.control_id.in_(control_ids or [0]))).scalars():
        tests.setdefault(t.control_id, []).append(t)
    counts = {"Passing": 0, "Failing": 0, "Not tested": 0}
    per_control = []
    per_objective: dict[int, dict[str, int]] = {}
    for c in controls:
        result = _control_result(tests.get(c.id, []))
        counts[result] += 1
        per_objective.setdefault(c.objective_id, {"Passing": 0, "Failing": 0, "Not tested": 0})[result] += 1
        per_control.append({"id": c.id, "ref": c.ref, "title": c.title, "audit_id": c.objective.audit_id,
                            "objective_id": c.objective_id, "result": result})
    total = sum(counts.values())
    # Issues roll up only when they belong to a treated objective (its control, test or procedure) and are
    # published: issues outside a linked objective, or not yet published, are not counted.
    proc_ids = list(db.execute(select(Procedure.id).where(Procedure.objective_id.in_(obj_ids or [0]))).scalars())
    findings = list(db.execute(select(Finding).where(
        Finding.audit_id.in_(list(audits) or [0]), Finding.published.is_(True),
        or_(Finding.control_id.in_(control_ids or [0]), Finding.procedure_id.in_(proc_ids or [0])))).scalars())
    recent = utcnow() - timedelta(days=90)
    closed = [f for f in findings if f.status.value == "Closed"]
    issues = {"open": len(findings) - len(closed),
              "new_90_days": sum(1 for f in findings if f.created_at >= recent),
              "remediated": len(closed), "total": len(findings)}

    treatments = []
    programs = {p.id: p for p in db.execute(select(AuditProgram)).scalars()}
    for t in db.execute(select(RiskTreatment).where(RiskTreatment.risk_id == risk_id)
                        .order_by(RiskTreatment.id)).scalars():
        if t.objective_id:
            o = next((x for x in objs if x.id == t.objective_id), None)
            if o is None:
                continue  # outside the viewer's access
            a = audits.get(o.audit_id)
            treatments.append({"treatment_id": t.id, "type": "Project objective", "title": o.title, "ref": o.ref,
                               "source": f"AUD-{o.audit_id:04d} {a.title}" if a else None, "audit_id": o.audit_id,
                               "program_id": None, "objectives": 1, **_tally(per_objective.get(o.id, {}))})
        else:
            p = programs.get(t.program_id)
            mine = [x for x in objs if links.get(x.id) == "Framework treatment"
                    and x.source_program_id == t.program_id
                    and x.title.strip().lower() == (t.program_objective or "").strip().lower()]
            agg = {"Passing": 0, "Failing": 0, "Not tested": 0}
            for x in mine:
                for k, v in per_objective.get(x.id, {}).items():
                    agg[k] += v
            treatments.append({"treatment_id": t.id, "type": "Framework objective", "title": t.program_objective,
                               "ref": p.prog_ref if p else None, "source": p.name if p else "Framework removed",
                               "audit_id": None, "program_id": t.program_id, "objectives": len(mine), **_tally(agg)})
    return {
        "objectives": [{"id": o.id, "ref": o.ref, "title": o.title, "audit_id": o.audit_id,
                        "audit": f"AUD-{o.audit_id:04d} {audits[o.audit_id].title}" if o.audit_id in audits else None,
                        "audit_status": audits[o.audit_id].status.value if o.audit_id in audits else None,
                        "link": links[o.id]} for o in objs],
        "treatments": treatments,
        "controls": {"passing": counts["Passing"], "failing": counts["Failing"], "not_tested": counts["Not tested"],
                     "total": total, "items": per_control},
        "issues": issues,
        # Overall assurance: share of treated controls tested and concluded effective. Untested controls count
        # against it, so a risk with nothing tested shows 0 %, never a reassuring blank.
        "overall_assurance": round(100 * counts["Passing"] / total, 1) if total else None,
        "basis": "Controls in objectives that treat this risk. Passing = latest operating test Effective; "
                 "Failing = an Ineffective test or design failure. Issues: published issues inside those objectives.",
    }


@router.get("/treatment-sources")
def treatment_sources(q: str = Query("", max_length=100), db: DBSession = Depends(get_db),
                      user: User = RiskEditor) -> list[dict]:
    """Define Risk Treatment › Find projects/frameworks: frameworks and the audits the user can see, each with its
    objectives (expand to select)."""
    from app.domains.audit.audits.models import Audit
    from app.domains.audit.programs.models import AuditProgram
    from app.domains.audit.rcm.models import Objective

    like = q.strip().lower()
    out = []
    active = select(AuditProgram).where(AuditProgram.status == "Active").order_by(AuditProgram.name)
    for p in db.execute(active).scalars():
        titles = list(dict.fromkeys(s.get("objective", "").strip() for s in p.step_list if s.get("objective")))
        if titles and (not like or like in p.name.lower() or any(like in t.lower() for t in titles)):
            out.append({"type": "framework", "id": p.id, "ref": p.prog_ref, "name": p.name,
                        "objectives": [{"title": t} for t in titles]})
    scope = _scope(db, user)
    by_audit: dict[int, list] = {}
    for o in db.execute(select(Objective).order_by(Objective.id)).scalars():
        if scope is None or o.audit_id in scope:
            by_audit.setdefault(o.audit_id, []).append(o)
    for a in db.execute(select(Audit).where(Audit.id.in_(list(by_audit) or [0])).order_by(Audit.id.desc())).scalars():
        objs = by_audit[a.id]
        if like and like not in a.title.lower() and not any(like in o.title.lower() or like in o.ref.lower()
                                                            for o in objs):
            continue
        out.append({"type": "project", "id": a.id, "ref": f"AUD-{a.id:04d}", "name": a.title,
                    "status": a.status.value, "objectives": [{"id": o.id, "ref": o.ref, "title": o.title}
                                                             for o in objs]})
    return out[:150]


@router.get("/risks/{risk_id}/assurance")
def get_assurance(risk_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> dict:
    r = _risk(db, risk_id, user)
    return {"risk_id": r.id, "ref": r.ref, "title": r.title, "can_edit": can(user, "grc.risk"),
            "inherent_score": r.inherent_score, "inherent_level": band(r.inherent_score),
            "residual_score": r.residual_score, "residual_level": band(r.residual_score),
            **risk_assurance(db, r.id, _scope(db, user))}


@router.post("/risks/{risk_id}/treatments", status_code=201)
def link_treatments(risk_id: int, payload: TreatmentIn, request: Request, db: DBSession = Depends(get_db),
                    user: User = RiskEditor) -> dict:
    """Link # Treatments: project objectives and/or framework objectives."""
    from app.domains.audit.programs.models import AuditProgram
    from app.domains.audit.rcm.models import Objective

    if not payload.objective_ids and not payload.framework_objectives:
        raise HTTPException(status_code=422, detail="Select at least one objective")
    r = _risk(db, risk_id, user)
    scope = _scope(db, user)
    existing = list(db.execute(select(RiskTreatment).where(RiskTreatment.risk_id == r.id)).scalars())
    linked_objs = {t.objective_id for t in existing if t.objective_id}
    linked_fw = {(t.program_id, (t.program_objective or "").strip().lower()) for t in existing if t.program_id}
    added = []
    for fo in payload.framework_objectives:
        p = db.get(AuditProgram, fo.program_id)
        titles = {s.get("objective", "").strip().lower() for s in (p.step_list if p else [])}
        key = (fo.program_id, fo.title.strip().lower())
        if p is None or key[1] not in titles:
            raise HTTPException(status_code=422, detail=f"'{fo.title}' is not an objective of that framework")
        if key in linked_fw:
            continue
        if set(_framework_objectives(db, fo.program_id, fo.title)) & linked_objs:
            raise HTTPException(status_code=409, detail=f"Project objectives from '{fo.title}' are already linked; "
                                                        "link the framework objective or its project objectives, "
                                                        "not both")
        db.add(RiskTreatment(risk_id=r.id, program_id=fo.program_id, program_objective=fo.title.strip(),
                             note=payload.note.strip(), created_by=user.id))
        linked_fw.add(key)
        added.append(f"{p.prog_ref}:{fo.title.strip()}")
    for oid in dict.fromkeys(payload.objective_ids):
        o = db.get(Objective, oid)
        if o is None or (scope is not None and o.audit_id not in scope):
            raise HTTPException(status_code=422, detail=f"Objective {oid} is not one you can link")
        if oid in linked_objs:
            continue
        if o.source_program_id and (o.source_program_id, o.title.strip().lower()) in linked_fw:
            raise HTTPException(status_code=409, detail=f"{o.ref} comes from a framework objective that is already "
                                                        "linked; link the framework objective or its project "
                                                        "objectives, not both")
        db.add(RiskTreatment(risk_id=r.id, objective_id=oid, note=payload.note.strip(), created_by=user.id))
        linked_objs.add(oid)
        added.append(o.ref)
    log_action(db, user_id=user.id, action=f"ERM_TREATMENT_LINK {r.ref} objectives={added}", request=request)
    db.commit()
    return {"linked": len(added), **risk_assurance(db, r.id, scope)}


@router.delete("/risks/{risk_id}/treatments/{treatment_id}")
def unlink_treatment(risk_id: int, treatment_id: int, request: Request, db: DBSession = Depends(get_db),
                     user: User = RiskEditor) -> dict:
    r = _risk(db, risk_id, user)
    t = db.get(RiskTreatment, treatment_id)
    if t is None or t.risk_id != r.id:
        raise HTTPException(status_code=404, detail="Treatment link not found")
    what = t.objective_id or f"{t.program_id}:{t.program_objective}"
    db.delete(t)
    log_action(db, user_id=user.id, action=f"ERM_TREATMENT_UNLINK {r.ref} objective={what}", request=request)
    db.commit()
    return risk_assurance(db, r.id, _scope(db, user))
