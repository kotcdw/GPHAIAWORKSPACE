"""AI Service endpoints. Every answer is a draft; nothing is saved to the record here."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.access import ensure_can_view
from app.core.database import get_db
from app.core.deps import csrf_protect, require_active_user, require_perm
from app.core.permissions import has_perm
from app.platform.users.models import User
from app.services.ai import service
from app.services.ai.models import AiRequest
from app.services.ai.providers import AiError

router = APIRouter(prefix="/api/ai", tags=["ai"])


class FindingDraftIn(BaseModel):
    notes: str = Field(default="", max_length=8000)


def _call(db: DBSession, user: User, request: Request, **kwargs) -> str:
    try:
        return service.run(db, user=user, request=request, **kwargs)
    except AiError as exc:
        raise HTTPException(status_code=503 if "turned off" not in str(exc) else 409, detail=str(exc)) from None


@router.get("/status")
def ai_status(user: User = Depends(require_active_user), db: DBSession = Depends(get_db)) -> dict:
    out = service.status()
    out["can_use"] = out["ready"] and has_perm(user, "ai.use")
    if not has_perm(user, "system.config", "system.technical"):
        for key in ("endpoint", "api_key_set", "problems", "providers"):
            out.pop(key, None)
    else:
        rows = db.execute(select(AiRequest.status, func.count()).group_by(AiRequest.status)).all()
        out["requests"] = {status: count for status, count in rows}
    return out


@router.post("/findings/{finding_id}/draft", dependencies=[Depends(csrf_protect)])
def draft_finding(finding_id: int, payload: FindingDraftIn, request: Request,
                  user: User = Depends(require_perm("ai.use")), db: DBSession = Depends(get_db)) -> dict:
    from app.domains.audit.audits.models import Finding

    finding = db.get(Finding, finding_id)
    ensure_can_view(db, user, "finding", finding)
    text = _call(db, user, request, feature="finding_draft", record_type="finding", record_id=finding.id,
                 prompt=service.finding_prompt(finding, finding.audit, payload.notes))
    try:
        return {"draft": service.parse_finding(text), "accept_required": True}
    except AiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None


@router.post("/reports/{report_id}/executive-summary", dependencies=[Depends(csrf_protect)])
def draft_summary(report_id: int, request: Request, user: User = Depends(require_perm("ai.use")),
                  db: DBSession = Depends(get_db)) -> dict:
    from app.domains.audit.audits.models import Audit, Finding
    from app.domains.audit.reports.models import AuditReport

    report = db.get(AuditReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Not found")
    audit = db.get(Audit, report.audit_id)
    ensure_can_view(db, user, "audit", audit)
    findings = db.execute(select(Finding).where(Finding.audit_id == audit.id)).scalars().all()
    text = _call(db, user, request, feature="report_summary", record_type="audit_report", record_id=report.id,
                 prompt=service.report_prompt(report, audit, findings))
    return {"draft": {"executive_summary": text}, "accept_required": True}


@router.post("/objectives/{objective_id}/risks", dependencies=[Depends(csrf_protect)])
def suggest_risks(objective_id: int, request: Request, user: User = Depends(require_perm("ai.use")),
                  db: DBSession = Depends(get_db)) -> dict:
    from app.domains.audit.audits.models import Audit
    from app.domains.audit.rcm.models import Objective

    objective = db.get(Objective, objective_id)
    if objective is None:
        raise HTTPException(status_code=404, detail="Not found")
    ensure_can_view(db, user, "audit", db.get(Audit, objective.audit_id))
    text = _call(db, user, request, feature="rcm_suggest", record_type="objective", record_id=objective.id,
                 prompt=service.rcm_prompt(objective, db.get(Audit, objective.audit_id)))
    try:
        return {"draft": {"risks": service.parse_rcm(text)}, "accept_required": True}
    except AiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
