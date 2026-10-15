"""Task Tracker priorities from the risk & compliance apps: attestations, risk reviews, KRI readings, compliance
assessments and third-party due diligence owned by the signed-in person."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session as DBSession

from app.platform.users.models import User

KRI_DAYS = {"Monthly": 31, "Quarterly": 92, "Half-yearly": 183, "Annually": 366}


def items(db: DBSession, user: User) -> list[dict]:
    from app.domains.grc.assets.models import Asset
    from app.domains.grc.compliance.models import Regulation, Requirement
    from app.domains.grc.policies.router import my_attestations
    from app.domains.grc.risk.models import EnterpriseRisk, KeyRiskIndicator, KriReading
    from app.platform.apps.registry import enabled

    out: list[dict] = []
    today = date.today()
    for a in my_attestations(db, user.id) if enabled("policies") else []:
        out.append({"section": "Attest to policies", "kind": "attestation", "id": a["id"], "ref": a["policy_ref"],
                    "title": a["policy_title"], "detail": f"Version {a['version']}", "due": a["due_date"],
                    "status": "Pending", "action": "Read and attest", "open": {"type": "attestation", "id": a["id"]},
                    "data": a})

    risk_on = enabled("risk")
    for r in db.execute(select(EnterpriseRisk).where(EnterpriseRisk.owner_id == user.id,
                                                     EnterpriseRisk.status == "Active")).scalars() if risk_on else []:
        if r.next_review_date is None or r.next_review_date <= today + timedelta(days=14):
            out.append({"section": "Assess your risks", "kind": "erm_risk", "id": r.id, "ref": r.ref, "title": r.title,
                        "detail": f"Residual {r.residual_score}", "due": r.next_review_date or today,
                        "status": "Review due", "action": "Assess", "open": {"type": "erm_risk", "id": r.id}})

    kris = db.execute(select(KeyRiskIndicator, EnterpriseRisk).join(
        EnterpriseRisk, EnterpriseRisk.id == KeyRiskIndicator.risk_id).where(
        KeyRiskIndicator.active.is_(True), EnterpriseRisk.status == "Active",
        or_(KeyRiskIndicator.owner_id == user.id,
            (KeyRiskIndicator.owner_id.is_(None)) & (EnterpriseRisk.owner_id == user.id)))).all() if risk_on else []
    for k, r in kris:
        last = db.execute(select(KriReading.period_date).where(KriReading.kri_id == k.id)
                          .order_by(KriReading.period_date.desc()).limit(1)).scalar()
        due = (last + timedelta(days=KRI_DAYS.get(k.frequency, 31))) if last else today
        if due <= today + timedelta(days=7):
            out.append({"section": "Record indicators", "kind": "kri", "id": k.id, "ref": r.ref, "title": k.name,
                        "detail": f"{k.frequency}{' · last ' + last.isoformat() if last else ' · no reading yet'}",
                        "due": due, "status": "Reading due", "action": "Record reading",
                        "open": {"type": "erm_risk", "id": r.id},
                        "data": {"kri_id": k.id, "unit": k.unit, "risk_id": r.id}})

    reqs = db.execute(select(Requirement, Regulation).join(Regulation, Regulation.id == Requirement.regulation_id)
                      .where(Requirement.owner_id == user.id, Regulation.active.is_(True),
                             Requirement.status != "Not applicable")).all() if enabled("compliance") else []
    for q, g in reqs:
        stale = q.last_assessed_at is None or q.last_assessed_at.date() < today - timedelta(days=365)
        if q.review_required or q.status == "Not assessed" or stale:
            why = "Obligation changed" if q.review_required else "Never assessed" if q.last_assessed_at is None \
                else "Assessment over a year old"
            out.append({"section": "Assess compliance", "kind": "requirement", "id": q.id, "ref": f"{g.code} {q.ref}",
                        "title": q.title, "detail": why, "due": None, "status": q.status, "action": "Assess",
                        "open": {"type": "regulation", "id": g.id},
                        "data": {"regulation_id": g.id, "status": q.status, "comment": q.assessment_comment}})

    assets = db.execute(select(Asset).where(Asset.owner_id == user.id, Asset.status == "Active")).scalars() \
        if enabled("assets") else []
    for a in assets:
        due_soon = a.next_assessment_date is None or a.next_assessment_date <= today + timedelta(days=30)
        if a.is_third_party and due_soon:
            out.append({"section": "Third-party due diligence", "kind": "asset", "id": a.id, "ref": a.ref,
                        "title": a.name, "detail": f"{a.criticality} · {a.due_diligence}",
                        "due": a.next_assessment_date or today, "status": "Assessment due",
                        "action": "Record assessment", "open": {"type": "asset", "id": a.id}})
    return out
