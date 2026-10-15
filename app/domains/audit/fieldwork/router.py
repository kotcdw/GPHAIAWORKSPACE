"""Fieldwork workflows (HighBond Projects).

* **Workplan**: Objectives -> Risks -> Procedures -> Execute procedures (results, "Were issues identified?",
  preparer and reviewer sign-offs) -> Issues.
* **Internal Control**: Objectives -> Risks and Controls (RCM) -> Walkthroughs ("Is the control designed
  appropriately?") -> Test plan -> Testing rounds (1, 2 or 4; one test per key control per round) -> Issues.

An audit uses one workflow, chosen when it is created (Configuration > Audit methodology lists the audit types that
use the Workplan) and switchable while it has neither procedures nor controls. Every route here resolves to an
audit, so the port / engagement-team scope guard applies.
"""

from __future__ import annotations

from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.appconfig import cfg, parse_sample_sizes
from app.core.approvalsvc import sign
from app.core.audit import log_action
from app.core.database import get_db
from app.core.enums import (
    ControlNature,
    FindingStatus,
    RiskRating,
    TestConclusion,
    TestStatus,
    TestType,
    utcnow,
)
from app.core.errors import field_error
from app.core.refs import next_reference
from app.core.schemas import ESignRequest, MessageOut
from app.domains.audit.audits.models import Audit, AuditTeamMember, Finding
from app.domains.audit.audits.schemas import FindingOut
from app.domains.audit.rcm.models import Control, ControlTest, Objective, Procedure, ProcedureRisk, Risk
from app.domains.audit.rcm.router import (
    Staff,
    _assignee,
    _audit_or_404,
    _conflict,
    _ensure_open,
    _history,
    _not_found,
    _objective,
    control_effectiveness,
)
from app.platform.users.models import User

router = APIRouter(tags=["fieldwork"])

WORKPLAN = "Workplan"
INTERNAL_CONTROL = "Internal Control"
WORKFLOWS = (WORKPLAN, INTERNAL_CONTROL)

# HighBond testing rounds: the number is fixed once testing starts; each count has its own round names.
ROUND_LABELS = {1: ["Testing"], 2: ["Interim", "Final"], 4: ["Q1", "Q2", "Q3", "Q4"]}

P_NOT_STARTED, P_IN_PROGRESS, P_PREPARED, P_REVIEWED = "Not Started", "In Progress", "Prepared", "Reviewed"
PROCEDURE_STATUSES = (P_NOT_STARTED, P_IN_PROGRESS, P_PREPARED, P_REVIEWED)
NO_ISSUES, ISSUES_NOTED = "No Issues", "Issue(s) noted"

# Walkthrough conclusion as HighBond words it ("Is the control designed appropriately?").
WALKTHROUGH_LABELS = {TestConclusion.Effective: "Designed appropriately", TestConclusion.Ineffective: "Design failure",
                      TestConclusion.NotTested: "Not concluded"}


def default_workflow(audit_type: str | None) -> str:
    types = {t.lower() for t in (cfg("workplan_audit_types") or [])}
    return WORKPLAN if audit_type and audit_type.lower() in types else INTERNAL_CONTROL


def default_sample(control: Control) -> int:
    if control.total_sample_size:
        return control.total_sample_size
    if control.nature == ControlNature.Automated:
        return 1
    try:
        return parse_sample_sizes(cfg("sample_sizes_by_frequency")).get(control.frequency.value, 1)
    except ValueError:
        return 1


def _names(db: DBSession, ids) -> dict[int, str]:  # noqa: ANN001
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    rows = db.execute(select(User.id, User.full_name, User.username).where(User.id.in_(wanted))).all()
    return {r.id: r.full_name or r.username for r in rows}


def _counts(db: DBSession, audit_id: int) -> tuple[int, int]:
    obj_ids = select(Objective.id).where(Objective.audit_id == audit_id)
    procs = db.execute(select(func.count()).select_from(Procedure).where(Procedure.objective_id.in_(obj_ids)))
    ctls = db.execute(select(func.count()).select_from(Control).where(Control.objective_id.in_(obj_ids)))
    return procs.scalar_one(), ctls.scalar_one()


