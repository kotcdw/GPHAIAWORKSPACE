"""Audit routes with a simple status workflow."""

from __future__ import annotations

import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.access import ensure_can_view, visible
from app.core.approvalsvc import sign
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user, require_module_tier, require_perm, require_role
from app.core.enums import ApprovalStatus, AuditStatus, Role, TestStatus, utcnow
from app.core.history import log_record_history
from app.core.paging import Page, PageParams, matches, page_params, paginate_rows
from app.core.schemas import ESignRequest, MessageOut
from app.domains.audit.audits.models import Audit, AuditAuditee, AuditTeamMember, Finding, WorkingPaper
from app.domains.audit.audits.schemas import AuditCreate, AuditeeAssign, AuditeeOut, AuditOut, AuditUpdate
from app.domains.issues.nonconformances.models import Nonconformance
from app.platform.approvals.models import ApprovalCycle
from app.platform.users.models import User

router = APIRouter(prefix="/api/audits", tags=["audits"])

AdminAudit = Depends(require_module_tier("audits", Role.Admin))
CloseAudit = Depends(require_perm("audit.close"))

WriteAudit = Depends(require_role(Role.Admin, Role.Auditor))

# Status transitions allowed through PATCH (a no-op change is allowed).
# Review -> Closed is deliberately absent: closing an audit is only possible
# through the e-signed ``POST /{id}/close`` route.
_ALLOWED_TRANSITIONS: dict[AuditStatus, set[AuditStatus]] = {
    AuditStatus.Planned: {AuditStatus.InProgress},
    AuditStatus.InProgress: {AuditStatus.Review, AuditStatus.Planned},
    AuditStatus.Review: {AuditStatus.InProgress},
    AuditStatus.Closed: set(),
}


def _check_transition(current: AuditStatus, new: AuditStatus) -> None:
    if new == current:
        return
    if new == AuditStatus.Closed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audits can only be closed by an e-signed sign-off (POST /api/audits/{id}/close)",
        )
    if new not in _ALLOWED_TRANSITIONS[current]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status transition: {current.value} -> {new.value}",
        )


@router.get("", response_model=list[AuditOut])
def list_audits(db: DBSession = Depends(get_db), user: User = Depends(require_active_user),
                audit_type: str | None = None, port_id: int | None = None, mine: bool = False) -> list[Audit]:
    stmt = select(Audit).order_by(Audit.created_at.desc())
    if audit_type:
        stmt = stmt.where(Audit.audit_type == audit_type)
    if mine:
        from app.platform.organizations.router import Index

        idx = Index(db)
        home = idx.rows.get(user.work_entity_id) if user.work_entity_id else None
        port = idx.port_of(home) if home else None
        port_id = port.id if port else -1
    if port_id is not None:
        stmt = stmt.where(Audit.port_entity_id == port_id)
    audits = list(db.execute(stmt).scalars().all())
    return visible(db, user, "audit", audits)


class AuditRow(BaseModel):
    id: int
    ref: str
    title: str
    audit_type: str | None
    nature: str = "Assurance"
    phase: str = "Plan"
    status: str
    approval_status: str | None
    port: str | None
    port_id: int | None
    plan: str | None
    plan_id: int | None
    lead: str | None
    planned_quarter: str | None
    planned_start: date | None
    planned_end: date | None
    budget_hours: int | None
    open_findings: int
    open_high: int = 0
    findings: int
    report_status: str | None
    progress: int = 0
    favorite: bool = False
    updated_at: datetime


_AUDIT_SORT = {
    "ref": lambda r: r["id"], "title": lambda r: r["title"], "status": lambda r: r["status"],
    "audit_type": lambda r: r["audit_type"], "port": lambda r: r["port"], "plan": lambda r: r["plan"],
    "lead": lambda r: r["lead"], "planned_start": lambda r: r["planned_start"],
    "open_findings": lambda r: r["open_findings"], "updated_at": lambda r: r["updated_at"],
    "progress": lambda r: r["progress"], "phase": lambda r: _PHASES.index(r["phase"]),
    "nature": lambda r: r["nature"], "open_high": lambda r: r["open_high"],
}

