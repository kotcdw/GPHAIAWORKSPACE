"""Declarations and CPD queries shared by the router, the fieldwork gate and automations."""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.appconfig import cfg
from app.core.enums import utcnow
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
    """Everyone who must declare before fieldwork: the engagement creator, the plan's lead auditor and every member
    of the engagement team."""
    from app.domains.assurance.planning.models import PlanEngagement
    from app.domains.audit.audits.models import AuditTeamMember

    ids = [audit.created_by]
    eng = db.execute(select(PlanEngagement).where(PlanEngagement.audit_id == audit.id)).scalars().first()
    if eng is not None and eng.lead_auditor_id:
        ids.append(eng.lead_auditor_id)
    ids += list(db.execute(select(AuditTeamMember.user_id).where(AuditTeamMember.audit_id == audit.id)).scalars())
    return [i for i in dict.fromkeys(ids) if i]


# ---------------------------------------------------------------- objectivity: rotation and cooling-off (GIAS 2.2)


def _year(db: DBSession, audit) -> int:  # noqa: ANN001
    from app.domains.assurance.planning.models import AssurancePlan

    plan = db.get(AssurancePlan, audit.plan_id) if audit.plan_id else None
    return plan.fiscal_year if plan is not None else audit.created_at.year


def _entities(db: DBSession, audit) -> set[int]:  # noqa: ANN001
    from app.domains.assurance.universe.models import AuditEntity

    ids = set(db.execute(select(AuditEntity.entity_id).where(AuditEntity.audit_id == audit.id)).scalars())
    return ids | ({audit.entity_unit_id} if audit.entity_unit_id else set())


def _leads(db: DBSession, audit) -> set[int]:  # noqa: ANN001
    from app.domains.assurance.planning.models import PlanEngagement
    from app.domains.audit.audits.models import AuditTeamMember

    ids = set(db.execute(select(AuditTeamMember.user_id).where(AuditTeamMember.audit_id == audit.id,
                                                               AuditTeamMember.team_role == "Lead auditor")).scalars())
    eng = db.execute(select(PlanEngagement).where(PlanEngagement.audit_id == audit.id)).scalars().first()
    return ids | ({eng.lead_auditor_id} if eng is not None and eng.lead_auditor_id else set())


def _audit_units(db: DBSession, audit) -> set[int]:  # noqa: ANN001
    """The org units the engagement looks at, with every unit above them."""
    from app.domains.assurance.universe.models import EntityOrgUnit
    from app.platform.organizations.models import Organization

    start = {u for u in (audit.organization_id, audit.port_entity_id) if u}
    entities = _entities(db, audit)
    if entities:
        start |= set(db.execute(select(EntityOrgUnit.org_id).where(EntityOrgUnit.entity_id.in_(entities))).scalars())
    seen: set[int] = set()
    for unit_id in start:
        while unit_id and unit_id not in seen:
            seen.add(unit_id)
            org = db.get(Organization, unit_id)
            unit_id = org.parent_id if org is not None else None
    return seen


def objectivity_issues(db: DBSession, audit, user_id: int) -> list[str]:  # noqa: ANN001
    """Automatic threats to objectivity for one team member: leading the same entity too many years in a row, or
    having worked in an audited unit within the cooling-off period."""
    from datetime import timedelta

    from app.domains.assurance.planning.models import PlanEngagement
    from app.domains.audit.audits.models import Audit, AuditTeamMember
    from app.domains.audit.proficiency.models import AuditorPriorRole
    from app.platform.organizations.models import Organization

    issues = []
    years = int(cfg("auditor_rotation_years") or 0)
    entities = _entities(db, audit)
    if years and entities and user_id in _leads(db, audit):
        from app.domains.assurance.universe.models import AuditEntity

        others = set(db.execute(select(AuditEntity.audit_id).where(AuditEntity.entity_id.in_(entities))).scalars())
        others |= set(db.execute(select(Audit.id).where(Audit.entity_unit_id.in_(entities))).scalars())
        others.discard(audit.id)
        led = set(db.execute(select(AuditTeamMember.audit_id).where(
            AuditTeamMember.user_id == user_id, AuditTeamMember.team_role == "Lead auditor",
            AuditTeamMember.audit_id.in_(others))).scalars()) if others else set()
        led |= set(db.execute(select(PlanEngagement.audit_id).where(
            PlanEngagement.lead_auditor_id == user_id, PlanEngagement.audit_id.in_(others))).scalars()) if others \
            else set()
        led_years = {_year(db, a) for a in (db.get(Audit, i) for i in led) if a is not None}
        current, run = _year(db, audit), 0
        while current - run - 1 in led_years:
            run += 1
        if run >= years:
            issues.append(f"Led audits of this entity in the previous {run} consecutive years (rotation after {years})")
    months = int(cfg("cooling_off_months") or 0)
    if months:
        units = _audit_units(db, audit)
        cutoff = (utcnow() - timedelta(days=round(months * 30.44))).date()
        for r in db.execute(select(AuditorPriorRole).where(AuditorPriorRole.user_id == user_id)).scalars():
            if r.org_unit_id in units and (r.to_date is None or r.to_date >= cutoff):
                org = db.get(Organization, r.org_unit_id)
                until = f"until {r.to_date:%d %b %Y}" if r.to_date else "currently"
                issues.append(f"Worked in {org.name if org else 'an audited unit'} as {r.role} {until} "
                              f"(cooling-off {months} months)")
    return issues


def independence_status(db: DBSession, audit, user_id: int) -> tuple[str, list[str]]:  # noqa: ANN001
    """The member's engagement declaration status and any objectivity threat not yet cleared by a reviewer."""
    d = engagement_declaration(db, user_id, audit.id)
    issues = objectivity_issues(db, audit, user_id)
    if d is None:
        return "Not declared", issues
    if d.review_status == "Pending review":
        return "Conflict pending review", issues
    if d.review_status == "Reassigned":
        return "Reassigned", issues
    if d.review_status == "Cleared":
        return "Cleared", [] if d.has_conflict else issues
    return "Declared", issues


def declaration_blockers(db: DBSession, audit) -> list[str]:  # noqa: ANN001
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
        status, issues = independence_status(db, audit, uid)
        if status == "Not declared":
            problems.append(f"{name} has not declared independence for this engagement")
        elif status == "Conflict pending review":
            problems.append(f"{name}'s declared conflict is awaiting review")
        elif status == "Reassigned":
            problems.append(f"{name} was reassigned because of a conflict; update the engagement team")
        problems += [f"{name}: {i}; declare it as a conflict for the reviewer to clear, or change the team"
                     for i in issues]
    return problems


def ensure_declarations(db: DBSession, audit) -> None:  # noqa: ANN001
    if not cfg("require_engagement_declaration"):
        return
    problems = declaration_blockers(db, audit)
    if problems:
        raise HTTPException(status_code=409, detail="Fieldwork cannot start (IIA GIAS 2 and 7.1 - independence): "
                                                    + "; ".join(problems))
