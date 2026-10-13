"""Risk & control matrix routes for an audit project.

Objectives -> risks and controls (mapped many-to-many) -> control tests
(walkthrough, test of design, test of operating effectiveness, with sampling
and an e-signed reviewer sign-off) -> issues (findings) -> actions (CAPA).

Only Admins and Auditors can read or change the matrix. Everything is locked
once the audit is closed, and nothing that carries test evidence can be
deleted.
"""

from __future__ import annotations

import json
import random
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session as DBSession

from app.core.approvalsvc import sign
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_role
from app.core.enums import (
    AuditStatus,
    CapaStatus,
    ControlFrequency,
    ControlNature,
    FindingStatus,
    RiskRating,
    Role,
    Severity,
    TestConclusion,
    TestStatus,
    TestType,
    utcnow,
)
from app.core.errors import FieldValidationError, field_error
from app.core.history import log_record_history
from app.core.refs import next_reference
from app.core.schemas import ESignRequest, MessageOut
from app.core.tasksvc import auto_task_for_record
from app.modules.audits.lifecycle import default_due_date
from app.modules.audits.models import Audit, Finding
from app.modules.audits.schemas import FindingOut
from app.modules.capa.models import Capa
from app.modules.capa.schemas import CapaOut
from app.modules.rcm.models import Control, ControlTest, Objective, Risk, RiskControl
from app.modules.rcm.schemas import (
    ControlIn,
    ControlOut,
    ControlUpdate,
    ObjectiveIn,
    ObjectiveOut,
    ObjectiveUpdate,
    RcmOut,
    RcmSummary,
    RiskIn,
    RiskMapping,
    RiskOut,
    RiskUpdate,
    SampleRecommendation,
    SampleRequest,
    TestIn,
    TestOut,
    TestUpdate,
)
from app.modules.users.models import User

router = APIRouter(tags=["risk-control-matrix"])

Staff = Depends(require_role(Role.Admin, Role.Auditor))

_BANDS = ["Low", "Medium", "High"]


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


# ---------------------------------------------------------------- lookups + locks


def _audit_or_404(db: DBSession, audit_id: int) -> Audit:
    audit = db.get(Audit, audit_id)
    if audit is None:
        raise _not_found("Audit")
    return audit


def _ensure_open(audit: Audit) -> None:
    if audit.status == AuditStatus.Closed:
        raise _conflict("The audit is closed; its risk & control matrix is locked")


def _objective(db: DBSession, objective_id: int) -> Objective:
    obj = db.get(Objective, objective_id)
    if obj is None:
        raise _not_found("Objective")
    return obj


def _risk(db: DBSession, risk_id: int) -> Risk:
    risk = db.get(Risk, risk_id)
    if risk is None:
        raise _not_found("Risk")
    return risk


def _control(db: DBSession, control_id: int) -> Control:
    control = db.get(Control, control_id)
    if control is None:
        raise _not_found("Control")
    return control


def _test(db: DBSession, test_id: int) -> ControlTest:
    test = db.get(ControlTest, test_id)
    if test is None:
        raise _not_found("Control test")
    return test


def _audit_of(db: DBSession, objective: Objective) -> Audit:
    return _audit_or_404(db, objective.audit_id)


def _history(db: DBSession, audit_id: int, user: User, action: str, request: Request) -> None:
    log_record_history(db, record_type="audit", record_id=audit_id, user_id=user.id, action=action, request=request)


# ---------------------------------------------------------------- derived ratings


def control_effectiveness(control: Control) -> str:
    """Effectiveness from the control's completed tests (latest evidence wins)."""
    done = [t for t in control.tests if t.status in (TestStatus.Completed, TestStatus.Reviewed)]
    if any(t.conclusion == TestConclusion.Ineffective for t in done):
        return "Ineffective"
    if any(t.test_type == TestType.OperatingEffectiveness and t.conclusion == TestConclusion.Effective for t in done):
        return "Effective"
    if any(t.conclusion == TestConclusion.Effective for t in done):
        return "Design Effective"
    return "Not Tested"


