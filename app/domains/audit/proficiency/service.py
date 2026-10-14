"""Declarations and CPD queries shared by the router, the fieldwork gate and automations."""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.appconfig import cfg
from app.domains.audit.proficiency.models import CpdRecord, Declaration


def annual_declared(db: DBSession, user_id: int, year: int) -> bool:
    return db.execute(select(Declaration.id).where(Declaration.user_id == user_id, Declaration.kind == "annual",
                                                   Declaration.year == year)).first() is not None


def engagement_declaration(db: DBSession, user_id: int, audit_id: int) -> Declaration | None:
    return db.execute(select(Declaration).where(Declaration.user_id == user_id, Declaration.kind == "engagement",
                                                Declaration.audit_id == audit_id)
                      .order_by(Declaration.signed_at.desc())).scalars().first()


def cpd_hours(db: DBSession, user_id: int, year: int) -> float:
    total = db.execute(select(func.coalesce(func.sum(CpdRecord.hours), 0)).where(
        CpdRecord.user_id == user_id, CpdRecord.activity_date >= datetime(year, 1, 1),
        CpdRecord.activity_date < datetime(year + 1, 1, 1))).scalar()
    return float(total or 0)


def engagement_team(db: DBSession, audit) -> list[int]:  # noqa: ANN001
    """People who must declare before fieldwork: the engagement creator and the plan's lead auditor."""
    ids = [audit.created_by]
    from app.domains.assurance.planning.models import PlanEngagement

    eng = db.execute(select(PlanEngagement).where(PlanEngagement.audit_id == audit.id)).scalars().first()
    if eng is not None and eng.lead_auditor_id:
        ids.append(eng.lead_auditor_id)
    return [i for i in dict.fromkeys(ids) if i]


def declaration_blockers(db: DBSession, audit) -> list[str]:  # noqa: ANN001
    from app.core.enums import utcnow
    from app.platform.users.models import User

    problems = []
    year = utcnow().year
    for uid in engagement_team(db, audit):
        user = db.get(User, uid)
        if user is None or not user.is_active:
            continue
        name = user.full_name or user.username
        if not annual_declared(db, uid, year):
            problems.append(f"{name} has not signed the {year} annual declaration")
        d = engagement_declaration(db, uid, audit.id)
        if d is None:
            problems.append(f"{name} has not declared independence for this engagement")
        elif d.review_status == "Pending review":
            problems.append(f"{name}'s declared conflict is awaiting review")
        elif d.review_status == "Reassigned":
            problems.append(f"{name} was reassigned because of a conflict; update the engagement team")
    return problems


def ensure_declarations(db: DBSession, audit) -> None:  # noqa: ANN001
    if not cfg("require_engagement_declaration"):
        return
    problems = declaration_blockers(db, audit)
    if problems:
        raise HTTPException(status_code=409, detail="Fieldwork cannot start (IIA GIAS 2 and 7.1 - independence): "
                                                    + "; ".join(problems))
