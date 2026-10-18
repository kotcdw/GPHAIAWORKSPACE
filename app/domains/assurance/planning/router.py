"""Audit universe and Assurance Plan routes.

Workflow
--------
1. Admins maintain the **audit universe**: locations and their entity units,
   each with an inherent risk assessment (likelihood x impact).
2. An Admin or Auditor drafts the **Assurance Plan** for a fiscal year and adds
   planned **engagements** (entity unit, quarter, budget hours, lead auditor).
3. An Admin who did not prepare the plan approves it by e-signature. An
   approved plan is frozen; reopening it (back to Draft) is logged.
4. Starting an engagement of an approved plan creates the audit project,
   linked to the plan and the entity unit.
"""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.approvalsvc import sign
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import ensure_perm, require_perm, require_role
from app.core.enums import AuditStatus, EngagementStatus, PlanStatus, Role, utcnow
from app.core.history import log_record_history
from app.core.refs import next_reference
from app.core.schemas import ESignRequest, MessageOut
from app.domains.assurance.planning.models import AssurancePlan, EntityUnit, PlanEngagement
from app.domains.assurance.planning.schemas import (
    EngagementIn,
    EngagementOut,
    EngagementUpdate,
    EntityUnitOut,
    PlanDetail,
    PlanIn,
    PlanOut,
    PlanSummary,
    PlanUpdate,
    UncoveredUnit,
)
from app.domains.audit.audits.models import Audit
from app.platform.users.models import User


class CancelIn(BaseModel):
    reason: str = Field(default="", max_length=2000)


router = APIRouter(tags=["planning"])

Staff = Depends(require_role(Role.Admin, Role.Auditor))
PlanApprove = Depends(require_perm("plan.approve"))
PlanAmend = Depends(require_perm("plan.amend"))


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


# ====================================================================== universe


def _unit_out(unit: EntityUnit) -> EntityUnitOut:
    out = EntityUnitOut.model_validate(unit)
    out.location_name = unit.location.name if unit.location else ""
    out.risk_rating = unit.effective_rating
    return out


@router.get("/api/entity-units", response_model=list[EntityUnitOut])
def list_entity_units(
    db: DBSession = Depends(get_db), _: User = Staff, location_id: int | None = None, active_only: bool = False
) -> list[EntityUnitOut]:
    stmt = select(EntityUnit).order_by(EntityUnit.location_id, EntityUnit.code)
    if location_id is not None:
        stmt = stmt.where(EntityUnit.location_id == location_id)
    if active_only:
        stmt = stmt.where(EntityUnit.is_active.is_(True))
    return [_unit_out(u) for u in db.execute(stmt).scalars()]


# ====================================================================== plans


def _entity_port(db: DBSession, unit: EntityUnit | None) -> int | None:
    """The port / office of the auditable entity's org unit (Org Structure)."""
    if unit is None or not unit.org_unit_id:
        return None
    from app.platform.organizations.router import Index

    idx = Index(db)
    org = idx.rows.get(unit.org_unit_id)
    port = idx.port_of(org) if org else None
    return port.id if port else None


def _plan_or_404(db: DBSession, plan_id: int) -> AssurancePlan:
    plan = db.get(AssurancePlan, plan_id)
    if plan is None:
        raise _not_found("Assurance Plan")
    return plan


def _require_draft(plan: AssurancePlan) -> None:
    if plan.status != PlanStatus.Draft:
        raise _conflict(f"The {plan.fiscal_year} Assurance Plan is {plan.status.value}; reopen it to make changes")


def _engagement_out(eng: PlanEngagement) -> EngagementOut:
    out = EngagementOut.model_validate(eng)
    if eng.site_entity_id:
        from sqlalchemy.orm import object_session

        from app.platform.organizations.models import Organization

        site = object_session(eng).get(Organization, eng.site_entity_id)
        out.site_name = site.name if site else None
    if eng.entity_unit is not None:
        out.entity_unit_name = f"{eng.entity_unit.location.name} / {eng.entity_unit.name}"
        out.entity_risk_score = eng.entity_unit.risk_score
    return out


