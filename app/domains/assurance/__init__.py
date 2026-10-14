"""Assurance Domain Module: the annual assurance plan and its governance."""

from __future__ import annotations

NAME = "Assurance Domain Module"
DESCRIPTION = (
    "Audit universe and annual assurance plan, planning cycle, plan changes and versions, controlled "
    "distribution, Audit Committee, governance and QAIP."
)
MODULES = {
    "planning": "Audit universe, risk assessment and the annual assurance plan",
    "plancycle": "Planning cycle, statuses, versions, change requests, IAA submission, distribution",
    "committee": "Audit Committee packs and decisions",
    "governance": "Governance portal and charter",
    "qaip": "Quality assurance and improvement programme",
}


def routers() -> list:
    from app.domains.assurance.committee.router import router as committee
    from app.domains.assurance.governance.router import router as governance
    from app.domains.assurance.plancycle.changes import router as plan_changes
    from app.domains.assurance.plancycle.router import router as plancycle
    from app.domains.assurance.planning.router import router as planning
    from app.domains.assurance.qaip.router import router as qaip

    return [planning, committee, qaip, governance, plancycle, plan_changes]
