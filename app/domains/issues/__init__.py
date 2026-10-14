"""Issues Domain Module: what happens to issues after they are raised."""

from __future__ import annotations

NAME = "Issues Domain Module"
DESCRIPTION = (
    "Non-conformances, corrective and preventive actions (CAPA) and follow-up of agreed actions with "
    "escalation."
)
MODULES = {
    "nonconformances": "Non-conformances",
    "capa": "Corrective and preventive actions",
    "followup": "Follow-up of agreed actions, reminders and escalation",
}


def routers() -> list:
    from app.domains.issues.capa.router import router as capa
    from app.domains.issues.followup.router import router as followup
    from app.domains.issues.nonconformances.router import router as nonconformances

    return [nonconformances, capa, followup]