# Engagement phase in the IIA GIAS cycle: Plan (13), Perform (14), Communicate (15.1), Monitor (15.2).
_PHASE = {"Planned": "Plan", "In Progress": "Perform", "Review": "Communicate", "Closed": "Monitor"}
_PHASES = ["Plan", "Perform", "Communicate", "Monitor", "Completed"]


@router.get("/register", response_model=Page[AuditRow])
def audit_register(
    db: DBSession = Depends(get_db),
    user: User = Depends(require_active_user),
    params: PageParams = Depends(page_params),
    status_filter: AuditStatus | None = Query(None, alias="status"),
    audit_type: str | None = Query(None, max_length=60),
    port_id: int | None = None,
    plan_id: int | None = None,
    mine: bool = False,
    fav_first: bool = False,
) -> Page[AuditRow]:
    """The engagement register: one row per audit the user may read, with plan, lead, port and progress counts.

    Rows are authorized first, then searched, sorted and paged on the server.
    """
    from app.domains.assurance.planning.coverage import engagement_progress
    from app.domains.assurance.planning.models import AssurancePlan, PlanEngagement
    from app.domains.audit.audits.nature import nature
    from app.domains.audit.fieldwork.extras import favorite_ids
    from app.domains.audit.reports.models import AuditReport
    from app.platform.organizations.models import Organization

    stmt = select(Audit)
    if status_filter is not None:
        stmt = stmt.where(Audit.status == status_filter)
    if audit_type:
        stmt = stmt.where(Audit.audit_type == audit_type)
    if plan_id is not None:
        stmt = stmt.where(Audit.plan_id == plan_id)
    if mine:
        from app.platform.organizations.router import Index

        idx = Index(db)
        home = idx.rows.get(user.work_entity_id) if user.work_entity_id else None
        port = idx.port_of(home) if home else None
        port_id = port.id if port else -1
    if port_id is not None:
        stmt = stmt.where(Audit.port_entity_id == port_id)
    audits = visible(db, user, "audit", list(db.execute(stmt).scalars().all()))
    ids = [a.id for a in audits] or [0]

    counts: dict[int, list[int]] = {}
    for aid, st, rating in db.execute(select(Finding.audit_id, Finding.status, Finding.risk_rating)
                                      .where(Finding.audit_id.in_(ids))).all():
        c = counts.setdefault(aid, [0, 0, 0])
        c[0] += 1
        if st.value != "Closed":
            c[1] += 1
            c[2] += 1 if getattr(rating, "value", rating) == "High" else 0
    reports = {r.audit_id: r.status.value for r in
               db.execute(select(AuditReport).where(AuditReport.audit_id.in_(ids))).scalars()}
    engagements = {e.audit_id: e for e in
                   db.execute(select(PlanEngagement).where(PlanEngagement.audit_id.in_(ids))).scalars()}
    plans = {p.id: p for p in db.execute(select(AssurancePlan)).scalars()}
    port_ids = {a.port_entity_id for a in audits if a.port_entity_id}
    ports = {o.id: o.name for o in
             db.execute(select(Organization).where(Organization.id.in_(port_ids or {0}))).scalars()}
    team_leads = dict(db.execute(select(AuditTeamMember.audit_id, AuditTeamMember.user_id).where(
        AuditTeamMember.audit_id.in_(ids), AuditTeamMember.team_role == "Lead auditor")).all())
    lead_ids = {e.lead_auditor_id for e in engagements.values() if e.lead_auditor_id} | set(team_leads.values())
    leads = {u.id: (u.full_name or u.username) for u in
             db.execute(select(User).where(User.id.in_(lead_ids or {0}))).scalars()}

    favs = favorite_ids(db, user)
    rows = []
    for a in audits:
        e = engagements.get(a.id)
        p = plans.get(a.plan_id) if a.plan_id else None
        f_total, f_open, f_high = counts.get(a.id, [0, 0, 0])
        rows.append({
            "id": a.id, "ref": f"AUD-{a.id:04d}", "title": a.title, "audit_type": a.audit_type,
            "nature": nature(a),
            "phase": "Completed" if a.status.value == "Closed" and not f_open else _PHASE.get(a.status.value, "Plan"),
            "status": a.status.value, "approval_status": a.approval_status.value if a.approval_status else None,
            "port": ports.get(a.port_entity_id), "port_id": a.port_entity_id,
            "plan": f"FY{p.fiscal_year} · {p.plan_ref}" if p else None, "plan_id": a.plan_id,
            "lead": leads.get(team_leads.get(a.id))
            or (leads.get(e.lead_auditor_id) if e and e.lead_auditor_id else None),
            "planned_quarter": e.planned_quarter if e else None, "planned_start": e.planned_start if e else None,
            "planned_end": e.planned_end if e else None, "budget_hours": e.budget_hours if e else None,
            "open_findings": f_open, "open_high": f_high, "findings": f_total,
            "report_status": reports.get(a.id), "progress": engagement_progress(db, a), "updated_at": a.updated_at,
            "favorite": a.id in favs,
        })
    rows = [r for r in rows if matches(params.q, r["ref"], r["title"], r["port"], r["lead"], r["audit_type"],
                                       r["plan"])]
    page, total, sort = paginate_rows(rows, params, _AUDIT_SORT, "-updated_at", first=(
        (lambda r: r["favorite"]) if fav_first else None))
    return Page[AuditRow](items=page, total=total, page=params.page, page_size=params.page_size, sort=sort)


