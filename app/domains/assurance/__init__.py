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
    "committee": "Audit Committee packs, meetings register, minutes and decisions on recommendations",
    "governance": "Governance portal and charter",
    "qaip": "Quality assurance and improvement programme",
    "scheduler": "Timeline of engagements and auditor bookings with double-booking warnings",
    "conformance": "Internal audit charter, external quality assessments, conformance statement, retention review",
}


def routers() -> list:
    from app.domains.assurance.committee.meetings import router as committee_meetings
    from app.domains.assurance.committee.router import router as committee
    from app.domains.assurance.conformance.router import router as conformance
    from app.domains.assurance.governance.router import router as governance
    from app.domains.assurance.plancycle.changes import router as plan_changes
    from app.domains.assurance.plancycle.router import router as plancycle
    from app.domains.assurance.planning.router import router as planning
    from app.domains.assurance.qaip.router import router as qaip
    from app.domains.assurance.scheduler.router import router as scheduler

    return [planning, committee, committee_meetings, qaip, governance, plancycle, plan_changes, conformance, scheduler]
