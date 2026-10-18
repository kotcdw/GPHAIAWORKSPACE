"""Workflow definitions: the states of each record type and the moves between them.

The shipped definitions reproduce GIAW's behaviour before the workflow engine existed, so nothing changes for
users until an administrator edits one. A definition is plain data (JSON-compatible):

    {"label": ..., "initial": <state>, "states": [...], "final": [...],
     "transitions": [{"action": "start", "label": "Start", "from": [<state>, ...], "to": <state>,
                      "permission": "audit.fieldwork"}, ...]}

A status change that no transition describes is still saved and recorded, flagged ``allowed = False``; the engine
reports it rather than blocking work while definitions are being customised.
"""

from __future__ import annotations

import copy
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession


def _t(action: str, label: str, frm: list[str], to: str, permission: str | None = None) -> dict[str, Any]:
    return {"action": action, "label": label, "from": frm, "to": to, "permission": permission}


DEFAULTS: dict[str, dict[str, Any]] = {
    "audit": {
        "label": "Audit engagement", "initial": "Planned", "states": ["Planned", "In Progress", "Review", "Closed"],
        "final": ["Closed"],
        "transitions": [
            _t("start", "Start fieldwork", ["Planned"], "In Progress", "audit.fieldwork"),
            _t("submit_review", "Submit for review", ["Planned", "In Progress"], "Review", "audit.fieldwork"),
            _t("return", "Return to fieldwork", ["Review"], "In Progress", "review.workpapers"),
            _t("close", "Close the audit", ["Planned", "In Progress", "Review"], "Closed", "audit.close"),
            _t("reopen", "Reopen", ["Closed"], "In Progress", "audit.close"),
            _t("replan", "Back to planned", ["In Progress", "Review"], "Planned", "audit.plan"),
        ],
    },
    "procedure": {
        "label": "Procedure", "initial": "Not Started",
        "states": ["Not Started", "In Progress", "Prepared", "Reviewed"],
        "final": ["Reviewed"],
        "transitions": [
            _t("start", "Start", ["Not Started"], "In Progress", "audit.fieldwork"),
            _t("prepare", "Sign off as preparer", ["Not Started", "In Progress"], "Prepared", "audit.fieldwork"),
            _t("review", "Sign off as reviewer", ["Prepared"], "Reviewed", "review.workpapers"),
            _t("return", "Return to preparer", ["Prepared", "Reviewed"], "In Progress", "review.workpapers"),
            _t("reopen_review", "Reopen the review", ["Reviewed"], "Prepared", "review.workpapers"),
            _t("reset", "Back to not started", ["In Progress"], "Not Started", "audit.fieldwork"),
        ],
    },
    "control_test": {
        "label": "Control test", "initial": "Not Started",
        "states": ["Not Started", "In Progress", "Completed", "Reviewed"], "final": ["Reviewed"],
        "transitions": [
            _t("start", "Start", ["Not Started"], "In Progress", "audit.fieldwork"),
            _t("prepare", "Complete and sign off as preparer", ["Not Started", "In Progress"], "Completed",
               "audit.fieldwork"),
            _t("review", "Sign off as reviewer", ["Completed"], "Reviewed", "review.workpapers"),
            _t("return", "Return to preparer", ["Completed", "Reviewed"], "In Progress", "review.workpapers"),
            _t("reopen_review", "Reopen the review", ["Reviewed"], "Completed", "review.workpapers"),
            _t("reset", "Back to not started", ["In Progress", "Completed"], "Not Started", "audit.fieldwork"),
        ],
    },
    "evidence_request": {
        "label": "Evidence request", "initial": "Requested",
        "states": ["Requested", "Submitted", "Accepted", "Returned", "Cancelled"], "final": ["Accepted", "Cancelled"],
        "transitions": [
            _t("submit", "Submit evidence", ["Requested", "Returned"], "Submitted", "auditee.respond"),
            _t("accept", "Accept", ["Submitted"], "Accepted", "audit.evidence"),
            _t("return", "Return for more", ["Submitted"], "Returned", "audit.evidence"),
            _t("cancel", "Cancel the request", ["Requested", "Submitted", "Returned"], "Cancelled", "audit.evidence"),
            _t("reopen", "Reopen", ["Accepted", "Cancelled"], "Requested", "audit.evidence"),
        ],
    },
    "review_note": {
        "label": "Review note", "initial": "Open", "states": ["Open", "Responded", "Cleared"], "final": ["Cleared"],
        "transitions": [
            _t("respond", "Respond", ["Open"], "Responded", "audit.fieldwork"),
            _t("clear", "Clear", ["Open", "Responded"], "Cleared", "review.notes"),
            _t("reopen", "Reopen", ["Responded", "Cleared"], "Open", "review.notes"),
        ],
    },
    "finding": {
        "label": "Finding", "initial": "Open", "states": ["Open", "Remediating", "Closed"], "final": ["Closed"],
        "transitions": [
            _t("remediate", "Start remediation", ["Open"], "Remediating", "audit.findings"),
            _t("close", "Close", ["Open", "Remediating"], "Closed", "audit.findings"),
            _t("reopen", "Reopen", ["Closed", "Remediating"], "Open", "audit.findings"),
            _t("reopen_remediation", "Reopen remediation", ["Closed"], "Remediating", "followup.manage"),
        ],
    },
    "audit_report": {
        "label": "Audit report", "initial": "Draft",
        "states": ["Draft", "Management Review", "Manager Review", "CAE Approval", "Issued"], "final": ["Issued"],
        "transitions": [
            _t("send_to_management", "Send to management", ["Draft"], "Management Review", "report.prepare"),
            _t("submit_for_review", "Submit for review", ["Draft", "Management Review"], "Manager Review",
               "report.prepare"),
            _t("submit_to_cae", "Submit for CAE approval", ["Draft", "Management Review", "Manager Review"],
               "CAE Approval", "report.review"),
            _t("return", "Return to draft", ["Management Review", "Manager Review", "CAE Approval"], "Draft",
               "report.review"),
            _t("issue", "Approve and issue", ["CAE Approval"], "Issued", "report.approve"),
        ],
    },
    "capa": {
        "label": "Remediation action", "initial": "Open", "states": ["Open", "In Progress", "Review", "Closed"],
        "final": ["Closed"],
        "transitions": [
            _t("progress", "Record progress", ["Open"], "In Progress", "auditee.respond"),
            _t("implement", "Mark implemented", ["Open", "In Progress"], "Review", "auditee.respond"),
            _t("not_effective", "Validate: not effective", ["Review"], "In Progress", "followup.validate"),
            _t("close", "Close", ["Open", "In Progress", "Review"], "Closed", "followup.manage"),
            _t("reopen", "Reopen", ["Closed"], "In Progress", "followup.manage"),
            _t("back_to_open", "Back to open", ["In Progress", "Review"], "Open", "followup.manage"),
        ],
    },
}