def _summary(db: DBSession, plan: AssurancePlan) -> PlanSummary:
    live = [e for e in plan.engagements if e.status != EngagementStatus.Cancelled]
    counts = Counter(e.status for e in plan.engagements)
    units = list(db.execute(select(EntityUnit).where(EntityUnit.is_active.is_(True))).scalars())
    covered = {e.entity_unit_id for e in live if e.entity_unit_id is not None}
    uncovered_high = [
        UncoveredUnit(
            id=u.id,
            name=u.name,
            location_name=u.location.name,
            risk_score=u.risk_score,
            risk_rating=u.effective_rating,
        )
        for u in sorted(units, key=lambda u: -u.risk_score)
        if u.id not in covered and u.effective_rating == "High"
    ]
    return PlanSummary(
        engagements=len(plan.engagements),
        planned=counts[EngagementStatus.Planned],
        started=counts[EngagementStatus.Started],
        cancelled=counts[EngagementStatus.Cancelled],
        planned_hours=sum(e.budget_hours for e in live),
        budget_hours=plan.total_budget_hours,
        universe_units=len(units),
        covered_units=len(covered & {u.id for u in units}),
        coverage_pct=round(100 * len(covered & {u.id for u in units}) / len(units), 1) if units else 0.0,
        uncovered_high_risk=uncovered_high,
        by_quarter={q: sum(1 for e in live if e.planned_quarter == q) for q in ("Q1", "Q2", "Q3", "Q4")},
    )


def _detail(db: DBSession, plan: AssurancePlan) -> PlanDetail:
    base = PlanOut.model_validate(plan).model_dump()
    return PlanDetail(
        **base,
        engagements=[_engagement_out(e) for e in plan.engagements],
        summary=_summary(db, plan),
    )


def _history(db: DBSession, plan_id: int, user: User, action: str, request: Request) -> None:
    log_record_history(
        db, record_type="assurance_plan", record_id=plan_id, user_id=user.id, action=action, request=request
    )


@router.get("/api/assurance-plans", response_model=list[PlanOut])
def list_plans(
    db: DBSession = Depends(get_db),
    _: User = Staff,
    include_archived: bool = False,
    lifecycle_status: str | None = None,
) -> list[AssurancePlan]:
    stmt = select(AssurancePlan).order_by(AssurancePlan.fiscal_year.desc())
    if lifecycle_status:
        stmt = stmt.where(AssurancePlan.lifecycle_status == lifecycle_status)
    elif not include_archived:
        stmt = stmt.where(AssurancePlan.archived_at.is_(None))
    return list(db.execute(stmt).scalars())


