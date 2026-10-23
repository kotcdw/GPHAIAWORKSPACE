"""The records people collaborate on: how each is loaded, who may read it, and how it is named."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.core.enums import Role
from app.platform.users.models import User

GRC = ("grc.view", "grc.manage", "grc.risk", "grc.compliance", "grc.policy", "grc.policy_approve", "grc.assets")

LABEL = {"audit": "Audit", "finding": "Issue", "capa": "Action", "assurance_plan": "Assurance Plan",
         "audit_report": "Report", "erm_risk": "Enterprise risk", "entity_unit": "Auditable entity",
         "risk_assessment": "Risk assessment", "control_test": "Control test", "quality_review": "Quality review",
         "strategic_objective": "Strategic objective", "organization": "Org unit"}


def model_for(record_type: str):  # noqa: ANN201
    from app.core.access import _model_for

    m = _model_for(record_type)
    if m is not None:
        return m
    if record_type == "erm_risk":
        from app.domains.grc.risk.models import EnterpriseRisk

        return EnterpriseRisk
    if record_type == "entity_unit":
        from app.domains.assurance.planning.models import EntityUnit

        return EntityUnit
    if record_type == "risk_assessment":
        from app.domains.assurance.universe.models import AuditRiskAssessment

        return AuditRiskAssessment
    return None


COMMENTABLE = ("audit", "finding", "capa", "assurance_plan", "audit_report", "erm_risk", "entity_unit",
               "risk_assessment")


def can_read(db: DBSession, user: User, record_type: str, obj) -> bool:  # noqa: ANN001
    from app.core.access import can_view
    from app.core.permissions import has_perm

    if obj is None:
        return False
    if record_type == "erm_risk":
        return user.role == Role.Admin or has_perm(user, *GRC)
    if record_type in ("entity_unit", "risk_assessment", "assurance_plan", "control_test", "quality_review",
                       "strategic_objective", "organization"):
        return user.role in (Role.Admin, Role.Auditor)
    if record_type == "audit_report":
        from app.domains.audit.audits.models import Audit

        return can_view(db, user, "audit", db.get(Audit, obj.audit_id))
    return can_view(db, user, record_type, obj)


def load(db: DBSession, user: User, record_type: str, record_id: int):  # noqa: ANN201
    """The record, or 404 when it does not exist or the person may not read it."""
    if record_type not in COMMENTABLE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown record type")
    obj = db.get(model_for(record_type), record_id)
    if not can_read(db, user, record_type, obj):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")
    return obj


def name(record_type: str, obj) -> tuple[str, str]:  # noqa: ANN001
    """(reference, title) shown on chips and in notifications."""
    if record_type == "audit":
        return f"AUD-{obj.id:04d}", obj.title
    if record_type == "finding":
        return f"ISS-{obj.id:04d}", obj.title
    if record_type == "capa":
        return obj.capa_ref, obj.title
    if record_type == "assurance_plan":
        return obj.plan_ref, obj.title
    if record_type == "audit_report":
        return obj.report_ref, obj.title
    if record_type == "erm_risk":
        return obj.ref, obj.title
    if record_type == "entity_unit":
        return obj.code, obj.name
    if record_type == "risk_assessment":
        return obj.ref, obj.name
    if record_type == "control_test":
        return obj.ref, "Control test"
    return str(getattr(obj, "ref", "") or f"#{obj.id}"), str(getattr(obj, "title", "") or getattr(obj, "name", ""))