_CACHE: dict[str, dict[str, Any]] | None = None


def invalidate() -> None:
    global _CACHE  # noqa: PLW0603 - process-wide cache of the active definitions
    _CACHE = None


def _load(db: DBSession | None) -> dict[str, dict[str, Any]]:
    """Active definitions: the newest active database version of each record type, else the shipped default."""
    global _CACHE  # noqa: PLW0603
    if _CACHE is not None:
        return _CACHE
    out = copy.deepcopy(DEFAULTS)
    if db is not None:
        from app.platform.workflow.models import WorkflowDefinition

        try:
            rows = db.execute(select(WorkflowDefinition).where(WorkflowDefinition.active.is_(True),
                                                               WorkflowDefinition.audit_type.is_(None))
                              .order_by(WorkflowDefinition.version)).scalars().all()
        except Exception:  # noqa: BLE001 - table missing during an upgrade: shipped defaults
            rows = []
        for row in rows:
            try:
                out[row.record_type] = {**out.get(row.record_type, {}), **json.loads(row.definition),
                                        "version": row.version}
            except ValueError:
                continue
    _CACHE = out
    return out


def definition(record_type: str, db: DBSession | None = None) -> dict[str, Any] | None:
    return _load(db).get(record_type)


def all_definitions(db: DBSession | None = None) -> dict[str, dict[str, Any]]:
    return _load(db)


def match(record_type: str, from_state: str | None, to_state: str, db: DBSession | None = None) -> dict | None:
    """The transition that moves ``from_state`` to ``to_state``, or None when the definition has none."""
    d = definition(record_type, db)
    if d is None:
        return None
    for t in d.get("transitions", []):
        if t["to"] == to_state and (from_state is None or from_state in t["from"]):
            return t
    return None


def is_allowed(record_type: str, from_state: str | None, to_state: str, db: DBSession | None = None) -> bool:
    d = definition(record_type, db)
    if d is None:
        return True
    if from_state is None:  # a new record: any listed state may be its first
        return to_state in d.get("states", [])
    if from_state == to_state:
        return True
    return match(record_type, from_state, to_state, db) is not None