def _audit_type(value: str | None) -> str | None:
    from app.core.appconfig import cfg
    from app.core.errors import field_error

    if not value or not value.strip():
        return None
    match = next((t for t in cfg("audit_types") if t.lower() == value.strip().lower()), None)
    if match is None:
        raise field_error("audit_type", f"must be one of: {', '.join(cfg('audit_types'))}")
    return match


def _organization(db: DBSession, org_id: int | None, current: int | None = None) -> int | None:
    from app.core.errors import field_error
    from app.platform.organizations.models import Organization

    if org_id is None:
        return None
    org = db.get(Organization, org_id)
    if org is None:
        raise field_error("organization_id", "is not a known entity")
    if not org.is_active and org_id != current:  # an audit that already names a deactivated unit keeps it
        raise field_error("organization_id", f"{org.name} is deactivated: choose an active unit")
    return org_id


def _port(db: DBSession, port_id: int | None, current: int | None = None) -> int | None:
    from app.core.errors import field_error
    from app.platform.organizations.router import Index

    if port_id is None:
        return None
    idx = Index(db)
    row = idx.rows.get(port_id)
    if row is None or not idx.is_port(row):
        raise field_error("port_entity_id", "is not a port / site entity")
    if not row.is_active and port_id != current:  # an audit that already names a deactivated port keeps it
        raise field_error("port_entity_id", f"{row.name} is deactivated: choose an active port")
    return port_id


def _home_port(db: DBSession, user: User) -> int | None:
    from app.platform.organizations.router import Index

    if not user.work_entity_id:
        return None
    idx = Index(db)
    home = idx.rows.get(user.work_entity_id)
    port = idx.port_of(home) if home else None
    return port.id if port else None


@router.get("/auditee-candidates", response_model=list[AuditeeOut])
def auditee_candidates(db: DBSession = Depends(get_db), _: User = WriteAudit) -> list[AuditeeOut]:
    """Active Auditee accounts that can be assigned to an audit."""
    users = db.execute(
        select(User).where(User.role == Role.Auditee, User.is_active.is_(True)).order_by(User.username)
    ).scalars()
    return [AuditeeOut(user_id=u.id, username=u.username, full_name=u.full_name, email=u.email) for u in users]