def residual_rating(risk: Risk) -> str:
    """Inherent rating reduced one band when every mapped control is proven effective."""
    inherent = risk.inherent_rating
    states = [control_effectiveness(c) for c in risk.controls]
    if states and all(s == "Effective" for s in states):
        return _BANDS[max(0, _BANDS.index(inherent) - 1)]
    return inherent


def recommended_sample(frequency: ControlFrequency, nature: ControlNature, test_type: TestType) -> tuple[int, str]:
    """Sample-size guidance commonly used for tests of controls (auditor judgement applies)."""
    if test_type in (TestType.Walkthrough, TestType.Design):
        return 1, "Walkthroughs and tests of design examine one instance of the control"
    if nature == ControlNature.Automated:
        return 1, "Automated control: test one instance, relying on effective IT general controls"
    table = {
        ControlFrequency.Annual: 1,
        ControlFrequency.Quarterly: 2,
        ControlFrequency.Monthly: 3,
        ControlFrequency.Weekly: 10,
        ControlFrequency.Daily: 25,
        ControlFrequency.MultipleDaily: 40,
        ControlFrequency.AdHoc: 25,
    }
    return table[frequency], f"{frequency.value} manual control (common guidance range for tests of controls)"


def _risk_out(risk: Risk) -> RiskOut:
    out = RiskOut.model_validate(risk)
    out.control_ids = [c.id for c in risk.controls]
    out.residual_rating = residual_rating(risk)
    return out


def _control_out(control: Control) -> ControlOut:
    out = ControlOut.model_validate(control)
    out.risk_ids = [r.id for r in control.risks]
    out.tests = [TestOut.model_validate(t) for t in control.tests]
    out.effectiveness = control_effectiveness(control)
    return out


def _objective_out(obj: Objective) -> ObjectiveOut:
    out = ObjectiveOut.model_validate(obj)
    out.risks = [_risk_out(r) for r in obj.risks]
    out.controls = [_control_out(c) for c in obj.controls]
    return out


def _objectives(db: DBSession, audit_id: int) -> list[Objective]:
    return list(db.execute(select(Objective).where(Objective.audit_id == audit_id).order_by(Objective.id)).scalars())


# ---------------------------------------------------------------- matrix


@router.get("/api/audits/{audit_id}/rcm", response_model=RcmOut)
def get_rcm(audit_id: int, db: DBSession = Depends(get_db), _: User = Staff) -> RcmOut:
    audit = _audit_or_404(db, audit_id)
    objectives = _objectives(db, audit_id)
    risks = [r for o in objectives for r in o.risks]
    controls = [c for o in objectives for c in o.controls]
    tests = [t for c in controls for t in c.tests]
    open_issues = db.execute(
        select(func.count())
        .select_from(Finding)
        .where(Finding.audit_id == audit_id, Finding.status != FindingStatus.Closed)
    ).scalar_one()
    effectiveness = Counter(control_effectiveness(c) for c in controls)
    summary = RcmSummary(
        objectives=len(objectives),
        risks=len(risks),
        risks_by_rating={band: sum(1 for r in risks if r.inherent_rating == band) for band in _BANDS},
        risks_without_controls=[f"{r.ref} {r.title}" for r in risks if not r.controls],
        controls=len(controls),
        key_controls=sum(1 for c in controls if c.is_key),
        controls_by_effectiveness={
            k: effectiveness.get(k, 0) for k in ("Effective", "Design Effective", "Ineffective", "Not Tested")
        },
        key_controls_untested=[
            f"{c.ref} {c.title}" for c in controls if c.is_key and control_effectiveness(c) == "Not Tested"
        ],
        tests=len(tests),
        tests_awaiting_review=sum(1 for t in tests if t.status == TestStatus.Completed),
        open_issues=open_issues,
    )
    return RcmOut(
        audit_id=audit_id,
        locked=audit.status == AuditStatus.Closed,
        objectives=[_objective_out(o) for o in objectives],
        summary=summary,
    )


# ---------------------------------------------------------------- objectives


