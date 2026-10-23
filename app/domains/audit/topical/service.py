"""Topical Requirements on an engagement: what applies, what is still open, and the closure rule."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.domains.audit.topical.models import (
    EngagementTopical,
    EngagementTopicalItem,
    TopicalRequirement,
    TopicalRequirementItem,
)

TRIGGERS = ["Subject of a planned engagement", "Identified during the engagement", "Engagement request"]
OUTCOMES = ["Assessed", "Excluded"]
CONCLUSIONS = ["No exceptions", "Exceptions noted"]
AREAS = ["Governance", "Risk management", "Control processes"]


def active_requirements(db: DBSession) -> list[TopicalRequirement]:
    return list(db.execute(select(TopicalRequirement).where(TopicalRequirement.is_active.is_(True))
                           .order_by(TopicalRequirement.id)).scalars())


def in_force(req: TopicalRequirement, today: date | None = None) -> bool:
    """Active and past its effective date: from then on an undecided requirement blocks closure."""
    return bool(req.is_active) and (req.effective_on is None or req.effective_on <= (today or date.today()))


def requirements_for(db: DBSession, audit_id: int) -> list[TopicalRequirement]:
    """The active catalogue plus any retired requirement (an earlier version) already decided on this engagement."""
    decided = select(EngagementTopical.requirement_id).where(EngagementTopical.audit_id == audit_id)
    return list(db.execute(select(TopicalRequirement).where(
        (TopicalRequirement.is_active.is_(True)) | TopicalRequirement.id.in_(decided))
        .order_by(TopicalRequirement.id)).scalars())


def use_count(db: DBSession, requirement_id: int) -> int:
    """Engagements that have decided on this requirement; its checklist is then fixed (make a new version)."""
    return db.execute(select(func.count()).select_from(EngagementTopical)
                      .where(EngagementTopical.requirement_id == requirement_id)).scalar() or 0


def decision(db: DBSession, audit_id: int, requirement_id: int) -> EngagementTopical | None:
    return db.execute(select(EngagementTopical).where(EngagementTopical.audit_id == audit_id,
                                                      EngagementTopical.requirement_id == requirement_id)
                      ).scalar_one_or_none()


def ensure_items(db: DBSession, et: EngagementTopical) -> None:
    """Create a checklist row for every requirement item not yet on the engagement."""
    have = set(db.execute(select(EngagementTopicalItem.item_id)
                          .where(EngagementTopicalItem.engagement_topical_id == et.id)).scalars())
    for item_id in db.execute(select(TopicalRequirementItem.id)
                              .where(TopicalRequirementItem.requirement_id == et.requirement_id)).scalars():
        if item_id not in have:
            db.add(EngagementTopicalItem(engagement_topical_id=et.id, item_id=item_id, notes=""))
    db.flush()


def progress(db: DBSession, et: EngagementTopical | None) -> dict:
    if et is None or not et.in_scope:
        return {"total": 0, "done": 0, "assessed": 0, "excluded": 0, "exceptions": 0}
    rows = list(db.execute(select(EngagementTopicalItem)
                           .where(EngagementTopicalItem.engagement_topical_id == et.id)).scalars())
    total = db.execute(select(TopicalRequirementItem.id)
                       .where(TopicalRequirementItem.requirement_id == et.requirement_id)).scalars().all()
    return {"total": len(total), "done": sum(1 for r in rows if r.outcome),
            "assessed": sum(1 for r in rows if r.outcome == "Assessed"),
            "excluded": sum(1 for r in rows if r.outcome == "Excluded"),
            "exceptions": sum(1 for r in rows if r.conclusion == "Exceptions noted")}


def open_points(db: DBSession, audit) -> list[str]:  # noqa: ANN001
    """What still blocks closure: an undecided requirement, or an applicable checklist with open items."""
    out = []
    for req in requirements_for(db, audit.id):
        et = decision(db, audit.id, req.id)
        if et is None:
            if in_force(req):
                out.append(f"{req.title}: applicability not decided")
            continue
        p = progress(db, et)
        if et.in_scope and p["done"] < p["total"]:
            out.append(f"{req.title}: {p['total'] - p['done']} requirement(s) not assessed or excluded")
    return out