@router.post("", response_model=AuditOut, status_code=status.HTTP_201_CREATED)
def create_audit(
    payload: AuditCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_role(Role.Admin, Role.Auditor)),
) -> Audit:
    if payload.status != AuditStatus.Planned:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New audits must start as Planned")
    from app.core.deps import ensure_perm

    ensure_perm(user, "audit.create")
    from app.core.errors import field_error
    from app.domains.audit.fieldwork.router import WORKFLOWS, default_workflow

    audit_type = _audit_type(payload.audit_type)
    if payload.workflow is not None and payload.workflow not in WORKFLOWS:
        raise field_error("workflow", f"must be {' or '.join(WORKFLOWS)}")
    audit = Audit(
        title=payload.title,
        description=payload.description,
        scope=payload.scope,
        status=payload.status,
        organization_id=_organization(db, payload.organization_id),
        audit_type=audit_type,
        workflow=payload.workflow or default_workflow(audit_type),
        port_entity_id=_port(db, payload.port_entity_id) if payload.port_entity_id else _home_port(db, user),
        custom_fields=json.dumps(_custom(db, payload.custom_fields, None)),
        created_by=user.id,
    )
    db.add(audit)
    db.flush()
    db.add(AuditTeamMember(audit_id=audit.id, user_id=user.id, team_role="Lead auditor", added_by=user.id))
    log_action(db, user_id=user.id, action=f"AUDIT_CREATE id={audit.id} title={audit.title}", request=request)
    log_record_history(
        db, record_type="audit", record_id=audit.id, user_id=user.id, action="CREATED", request=request
    )
    db.commit()
    db.refresh(audit)
    return audit


@router.get("/{audit_id}", response_model=AuditOut)
def get_audit(audit_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> Audit:
    audit = db.get(Audit, audit_id)
    ensure_can_view(db, user, "audit", audit)
    return audit


@router.patch("/{audit_id}", response_model=AuditOut)
def update_audit(
    audit_id: int,
    payload: AuditUpdate,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_role(Role.Admin, Role.Auditor)),
) -> Audit:
    audit = db.get(Audit, audit_id)
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit not found")
    if audit.status == AuditStatus.Closed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A closed audit cannot be edited")

    changes: list[str] = []
    if payload.title is not None:
        audit.title = payload.title
        changes.append("title")
    if payload.description is not None:
        audit.description = payload.description
        changes.append("description")
    if payload.scope is not None:
        audit.scope = payload.scope
        changes.append("scope")
    if payload.organization_id is not None:
        audit.organization_id = _organization(db, payload.organization_id, audit.organization_id)
        changes.append("organization_id")
    if "audit_type" in payload.model_fields_set:
        audit.audit_type = _audit_type(payload.audit_type)
        changes.append("audit_type")
    if "port_entity_id" in payload.model_fields_set:
        audit.port_entity_id = _port(db, payload.port_entity_id, audit.port_entity_id)
        changes.append("port")
    if payload.custom_fields is not None:
        audit.custom_fields = json.dumps(_custom(db, payload.custom_fields, audit.custom_fields))
        changes.append("custom fields")
    if payload.status is not None:
        _check_transition(audit.status, payload.status)
        if payload.status != audit.status:
            changes.append(f"status={payload.status.value}")
            started = audit.status == AuditStatus.Planned and payload.status == AuditStatus.InProgress
            if started:
                from app.domains.audit.memos.router import ensure_fieldwork_can_start

                ensure_fieldwork_can_start(db, audit)
            audit.status = payload.status
            if started:
                from app.domains.audit.audits.lifecycle import notify_fieldwork_started

                notify_fieldwork_started(db, audit, user)

    log_action(db, user_id=user.id, action=f"AUDIT_UPDATE id={audit.id} [{', '.join(changes)}]", request=request)
    log_record_history(
        db,
        record_type="audit",
        record_id=audit.id,
        user_id=user.id,
        action=f"UPDATED [{', '.join(changes)}]",
        request=request,
    )
    db.commit()
    db.refresh(audit)
    return audit


def _custom(db: DBSession, values: dict | None, existing: str | None) -> dict:
    from app.platform.customfields.router import clean_values

    return clean_values(db, "audits", values, json.loads(existing or "{}"))


@router.delete("/{audit_id}", response_model=MessageOut)
def delete_audit(
    audit_id: int,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_role(Role.Admin)),
) -> MessageOut:
    audit = db.get(Audit, audit_id)
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit not found")
    _ensure_deletable(db, audit)
    title = audit.title
    db.delete(audit)
    log_action(db, user_id=user.id, action=f"AUDIT_DELETE id={audit_id} title={title}", request=request)
    db.commit()
    return MessageOut(message=f"Audit {audit_id} deleted")