@router.post("/api/assurance-plans", response_model=PlanDetail, status_code=status.HTTP_201_CREATED)
def create_plan(payload: PlanIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> PlanDetail:
    if db.execute(select(AssurancePlan).where(AssurancePlan.fiscal_year == payload.fiscal_year)).first():
        raise _conflict(f"An Assurance Plan for {payload.fiscal_year} already exists")
    plan = AssurancePlan(plan_ref=next_reference(db, "AP"), created_by=user.id, **payload.model_dump())
    db.add(plan)
    db.flush()
    log_action(db, user_id=user.id, action=f"PLAN_CREATE id={plan.id} fy={plan.fiscal_year}", request=request)
    _history(db, plan.id, user, f"CREATED plan for FY{plan.fiscal_year}", request)
    db.commit()
    db.refresh(plan)
    return _detail(db, plan)


@router.get("/api/assurance-plans/{plan_id}", response_model=PlanDetail)
def get_plan(plan_id: int, db: DBSession = Depends(get_db), _: User = Staff) -> PlanDetail:
    return _detail(db, _plan_or_404(db, plan_id))


@router.patch("/api/assurance-plans/{plan_id}", response_model=PlanDetail)
def update_plan(
    plan_id: int, payload: PlanUpdate, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> PlanDetail:
    plan = _plan_or_404(db, plan_id)
    _require_draft(plan)
    changes = payload.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(plan, key, value)
    log_action(db, user_id=user.id, action=f"PLAN_UPDATE id={plan.id} [{', '.join(changes)}]", request=request)
    _history(db, plan.id, user, f"UPDATED [{', '.join(changes)}]", request)
    db.commit()
    db.refresh(plan)
    return _detail(db, plan)


@router.post("/api/assurance-plans/{plan_id}/approve", response_model=PlanDetail)
def approve_plan(
    plan_id: int, payload: ESignRequest, request: Request, db: DBSession = Depends(get_db), user: User = PlanApprove
) -> PlanDetail:
    from app.domains.assurance.plancycle import router as cycle

    plan = _plan_or_404(db, plan_id)
    _require_draft(plan)
    if not any(e.status != EngagementStatus.Cancelled for e in plan.engagements):
        raise _conflict("Add at least one engagement before approving the plan")
    if plan.created_by != user.id:  # the preparer is refused by the e-signature check (segregation of duties)
        cycle.ready_for_approval(plan)

    def _on_approve(_: DBSession) -> None:
        plan.status = PlanStatus.Approved
        plan.approved_by = user.id
        plan.approved_at = utcnow()
        cycle.on_internal_decision(db, plan, user, True, payload.comment, request)

    sign(
        db,
        record_type="assurance_plan",
        record_id=plan.id,
        user=user,
        password=payload.password,
        decision=payload.decision.value,
        comment=payload.comment,
        request=request,
        on_approve=_on_approve,
        preparer_id=plan.created_by,
    )
    if payload.decision.value == "Reject":
        cycle.on_internal_decision(db, plan, user, False, payload.comment, request)
    log_action(db, user_id=user.id, action=f"PLAN_{payload.decision.value.upper()} id={plan.id}", request=request)
    db.commit()
    db.refresh(plan)
    return _detail(db, plan)


@router.post("/api/assurance-plans/{plan_id}/reopen", response_model=PlanDetail)
def reopen_plan(
    plan_id: int,
    request: Request,
    payload: CancelIn | None = None,
    db: DBSession = Depends(get_db),
    user: User = PlanAmend,
) -> PlanDetail:
    """Full revision: return an approved plan to Draft. It goes back through internal review and the Audit
    Committee, and re-approval freezes the next version. Smaller changes use a plan change request."""
    plan = _plan_or_404(db, plan_id)
    if plan.status != PlanStatus.Approved:
        raise _conflict("Only an approved plan can be reopened")
    reason = (payload.reason if payload else "").strip()
    if len(reason) < 10:
        from app.core.errors import field_error

        raise field_error("reason", "explain why the approved plan is being revised (10+ characters)")
    from app.domains.assurance.planning.models import PlanChange

    db.add(
        PlanChange(
            plan_id=plan.id,
            change_type="Revision",
            reason=reason,
            changed_by=user.id,
            description=f"Approved version {plan.current_version} reopened for a full revision",
        )
    )
    plan.status = PlanStatus.Draft
    plan.approved_by = None
    plan.approved_at = None
    from app.domains.assurance.plancycle.router import on_reopen

    on_reopen(db, plan, user, request)
    log_action(db, user_id=user.id, action=f"PLAN_REOPEN id={plan.id}", request=request)
    _history(db, plan.id, user, "REOPENED for changes (re-approval required)", request)
    db.commit()
    db.refresh(plan)
    return _detail(db, plan)


@router.post("/api/assurance-plans/{plan_id}/close", response_model=PlanDetail)
def close_plan(plan_id: int, request: Request, db: DBSession = Depends(get_db), user: User = PlanAmend) -> PlanDetail:
    plan = _plan_or_404(db, plan_id)
    if plan.status != PlanStatus.Approved:
        raise _conflict("Only an approved plan can be closed")
    open_audits = [
        e.audit_id
        for e in plan.engagements
        if e.audit_id is not None and (a := db.get(Audit, e.audit_id)) is not None and a.status != AuditStatus.Closed
    ]
    if open_audits:
        raise _conflict(f"Plan still has open audits: {', '.join(f'#{i}' for i in open_audits)}")
    plan.status = PlanStatus.Closed
    log_action(db, user_id=user.id, action=f"PLAN_CLOSE id={plan.id}", request=request)
    _history(db, plan.id, user, "CLOSED (fiscal year complete)", request)
    db.commit()
    db.refresh(plan)
    return _detail(db, plan)


# ====================================================================== engagements


def _engagement_or_404(db: DBSession, eng_id: int) -> PlanEngagement:
    eng = db.get(PlanEngagement, eng_id)
    if eng is None:
        raise _not_found("Engagement")
    return eng


def check_site(db: DBSession, site_entity_id: int | None) -> None:
    """The responsible site must be one of the plan destinations administrators set up (Organizations)."""
    if site_entity_id is None:
        return
    from app.domains.assurance.plancycle.router import sites

    if site_entity_id not in {x["id"] for x in sites(db)}:
        from app.core.errors import field_error

        raise field_error("site_entity_id", "is not set up as a plan destination (Organizations register)")


def _check_refs(db: DBSession, entity_unit_id: int | None, lead_auditor_id: int | None) -> None:
    if entity_unit_id is not None:
        unit = db.get(EntityUnit, entity_unit_id)
        if unit is None:
            raise _not_found("Entity unit")
        if not unit.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Entity unit is inactive")
    if lead_auditor_id is not None:
        lead = db.get(User, lead_auditor_id)
        if lead is None or lead.role not in (Role.Admin, Role.Auditor):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Lead auditor must be an auditor")


@router.post(
    "/api/assurance-plans/{plan_id}/engagements", response_model=EngagementOut, status_code=status.HTTP_201_CREATED
)
def add_engagement(
    plan_id: int, payload: EngagementIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> EngagementOut:
    plan = _plan_or_404(db, plan_id)
    _require_draft(plan)
    _check_refs(db, payload.entity_unit_id, payload.lead_auditor_id)
    check_site(db, payload.site_entity_id)
    duplicate = next(
        (
            e
            for e in plan.engagements
            if e.status != EngagementStatus.Cancelled
            and e.title.strip().lower() == payload.title.strip().lower()
            and e.entity_unit_id == payload.entity_unit_id
        ),
        None,
    )
    if duplicate is not None:
        raise _conflict(f"'{payload.title}' is already planned for this entity (engagement #{duplicate.id})")
    eng = PlanEngagement(plan_id=plan.id, created_by=user.id, **payload.model_dump())
    db.add(eng)
    db.flush()
    log_action(db, user_id=user.id, action=f"ENGAGEMENT_ADD id={eng.id} plan={plan.id}", request=request)
    _history(db, plan.id, user, f"ENGAGEMENT ADDED #{eng.id} {eng.title} ({eng.planned_quarter})", request)
    db.commit()
    db.refresh(eng)
    return _engagement_out(eng)


@router.patch("/api/plan-engagements/{eng_id}", response_model=EngagementOut)
def update_engagement(
    eng_id: int, payload: EngagementUpdate, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> EngagementOut:
    eng = _engagement_or_404(db, eng_id)
    _require_draft(eng.plan)
    _check_refs(db, payload.entity_unit_id, payload.lead_auditor_id)
    check_site(db, payload.site_entity_id)
    changes = payload.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(eng, key, value)
    log_action(db, user_id=user.id, action=f"ENGAGEMENT_UPDATE id={eng.id} [{', '.join(changes)}]", request=request)
    _history(db, eng.plan_id, user, f"ENGAGEMENT UPDATED #{eng.id} [{', '.join(changes)}]", request)
    db.commit()
    db.refresh(eng)
    return _engagement_out(eng)


@router.delete("/api/plan-engagements/{eng_id}", response_model=MessageOut)
def remove_engagement(eng_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> MessageOut:
    eng = _engagement_or_404(db, eng_id)
    _require_draft(eng.plan)
    if eng.audit_id is not None:
        raise _conflict("A started engagement cannot be removed")
    plan_id, title = eng.plan_id, eng.title
    db.delete(eng)
    log_action(db, user_id=user.id, action=f"ENGAGEMENT_REMOVE id={eng_id} plan={plan_id}", request=request)
    _history(db, plan_id, user, f"ENGAGEMENT REMOVED #{eng_id} {title}", request)
    db.commit()
    return MessageOut(message=f"Engagement {title} removed from the draft plan")


@router.post("/api/plan-engagements/{eng_id}/cancel", response_model=EngagementOut)
def cancel_engagement(
    eng_id: int,
    request: Request,
    payload: CancelIn | None = None,
    db: DBSession = Depends(get_db),
    user: User = PlanAmend,
) -> EngagementOut:
    eng = _engagement_or_404(db, eng_id)
    if eng.status != EngagementStatus.Planned:
        raise _conflict("Only an engagement that has not started can be cancelled")
    if eng.plan.status == PlanStatus.Approved:
        raise _conflict(
            "Approved plans are changed through a plan change request (reason, impact, review and approval)"
        )
    eng.status = EngagementStatus.Cancelled
    log_action(db, user_id=user.id, action=f"ENGAGEMENT_CANCEL id={eng.id}", request=request)
    _history(db, eng.plan_id, user, f"ENGAGEMENT CANCELLED #{eng.id} {eng.title}", request)
    db.commit()
    db.refresh(eng)
    return _engagement_out(eng)


@router.post("/api/plan-engagements/{eng_id}/start", response_model=EngagementOut)
def start_engagement(
    eng_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> EngagementOut:
    """Create the audit project for a planned engagement of an approved plan."""
    from app.domains.audit.audits.router import _home_port

    ensure_perm(user, "audit.create")
    eng = _engagement_or_404(db, eng_id)
    if eng.plan.status != PlanStatus.Approved:
        raise _conflict("Engagements can only be started from an approved Assurance Plan")
    if eng.status != EngagementStatus.Planned:
        raise _conflict(f"Engagement is already {eng.status.value}")
    from app.domains.assurance.plancycle.router import ensure_can_execute

    ensure_can_execute(eng.plan)
    unit = eng.entity_unit
    scope = f"Entity: {unit.location.name} / {unit.name}\n" if unit else ""
    audit = Audit(
        title=eng.title,
        description=eng.rationale,
        scope=f"{scope}Assurance Plan FY{eng.plan.fiscal_year} ({eng.plan.plan_ref}), {eng.planned_quarter}",
        status=AuditStatus.Planned,
        created_by=user.id,
        plan_id=eng.plan_id,
        entity_unit_id=eng.entity_unit_id,
        port_entity_id=eng.site_entity_id or _entity_port(db, unit) or _home_port(db, user),
    )
    db.add(audit)
    db.flush()
    if eng.entity_unit_id:
        from app.domains.assurance.universe.models import AuditEntity

        db.add(AuditEntity(audit_id=audit.id, entity_id=eng.entity_unit_id))
    eng.status = EngagementStatus.Started
    eng.audit_id = audit.id
    from app.domains.audit.audits.models import AuditTeamMember

    lead = eng.lead_auditor_id if eng.lead_auditor_id and db.get(User, eng.lead_auditor_id) else None
    if lead:
        db.add(AuditTeamMember(audit_id=audit.id, user_id=lead, team_role="Lead auditor", added_by=user.id))
    if user.id != lead:
        db.add(AuditTeamMember(audit_id=audit.id, user_id=user.id, team_role="Auditor" if lead else "Lead auditor",
                               added_by=user.id))
    log_action(db, user_id=user.id, action=f"ENGAGEMENT_START id={eng.id} audit={audit.id}", request=request)
    _history(db, eng.plan_id, user, f"ENGAGEMENT STARTED #{eng.id} -> audit #{audit.id}", request)
    log_record_history(
        db,
        record_type="audit",
        record_id=audit.id,
        user_id=user.id,
        action=f"CREATED from Assurance Plan {eng.plan.plan_ref} engagement #{eng.id}",
        request=request,
    )
    db.commit()
    db.refresh(eng)
    return _engagement_out(eng)
