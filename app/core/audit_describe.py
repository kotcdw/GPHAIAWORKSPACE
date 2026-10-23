"""Plain-language names for audit trail entries.

Entries are stored as a code and details, e.g. ``CONFIG_UPDATE date_format=DD MMM YYYY``. ``describe`` turns
the code into words ("Changed settings") and returns the rest as details. Codes not listed are named by rule:
``FINDING_CREATE`` -> "Finding created". The stored text is never changed.
"""

from __future__ import annotations

EVENTS = {
    # sign-in and sessions
    "LOGIN": "Signed in", "LOGIN_FAILED": "Failed sign-in", "LOGIN_DENIED": "Sign-in refused",
    "LOGIN_RATE_LIMITED": "Too many sign-in attempts", "LOGOUT": "Signed out",
    "ACCOUNT_LOCKED": "Account locked", "SESSION_IDLE_TIMEOUT": "Signed out for inactivity",
    "PASSWORD_CHANGE": "Changed own password", "PASSWORD_CHANGE_FAILED": "Password change failed",
    "MFA_ENABLED": "Turned on two-step verification", "MFA_DISABLED": "Turned off two-step verification",
    "MFA_SETUP_STARTED": "Started two-step set-up", "MFA_ENABLE_FAILED": "Two-step set-up failed",
    "MFA_DISABLE_FAILED": "Two-step removal failed", "REGISTER": "Signed up", "PROFILE_UPDATE": "Updated own profile",
    "DIRECTORY_ACCOUNT_CREATED": "Account created from the directory",
    "ACCOUNT_ACTIVATED": "Activated an invited account", "ACTIVATION_FAILED": "Invitation link refused",
    # user administration
    "USER_CREATE": "Created a user", "USER_UPDATE": "Changed a user", "USER_DELETE": "Deleted a user",
    "HOME_PAD": "Arranged own home pad",
    "COMMENT_POST": "Commented on a record", "COMMENT_WITHDRAW": "Withdrew a comment",
    "TOPICAL_DECISION": "Decided a topical requirement's scope", "TOPICAL_ITEM": "Assessed a topical requirement",
    "USER_INVITE": "Invited a user", "USER_INVITE_RESEND": "Sent an invitation again",
    "USER_INVITE_REVOKE": "Withdrew an invitation", "USER_GROUP_ROLE": "Gave a group's members a role",
    "USER_UNLOCK": "Unlocked a user", "USER_SESSIONS_REVOKED": "Signed a user out everywhere",
    "JOB_ROLE": "Changed a user's role", "ROLE_PERMISSIONS": "Changed role permissions",
    "ROLE_RESET": "Reset role permissions", "APPS_CUSTOMIZE": "Changed apps and branding",
    # settings and system
    "CONFIG_UPDATE": "Changed settings", "CONFIG_RESET": "Reset a setting", "SLA_POLICY_UPDATE": "Changed SLA limits",
    "BACKUP_CREATE": "Backup created", "BACKUP_FAILED": "Backup failed", "BACKUP_DELETE": "Backup deleted",
    "BACKUP_VERIFY": "Backup checked", "BACKUP_RESTORE_TEST": "Restore test",
    "AUDIT_LOG_EXPORT": "Exported the audit trail", "ESCALATION_RUN": "Escalations run",
    "ESCALATION_RAISED": "Escalation raised", "WORKFLOW_RESYNC": "Workflow re-synchronised",
    "WORKFLOW_TRANSITION": "Status changed",
    # security
    "ESIGN": "Signed electronically", "ESIGN_FAILED": "Electronic signature failed",
    "ACCESS_DENIED": "Access refused",
    # organisation
    "ORG_CREATE": "Org unit created", "ORG_UPDATE": "Org unit changed", "ORG_DELETE": "Org unit deleted",
    "ORG_APPROVE": "Org unit approved", "ORG_DEACTIVATE": "Org unit deactivated",
    "ORG_REACTIVATE": "Org unit reactivated",
    "ORG_COPY": "Org unit copied", "ORG_SET_PENDING": "Org unit set back to pending",
    "EXPORT_XLSX": "Exported to Excel",
}

NOUNS = {
    "ARA": "Audit risk assessment", "NC": "Non-conformity", "SF": "Saved filter", "SH": "Contact",
    "KRI": "Key risk indicator", "ERM": "Enterprise risk", "PCR": "Plan change request", "TP": "Third party",
    "WP": "Working paper", "QA": "Quality review", "QAIP": "Quality programme", "CPD": "CPD",
    "EQA": "External quality assessment",
    "GRC": "Risk and compliance", "AI": "AI assistant",
}

VERBS = {
    "CREATE": "created", "UPDATE": "changed", "DELETE": "deleted", "APPROVE": "approved", "APPROVED": "approved",
    "EXPORT": "exported", "DOWNLOAD": "downloaded", "UPLOAD": "uploaded", "RESET": "reset", "CLOSE": "closed",
    "REOPEN": "reopened", "SUBMIT": "submitted", "SUBMITTED": "submitted", "PUBLISH": "published", "REVIEW": "reviewed",
    "RUN": "run", "SAVE": "saved", "COPY": "copied", "LINK": "linked", "UNLINK": "unlinked", "ASSESS": "assessed",
    "REMIND": "reminder sent", "CANCEL": "cancelled", "START": "started", "ADD": "added", "REMOVE": "removed",
    "RETIRE": "retired", "RETURN": "returned", "DISTRIBUTED": "distributed", "VALIDATED": "validated",
    "IMPLEMENTED": "implemented", "RECORDED": "recorded", "SIGNED": "signed", "SET": "set", "APPLY": "applied",
    "DEFINE": "defined", "DRAFT": "drafted", "BOOK": "booked", "SHARE": "shared", "ARCHIVE": "archived",
    "INCLUDE": "included", "EXCLUDE": "excluded", "IMPORT": "imported", "RAISE": "raised", "WITHDRAW": "withdrawn",
    "ADDED": "added", "DELETED": "deleted", "VERIFIED": "verified", "REVIEWED": "reviewed",
}


def _words(parts: list[str]) -> str:
    text = " ".join(NOUNS.get(p, p.lower()) for p in parts if p)
    return text[:1].upper() + text[1:] if text else ""


def event_name(code: str) -> str:
    code = (code or "").strip().upper()
    if code in EVENTS:
        return EVENTS[code]
    parts = [p for p in code.split("_") if p]
    if not parts:
        return "Activity"
    if parts[0] == "IMPORT" and len(parts) > 1:
        return f"Imported {_words(parts[1:]).lower()}"
    if parts[-1] in VERBS and len(parts) > 1:
        return f"{_words(parts[:-1])} {VERBS[parts[-1]]}"
    return _words(parts)


def describe(action: str) -> tuple[str, str]:
    """``(event, details)`` for a stored action text."""
    code, _, rest = (action or "").partition(" ")
    if code == "LOGIN" and rest.startswith("directory"):
        return "Signed in (company directory)", rest[len("directory"):].strip()
    return event_name(code), rest.strip()