def _ensure_fieldwork_reviewed(db: DBSession, audit: Audit) -> None:
    """Every control test must be reviewed (or not started) before sign-off."""
    from app.domains.audit.rcm.models import Control, ControlTest, Objective

    pending = db.execute(
        select(ControlTest.ref)
        .join(Control, Control.id == ControlTest.control_id)
        .join(Objective, Objective.id == Control.objective_id)
        .where(
            Objective.audit_id == audit.id,
            ControlTest.status.in_([TestStatus.InProgress, TestStatus.Completed]),
        )
    ).scalars().all()
    if pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Control tests not yet reviewed: {', '.join(pending)}",
        )


def _ensure_deletable(db: DBSession, audit: Audit) -> None:
    """Only an untouched, Planned audit may be deleted - never one with evidence."""
    if audit.status != AuditStatus.Planned:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Only audits still in Planned status can be deleted"
        )
    checks = (
        (Finding, Finding.audit_id, "findings"),
        (WorkingPaper, WorkingPaper.audit_id, "working papers"),
        (Nonconformance, Nonconformance.audit_id, "nonconformances"),
    )
    for model, column, label in checks:
        if db.execute(select(func.count()).select_from(model).where(column == audit.id)).scalar_one():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=f"Audit has {label} and cannot be deleted"
            )
    signed = db.execute(
        select(func.count())
        .select_from(ApprovalCycle)
        .where(ApprovalCycle.record_type == "audit", ApprovalCycle.record_id == audit.id)
    ).scalar_one()
    if signed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Audit has e-signatures and cannot be deleted")


@router.post("/{audit_id}/in-approval", response_model=AuditOut)
def set_in_approval(
    audit_id: int,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_role(Role.Admin, Role.Auditor)),
) -> Audit:
    audit = db.get(Audit, audit_id)
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit not found")
    if audit.status != AuditStatus.Review:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Only audits in Review can be submitted for approval"
        )
    audit.approval_status = ApprovalStatus.InApproval
    log_action(db, user_id=user.id, action=f"AUDIT_IN_APPROVAL id={audit.id}", request=request)
    log_record_history(
        db, record_type="audit", record_id=audit.id, user_id=user.id, action="MOVED TO IN APPROVAL", request=request
    )
    db.commit()
    db.refresh(audit)
    return audit


@router.post("/{audit_id}/close", response_model=AuditOut)
def close_audit(
    audit_id: int,
    payload: ESignRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = CloseAudit,
) -> Audit:
    audit = db.get(Audit, audit_id)
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit not found")
    if audit.status != AuditStatus.Review:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only audits in Review can be closed (current status: {audit.status.value})",
        )

    _ensure_fieldwork_reviewed(db, audit)
    from app.domains.audit.audits.lifecycle import ensure_closable

    ensure_closable(db, audit)

    def _on_approve(session: DBSession) -> None:
        audit.status = AuditStatus.Closed
        audit.approval_status = ApprovalStatus.Approved
        from app.domains.assurance.planning.models import EntityUnit
        from app.domains.assurance.universe.models import AuditEntity

        covered = {e for (e,) in session.execute(select(AuditEntity.entity_id).where(
            AuditEntity.audit_id == audit.id)).all()} | ({audit.entity_unit_id} if audit.entity_unit_id else set())
        if audit.nature == "Advisory":
            covered = set()  # advisory work is not audit coverage of the entity
        for eid in covered:  # every auditable entity the audit covers
            unit = session.get(EntityUnit, eid)
            if unit is not None:
                unit.last_audited_at = utcnow()

    sign(
        db,
        record_type="audit",
        record_id=audit.id,
        user=user,
        password=payload.password,
        decision="Approve",
        preparer_id=audit.created_by,
        comment=payload.comment,
        request=request,
        on_approve=_on_approve,
    )
    log_action(db, user_id=user.id, action=f"AUDIT_CLOSE id={audit.id} title={audit.title}", request=request)
    if audit.status == AuditStatus.Closed:
        from app.domains.assurance.qaip.router import invite_survey

        invite_survey(db, audit)
    db.commit()
    db.refresh(audit)
    return audit

