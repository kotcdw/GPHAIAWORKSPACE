"""Finding closure follows verified remediation (mainBLUEPRINT 6.4, Module 7).

A finding is closed by its remediation, not by editing it:

* while any action raised from the finding is open, or was closed without Internal Audit validating it as
  Effective (or without a recorded Committee / external-body decision), the finding cannot be set to Closed;
* when the last action of a finding closes (e-signed close, Audit Committee close or withdrawal), the finding
  closes automatically, and a reopened action moves it back to Remediating;
* a finding with no action can be closed by hand only when it is rated Low and the configuration allows it
  (Configuration > Audit workflow), with a recorded reason.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.enums import CapaStatus, FindingStatus, RiskRating, ValidationResult


def actions_of(db: DBSession, finding_id: int) -> list:
    from app.domains.issues.capa.models import Capa

    return list(db.execute(select(Capa).where(Capa.source_type == "finding", Capa.source_id == finding_id)
                           .order_by(Capa.id)).scalars())


def _verified(capa) -> bool:  # noqa: ANN001
    """Closed with Internal Audit's 'Effective' validation, or closed by an authorized decision (withdrawn or an
    external body's closure reference)."""
    if capa.status != CapaStatus.Closed:
        return False
    return (capa.validation_result == ValidationResult.Effective or bool(capa.withdrawal_reason)
            or bool((capa.external_closure_ref or "").strip()))


def remediation_summary(db: DBSession, finding) -> dict:  # noqa: ANN001
    """One status for the finding and its actions, for registers and the finding form."""
    acts = actions_of(db, finding.id)
    open_ = [a for a in acts if a.status != CapaStatus.Closed]
    awaiting = [a for a in open_ if a.status == CapaStatus.Review]
    if finding.status == FindingStatus.Closed:
        state = "Closed - verified" if acts and all(_verified(a) for a in acts) else "Closed"
    elif not acts:
        state = "No action raised"
    elif awaiting and len(awaiting) == len(open_):
        state = "Awaiting verification"
    elif open_:
        state = "Action in progress"
    else:
        state = "Actions closed"
    return {"state": state, "actions": len(acts), "open_actions": len(open_),
            "refs": [a.capa_ref for a in acts]}


def closure_blockers(db: DBSession, finding) -> list[str]:  # noqa: ANN001
    """Why the finding cannot be closed now (empty list = it may be closed)."""
    from app.core.appconfig import cfg

    acts = actions_of(db, finding.id)
    if acts:
        problems = []
        for a in acts:
            if a.status != CapaStatus.Closed:
                problems.append(f"{a.capa_ref} is still {a.status.value}")
            elif not _verified(a):
                problems.append(f"{a.capa_ref} was closed without Internal Audit validating it as Effective")
        return problems
    if finding.risk_rating != RiskRating.Low:
        return [f"a {finding.risk_rating.value}-rated finding is closed through a verified remediation action; "
                "raise the action first"]
    if not cfg("low_findings_close_without_action"):
        return ["findings are closed through a verified remediation action; raise the action first"]
    return []


def sync_finding(db: DBSession, finding_id: int | None, user_id: int | None, request=None) -> str | None:  # noqa: ANN001
    """Bring the finding's status in line with its actions. Returns the new status when it changed."""
    from app.core.history import log_record_history
    from app.domains.audit.audits.models import Finding

    if not finding_id:
        return None
    finding = db.get(Finding, finding_id)
    if finding is None:
        return None
    acts = actions_of(db, finding_id)
    if not acts:
        return None
    new = None
    if all(a.status == CapaStatus.Closed for a in acts):
        if finding.status != FindingStatus.Closed:
            new = FindingStatus.Closed
    elif finding.status == FindingStatus.Closed or finding.status == FindingStatus.Open:
        new = FindingStatus.Remediating
    if new is None:
        return None
    finding.status = new
    refs = ", ".join(a.capa_ref for a in acts)
    log_record_history(db, record_type="audit", record_id=finding.audit_id, user_id=user_id, request=request,
                       action=f"FINDING #{finding.id} {new.value.upper()} by its remediation ({refs})")
    return new.value