def _round_tests_exist(db: DBSession, audit_id: int) -> bool:
    obj_ids = select(Objective.id).where(Objective.audit_id == audit_id)
    ctl_ids = select(Control.id).where(Control.objective_id.in_(obj_ids))
    return db.execute(
        select(func.count()).select_from(ControlTest)
        .where(ControlTest.control_id.in_(ctl_ids), ControlTest.test_type == TestType.OperatingEffectiveness)
    ).scalar_one() > 0


# ==================================================================== workflow settings


class FieldworkSettingsIn(BaseModel):
    workflow: str | None = None
    testing_rounds: int | None = None


def _settings(db: DBSession, audit: Audit) -> dict:
    procs, ctls = _counts(db, audit.id)
    workflow_lock = "" if not (procs or ctls) else (
        f"The audit already has {procs} procedure(s) and {ctls} control(s)")
    rounds_lock = "Testing has started in a round" if _round_tests_exist(db, audit.id) else ""
    return {"audit_id": audit.id, "workflow": audit.workflow, "workflows": list(WORKFLOWS),
            "testing_rounds": audit.testing_rounds, "round_options": sorted(ROUND_LABELS),
            "round_labels": ROUND_LABELS.get(audit.testing_rounds, ["Testing"]),
            "workflow_locked": workflow_lock, "rounds_locked": rounds_lock,
            "procedures": procs, "controls": ctls}


@router.get("/api/audits/{audit_id}/fieldwork")
def get_fieldwork(audit_id: int, db: DBSession = Depends(get_db), _: User = Staff) -> dict:
    return _settings(db, _audit_or_404(db, audit_id))