# ---------------------------------------------------------------- auditees


def _audit_or_404(db: DBSession, audit_id: int) -> Audit:
    audit = db.get(Audit, audit_id)
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit not found")
    return audit


TEAM_ROLES = ("Lead auditor", "Auditor", "Reviewer")


class TeamMemberIn(BaseModel):
    user_id: int
    team_role: str = "Auditor"


class TeamMemberOut(BaseModel):
    user_id: int
    name: str
    username: str
    team_role: str
    approval_level: str | None
    workplace_id: int | None
    added_at: datetime
    independence: str | None = None
    objectivity: list[str] = []


def _team_out(db: DBSession, audit_id: int) -> list[TeamMemberOut]:
    from app.domains.audit.proficiency.service import independence_status

    audit = db.get(Audit, audit_id)
    rows = db.execute(select(AuditTeamMember, User).join(User, User.id == AuditTeamMember.user_id)
                      .where(AuditTeamMember.audit_id == audit_id)).all()
    order = {r: i for i, r in enumerate(TEAM_ROLES)}
    out = []
    for m, u in rows:
        declared, issues = independence_status(db, audit, u.id)
        out.append(TeamMemberOut(user_id=u.id, name=u.full_name or u.username, username=u.username,
                                 team_role=m.team_role, approval_level=u.review_level.value if u.review_level else None,
                                 workplace_id=u.work_entity_id, added_at=m.added_at, independence=declared,
                                 objectivity=issues))
    return sorted(out, key=lambda t: (order.get(t.team_role, 9), t.name.lower()))


