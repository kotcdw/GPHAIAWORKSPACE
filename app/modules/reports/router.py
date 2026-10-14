"""Audit report routes: build, comment, review, approve, issue and export."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.access import assigned_audit_ids, is_privileged
from app.core.appconfig import cfg
from app.core.approvalsvc import sign
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user, require_module_tier
from app.core.enums import ReportStatus, ReviewLevel, Role, utcnow
from app.core.history import log_record_history
from app.core.refs import next_reference
from app.core.schemas import ESignRequest
from app.modules.audits.models import Audit, AuditAuditee, Finding
from app.modules.notifications.service import notify, notify_many, user_id_by_email, user_ids_with_level
from app.modules.reports import service
from app.modules.reports.models import AuditReport
from app.modules.reports.schemas import ManagementComments, ReportOut, ReportUpdate, SignoffOut
from app.modules.users.models import User

router = APIRouter(tags=["reports"])

Staff = Depends(require_module_tier("reports", Role.Admin, Role.Auditor))
_AUDITEE_STAGES = (ReportStatus.ManagementReview, ReportStatus.Issued)
_EDITABLE = ("title", "overall_rating", "executive_summary", "background", "scope_objectives", "methodology",
             "overall_opinion", "distribution_list")


# ------------------------------------------------------------------ helpers


def _audit_or_404(db: DBSession, audit_id: int) -> Audit:
    audit = db.get(Audit, audit_id)
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit not found")
    return audit


def _report_or_404(db: DBSession, report_id: int, user: User) -> AuditReport:
    report = db.get(AuditReport, report_id)
    if report is None or not _can_view(db, user, report):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return report


def _can_view(db: DBSession, user: User, report: AuditReport) -> bool:
    if is_privileged(user):
        return True
    from app.core.permissions import has_perm

    if report.status == ReportStatus.Issued and has_perm(user, "governance.view"):
        return True
    return report.status in _AUDITEE_STAGES and report.audit_id in assigned_audit_ids(db, user)


def _blockers(db: DBSession, report: AuditReport) -> list[str]:
    """What must be fixed before the report can go to review."""
    problems = []
    if report.overall_rating is None:
        problems.append("Choose an overall rating.")
    if not report.executive_summary.strip():
        problems.append("Write the executive summary.")
    if not report.overall_opinion.strip():
        problems.append("Write the overall opinion.")
    findings = db.execute(select(Finding).where(Finding.audit_id == report.audit_id)).scalars().all()
    no_response = [f.id for f in findings if not (f.management_response or "").strip()]
    if no_response and cfg("require_management_response_for_review"):
        problems.append(f"{len(no_response)} finding(s) still need a management response.")
    return problems


def _auditee_ids(db: DBSession, audit_id: int) -> list[int]:
    return list(db.execute(select(AuditAuditee.user_id).where(AuditAuditee.audit_id == audit_id)).scalars())


def _out(db: DBSession, report: AuditReport, user: User) -> ReportOut:
    out = ReportOut.model_validate(report)
    staff = is_privileged(user)
    level = user.review_level
    out.can_edit = staff and report.status == ReportStatus.Draft
    out.can_comment = report.status == ReportStatus.ManagementReview and (
        staff or report.audit_id in assigned_audit_ids(db, user)
    )
    out.can_manager_review = (
        staff and report.status == ReportStatus.ManagerReview
        and level in (ReviewLevel.Manager, ReviewLevel.CAE) and report.created_by != user.id
    )
    out.can_cae_approve = (
        staff and report.status == ReportStatus.CAEApproval and level == ReviewLevel.CAE
        and user.id not in (report.created_by, report.manager_reviewed_by)
    )
    out.blockers = _blockers(db, report) if staff and report.status != ReportStatus.Issued else []
    out.signoffs = [SignoffOut(**s) for s in service.signoffs(db, report)]
    return out


def _history(db: DBSession, report: AuditReport, user: User, action: str, request: Request) -> None:
    log_record_history(db, record_type="audit_report", record_id=report.id, user_id=user.id, action=action,
                       request=request)
    log_action(db, user_id=user.id, action=f"REPORT_{action.split()[0]} id={report.id}", request=request)


# ------------------------------------------------------------------ read / create / edit


@router.get("/api/audits/{audit_id}/report", response_model=ReportOut)
def get_audit_report(audit_id: int, db: DBSession = Depends(get_db),
                     user: User = Depends(require_active_user)) -> ReportOut:
    report = db.execute(select(AuditReport).where(AuditReport.audit_id == audit_id)).scalar_one_or_none()
    if report is None or not _can_view(db, user, report):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No report for this audit yet")
    return _out(db, report, user)


@router.post("/api/audits/{audit_id}/report", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
def create_audit_report(audit_id: int, request: Request, db: DBSession = Depends(get_db),
                        user: User = Staff) -> ReportOut:
    audit = _audit_or_404(db, audit_id)
    if db.execute(select(AuditReport.id).where(AuditReport.audit_id == audit_id)).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This audit already has a report")
    report = AuditReport(
        audit_id=audit.id,
        report_ref=next_reference(db, "RPT"),
        title=f"Internal Audit Report: {audit.title}"[:255],
        status=ReportStatus.Draft,
        background=audit.description or "",
        scope_objectives=audit.scope or "",
        methodology=cfg("report_methodology"),
        created_by=user.id,
    )
    db.add(report)
    db.flush()
    _history(db, report, user, "CREATED draft", request)
    db.commit()
    db.refresh(report)
    return _out(db, report, user)


@router.get("/api/reports/{report_id}", response_model=ReportOut)
def get_report(report_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> ReportOut:
    return _out(db, _report_or_404(db, report_id, user), user)


@router.patch("/api/reports/{report_id}", response_model=ReportOut)
def update_report(report_id: int, payload: ReportUpdate, request: Request, db: DBSession = Depends(get_db),
                  user: User = Staff) -> ReportOut:
    report = _report_or_404(db, report_id, user)
    if report.status != ReportStatus.Draft:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"The report can only be edited in Draft (now: {report.status.value})")
    changed = []
    for field in _EDITABLE:
        value = getattr(payload, field)
        if value is not None:
            setattr(report, field, value)
            changed.append(field)
    if changed:
        _history(db, report, user, f"UPDATED [{', '.join(changed)}]", request)
    db.commit()
    db.refresh(report)
    return _out(db, report, user)


@router.put("/api/reports/{report_id}/management-comments", response_model=ReportOut)
def save_management_comments(report_id: int, payload: ManagementComments, request: Request,
                             db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> ReportOut:
    report = _report_or_404(db, report_id, user)
    if report.status != ReportStatus.ManagementReview:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Management comments are only open while the report is with management")
    if not (is_privileged(user) or report.audit_id in assigned_audit_ids(db, user)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not an auditee of this audit")
    report.management_comments = payload.management_comments
    _history(db, report, user, "COMMENTED management comments saved", request)
    notify(db, report.created_by, f"Management comments on {report.report_ref}",
           f"{user.full_name or user.username} added comments to the draft report.",
           link_type="audit_report", link_id=report.id)
    db.commit()
    db.refresh(report)
    return _out(db, report, user)


# ------------------------------------------------------------------ workflow


@router.post("/api/reports/{report_id}/send-to-management", response_model=ReportOut)
def send_to_management(report_id: int, request: Request, db: DBSession = Depends(get_db),
                       user: User = Staff) -> ReportOut:
    report = _report_or_404(db, report_id, user)
    if report.status != ReportStatus.Draft:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only a draft can be sent to management")
    if report.overall_rating is None or not report.executive_summary.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Add the overall rating and executive summary before sending to management")
    report.status = ReportStatus.ManagementReview
    owners = [user_id_by_email(db, f.assigned_owner_email)
              for f in db.execute(select(Finding).where(Finding.audit_id == report.audit_id)).scalars()]
    notify_many(db, _auditee_ids(db, report.audit_id) + owners, f"Draft audit report for your comments: {report.title}",
                "Please review the draft report and add management comments and responses to each finding.",
                link_type="audit_report", link_id=report.id)
    _history(db, report, user, "SENT to management for comments", request)
    db.commit()
    db.refresh(report)
    return _out(db, report, user)


@router.post("/api/reports/{report_id}/submit-for-review", response_model=ReportOut)
def submit_for_review(report_id: int, request: Request, db: DBSession = Depends(get_db),
                      user: User = Staff) -> ReportOut:
    report = _report_or_404(db, report_id, user)
    if report.status not in (ReportStatus.Draft, ReportStatus.ManagementReview):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"The report is already in {report.status.value}")
    problems = _blockers(db, report)
    if problems:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Not ready for review: " + " ".join(problems))
    report.status = ReportStatus.ManagerReview
    notify_many(db, [u for u in user_ids_with_level(db, ReviewLevel.Manager, ReviewLevel.CAE) if u != user.id],
                f"Report to review: {report.report_ref}", f"{report.title} is ready for Audit Manager review.",
                link_type="audit_report", link_id=report.id)
    _history(db, report, user, "SUBMITTED for manager review", request)
    db.commit()
    db.refresh(report)
    return _out(db, report, user)


@router.post("/api/reports/{report_id}/manager-review", response_model=ReportOut)
def manager_review(report_id: int, payload: ESignRequest, request: Request, db: DBSession = Depends(get_db),
                   user: User = Staff) -> ReportOut:
    report = _report_or_404(db, report_id, user)
    if report.status != ReportStatus.ManagerReview:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The report is not awaiting manager review")
    if user.review_level not in (ReviewLevel.Manager, ReviewLevel.CAE):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Only an Audit Manager or the CAE can review a report")
    decision = payload.decision.value

    def _approve(_: DBSession) -> None:
        report.status = ReportStatus.CAEApproval
        report.manager_reviewed_by = user.id
        report.manager_reviewed_at = utcnow()

    sign(db, record_type="audit_report", record_id=report.id, user=user, password=payload.password,
         decision=decision, comment=payload.comment, request=request, on_approve=_approve,
         preparer_id=report.created_by)
    if decision == "Approve":
        notify_many(db, [u for u in user_ids_with_level(db, ReviewLevel.CAE) if u != user.id],
                    f"Report awaiting CAE approval: {report.report_ref}", report.title,
                    link_type="audit_report", link_id=report.id)
    else:
        report.status = ReportStatus.Draft
        notify(db, report.created_by, f"Report returned: {report.report_ref}",
               payload.comment or "The Audit Manager returned the report for changes.",
               link_type="audit_report", link_id=report.id)
    db.commit()
    db.refresh(report)
    return _out(db, report, user)


@router.post("/api/reports/{report_id}/cae-approve", response_model=ReportOut)
def cae_approve(report_id: int, payload: ESignRequest, request: Request, db: DBSession = Depends(get_db),
                user: User = Staff) -> ReportOut:
    report = _report_or_404(db, report_id, user)
    if report.status != ReportStatus.CAEApproval:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The report is not awaiting CAE approval")
    if user.review_level != ReviewLevel.CAE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the CAE can approve and issue a report")
    if user.id == report.manager_reviewed_by:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Segregation of duties: the manager reviewer cannot also give CAE approval")
    decision = payload.decision.value

    def _approve(session: DBSession) -> None:
        now = utcnow()
        report.cae_approved_by = user.id
        report.cae_approved_at = now
        report.issued_at = now
        report.status = ReportStatus.Issued
        report.issued_snapshot = service.take_snapshot(session, report)

    sign(db, record_type="audit_report", record_id=report.id, user=user, password=payload.password,
         decision=decision, comment=payload.comment, request=request, on_approve=_approve,
         preparer_id=report.created_by)
    if decision == "Approve":
        notify_many(db, _auditee_ids(db, report.audit_id) + [report.created_by, report.manager_reviewed_by],
                    f"Audit report issued: {report.title}", f"{report.report_ref} has been approved and issued.",
                    link_type="audit_report", link_id=report.id)
    else:
        report.status = ReportStatus.Draft
        notify_many(db, [report.created_by, report.manager_reviewed_by], f"Report returned by CAE: {report.report_ref}",
                    payload.comment or "The CAE returned the report for changes.",
                    link_type="audit_report", link_id=report.id)
        report.manager_reviewed_by = None
        report.manager_reviewed_at = None
    db.commit()
    db.refresh(report)
    return _out(db, report, user)


# ------------------------------------------------------------------ exports


_PRINT_CSP = "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'"


def _filename(report: AuditReport, ext: str) -> str:
    return f"{report.report_ref}{'' if report.status == ReportStatus.Issued else '-DRAFT'}.{ext}"


@router.get("/api/reports/{report_id}/export.docx")
def export_docx(report_id: int, request: Request, db: DBSession = Depends(get_db),
                user: User = Depends(require_active_user)) -> Response:
    report = _report_or_404(db, report_id, user)
    data = service.to_docx(db, report)
    log_action(db, user_id=user.id, action=f"REPORT_EXPORT id={report.id} format=docx", request=request)
    db.commit()
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{_filename(report, "docx")}"'},
    )


@router.get("/api/reports/{report_id}/print", response_class=HTMLResponse)
def print_view(report_id: int, request: Request, db: DBSession = Depends(get_db),
               user: User = Depends(require_active_user)) -> HTMLResponse:
    report = _report_or_404(db, report_id, user)
    log_action(db, user_id=user.id, action=f"REPORT_EXPORT id={report.id} format=print", request=request)
    db.commit()
    return HTMLResponse(
        service.to_html(db, report),
        headers={"Content-Security-Policy": _PRINT_CSP},
    )
