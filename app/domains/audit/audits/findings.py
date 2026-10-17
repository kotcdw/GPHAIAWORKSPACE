"""Finding routes (nested under an audit)."""

from __future__ import annotations

import json
from datetime import datetime, time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.access import ensure_can_view
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user, require_role
from app.core.enums import AuditStatus, CapaStatus, FindingStatus, Role
from app.core.errors import field_error
from app.core.history import log_record_history
from app.core.schemas import MessageOut
from app.domains.audit.audits.models import Audit, Finding
from app.domains.audit.audits.schemas import (
    ClientResponse,
    FindingCreate,
    FindingOut,
    FindingUpdate,
    ManagementResponse,
)
from app.platform.users.models import User

router = APIRouter(tags=["findings"])


def _get_audit_or_404(db: DBSession, audit_id: int) -> Audit:
    audit = db.get(Audit, audit_id)
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit not found")
    return audit


def _ensure_audit_open(audit: Audit) -> None:
    if audit.status == AuditStatus.Closed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The audit is closed; findings are locked")


_ISSUE_TEXT = ("criteria", "condition", "cause", "effect", "recommendation")


def _apply_issue_fields(db: DBSession, finding: Finding, payload, audit_id: int) -> list[str]:  # noqa: ANN001
    """Copy the issue attributes (5 Cs, 5 Whys, control link) onto ``finding``."""
    changed: list[str] = []
    for name in _ISSUE_TEXT:
        value = getattr(payload, name, None)
        if value is not None:
            setattr(finding, name, value)
            changed.append(name)
    if payload.root_cause_whys is not None:
        finding.root_cause_whys = json.dumps([w.strip() for w in payload.root_cause_whys if w and w.strip()])
        changed.append("root_cause_whys")
    if payload.control_id is not None:
        from app.domains.audit.rcm.models import Control, Objective

        control = db.get(Control, payload.control_id)
        if control is None or db.get(Objective, control.objective_id).audit_id != audit_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Control does not belong to this audit")
        finding.control_id = control.id
        changed.append("control_id")
    if payload.criterion_id is not None:
        from app.domains.audit.methodology.models import Criterion

        crit = db.get(Criterion, payload.criterion_id)
        if crit is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown criterion")
        finding.criterion_id = crit.id
        changed.append("criterion_id")
    if "custom_fields" in payload.model_fields_set and payload.custom_fields is not None:
        from app.platform.customfields.router import clean_values

        finding.custom_fields = json.dumps(clean_values(db, "findings", payload.custom_fields,
                                                        json.loads(finding.custom_fields or "{}")))
        changed.append("custom fields")
    return changed


def _issue_type(value: str | None) -> str | None:
    from app.core.appconfig import cfg

    if value is None or not value.strip():
        return None
    types = {t.lower(): t for t in (cfg("finding_issue_types") or [])}
    if value.strip().lower() not in types:
        raise field_error("issue_type", f"must be one of: {', '.join(types.values())}")
    return types[value.strip().lower()]


def _signoffs(db: DBSession, findings: list[Finding]) -> None:
    from app.domains.audit.audits.issue_tracker import signoffs_map

    dots = signoffs_map(db, findings)
    for f in findings:
        f.signoffs = dots.get(f.id, [])


def _get_finding_or_404(db: DBSession, finding_id: int) -> Finding:
    finding = db.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")
    return finding


@router.get("/api/audits/{audit_id}/findings", response_model=list[FindingOut])
def list_findings(
    audit_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)
) -> list[Finding]:
    ensure_can_view(db, user, "audit", db.get(Audit, audit_id))
    from app.domains.issues.capa.closure import remediation_summary

    rows = list(
        db.execute(select(Finding).where(Finding.audit_id == audit_id).order_by(Finding.created_at.desc()))
        .scalars()
        .all()
    )
    if user.role not in (Role.Admin, Role.Auditor):  # auditees see published issues only
        rows = [f for f in rows if f.published]
    for f in rows:
        f.remediation = remediation_summary(db, f)
    _signoffs(db, rows)
    return rows