@router.post("/api/audits/{audit_id}/objectives", response_model=ObjectiveOut, status_code=status.HTTP_201_CREATED)
def create_objective(
    audit_id: int, payload: ObjectiveIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> ObjectiveOut:
    _ensure_open(_audit_or_404(db, audit_id))
    obj = Objective(audit_id=audit_id, ref=next_reference(db, "OBJ"), created_by=user.id, **payload.model_dump())
    db.add(obj)
    db.flush()
    log_action(db, user_id=user.id, action=f"OBJECTIVE_CREATE id={obj.id} audit={audit_id}", request=request)
    _history(db, audit_id, user, f"OBJECTIVE ADDED {obj.ref} {obj.title}", request)
    db.commit()
    db.refresh(obj)
    return _objective_out(obj)


@router.patch("/api/objectives/{objective_id}", response_model=ObjectiveOut)
def update_objective(
    objective_id: int, payload: ObjectiveUpdate, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> ObjectiveOut:
    obj = _objective(db, objective_id)
    _ensure_open(_audit_of(db, obj))
    changes = payload.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(obj, key, value)
    log_action(db, user_id=user.id, action=f"OBJECTIVE_UPDATE id={obj.id} [{', '.join(changes)}]", request=request)
    _history(db, obj.audit_id, user, f"OBJECTIVE UPDATED {obj.ref} [{', '.join(changes)}]", request)
    db.commit()
    db.refresh(obj)
    return _objective_out(obj)


def _has_evidence(db: DBSession, controls: list[Control]) -> bool:
    ids = [c.id for c in controls]
    if not ids:
        return False
    tested = any(t.status != TestStatus.NotStarted for c in controls for t in c.tests)
    issues = db.execute(select(func.count()).select_from(Finding).where(Finding.control_id.in_(ids))).scalar_one()
    return tested or bool(issues)


@router.delete("/api/objectives/{objective_id}", response_model=MessageOut)
def delete_objective(
    objective_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> MessageOut:
    obj = _objective(db, objective_id)
    _ensure_open(_audit_of(db, obj))
    if _has_evidence(db, obj.controls):
        raise _conflict("This objective has controls with test work or issues; it is retained")
    audit_id, ref = obj.audit_id, obj.ref
    for control in obj.controls:
        db.delete(control)
    for risk in obj.risks:
        db.delete(risk)
    db.delete(obj)
    log_action(db, user_id=user.id, action=f"OBJECTIVE_DELETE id={objective_id} ref={ref}", request=request)
    _history(db, audit_id, user, f"OBJECTIVE DELETED {ref}", request)
    db.commit()
    return MessageOut(message=f"Objective {ref} deleted")


# ---------------------------------------------------------------- risks


@router.post("/api/objectives/{objective_id}/risks", response_model=RiskOut, status_code=status.HTTP_201_CREATED)
def create_risk(
    objective_id: int, payload: RiskIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> RiskOut:
    obj = _objective(db, objective_id)
    _ensure_open(_audit_of(db, obj))
    risk = Risk(objective_id=obj.id, ref=next_reference(db, "RSK"), created_by=user.id, **payload.model_dump())
    db.add(risk)
    db.flush()
    log_action(db, user_id=user.id, action=f"RISK_CREATE id={risk.id} objective={obj.id}", request=request)
    _history(db, obj.audit_id, user, f"RISK ADDED {risk.ref} {risk.title} ({risk.inherent_rating})", request)
    db.commit()
    db.refresh(risk)
    return _risk_out(risk)


@router.patch("/api/risks/{risk_id}", response_model=RiskOut)
def update_risk(
    risk_id: int, payload: RiskUpdate, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> RiskOut:
    risk = _risk(db, risk_id)
    _ensure_open(_audit_of(db, risk.objective))
    changes = payload.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(risk, key, value)
    log_action(db, user_id=user.id, action=f"RISK_UPDATE id={risk.id} [{', '.join(changes)}]", request=request)
    _history(db, risk.objective.audit_id, user, f"RISK UPDATED {risk.ref} [{', '.join(changes)}]", request)
    db.commit()
    db.refresh(risk)
    return _risk_out(risk)


@router.delete("/api/risks/{risk_id}", response_model=MessageOut)
def delete_risk(risk_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> MessageOut:
    risk = _risk(db, risk_id)
    _ensure_open(_audit_of(db, risk.objective))
    if _has_evidence(db, risk.controls):
        raise _conflict("This risk is mitigated by tested controls; it is retained")
    audit_id, ref = risk.objective.audit_id, risk.ref
    db.delete(risk)
    log_action(db, user_id=user.id, action=f"RISK_DELETE id={risk_id} ref={ref}", request=request)
    _history(db, audit_id, user, f"RISK DELETED {ref}", request)
    db.commit()
    return MessageOut(message=f"Risk {ref} deleted")


# ---------------------------------------------------------------- controls


def _set_mapping(db: DBSession, control: Control, risk_ids: list[int]) -> None:
    """Map ``control`` to the given risks, which must belong to the same audit."""
    audit_id = control.objective.audit_id
    wanted = set(risk_ids)
    if wanted:
        found = db.execute(
            select(Risk.id).join(Objective, Objective.id == Risk.objective_id).where(
                Risk.id.in_(wanted), Objective.audit_id == audit_id
            )
        ).scalars().all()
        missing = wanted - set(found)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Risks {sorted(missing)} do not belong to this audit",
            )
    db.execute(delete(RiskControl).where(RiskControl.control_id == control.id))
    if wanted:
        db.execute(insert(RiskControl), [{"risk_id": r, "control_id": control.id} for r in sorted(wanted)])
    db.flush()
    db.expire(control, ["risks"])


@router.post(
    "/api/objectives/{objective_id}/controls", response_model=ControlOut, status_code=status.HTTP_201_CREATED
)
def create_control(
    objective_id: int, payload: ControlIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> ControlOut:
    obj = _objective(db, objective_id)
    _ensure_open(_audit_of(db, obj))
    data = payload.model_dump(exclude={"risk_ids"})
    control = Control(objective_id=obj.id, ref=next_reference(db, "CTL"), created_by=user.id, **data)
    db.add(control)
    db.flush()
    _set_mapping(db, control, payload.risk_ids)
    log_action(db, user_id=user.id, action=f"CONTROL_CREATE id={control.id} objective={obj.id}", request=request)
    _history(db, obj.audit_id, user, f"CONTROL ADDED {control.ref} {control.title}", request)
    db.commit()
    db.refresh(control)
    return _control_out(control)


@router.patch("/api/controls/{control_id}", response_model=ControlOut)
def update_control(
    control_id: int, payload: ControlUpdate, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> ControlOut:
    control = _control(db, control_id)
    _ensure_open(_audit_of(db, control.objective))
    changes = payload.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(control, key, value)
    log_action(db, user_id=user.id, action=f"CONTROL_UPDATE id={control.id} [{', '.join(changes)}]", request=request)
    _history(db, control.objective.audit_id, user, f"CONTROL UPDATED {control.ref} [{', '.join(changes)}]", request)
    db.commit()
    db.refresh(control)
    return _control_out(control)


@router.put("/api/controls/{control_id}/risks", response_model=ControlOut)
def map_control_risks(
    control_id: int, payload: RiskMapping, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> ControlOut:
    control = _control(db, control_id)
    _ensure_open(_audit_of(db, control.objective))
    _set_mapping(db, control, payload.risk_ids)
    log_action(db, user_id=user.id, action=f"CONTROL_MAP id={control.id} risks={payload.risk_ids}", request=request)
    _history(db, control.objective.audit_id, user, f"CONTROL {control.ref} MAPPED TO RISKS {payload.risk_ids}", request)
    db.commit()
    db.refresh(control)
    return _control_out(control)


@router.delete("/api/controls/{control_id}", response_model=MessageOut)
def delete_control(
    control_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> MessageOut:
    control = _control(db, control_id)
    _ensure_open(_audit_of(db, control.objective))
    if _has_evidence(db, [control]):
        raise _conflict("This control has test work or issues; it is retained")
    audit_id, ref = control.objective.audit_id, control.ref
    db.delete(control)
    log_action(db, user_id=user.id, action=f"CONTROL_DELETE id={control_id} ref={ref}", request=request)
    _history(db, audit_id, user, f"CONTROL DELETED {ref}", request)
    db.commit()
    return MessageOut(message=f"Control {ref} deleted")


# ---------------------------------------------------------------- tests


@router.post("/api/controls/{control_id}/tests", response_model=TestOut, status_code=status.HTTP_201_CREATED)
def create_test(
    control_id: int, payload: TestIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> ControlTest:
    control = _control(db, control_id)
    _ensure_open(_audit_of(db, control.objective))
    test = ControlTest(
        control_id=control.id,
        ref=next_reference(db, "TST"),
        test_type=payload.test_type,
        procedure=payload.procedure,
        created_by=user.id,
    )
    db.add(test)
    db.flush()
    log_action(db, user_id=user.id, action=f"TEST_CREATE id={test.id} control={control.id}", request=request)
    label = f"TEST ADDED {test.ref} ({test.test_type.value}) on {control.ref}"
    _history(db, control.objective.audit_id, user, label, request)
    db.commit()
    db.refresh(test)
    return test


@router.get("/api/control-tests/{test_id}", response_model=TestOut)
def get_test(test_id: int, db: DBSession = Depends(get_db), _: User = Staff) -> ControlTest:
    return _test(db, test_id)


@router.get("/api/control-tests/{test_id}/sample-recommendation", response_model=SampleRecommendation)
def sample_recommendation(test_id: int, db: DBSession = Depends(get_db), _: User = Staff) -> SampleRecommendation:
    test = _test(db, test_id)
    control = test.control
    size, basis = recommended_sample(control.frequency, control.nature, test.test_type)
    return SampleRecommendation(
        frequency=control.frequency.value,
        nature=control.nature.value,
        test_type=test.test_type.value,
        recommended_size=size,
        basis=basis,
    )


@router.post("/api/control-tests/{test_id}/sample", response_model=TestOut)
def draw_sample(
    test_id: int, payload: SampleRequest, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> ControlTest:
    """Select sample items at random from a population numbered 1..N (reproducible via the seed)."""
    test = _test(db, test_id)
    _ensure_open(_audit_of(db, test.control.objective))
    if test.status in (TestStatus.Completed, TestStatus.Reviewed):
        raise _conflict("The test is completed; its sample is fixed")
    recommended, _ = recommended_sample(test.control.frequency, test.control.nature, test.test_type)
    size = min(payload.sample_size or recommended, payload.population_size)
    seed = payload.seed if payload.seed is not None else random.SystemRandom().randrange(1, 2**31 - 1)
    items = sorted(random.Random(seed).sample(range(1, payload.population_size + 1), size))
    test.population_size = payload.population_size
    test.sample_size = size
    test.sample_seed = seed
    test.sample_items = ", ".join(str(i) for i in items)
    if test.status == TestStatus.NotStarted:
        test.status = TestStatus.InProgress
    log_action(
        db,
        user_id=user.id,
        action=f"TEST_SAMPLE id={test.id} population={payload.population_size} size={size} seed={seed}",
        request=request,
    )
    _history(
        db,
        test.control.objective.audit_id,
        user,
        f"SAMPLE DRAWN {test.ref}: {size} of {payload.population_size} (seed {seed})",
        request,
    )
    db.commit()
    db.refresh(test)
    return test


@router.patch("/api/control-tests/{test_id}", response_model=TestOut)
def update_test(
    test_id: int, payload: TestUpdate, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> ControlTest:
    test = _test(db, test_id)
    _ensure_open(_audit_of(db, test.control.objective))
    if test.status == TestStatus.Reviewed:
        raise _conflict("A reviewed test is locked")
    if payload.status == TestStatus.Reviewed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Use the reviewer sign-off to mark a test Reviewed"
        )
    changes = payload.model_dump(exclude_none=True)
    for key, value in changes.items():
        if key != "status":
            setattr(test, key, value)
    _check_test_numbers(test)
    new_status = payload.status
    if new_status == TestStatus.Completed:
        if test.conclusion == TestConclusion.NotTested:
            raise field_error("conclusion", "record a conclusion before completing the test")
        if test.conclusion == TestConclusion.Ineffective and not test.results.strip():
            raise field_error("results", "describe the exceptions found before completing")
        test.performed_by = user.id
        test.performed_at = utcnow()
    if new_status is not None:
        test.status = new_status
    elif changes and test.status == TestStatus.NotStarted:
        test.status = TestStatus.InProgress
    log_action(db, user_id=user.id, action=f"TEST_UPDATE id={test.id} [{', '.join(changes)}]", request=request)
    _history(db, test.control.objective.audit_id, user, f"TEST UPDATED {test.ref} [{', '.join(changes)}]", request)
    db.commit()
    db.refresh(test)
    return test


def _check_test_numbers(test: ControlTest) -> None:
    """Accuracy rules: sample <= population, exceptions <= sample."""
    errors = []
    if test.population_size is not None and test.sample_size is not None and test.sample_size > test.population_size:
        errors.append({"field": "sample_size", "message": "cannot exceed the population size"})
    limit = test.sample_size if test.sample_size is not None else test.population_size
    if limit is not None and test.exceptions_found > limit:
        errors.append({"field": "exceptions_found", "message": f"cannot exceed the number of items tested ({limit})"})
    if errors:
        raise FieldValidationError(errors)


@router.post("/api/control-tests/{test_id}/review", response_model=TestOut)
def review_test(
    test_id: int, payload: ESignRequest, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> ControlTest:
    """Reviewer sign-off (e-signed). Approve -> Reviewed; Reject -> back to In Progress."""
    test = _test(db, test_id)
    _ensure_open(_audit_of(db, test.control.objective))
    if test.status != TestStatus.Completed:
        raise _conflict("Only a completed test can be reviewed")

    def _on_approve(_: DBSession) -> None:
        test.status = TestStatus.Reviewed
        test.reviewed_by = user.id
        test.reviewed_at = utcnow()
        test.review_comment = payload.comment

    entry = sign(
        db,
        record_type="control_test",
        record_id=test.id,
        user=user,
        password=payload.password,
        decision=payload.decision.value,
        comment=payload.comment,
        request=request,
        on_approve=_on_approve,
        preparer_id=test.performed_by,
    )
    if entry.decision.value == "Reject":
        test.status = TestStatus.InProgress
        test.review_comment = payload.comment
    log_action(db, user_id=user.id, action=f"TEST_REVIEW id={test.id} {payload.decision.value}", request=request)
    _history(
        db,
        test.control.objective.audit_id,
        user,
        f"TEST {test.ref} REVIEW {payload.decision.value}" + (f": {payload.comment}" if payload.comment else ""),
        request,
    )
    db.commit()
    db.refresh(test)
    return test


@router.delete("/api/control-tests/{test_id}", response_model=MessageOut)
def delete_test(test_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> MessageOut:
    test = _test(db, test_id)
    _ensure_open(_audit_of(db, test.control.objective))
    if test.status != TestStatus.NotStarted:
        raise _conflict("Test work has started; the test is retained")
    audit_id, ref = test.control.objective.audit_id, test.ref
    db.delete(test)
    log_action(db, user_id=user.id, action=f"TEST_DELETE id={test_id} ref={ref}", request=request)
    _history(db, audit_id, user, f"TEST DELETED {ref}", request)
    db.commit()
    return MessageOut(message=f"Test {ref} deleted")


# ---------------------------------------------------------------- issues + actions


def _rating_for(control: Control) -> RiskRating:
    ratings = [r.inherent_rating for r in control.risks] or ["Medium"]
    worst = max(ratings, key=_BANDS.index)
    return RiskRating(worst)


@router.post("/api/control-tests/{test_id}/raise-issue", response_model=FindingOut, status_code=status.HTTP_201_CREATED)
def raise_issue(test_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> Finding:
    """Create an issue (finding) from an ineffective test, pre-filled from the matrix."""
    test = _test(db, test_id)
    control = test.control
    audit = _audit_of(db, control.objective)
    _ensure_open(audit)
    if test.conclusion != TestConclusion.Ineffective or test.status not in (TestStatus.Completed, TestStatus.Reviewed):
        raise _conflict("Issues are raised from a completed test concluded Ineffective")
    existing = db.execute(select(Finding).where(Finding.test_id == test.id)).scalar_one_or_none()
    if existing is not None:
        raise _conflict(f"Issue #{existing.id} was already raised from this test")
    risks = "; ".join(f"{r.ref} {r.title}" for r in control.risks) or "unmapped"
    finding = Finding(
        audit_id=audit.id,
        title=f"Control deficiency: {control.title}",
        description=f"Raised from {test.ref} ({test.test_type.value}) on {control.ref}. Risks affected: {risks}.",
        risk_rating=_rating_for(control),
        status=FindingStatus.Open,
        assigned_owner_email=control.owner_email,
        control_id=control.id,
        test_id=test.id,
        criteria=control.description or f"{control.title} operates as designed ({control.frequency.value}).",
        condition=(
            f"{test.exceptions_found} exception(s) in a sample of {test.sample_size or '-'}"
            f" from {test.population_size or '-'} items. {test.results}"
        ).strip(),
        cause="",
        effect=f"Exposure to: {risks}",
        recommendation="",
        root_cause_whys="[]",
        management_response="",
        created_by=user.id,
    )
    db.add(finding)
    db.flush()
    log_action(db, user_id=user.id, action=f"ISSUE_RAISE finding={finding.id} test={test.id}", request=request)
    _history(db, audit.id, user, f"ISSUE RAISED #{finding.id} from {test.ref} ({finding.risk_rating.value})", request)
    db.commit()
    db.refresh(finding)
    return finding


_SEVERITY = {RiskRating.Low: Severity.Low, RiskRating.Medium: Severity.Medium, RiskRating.High: Severity.High}


@router.post("/api/findings/{finding_id}/raise-action", response_model=CapaOut, status_code=status.HTTP_201_CREATED)
def raise_action(finding_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> Capa:
    """Create the corrective action (CAPA) that remediates an issue."""
    finding = db.get(Finding, finding_id)
    if finding is None:
        raise _not_found("Finding")
    existing = db.execute(
        select(Capa).where(Capa.source_type == "finding", Capa.source_id == finding.id)
    ).scalar_one_or_none()
    if existing is not None:
        raise _conflict(f"Action {existing.capa_ref} already exists for this issue")
    whys = json.loads(finding.root_cause_whys or "[]") if (finding.root_cause_whys or "").startswith("[") else []
    root_cause = finding.cause or ""
    if whys:
        root_cause = (root_cause + "\n" if root_cause else "") + "\n".join(
            f"Why {i}: {w}" for i, w in enumerate(whys, start=1)
        )
    capa = Capa(
        capa_ref=next_reference(db, "CAPA"),
        title=f"Remediate: {finding.title}"[:255],
        description=finding.condition or finding.description,
        root_cause=root_cause,
        corrective_action=finding.recommendation or "",
        preventive_action="",
        effectiveness_check="Re-test the control after remediation.",
        severity=_SEVERITY[finding.risk_rating],
        status=CapaStatus.Open,
        owner_email=finding.assigned_owner_email,
        due_date=default_due_date(_SEVERITY[finding.risk_rating]),
        source_type="finding",
        source_id=finding.id,
        created_by=user.id,
    )
    db.add(capa)
    db.flush()
    if finding.status == FindingStatus.Open:
        finding.status = FindingStatus.Remediating
    auto_task_for_record(db, record_type="capa", record=capa, action="Action CAPA", assignor_id=user.id)
    log_action(db, user_id=user.id, action=f"ACTION_RAISE capa={capa.id} finding={finding.id}", request=request)
    _history(db, finding.audit_id, user, f"ACTION {capa.capa_ref} RAISED for issue #{finding.id}", request)
    log_record_history(
        db,
        record_type="capa",
        record_id=capa.id,
        user_id=user.id,
        action=f"CREATED from issue #{finding.id} ({finding.title})",
        request=request,
    )
    db.commit()
    db.refresh(capa)
    return capa