@router.patch("/api/audits/{audit_id}/fieldwork")
def update_fieldwork(audit_id: int, payload: FieldworkSettingsIn, request: Request,
                     db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    audit = _audit_or_404(db, audit_id)
    _ensure_open(audit)
    current = _settings(db, audit)
    changed = []
    if payload.workflow is not None and payload.workflow != audit.workflow:
        if payload.workflow not in WORKFLOWS:
            raise field_error("workflow", f"must be {' or '.join(WORKFLOWS)}")
        if current["workflow_locked"]:
            raise field_error("workflow", current["workflow_locked"] + "; the workflow can no longer change")
        audit.workflow = payload.workflow
        changed.append(f"workflow={payload.workflow}")
    if payload.testing_rounds is not None and payload.testing_rounds != audit.testing_rounds:
        if payload.testing_rounds not in ROUND_LABELS:
            raise field_error("testing_rounds", "must be 1, 2 or 4")
        if current["rounds_locked"]:
            raise field_error("testing_rounds", "testing has started; the number of rounds is fixed")
        audit.testing_rounds = payload.testing_rounds
        changed.append(f"rounds={payload.testing_rounds}")
    if changed:
        log_action(db, user_id=user.id, action=f"FIELDWORK_SETTINGS audit={audit.id} {' '.join(changed)}",
                   request=request)
        _history(db, audit.id, user, f"FIELDWORK SETTINGS {', '.join(changed)}", request)
        db.commit()
    return _settings(db, audit)


# ==================================================================== Workplan procedures


class ProcedureIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    steps: str = Field(default="", max_length=20000)
    risk_ids: list[int] = []
    assigned_to: int | None = None
    due_date: date | None = None


class ProcedureUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    steps: str | None = Field(default=None, max_length=20000)
    risk_ids: list[int] | None = None
    assigned_to: int | None = None  # 0 clears
    due_date: date | None = None
    results: str | None = Field(default=None, max_length=50000)
    outcome: str | None = None
    status: str | None = None


def _procedure(db: DBSession, procedure_id: int) -> Procedure:
    p = db.get(Procedure, procedure_id)
    if p is None:
        raise _not_found("Procedure")
    return p


def _audit_of_procedure(db: DBSession, p: Procedure) -> Audit:
    return _audit_or_404(db, _objective(db, p.objective_id).audit_id)


def _set_risks(db: DBSession, p: Procedure, audit_id: int, risk_ids: list[int]) -> None:
    ids = list(dict.fromkeys(risk_ids))
    if ids:
        found = db.execute(
            select(Risk.id).join(Objective, Objective.id == Risk.objective_id)
            .where(Risk.id.in_(ids), Objective.audit_id == audit_id)
        ).scalars().all()
        missing = sorted(set(ids) - set(found))
        if missing:
            raise field_error("risk_ids", f"risk(s) {missing} are not in this audit")
    db.query(ProcedureRisk).filter(ProcedureRisk.procedure_id == p.id).delete()
    for rid in ids:
        db.add(ProcedureRisk(procedure_id=p.id, risk_id=rid))
    db.flush()
    db.expire(p, ["risks"])


def _issue_ids(db: DBSession, procedure_ids: list[int]) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    if procedure_ids:
        for fid, pid in db.execute(select(Finding.id, Finding.procedure_id)
                                   .where(Finding.procedure_id.in_(procedure_ids))).all():
            out.setdefault(pid, []).append(fid)
    return out


def _request_counts(db: DBSession, target_type: str, ids: list[int]) -> dict[int, int]:
    from app.domains.audit.evidence.models import EvidenceRequest

    if not ids:
        return {}
    rows = db.execute(select(EvidenceRequest.target_id, func.count()).where(
        EvidenceRequest.target_type == target_type, EvidenceRequest.target_id.in_(ids))
        .group_by(EvidenceRequest.target_id)).all()
    return {tid: n for tid, n in rows}


def _procedure_out(p: Procedure, objective: Objective, names: dict[int, str], issues: list[int],
                   requests: int) -> dict:
    overdue = bool(p.due_date and p.status in (P_NOT_STARTED, P_IN_PROGRESS) and p.due_date < utcnow())
    return {
        "id": p.id, "objective_id": p.objective_id, "objective_ref": objective.ref, "objective": objective.title,
        "ref": p.ref, "title": p.title, "steps": p.steps,
        "risk_ids": [r.id for r in p.risks],
        "risks": [{"id": r.id, "ref": r.ref, "title": r.title, "rating": r.inherent_rating} for r in p.risks],
        "assigned_to": p.assigned_to, "assigned_name": names.get(p.assigned_to),
        "due_date": p.due_date.date().isoformat() if p.due_date else None, "overdue": overdue,
        "status": p.status, "results": p.results, "outcome": p.outcome,
        "prepared_by": names.get(p.performed_by), "prepared_by_id": p.performed_by,
        "prepared_at": p.performed_at.isoformat() if p.performed_at else None,
        "reviewed_by": names.get(p.reviewed_by), "reviewed_at": p.reviewed_at.isoformat() if p.reviewed_at else None,
        "review_comment": p.review_comment, "issue_ids": issues, "evidence_requests": requests,
    }


def _procedures_of(db: DBSession, audit_id: int) -> list[tuple[Procedure, Objective]]:
    return list(db.execute(
        select(Procedure, Objective).join(Objective, Objective.id == Procedure.objective_id)
        .where(Objective.audit_id == audit_id).order_by(Objective.id, Procedure.id)
    ).all())


def _one_out(db: DBSession, p: Procedure) -> dict:
    obj = _objective(db, p.objective_id)
    names = _names(db, [p.assigned_to, p.performed_by, p.reviewed_by])
    return _procedure_out(p, obj, names, _issue_ids(db, [p.id]).get(p.id, []),
                          _request_counts(db, "procedure", [p.id]).get(p.id, 0))


@router.get("/api/audits/{audit_id}/procedures")
def list_procedures(audit_id: int, db: DBSession = Depends(get_db), _: User = Staff) -> dict:
    """The Workplan: objectives with their risks (Project plan) and every procedure (Execute procedures)."""
    audit = _audit_or_404(db, audit_id)
    objectives = list(db.execute(select(Objective).where(Objective.audit_id == audit_id).order_by(Objective.id))
                      .scalars())
    rows = _procedures_of(db, audit_id)
    procs = [p for p, _ in rows]
    names = _names(db, [i for p in procs for i in (p.assigned_to, p.performed_by, p.reviewed_by)])
    issues = _issue_ids(db, [p.id for p in procs])
    reqs = _request_counts(db, "procedure", [p.id for p in procs])
    items = [_procedure_out(p, o, names, issues.get(p.id, []), reqs.get(p.id, 0)) for p, o in rows]
    covered = {rid for p in procs for rid in (r.id for r in p.risks)}
    risks = [r for o in objectives for r in o.risks]
    return {
        "audit_id": audit_id, "workflow": audit.workflow, "locked": audit.status.value == "Closed",
        "objectives": [{"id": o.id, "ref": o.ref, "title": o.title, "description": o.description,
                        "risks": [{"id": r.id, "ref": r.ref, "title": r.title, "rating": r.inherent_rating,
                                   "likelihood": r.likelihood, "impact": r.impact} for r in o.risks]}
                       for o in objectives],
        "items": items,
        "summary": {
            "procedures": len(items),
            "by_status": {s: sum(1 for i in items if i["status"] == s) for s in PROCEDURE_STATUSES},
            "issues_noted": sum(1 for i in items if i["outcome"] == ISSUES_NOTED),
            "overdue": sum(1 for i in items if i["overdue"]),
            "risks_without_procedures": [f"{r.ref} {r.title}" for r in risks if r.id not in covered],
        },
    }


@router.post("/api/objectives/{objective_id}/procedures", status_code=status.HTTP_201_CREATED)
def create_procedure(objective_id: int, payload: ProcedureIn, request: Request,
                     db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    obj = _objective(db, objective_id)
    audit = _audit_or_404(db, obj.audit_id)
    _ensure_open(audit)
    if audit.workflow != WORKPLAN:
        raise _conflict("This audit uses the Internal Control workflow; add controls and tests instead of procedures")
    p = Procedure(objective_id=obj.id, ref=next_reference(db, "PRC"), title=payload.title.strip(),
                  steps=payload.steps.strip(), assigned_to=_assignee(db, audit, payload.assigned_to),
                  due_date=datetime.combine(payload.due_date, time()) if payload.due_date else None,
                  status=P_NOT_STARTED, results="", review_comment="", created_by=user.id)
    db.add(p)
    db.flush()
    _set_risks(db, p, audit.id, payload.risk_ids)
    log_action(db, user_id=user.id, action=f"PROCEDURE_CREATE id={p.id} objective={obj.id}", request=request)
    _history(db, audit.id, user, f"PROCEDURE ADDED {p.ref} {p.title}", request)
    db.commit()
    return _one_out(db, p)


@router.get("/api/procedures/{procedure_id}")
def get_procedure(procedure_id: int, db: DBSession = Depends(get_db), _: User = Staff) -> dict:
    return _one_out(db, _procedure(db, procedure_id))


@router.patch("/api/procedures/{procedure_id}")
def update_procedure(procedure_id: int, payload: ProcedureUpdate, request: Request,
                     db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    """Plan fields, then Execute: results, "Were issues identified?", and the preparer sign-off (status Prepared)."""
    p = _procedure(db, procedure_id)
    audit = _audit_of_procedure(db, p)
    _ensure_open(audit)
    if p.status == P_REVIEWED:
        raise _conflict("A reviewed procedure is locked")
    sent = payload.model_dump(exclude_unset=True)
    new_status = sent.pop("status", None)
    if new_status is not None and new_status not in (P_NOT_STARTED, P_IN_PROGRESS, P_PREPARED):
        raise field_error("status", "use the reviewer sign-off to mark a procedure Reviewed")
    if p.status == P_PREPARED and sent and new_status != P_IN_PROGRESS:
        raise _conflict("The procedure is signed off as prepared; reopen it (In Progress) to change it")
    if "outcome" in sent and sent["outcome"] not in (None, NO_ISSUES, ISSUES_NOTED):
        raise field_error("outcome", f"answer {NO_ISSUES} or {ISSUES_NOTED}")
    for key in ("title", "steps", "results", "outcome"):
        if key in sent and sent[key] is not None:
            setattr(p, key, sent[key].strip() if isinstance(sent[key], str) else sent[key])
    if "outcome" in sent and sent["outcome"] is None:
        p.outcome = None
    if "assigned_to" in sent:
        p.assigned_to = _assignee(db, audit, sent["assigned_to"])
    if "due_date" in sent:
        p.due_date = datetime.combine(sent["due_date"], time()) if sent["due_date"] else None
    if sent.get("risk_ids") is not None:
        _set_risks(db, p, audit.id, sent["risk_ids"])
    if new_status == P_PREPARED:
        if not p.results.strip():
            raise field_error("results", "record the procedure results before signing off")
        if p.outcome not in (NO_ISSUES, ISSUES_NOTED):
            raise field_error("outcome", "answer 'Were issues identified?' before signing off")
        p.status, p.performed_by, p.performed_at = P_PREPARED, user.id, utcnow()
    elif new_status is not None:
        p.status = new_status
        if new_status != P_PREPARED:
            p.performed_by = p.performed_at = None
    elif sent and p.status == P_NOT_STARTED and ({"results", "outcome"} & set(sent)):
        p.status = P_IN_PROGRESS
    changed = list(sent) + ([f"status={new_status}"] if new_status else [])
    log_action(db, user_id=user.id, action=f"PROCEDURE_UPDATE id={p.id} [{', '.join(changed)}]", request=request)
    _history(db, audit.id, user, f"PROCEDURE {p.ref} UPDATED [{', '.join(changed)}]", request)
    db.commit()
    return _one_out(db, p)


@router.post("/api/procedures/{procedure_id}/review")
def review_procedure(procedure_id: int, payload: ESignRequest, request: Request,
                     db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    """Reviewer sign-off (e-signed; never the preparer). Approve -> Reviewed; Reject -> back to In Progress."""
    p = _procedure(db, procedure_id)
    audit = _audit_of_procedure(db, p)
    _ensure_open(audit)
    if p.status != P_PREPARED:
        raise _conflict("Only a procedure signed off as prepared can be reviewed")

    def _approve(_: DBSession) -> None:
        p.status, p.reviewed_by, p.reviewed_at, p.review_comment = P_REVIEWED, user.id, utcnow(), payload.comment

    entry = sign(db, record_type="procedure", record_id=p.id, user=user, password=payload.password,
                 decision=payload.decision.value, comment=payload.comment, request=request, on_approve=_approve,
                 preparer_id=p.performed_by)
    if entry.decision.value == "Reject":
        p.status, p.review_comment = P_IN_PROGRESS, payload.comment
        p.performed_by = p.performed_at = None
    log_action(db, user_id=user.id, action=f"PROCEDURE_REVIEW id={p.id} {payload.decision.value}", request=request)
    _history(db, audit.id, user, f"PROCEDURE {p.ref} REVIEW {payload.decision.value}"
             + (f": {payload.comment}" if payload.comment else ""), request)
    db.commit()
    return _one_out(db, p)


@router.post("/api/procedures/{procedure_id}/raise-issue", response_model=FindingOut,
             status_code=status.HTTP_201_CREATED)
def raise_procedure_issue(procedure_id: int, request: Request, db: DBSession = Depends(get_db),
                          user: User = Staff) -> Finding:
    """Create an issue from a procedure whose answer to 'Were issues identified?' is 'Issue(s) noted'."""
    p = _procedure(db, procedure_id)
    audit = _audit_of_procedure(db, p)
    _ensure_open(audit)
    if p.outcome != ISSUES_NOTED:
        raise _conflict("Issues are raised from a procedure whose outcome is 'Issue(s) noted'")
    bands = ["Low", "Medium", "High"]
    worst = max((r.inherent_rating for r in p.risks), key=bands.index, default="Medium")
    risks = "; ".join(f"{r.ref} {r.title}" for r in p.risks) or "no risk linked"
    finding = Finding(
        audit_id=audit.id, title=f"Issue from {p.ref}: {p.title}"[:255],
        description=f"Raised from Workplan procedure {p.ref}. Risks addressed: {risks}.",
        risk_rating=RiskRating(worst), status=FindingStatus.Open, procedure_id=p.id,
        criteria="", condition=p.results, cause="", effect=f"Exposure to: {risks}", recommendation="",
        root_cause_whys="[]", management_response="", created_by=user.id,
        issue_type=(cfg("finding_issue_types") or [None])[0],
    )
    db.add(finding)
    db.flush()
    log_action(db, user_id=user.id, action=f"ISSUE_RAISE finding={finding.id} procedure={p.id}", request=request)
    _history(db, audit.id, user, f"ISSUE RAISED #{finding.id} from {p.ref} ({finding.risk_rating.value})", request)
    db.commit()
    db.refresh(finding)
    return finding


@router.delete("/api/procedures/{procedure_id}", response_model=MessageOut)
def delete_procedure(procedure_id: int, request: Request, db: DBSession = Depends(get_db),
                     user: User = Staff) -> MessageOut:
    p = _procedure(db, procedure_id)
    audit = _audit_of_procedure(db, p)
    _ensure_open(audit)
    if p.status != P_NOT_STARTED or _issue_ids(db, [p.id]):
        raise _conflict("Work has started on this procedure; it is retained")
    ref = p.ref
    db.delete(p)
    log_action(db, user_id=user.id, action=f"PROCEDURE_DELETE id={procedure_id} ref={ref}", request=request)
    _history(db, audit.id, user, f"PROCEDURE DELETED {ref}", request)
    db.commit()
    return MessageOut(message=f"Procedure {ref} deleted")


# ==================================================================== Internal Control: walkthroughs + rounds


def _controls(db: DBSession, audit_id: int) -> list[Control]:
    return list(db.execute(
        select(Control).join(Objective, Objective.id == Control.objective_id)
        .where(Objective.audit_id == audit_id).order_by(Control.is_key.desc(), Control.id)
    ).scalars())


def _test_row(t: ControlTest, names: dict[int, str], issues: dict[int, int], requests: dict[int, int]) -> dict:
    return {
        "id": t.id, "ref": t.ref, "test_type": t.test_type.value, "round_no": t.round_no, "in_scope": t.in_scope,
        "assigned_to": t.assigned_to, "assigned_name": names.get(t.assigned_to), "procedure": t.procedure,
        "population_size": t.population_size, "sample_size": t.sample_size, "exceptions_found": t.exceptions_found,
        "results": t.results, "status": t.status.value, "conclusion": t.conclusion.value,
        "prepared_by": names.get(t.performed_by), "prepared_by_id": t.performed_by,
        "prepared_at": t.performed_at.isoformat() if t.performed_at else None,
        "reviewed_by": names.get(t.reviewed_by), "reviewed_at": t.reviewed_at.isoformat() if t.reviewed_at else None,
        "issue_id": issues.get(t.id), "evidence_requests": requests.get(t.id, 0),
    }


def _control_head(c: Control) -> dict:
    return {"control_id": c.id, "control_ref": c.ref, "control": c.title, "is_key": c.is_key,
            "frequency": c.frequency.value, "nature": c.nature.value, "control_type": c.control_type.value,
            "owner_email": c.owner_email, "test_method": c.test_method, "total_sample_size": c.total_sample_size,
            "test_steps": c.test_steps, "risks": [f"{r.ref} {r.title}" for r in c.risks],
            "effectiveness": control_effectiveness(c)}


def _lookups(db: DBSession, tests: list[ControlTest]) -> tuple[dict, dict, dict]:
    names = _names(db, [i for t in tests for i in (t.assigned_to, t.performed_by, t.reviewed_by)])
    ids = [t.id for t in tests]
    issues = dict(db.execute(select(Finding.test_id, Finding.id).where(Finding.test_id.in_(ids))).all()) if ids else {}
    return names, issues, _request_counts(db, "control_test", ids)


@router.get("/api/audits/{audit_id}/walkthroughs")
def list_walkthroughs(audit_id: int, db: DBSession = Depends(get_db), _: User = Staff) -> dict:
    """One row per control with its latest walkthrough: 'Is the control designed appropriately?'."""
    _audit_or_404(db, audit_id)
    controls = _controls(db, audit_id)
    latest = {c.id: next((t for t in reversed(c.tests) if t.test_type == TestType.Walkthrough), None)
              for c in controls}
    tests = [t for t in latest.values() if t]
    names, issues, reqs = _lookups(db, tests)
    rows = []
    for c in controls:
        t = latest[c.id]
        row = _control_head(c) | {"test": _test_row(t, names, issues, reqs) if t else None}
        row["design"] = WALKTHROUGH_LABELS[t.conclusion] if t else "Not walked through"
        rows.append(row)
    return {"audit_id": audit_id, "rows": rows, "summary": {
        "controls": len(rows),
        "designed_appropriately": sum(1 for r in rows if r["design"] == "Designed appropriately"),
        "design_failure": sum(1 for r in rows if r["design"] == "Design failure"),
        "not_walked_through": sum(1 for r in rows if r["test"] is None)}}


@router.get("/api/audits/{audit_id}/testing/{round_no}")
def testing_round(audit_id: int, round_no: int, db: DBSession = Depends(get_db), _: User = Staff) -> dict:
    """One row per control for the round: is it tested this round, by whom, sample, status, conclusion."""
    audit = _audit_or_404(db, audit_id)
    if not 1 <= round_no <= audit.testing_rounds:
        raise _not_found("Testing round")
    controls = _controls(db, audit_id)
    by_control = {c.id: next((t for t in c.tests if t.test_type == TestType.OperatingEffectiveness
                              and (t.round_no or 1) == round_no), None) for c in controls}
    tests = [t for t in by_control.values() if t]
    names, issues, reqs = _lookups(db, tests)
    rows = [_control_head(c) | {"suggested_sample": default_sample(c),
                                "test": _test_row(by_control[c.id], names, issues, reqs) if by_control[c.id] else None}
            for c in controls]
    in_scope = [r["test"] for r in rows if r["test"] and r["test"]["in_scope"]]
    labels = ROUND_LABELS.get(audit.testing_rounds, ["Testing"])
    return {"audit_id": audit_id, "round_no": round_no, "round_label": labels[round_no - 1], "round_labels": labels,
            "rows": rows, "summary": {
                "controls": len(rows), "key_controls": sum(1 for r in rows if r["is_key"]),
                "not_prepared": sum(1 for r in rows if r["is_key"] and r["test"] is None),
                "in_scope": len(in_scope),
                "by_status": {s.value: sum(1 for t in in_scope if t["status"] == s.value) for s in TestStatus},
                "effective": sum(1 for t in in_scope if t["conclusion"] == "Effective"),
                "ineffective": sum(1 for t in in_scope if t["conclusion"] == "Ineffective")}}


@router.post("/api/audits/{audit_id}/testing/{round_no}/prepare")
def prepare_round(audit_id: int, round_no: int, request: Request, db: DBSession = Depends(get_db),
                  user: User = Staff) -> dict:
    """Create the round's test for every key control that has none (sample from the test plan or configuration)."""
    audit = _audit_or_404(db, audit_id)
    _ensure_open(audit)
    if audit.workflow != INTERNAL_CONTROL:
        raise _conflict("Testing rounds belong to the Internal Control workflow")
    if not 1 <= round_no <= audit.testing_rounds:
        raise _not_found("Testing round")
    created = []
    for c in _controls(db, audit_id):
        if not c.is_key or any(t.test_type == TestType.OperatingEffectiveness and (t.round_no or 1) == round_no
                               for t in c.tests):
            continue
        t = ControlTest(control_id=c.id, ref=next_reference(db, "TST"), test_type=TestType.OperatingEffectiveness,
                        procedure=c.test_steps or "", round_no=round_no, sample_size=default_sample(c),
                        created_by=user.id)
        db.add(t)
        created.append(c.ref)
    label = ROUND_LABELS.get(audit.testing_rounds, ["Testing"])[round_no - 1]
    if created:
        log_action(db, user_id=user.id, action=f"ROUND_PREPARE audit={audit.id} round={round_no} n={len(created)}",
                   request=request)
        _history(db, audit.id, user, f"TESTING ROUND {label}: {len(created)} key control test(s) prepared", request)
        db.commit()
    return {"round_no": round_no, "round_label": label, "created": len(created), "controls": created}


# Members of the engagement team, for the "Assigned" pickers on procedures and tests.
@router.get("/api/audits/{audit_id}/assignees")
def assignees(audit_id: int, db: DBSession = Depends(get_db), _: User = Staff) -> list[dict]:
    _audit_or_404(db, audit_id)
    rows = db.execute(select(AuditTeamMember.user_id, AuditTeamMember.team_role, User.full_name, User.username)
                      .join(User, User.id == AuditTeamMember.user_id)
                      .where(AuditTeamMember.audit_id == audit_id).order_by(User.full_name)).all()
    return [{"id": r.user_id, "name": r.full_name or r.username, "team_role": r.team_role} for r in rows]


def ensure_workflow(audit: Audit, wanted: str) -> None:
    if audit.workflow != wanted:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"This audit uses the {audit.workflow} workflow")
