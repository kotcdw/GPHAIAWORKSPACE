"""Risk & Compliance Domain Module: the GRC apps around internal audit.

Risk Manager & Strategy (enterprise risk register, objectives, KRIs), Compliance Maps (obligations, requirements and
the controls that meet them), Policy Manager (policy lifecycle and attestations) and Asset Inventory (systems,
facilities, data and third parties). Records in these apps link to each other and to the standard controls library
through one link table, so a risk can show its controls, the requirements it threatens and the assets it sits on.
"""

from __future__ import annotations

NAME = "Risk & Compliance Domain Module"
DESCRIPTION = (
    "Enterprise risk register and strategic objectives with KRIs, compliance maps from obligations to controls, "
    "policy lifecycle with attestations, and the asset and third-party inventory."
)
MODULES = {
    "risk": "Risk Manager & Strategy: objectives, enterprise risks, assessments, heat map, KRIs",
    "compliance": "Compliance Maps: obligations, requirements, control coverage, compliance assessments",
    "policies": "Policy Manager: policies, versions, approval, publication, attestation campaigns",
    "assets": "Asset Inventory: systems, data, facilities, equipment and third parties with due diligence",
    "links": "Links between risks, controls, requirements, policies, assets and audit universe units",
}


def routers() -> list:
    from app.domains.grc.assets.router import router as assets
    from app.domains.grc.compliance.router import router as compliance
    from app.domains.grc.links import people_router
    from app.domains.grc.links import router as links
    from app.domains.grc.policies.router import router as policies
    from app.domains.grc.risk.router import router as risk

    return [risk, compliance, policies, assets, links, people_router]
