"""Strategy › Risk Library (Strategy walkthrough step 2): a starter list of common risks, filtered by industry, that
can be imported into the risk register and then described, assessed and owned like any other risk.

The entries are generic reference content, not GPHA data. An imported risk starts with neutral scores (3 x 3) until
it is assessed.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.appconfig import cfg
from app.core.audit import log_action
from app.core.database import get_db
from app.core.enums import utcnow
from app.core.refs import next_reference
from app.domains.grc.common import add_months, editor
from app.domains.grc.risk.models import EnterpriseRisk, RiskAssessment
from app.platform.users.models import User

router = APIRouter(prefix="/api/grc", tags=["risk & compliance"])
RiskEditor = editor("grc.risk")

INDUSTRIES = ("Ports & maritime", "Public sector", "All industries")

# key, title, category, industries, description
LIBRARY: tuple[tuple[str, str, str, tuple[str, ...], str], ...] = (
    ("cyber", "Cybersecurity and data protection", "Information Technology", ("All industries",),
     "Unauthorised access, ransomware or data loss disrupts operations or exposes personal and commercial data."),
    ("third-party", "Third-party service disruption", "Operational", ("All industries",),
     "Failure of a key supplier or service provider interrupts services or customer operations."),
    ("regulatory", "Regulatory non-compliance", "Compliance / Regulatory", ("All industries", "Public sector"),
     "Breach of laws, regulations or licence conditions leads to sanctions, penalties or loss of licence."),
    ("financial-reporting", "Financial reporting error", "Financial", ("All industries", "Public sector"),
     "Material misstatement in the financial statements through error, weak estimates or fraud."),
    ("revenue-leakage", "Revenue leakage", "Financial", ("Ports & maritime", "Public sector"),
     "Services delivered but not billed, billed incorrectly or not collected."),
    ("fraud", "Fraud and corruption", "Financial", ("All industries", "Public sector"),
     "Misappropriation of assets, procurement fraud or bribery causes loss and reputational damage."),
    ("procurement", "Procurement non-compliance", "Compliance / Regulatory", ("Public sector",),
     "Purchases made outside procurement law and policy, with poor value for money."),
    ("equipment", "Critical equipment failure", "Operational", ("Ports & maritime",),
     "Breakdown of cranes, tugs or other critical equipment halts or delays operations."),
    ("safety", "Workplace health and safety incident", "Safety, Health & Environment", ("All industries",),
     "Serious injury or fatality from operational activities."),
    ("environment", "Environmental pollution", "Safety, Health & Environment", ("Ports & maritime",),
     "Oil spill, emissions or waste discharge harms the environment and breaches permits."),
    ("security", "Port security breach", "Security", ("Ports & maritime",),
     "Unauthorised access, theft or smuggling through port facilities (ISPS Code)."),
    ("capacity", "Capacity and congestion", "Strategic", ("Ports & maritime",),
     "Infrastructure or capacity falls short of demand, losing traffic to competing ports."),
    ("project", "Capital project overrun", "Project", ("All industries", "Public sector"),
     "Major projects exceed budget or schedule, or do not deliver the expected benefits."),
    ("people", "Loss of key skills", "Operational", ("All industries",),
     "Inability to attract or keep people with critical skills."),
    ("continuity", "Business continuity failure", "Operational", ("All industries",),
     "A disaster or outage stops critical services for longer than they can tolerate."),
    ("reputation", "Reputational damage", "Reputational", ("All industries",),
     "Loss of stakeholder trust after an incident, failure or adverse publicity."),
)


class ImportIn(BaseModel):
    keys: list[str] = Field(min_length=1, max_length=len(LIBRARY))


@router.get("/risk-library")
def risk_library(industry: str | None = Query(None, max_length=60), db: DBSession = Depends(get_db),
                 _: User = RiskEditor) -> dict:
    have = {t.lower() for (t,) in db.execute(select(EnterpriseRisk.title)).all()}
    rows = [{"key": k, "title": t, "category": c, "industries": list(ind), "description": d,
             "in_register": t.lower() in have}
            for k, t, c, ind, d in LIBRARY if not industry or industry in ind]
    return {"industries": list(INDUSTRIES), "risks": rows}


@router.post("/risk-library/import", status_code=201)
def import_library(payload: ImportIn, request: Request, db: DBSession = Depends(get_db),
                   user: User = RiskEditor) -> dict:
    """Import (#) Risks: each chosen library risk becomes a register risk (skipped when one with the same title
    already exists)."""
    chosen = {k for k in payload.keys}
    unknown = chosen - {row[0] for row in LIBRARY}
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown library risks: {', '.join(sorted(unknown))}")
    categories = {c.lower(): c for c in (cfg("erm_risk_categories") or [])}
    created = []
    for key, title, category, _ind, desc in LIBRARY:
        if key not in chosen:
            continue
        exists = db.execute(select(EnterpriseRisk.id).where(func.lower(EnterpriseRisk.title) == title.lower())).first()
        if exists:
            continue
        r = EnterpriseRisk(ref=next_reference(db, "ERM"), title=title, description=desc,
                           category=categories.get(category.lower(), ""), inherent_likelihood=3, inherent_impact=3,
                           residual_likelihood=3, residual_impact=3, status="Active", created_by=user.id,
                           last_assessed_at=utcnow(), next_review_date=add_months(date.today(),
                                                                                   cfg("erm_review_months")))
        db.add(r)
        db.flush()
        db.add(RiskAssessment(risk_id=r.id, inherent_likelihood=3, inherent_impact=3, residual_likelihood=3,
                              residual_impact=3, comment="Imported from the Risk Library; not yet assessed",
                              assessed_by=user.id))
        created.append(r.ref)
    log_action(db, user_id=user.id, action=f"ERM_LIBRARY_IMPORT {created}", request=request)
    db.commit()
    return {"imported": len(created), "refs": created}
