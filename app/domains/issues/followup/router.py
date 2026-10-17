"""Follow-up routes: record implementation, validate it, track overdue actions."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session as DBSession

from app.core.access import _same_email, ensure_can_view, is_privileged
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user, require_module_tier, require_perm
from app.core.enums import CapaStatus, Role, ValidationResult, utcnow
from app.core.history import log_record_history
from app.domains.issues.capa.models import Capa
from app.domains.issues.capa.schemas import CapaOut
from app.domains.issues.capa.status import FULLY, NOT_IMPLEMENTED, PARTIALLY
from app.domains.issues.capa.timeline import add_event
from app.domains.issues.followup.service import LEVEL_NAMES, overdue_actions, run_escalations
from app.platform.automations.engine import capa_context, emit
from app.platform.notifications.service import notify, notify_many, user_id_by_email
from app.platform.users.models import User

router = APIRouter(tags=["follow-up"])

Staff = Depends(require_module_tier("follow-up", Role.Admin, Role.Auditor))


class ImplementIn(BaseModel):
    evidence: str = Field(min_length=10, max_length=20000)

    @field_validator("evidence")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 10:
            raise ValueError("describe what was done (at least 10 characters)")
        return value


class ValidateIn(BaseModel):
    result: ValidationResult
    comment: str = Field(default="", max_length=20000)
    # Follow-up testing performed (GIAS 15.2): what the auditor did to confirm the action works.
    procedures: str = Field(default="", max_length=20000)

    @field_validator("comment")
    @classmethod
    def _strip_comment(cls, value: str) -> str:
        return value.strip()


class OverdueOut(BaseModel):
    id: int
    capa_ref: str
    title: str
    owner_email: str | None
    status: str
    due_date: datetime
    days_overdue: int
    escalation_level: int
    escalation_name: str
    source_type: str | None
    source_id: int | None


def _load(db: DBSession, capa_id: int) -> Capa:
    capa = db.get(Capa, capa_id)
    if capa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Remediation not found")
    return capa


@router.post("/api/capa/{capa_id}/implement", response_model=CapaOut)
def record_implementation(
    capa_id: int,
    payload: ImplementIn,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_active_user),
) -> Capa:
    """The action owner (or audit staff on their behalf) records what was done."""
    capa = _load(db, capa_id)
    ensure_can_view(db, user, "capa", capa)
    if not (is_privileged(user) or _same_email(capa.owner_email, user.email)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the action owner can record this")
    if capa.status not in (CapaStatus.Open, CapaStatus.InProgress):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Implementation can only be recorded while the action is open (now: {capa.status.value})",
        )
    capa.implementation_evidence = payload.evidence
    capa.implemented_by = user.id
    capa.implemented_at = utcnow()
    capa.validation_result = None
    capa.validation_comment = None
    capa.validated_by = None
    capa.validated_at = None
    capa.status = CapaStatus.Review
    add_event(db, capa, "implementation", user_id=user.id, text=payload.evidence, request=request)
    log_record_history(db, record_type="capa", record_id=capa.id, user_id=user.id,
                       action="IMPLEMENTED evidence recorded", request=request)
    log_action(db, user_id=user.id, action=f"REMEDIATION_IMPLEMENTED id={capa.id}", request=request)
    notify(db, capa.created_by, f"Ready to validate: {capa.capa_ref}",
           f"{user.full_name or user.username} recorded the implementation of \"{capa.title}\".",
           link_type="capa", link_id=capa.id)
    emit(db, "action.implemented", "capa", capa.id, capa_context(db, capa), period=f"impl{capa.reopen_count or 0}")
    db.commit()
    db.refresh(capa)
    return capa


@router.post("/api/capa/{capa_id}/validate", response_model=CapaOut)
def validate_implementation(
    capa_id: int,
    payload: ValidateIn,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_perm("followup.validate")),
) -> Capa:
    """An auditor tests the evidence: Effective (ready to close) or Not Effective (reopened)."""
    capa = _load(db, capa_id)
    if capa.status != CapaStatus.Review or capa.implemented_at is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Only an action with recorded implementation can be validated")
    if capa.implemented_by == user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Segregation of duties: the person who implemented an action cannot validate it")
    if payload.result == ValidationResult.NotEffective and len(payload.comment) < 5:
        from app.core.errors import field_error

        raise field_error("comment", "explain why the action is not effective")
    procedures = payload.procedures.strip()
    if payload.result == ValidationResult.Effective and len(procedures) < 10:
        from app.core.errors import field_error

        raise field_error("procedures", "describe the follow-up testing performed (at least 10 characters)")
    capa.validation_result = payload.result
    capa.validation_comment = payload.comment
    capa.validation_procedures = procedures or None
    capa.validated_by = user.id
    capa.validated_at = utcnow()
    owner = user_id_by_email(db, capa.owner_email)
    if payload.result == ValidationResult.NotEffective:
        capa.status = CapaStatus.InProgress
        capa.implementation_status = PARTIALLY
        capa.reopen_count = (capa.reopen_count or 0) + 1
        emit(db, "action.reopened", "capa", capa.id, capa_context(db, capa), period=f"reopen{capa.reopen_count}")
        notify_many(db, [owner, capa.implemented_by], f"Action reopened: {capa.capa_ref}",
                    f"The auditor found the action not effective: {payload.comment}",
                    link_type="capa", link_id=capa.id)
    else:
        capa.implementation_status = FULLY
        notify_many(db, [owner, capa.created_by], f"Action validated: {capa.capa_ref}",
                    "The auditor confirmed the action is effective. It can now be closed with an e-signature.",
                    link_type="capa", link_id=capa.id)
    add_event(db, capa, "validation", user_id=user.id, request=request,
              text=f"{payload.result.value}. " + (f"Testing: {procedures}. " if procedures else "")
              + (payload.comment or ""))
    log_record_history(db, record_type="capa", record_id=capa.id, user_id=user.id,
                       action=f"VALIDATED {payload.result.value}", request=request)
    log_action(db, user_id=user.id, action=f"REMEDIATION_VALIDATED id={capa.id} result={payload.result.value}",
               request=request)
    db.commit()
    db.refresh(capa)
    return capa


@router.get("/api/followup/overdue", response_model=list[OverdueOut])
def list_overdue(db: DBSession = Depends(get_db), user: User = Staff) -> list[OverdueOut]:
    return [
        OverdueOut(
            id=i.capa.id, capa_ref=i.capa.capa_ref, title=i.capa.title, owner_email=i.capa.owner_email,
            status=i.capa.status.value, due_date=i.capa.due_date, days_overdue=i.days_overdue,
            escalation_level=i.due_level, escalation_name=LEVEL_NAMES[i.due_level],
            source_type=i.capa.source_type, source_id=i.capa.source_id,
        )
        for i in overdue_actions(db)
    ]


@router.post("/api/followup/run-escalations")
def trigger_escalations(request: Request, db: DBSession = Depends(get_db),
                        user: User = Depends(require_perm("followup.manage"))) -> dict:
    moved = run_escalations(db)
    log_action(db, user_id=user.id, action=f"ESCALATION_RUN manual escalated={moved}", request=request, commit=True)
    return {"escalated": moved}


class ProgressIn(BaseModel):
    status: str
    note: str = Field(min_length=10, max_length=10000)

    @field_validator("status")
    @classmethod
    def _status(cls, value: str) -> str:
        if value not in (NOT_IMPLEMENTED, PARTIALLY):
            raise ValueError(f"must be {NOT_IMPLEMENTED} or {PARTIALLY}; full implementation is recorded with "
                             "evidence and validated by an auditor")
        return value


@router.post("/api/capa/{capa_id}/progress", response_model=CapaOut)
def record_progress(capa_id: int, payload: ProgressIn, request: Request, db: DBSession = Depends(get_db),
                    user: User = Depends(require_active_user)) -> Capa:
    """A progress update between due dates (shown in the quarterly follow-up report)."""
    capa = _load(db, capa_id)
    ensure_can_view(db, user, "capa", capa)
    if not (is_privileged(user) or _same_email(capa.owner_email, user.email)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the action owner can record this")
    if capa.status not in (CapaStatus.Open, CapaStatus.InProgress):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The action is not open")
    capa.implementation_status = payload.status
    capa.progress_note = f"{utcnow():%d %b %Y}: {payload.note.strip()}"
    if capa.status == CapaStatus.Open and payload.status == PARTIALLY:
        capa.status = CapaStatus.InProgress
    add_event(db, capa, "progress", user_id=user.id, text=f"{payload.status}: {payload.note.strip()}",
              request=request)
    log_record_history(db, record_type="capa", record_id=capa.id, user_id=user.id,
                       action=f"PROGRESS {payload.status}", request=request)
    log_action(db, user_id=user.id, action=f"REMEDIATION_PROGRESS id={capa.id} {payload.status}", request=request)
    db.commit()
    db.refresh(capa)
    return capa


class WithdrawalIn(BaseModel):
    reason: str = Field(min_length=20, max_length=5000)


@router.post("/api/capa/{capa_id}/propose-withdrawal", response_model=CapaOut)
def propose_withdrawal(capa_id: int, payload: WithdrawalIn, request: Request, db: DBSession = Depends(get_db),
                       user: User = Depends(require_perm("followup.manage"))) -> Capa:
    """Re-evaluation: a recommendation no longer relevant or feasible goes to the Audit Committee to withdraw
    (MoF instructions s.6.1(8), s.7.7)."""
    capa = _load(db, capa_id)
    if capa.status == CapaStatus.Closed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The action is already closed")
    capa.withdrawal_reason = payload.reason.strip()
    capa.withdrawal_proposed_by = user.id
    capa.withdrawal_proposed_at = utcnow()
    add_event(db, capa, "withdrawal", user_id=user.id, request=request,
              text=f"Withdrawal proposed to the Audit Committee: {capa.withdrawal_reason}")
    log_record_history(db, record_type="capa", record_id=capa.id, user_id=user.id,
                       action="WITHDRAWAL PROPOSED to the Audit Committee", request=request)
    log_action(db, user_id=user.id, action=f"REMEDIATION_WITHDRAWAL_PROPOSED id={capa.id}", request=request)
    emit(db, "action.withdrawal_proposed", "capa", capa.id, capa_context(db, capa),
         period=f"wd{capa.withdrawal_proposed_at:%Y%m%d%H%M}")
    db.commit()
    db.refresh(capa)
    return capa