@router.post(
    "/api/audits/{audit_id}/findings",
    response_model=FindingOut,
    status_code=status.HTTP_201_CREATED,
)
def create_finding(
    audit_id: int,
    payload: FindingCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_role(Role.Admin, Role.Auditor)),
) -> Finding:
    from app.core.deps import ensure_perm

    ensure_perm(user, "audit.findings")
    _ensure_audit_open(_get_audit_or_404(db, audit_id))
    finding = Finding(
        audit_id=audit_id,
        title=payload.title,
        description=payload.description,
        risk_rating=payload.risk_rating,
        status=payload.status,
        assigned_owner_email=str(payload.assigned_owner_email) if payload.assigned_owner_email else None,
        issue_type=_issue_type(payload.issue_type),
        custom_fields="{}",
        created_by=user.id,
    )
    if "custom_fields" not in payload.model_fields_set:
        payload.custom_fields = {}
        payload.model_fields_set.add("custom_fields")
    _apply_issue_fields(db, finding, payload, audit_id)
    db.add(finding)
    db.flush()
    from app.platform.automations.engine import emit, finding_context

    emit(db, "finding.created", "finding", finding.id, finding_context(db, finding))
    log_action(
        db,
        user_id=user.id,
        action=f"FINDING_CREATE id={finding.id} audit={audit_id} risk={finding.risk_rating.value}",
        request=request,
    )
    log_record_history(
        db,
        record_type="audit",
        record_id=audit_id,
        user_id=user.id,
        action=f"FINDING ADDED #{finding.id} {finding.title}",
        request=request,
    )
    db.commit()
    db.refresh(finding)
    return finding


@router.get("/api/findings/{finding_id}", response_model=FindingOut)
def get_finding(
    finding_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)
) -> Finding:
    finding = db.get(Finding, finding_id)
    ensure_can_view(db, user, "finding", finding)
    from app.domains.issues.capa.closure import remediation_summary

    finding.remediation = remediation_summary(db, finding)
    _signoffs(db, [finding])
    return finding


@router.patch("/api/findings/{finding_id}", response_model=FindingOut)
def update_finding(
    finding_id: int,
    payload: FindingUpdate,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_role(Role.Admin, Role.Auditor)),
) -> Finding:
    from app.core.deps import ensure_perm

    ensure_perm(user, "audit.findings")
    finding = _get_finding_or_404(db, finding_id)
    _ensure_audit_open(_get_audit_or_404(db, finding.audit_id))
    changes: list[str] = []
    if payload.title is not None:
        finding.title = payload.title
        changes.append("title")
    if payload.description is not None:
        finding.description = payload.description
        changes.append("description")
    if payload.risk_rating is not None:
        finding.risk_rating = payload.risk_rating
        changes.append(f"risk_rating={payload.risk_rating.value}")
    if payload.status is not None:
        if payload.status == FindingStatus.Closed and finding.status != FindingStatus.Closed:
            from app.domains.issues.capa.closure import closure_blockers

            blockers = closure_blockers(db, finding)
            if blockers:
                raise field_error("status", "cannot be Closed yet: " + "; ".join(blockers))
        finding.status = payload.status
        changes.append(f"status={payload.status.value}")
    if payload.assigned_owner_email is not None:
        finding.assigned_owner_email = str(payload.assigned_owner_email)
        changes.append("assigned_owner_email")
    if "issue_type" in payload.model_fields_set:
        finding.issue_type = _issue_type(payload.issue_type)
        changes.append(f"issue_type={finding.issue_type}")
    changes.extend(_apply_issue_fields(db, finding, payload, finding.audit_id))

    log_action(db, user_id=user.id, action=f"FINDING_UPDATE id={finding.id} [{', '.join(changes)}]", request=request)
    log_record_history(
        db,
        record_type="audit",
        record_id=finding.audit_id,
        user_id=user.id,
        action=f"FINDING UPDATED #{finding.id} [{', '.join(changes)}]",
        request=request,
    )
    db.commit()
    db.refresh(finding)
    return finding


@router.delete("/api/findings/{finding_id}", response_model=MessageOut)
def delete_finding(
    finding_id: int,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_role(Role.Admin)),
) -> MessageOut:
    finding = _get_finding_or_404(db, finding_id)
    _ensure_audit_open(_get_audit_or_404(db, finding.audit_id))
    if finding.status != FindingStatus.Open:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only Open findings can be deleted; findings under remediation or closed are retained",
        )
    audit_id, title = finding.audit_id, finding.title
    db.delete(finding)
    log_action(db, user_id=user.id, action=f"FINDING_DELETE id={finding_id} title={title}", request=request)
    log_record_history(
        db,
        record_type="audit",
        record_id=audit_id,
        user_id=user.id,
        action=f"FINDING DELETED #{finding_id} {title}",
        request=request,
    )
    db.commit()
    return MessageOut(message=f"Finding {finding_id} deleted")