@router.get("/{audit_id}/team", response_model=list[TeamMemberOut])
def get_team(audit_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> list:
    """The engagement team. Team members work on the audit even when it belongs to another port."""
    ensure_can_view(db, user, "audit", db.get(Audit, audit_id))
    return _team_out(db, audit_id)


@router.get("/{audit_id}/team-candidates")
def team_candidates(audit_id: int, db: DBSession = Depends(get_db), user: User = WriteAudit) -> list[dict]:
    ensure_can_view(db, user, "audit", db.get(Audit, audit_id))
    rows = db.execute(select(User).where(User.is_active.is_(True), User.role.in_((Role.Admin, Role.Auditor)))
                      .order_by(User.full_name, User.username)).scalars()
    return [{"id": u.id, "name": u.full_name or u.username, "username": u.username,
             "approval_level": u.review_level.value if u.review_level else None} for u in rows]


@router.post("/{audit_id}/team", response_model=list[TeamMemberOut])
def add_team_member(audit_id: int, payload: TeamMemberIn, request: Request, db: DBSession = Depends(get_db),
                    user: User = WriteAudit) -> list:
    """Add or change a team member (audit staff only; one Lead auditor per engagement)."""
    from app.core.deps import ensure_perm
    from app.core.errors import field_error

    ensure_perm(user, "audit.create")
    audit = db.get(Audit, audit_id)
    ensure_can_view(db, user, "audit", audit)
    if audit.status == AuditStatus.Closed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The audit is closed")
    if payload.team_role not in TEAM_ROLES:
        raise field_error("team_role", f"choose one of: {', '.join(TEAM_ROLES)}")
    member = db.get(User, payload.user_id)
    if member is None or not member.is_active or member.role not in (Role.Admin, Role.Auditor):
        raise field_error("user_id", "choose an active member of audit staff")
    if payload.team_role == "Lead auditor":
        for m in db.execute(select(AuditTeamMember).where(AuditTeamMember.audit_id == audit_id,
                                                           AuditTeamMember.team_role == "Lead auditor")).scalars():
            if m.user_id != member.id:
                m.team_role = "Auditor"
    row = db.get(AuditTeamMember, (audit_id, member.id))
    if row is None:
        db.add(AuditTeamMember(audit_id=audit_id, user_id=member.id, team_role=payload.team_role, added_by=user.id))
    else:
        row.team_role = payload.team_role
    db.flush()
    from app.domains.audit.proficiency.service import objectivity_issues

    for issue in objectivity_issues(db, audit, member.id):
        log_record_history(db, record_type="audit", record_id=audit_id, user_id=user.id, request=request,
                           action=f"OBJECTIVITY: {member.full_name or member.username} - {issue}")
    log_action(db, user_id=user.id, request=request,
               action=f"AUDIT_TEAM_SET audit={audit_id} user={member.id} role={payload.team_role}")
    log_record_history(db, record_type="audit", record_id=audit_id, user_id=user.id, request=request,
                       action=f"TEAM: {member.full_name or member.username} as {payload.team_role}")
    db.commit()
    return _team_out(db, audit_id)


@router.delete("/{audit_id}/team/{user_id}", response_model=list[TeamMemberOut])
def remove_team_member(audit_id: int, user_id: int, request: Request, db: DBSession = Depends(get_db),
                       user: User = WriteAudit) -> list:
    from app.core.deps import ensure_perm

    ensure_perm(user, "audit.create")
    audit = db.get(Audit, audit_id)
    ensure_can_view(db, user, "audit", audit)
    row = db.get(AuditTeamMember, (audit_id, user_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not on the team")
    if row.team_role == "Lead auditor":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Choose another Lead auditor before removing the current one")
    db.delete(row)
    gone = db.get(User, user_id)
    log_action(db, user_id=user.id, request=request, action=f"AUDIT_TEAM_REMOVE audit={audit_id} user={user_id}")
    log_record_history(db, record_type="audit", record_id=audit_id, user_id=user.id, request=request,
                       action=f"TEAM: {(gone.full_name or gone.username) if gone else user_id} removed")
    db.commit()
    return _team_out(db, audit_id)


@router.get("/{audit_id}/auditees", response_model=list[AuditeeOut])
def list_auditees(audit_id: int, db: DBSession = Depends(get_db), _: User = WriteAudit) -> list[AuditeeOut]:
    _audit_or_404(db, audit_id)
    rows = db.execute(
        select(AuditAuditee, User)
        .join(User, User.id == AuditAuditee.user_id)
        .where(AuditAuditee.audit_id == audit_id)
        .order_by(User.username)
    ).all()
    return [
        AuditeeOut(
            user_id=u.id, username=u.username, full_name=u.full_name, email=u.email, assigned_at=link.assigned_at
        )
        for link, u in rows
    ]


@router.post("/{audit_id}/auditees", response_model=list[AuditeeOut], status_code=status.HTTP_201_CREATED)
def assign_auditee(
    audit_id: int,
    payload: AuditeeAssign,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = WriteAudit,
) -> list[AuditeeOut]:
    _audit_or_404(db, audit_id)
    target = db.get(User, payload.user_id)
    if target is None or target.role != Role.Auditee:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is not an Auditee account")
    if db.get(AuditAuditee, (audit_id, target.id)) is None:
        db.add(AuditAuditee(audit_id=audit_id, user_id=target.id, assigned_by=user.id))
        log_action(db, user_id=user.id, action=f"AUDIT_AUDITEE_ADD audit={audit_id} user={target.id}", request=request)
        log_record_history(
            db,
            record_type="audit",
            record_id=audit_id,
            user_id=user.id,
            action=f"AUDITEE ASSIGNED {target.username}",
            request=request,
        )
        db.commit()
    return list_auditees(audit_id, db, user)


@router.delete("/{audit_id}/auditees/{user_id}", response_model=list[AuditeeOut])
def remove_auditee(
    audit_id: int,
    user_id: int,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = WriteAudit,
) -> list[AuditeeOut]:
    _audit_or_404(db, audit_id)
    link = db.get(AuditAuditee, (audit_id, user_id))
    if link is not None:
        db.delete(link)
        log_action(db, user_id=user.id, action=f"AUDIT_AUDITEE_REMOVE audit={audit_id} user={user_id}", request=request)
        log_record_history(
            db,
            record_type="audit",
            record_id=audit_id,
            user_id=user.id,
            action=f"AUDITEE REMOVED user#{user_id}",
            request=request,
        )
        db.commit()
    return list_auditees(audit_id, db, user)
