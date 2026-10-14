"""Audit programme library (Audit Administrator) and applying a programme to an audit's RCM."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session as DBSession

from app.core.appconfig import cfg
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import ensure_perm, require_perm, require_role
from app.core.enums import AuditStatus, ControlType, Role, TestType
from app.core.errors import field_error
from app.core.history import log_record_history
from app.core.refs import next_reference
from app.domains.audit.audits.models import Audit
from app.domains.audit.programs.models import AuditProgram
from app.domains.audit.rcm.models import Control, ControlTest, Objective, Risk, RiskControl
from app.platform.users.models import User

router = APIRouter(tags=["audit programmes"])
Staff = Depends(require_role(Role.Admin, Role.Auditor))
Editor = Depends(require_perm("method.programs"))


class Step(BaseModel):
    objective: str = Field(min_length=2, max_length=255)
    risk: str = Field(min_length=2, max_length=255)
    likelihood: int = Field(3, ge=1, le=5)
    impact: int = Field(3, ge=1, le=5)
    control: str = Field(min_length=2, max_length=255)
    control_type: str = ControlType.Preventive.value
    test_type: str = TestType.OperatingEffectiveness.value
    procedure: str = Field("", max_length=4000)

    @field_validator("control_type")
    @classmethod
    def _ct(cls, v: str) -> str:
        if v not in {c.value for c in ControlType}:
            raise ValueError(f"must be one of {', '.join(c.value for c in ControlType)}")
        return v

    @field_validator("test_type")
    @classmethod
    def _tt(cls, v: str) -> str:
        if v not in {t.value for t in TestType}:
            raise ValueError(f"must be one of {', '.join(t.value for t in TestType)}")
        return v


class ProgramIn(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    audit_type: str | None = Field(None, max_length=60)
    description: str = Field("", max_length=8000)
    steps: list[Step] = Field(default_factory=list, max_length=300)


class ProgramUpdate(BaseModel):
    name: str | None = Field(None, min_length=3, max_length=255)
    audit_type: str | None = Field(None, max_length=60)
    description: str | None = Field(None, max_length=8000)
    steps: list[Step] | None = Field(None, max_length=300)
    status: str | None = None


class ProgramOut(BaseModel):
    id: int
    prog_ref: str
    name: str
    audit_type: str | None
    description: str
    steps: list[dict]
    step_count: int
    status: str
    times_used: int


def _out(p: AuditProgram) -> ProgramOut:
    steps = p.step_list
    return ProgramOut(id=p.id, prog_ref=p.prog_ref, name=p.name, audit_type=p.audit_type, description=p.description,
                      steps=steps, step_count=len(steps), status=p.status, times_used=p.times_used)


def _check_type(value: str | None) -> str | None:
    value = (value or "").strip() or None
    if value and value not in cfg("audit_types"):
        raise field_error("audit_type", "is not one of the configured audit types")
    return value


def _get(db: DBSession, program_id: int) -> AuditProgram:
    p = db.get(AuditProgram, program_id)
    if p is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Programme not found")
    return p


@router.get("/api/audit-programs", response_model=list[ProgramOut])
def list_programs(q: str | None = Query(None, max_length=100), audit_type: str | None = None,
                  include_retired: bool = False, db: DBSession = Depends(get_db),
                  user: User = Staff) -> list[ProgramOut]:
    stmt = select(AuditProgram).order_by(AuditProgram.name)
    if not include_retired:
        stmt = stmt.where(AuditProgram.status == "Active")
    if audit_type:
        stmt = stmt.where(AuditProgram.audit_type == audit_type)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(AuditProgram.name.like(like), AuditProgram.description.like(like),
                              AuditProgram.prog_ref.like(like)))
    return [_out(p) for p in db.execute(stmt).scalars()]


@router.get("/api/audit-programs/{program_id}", response_model=ProgramOut)
def get_program(program_id: int, db: DBSession = Depends(get_db), user: User = Staff) -> ProgramOut:
    return _out(_get(db, program_id))


@router.post("/api/audit-programs", response_model=ProgramOut, status_code=status.HTTP_201_CREATED)
def create_program(payload: ProgramIn, request: Request, db: DBSession = Depends(get_db),
                   user: User = Editor) -> ProgramOut:
    p = AuditProgram(prog_ref=next_reference(db, "PRG"), name=payload.name.strip(),
                     audit_type=_check_type(payload.audit_type), description=payload.description,
                     steps=json.dumps([s.model_dump() for s in payload.steps]), created_by=user.id)
    db.add(p)
    db.flush()
    log_action(db, user_id=user.id, action=f"PROGRAM_CREATE {p.prog_ref}", request=request)
    db.commit()
    return _out(p)


@router.patch("/api/audit-programs/{program_id}", response_model=ProgramOut)
def update_program(program_id: int, payload: ProgramUpdate, request: Request, db: DBSession = Depends(get_db),
                   user: User = Editor) -> ProgramOut:
    p = _get(db, program_id)
    fields = payload.model_fields_set
    if payload.name is not None:
        p.name = payload.name.strip()
    if "audit_type" in fields:
        p.audit_type = _check_type(payload.audit_type)
    if payload.description is not None:
        p.description = payload.description
    if payload.steps is not None:
        p.steps = json.dumps([s.model_dump() for s in payload.steps])
    if payload.status is not None:
        if payload.status not in ("Active", "Retired"):
            raise field_error("status", "must be Active or Retired")
        p.status = payload.status
    log_action(db, user_id=user.id, action=f"PROGRAM_UPDATE {p.prog_ref} [{', '.join(sorted(fields))}]",
               request=request)
    db.commit()
    return _out(p)


@router.post("/api/audits/{audit_id}/apply-program/{program_id}")
def apply_program(audit_id: int, program_id: int, request: Request, db: DBSession = Depends(get_db),
                  user: User = Staff) -> dict:
    """Copy a programme's objectives, risks, controls and test steps into the audit's risk & control matrix."""
    ensure_perm(user, "audit.plan", "audit.fieldwork")
    audit = db.get(Audit, audit_id)
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit not found")
    if audit.status == AuditStatus.Closed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The audit is closed")
    program = _get(db, program_id)
    if program.status != "Active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This programme is retired")
    steps = [Step(**s) for s in program.step_list]
    if not steps:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The programme has no steps")
    objectives = {o.title.lower(): o for o in db.execute(select(Objective).where(Objective.audit_id == audit_id))
                  .scalars()}
    counts = {"objectives": 0, "risks": 0, "controls": 0, "tests": 0}
    risks: dict[tuple[int, str], Risk] = {}
    controls: dict[tuple[int, str], Control] = {}
    for s in steps:
        obj = objectives.get(s.objective.lower())
        if obj is None:
            obj = Objective(audit_id=audit_id, ref=next_reference(db, "OBJ"), title=s.objective, created_by=user.id)
            db.add(obj)
            db.flush()
            objectives[s.objective.lower()] = obj
            counts["objectives"] += 1
        rk = risks.get((obj.id, s.risk.lower()))
        if rk is None:
            rk = Risk(objective_id=obj.id, ref=next_reference(db, "RSK"), title=s.risk, likelihood=s.likelihood,
                      impact=s.impact, created_by=user.id)
            db.add(rk)
            db.flush()
            risks[(obj.id, s.risk.lower())] = rk
            counts["risks"] += 1
        ctl = controls.get((obj.id, s.control.lower()))
        if ctl is None:
            ctl = Control(objective_id=obj.id, ref=next_reference(db, "CTL"), title=s.control,
                          control_type=ControlType(s.control_type), created_by=user.id)
            db.add(ctl)
            db.flush()
            controls[(obj.id, s.control.lower())] = ctl
            counts["controls"] += 1
        if db.get(RiskControl, (rk.id, ctl.id)) is None:
            db.add(RiskControl(risk_id=rk.id, control_id=ctl.id))
        if s.procedure.strip():
            db.add(ControlTest(control_id=ctl.id, ref=next_reference(db, "TST"), test_type=TestType(s.test_type),
                               procedure=s.procedure, created_by=user.id))
            counts["tests"] += 1
    program.times_used += 1
    if not audit.audit_type and program.audit_type:
        audit.audit_type = program.audit_type
    log_action(db, user_id=user.id, action=f"PROGRAM_APPLY {program.prog_ref} audit={audit_id} {counts}",
               request=request)
    log_record_history(db, record_type="audit", record_id=audit_id, user_id=user.id,
                       action=f"PROGRAMME {program.prog_ref} applied ({counts['tests']} test steps)", request=request)
    db.commit()
    return {"program": program.prog_ref, **counts}