@router.post("/api/findings/{finding_id}/response", response_model=FindingOut)
def respond_to_finding(
    finding_id: int,
    payload: ManagementResponse,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_active_user),
) -> Finding:
    """GPHA Management Response (action plan, responsible officer, target date) - typically from the auditee."""
    from app.core.appconfig import cfg
    from app.core.enums import ReportStatus, utcnow
    from app.domains.audit.reports.models import AuditReport

    finding = db.get(Finding, finding_id)
    ensure_can_view(db, user, "finding", finding)
    _ensure_audit_open(_get_audit_or_404(db, finding.audit_id))
    officer = (payload.responsible_officer or "").strip() or None
    if cfg("management_response_requires_owner_and_date"):
        if not officer:
            raise field_error("responsible_officer", "name the officer responsible for the action plan")
        if payload.target_date is None:
            raise field_error("target_date", "give the date by which the action will be implemented")
    finding.management_response = payload.management_response.strip()
    finding.responsible_officer = officer
    finding.target_date = datetime.combine(payload.target_date, time()) if payload.target_date else None
    finding.management_response_by, finding.management_response_at = user.id, utcnow()
    synced = _sync_action(db, finding, user, request)

    report = db.execute(select(AuditReport).where(AuditReport.audit_id == finding.audit_id)).scalars().first()
    if report is not None and report.status == ReportStatus.ManagementReview and report.response_received_at is None:
        report.response_received_at = utcnow()
    log_action(db, user_id=user.id, action=f"FINDING_RESPONSE id={finding.id}", request=request)
    log_record_history(
        db,
        record_type="audit",
        record_id=finding.audit_id,
        user_id=user.id,
        action=f"MANAGEMENT RESPONSE on finding #{finding.id} by {user.username}"
        + (f" (officer {officer}, target {payload.target_date})" if officer or payload.target_date else "")
        + (f"; action {synced} updated" if synced else ""),
        request=request,
    )
    db.commit()
    db.refresh(finding)
    return finding


def _sync_action(db: DBSession, finding: Finding, user: User, request: Request) -> str | None:
    """Carry an updated action plan / officer / target date onto the finding's open corrective action."""
    from app.domains.issues.capa.models import Capa

    capa = db.execute(
        select(Capa).where(Capa.source_type == "finding", Capa.source_id == finding.id)
    ).scalars().first()
    if capa is None or capa.status == CapaStatus.Closed or capa.implemented_at is not None:
        return None
    capa.corrective_action = finding.management_response or capa.corrective_action
    if finding.target_date:
        from app.domains.issues.capa.timeline import change_due_date

        change_due_date(db, capa, finding.target_date, user_id=user.id, request=request,
                        reason=f"Management response on issue #{finding.id} revised",
                        source="Agreed action plan")
    if finding.responsible_officer and "@" in finding.responsible_officer:
        capa.owner_email = finding.responsible_officer
    log_record_history(db, record_type="capa", record_id=capa.id, user_id=user.id, request=request,
                       action=f"UPDATED from the management response on issue #{finding.id}")
    return capa.capa_ref


@router.post("/api/findings/{finding_id}/client-response", response_model=FindingOut)
def client_response(
    finding_id: int,
    payload: ClientResponse,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_active_user),
) -> Finding:
    """The Audit Client (Head of Department) response. Audit staff confirm it at the exit meeting; once confirmed,
    only audit staff can change it (and must confirm it again)."""
    from app.core.enums import utcnow

    finding = db.get(Finding, finding_id)
    ensure_can_view(db, user, "finding", finding)
    _ensure_audit_open(_get_audit_or_404(db, finding.audit_id))
    staff = user.role in (Role.Admin, Role.Auditor)
    if finding.client_confirmed_at_exit and not staff:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="This response was confirmed at the exit meeting; ask the audit team to change it")
    if payload.confirmed_at_exit and not staff:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="The audit team confirms responses at the exit meeting")
    finding.client_response = payload.client_response.strip()
    finding.client_response_by, finding.client_response_at = user.id, utcnow()
    finding.client_confirmed_at_exit = bool(payload.confirmed_at_exit)
    log_action(db, user_id=user.id, action=f"FINDING_CLIENT_RESPONSE id={finding.id}", request=request)
    log_record_history(
        db, record_type="audit", record_id=finding.audit_id, user_id=user.id, request=request,
        action=f"AUDIT CLIENT RESPONSE on finding #{finding.id} by {user.username}"
        + (" (confirmed at the exit meeting)" if finding.client_confirmed_at_exit else ""),
    )
    db.commit()
    db.refresh(finding)
    return finding
