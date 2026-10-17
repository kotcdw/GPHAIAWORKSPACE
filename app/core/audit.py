"""Helpers for writing the immutable audit trail.

Every entry records who (user id and a snapshot of the username), what (the action text plus a category,
an outcome and, where known, the affected record), when, and from where (IP address and browser): the
standard "who, what, when, where" of an audit trail. Entries are append-only: the database refuses
UPDATE and DELETE on ``audit_logs``.
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.platform.history.models import AuditLog

# --------------------------------------------------------------------------- classification

CATEGORIES = ("authentication", "user_admin", "security", "export", "system", "data")
OUTCOMES = ("success", "failure")

_AUTH = ("LOGIN", "LOGOUT", "ACCOUNT_LOCKED", "PASSWORD_CHANGE", "MFA_", "REGISTER", "PROFILE_UPDATE",
         "SESSION_", "DIRECTORY_ACCOUNT")
_USER_ADMIN = ("USER_", "ROLE_", "ROLES_", "PERMISSION", "JOB_ROLE", "APP_CUSTOM", "APPS_")
_SECURITY = ("ESIGN_", "ACCESS_DENIED", "MFA_POLICY")
_SYSTEM = ("BACKUP", "RESTORE", "CONFIG", "SETTING", "ESCALATION", "AUTOMATION", "SCHEDULER", "ROBOT",
           "IMPORT", "AUDIT_LOG_EXPORT")
_FAILURE_WORDS = ("FAILED", "DENIED", "LOCKED", "RATE_LIMITED")
_VERBS = {"CREATE", "CREATED", "UPDATE", "UPDATED", "DELETE", "DELETED", "UPLOAD", "DOWNLOAD", "EXPORT",
          "APPROVE", "APPROVED", "REJECT", "CLOSE", "CLOSED", "REOPEN", "SUBMIT", "SIGN", "SIGNOFF", "LINK",
          "UNLINK", "COPY", "WITHDRAW", "ASSIGN", "IMPLEMENT", "VALIDATE", "PROGRESS", "EXTEND", "ESCALATE",
          "UNLOCK", "RUN", "SHARE", "ISSUE", "DISTRIBUTE", "STATUS", "ACCEPT", "RISK", "EVIDENCE"}
_ID = re.compile(r"\bid=(\d+)")


def classify(action: str) -> tuple[str, str, str | None, int | None]:
    """Return (category, outcome, entity_type, entity_id) for an action text such as
    ``"REMEDIATION_UPDATE id=5 [due_date]"`` or ``"LOGIN_FAILED username=x"``."""
    token = (action or "").split(" ", 1)[0].upper()
    outcome = "failure" if any(w in token for w in _FAILURE_WORDS) else "success"
    if token.startswith(_SECURITY):
        category = "security"
    elif token.startswith(_AUTH):
        category = "authentication"
    elif token.startswith(_USER_ADMIN):
        category = "user_admin"
    elif "EXPORT" in token or "DOWNLOAD" in token:
        category = "export"
    elif token.startswith(_SYSTEM):
        category = "system"
    else:
        category = "data"
    entity = None
    if category in ("data", "export", "user_admin"):
        parts = token.split("_")
        while len(parts) > 1 and parts[-1] in _VERBS:
            parts.pop()
        entity = "_".join(parts).lower()[:50] or None
    match = _ID.search(action or "")
    return category, outcome, entity, int(match.group(1)) if match else None


# --------------------------------------------------------------------------- request details

def client_ip(request) -> str | None:  # noqa: ANN001
    """The client's IP address.

    Uses the connection's peer address. Behind the HTTPS proxy Uvicorn runs with ``--proxy-headers`` and
    trusts only the proxy's ``X-Forwarded-For``, so this is the real client. A forwarding header sent by
    the client itself is never trusted: it could be forged to hide who did something.
    """
    if request is None:
        return None
    client = getattr(request, "client", None)
    return getattr(client, "host", None)


def user_agent(request) -> str | None:  # noqa: ANN001
    headers = getattr(request, "headers", None)
    value = headers.get("user-agent") if headers is not None else None
    return value[:255] if value else None


def _username(db: Session, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    from app.platform.users.models import User

    try:
        user = db.get(User, user_id)
    except Exception:  # noqa: BLE001 - the trail must never break the action it records
        return None
    return user.username[:64] if user is not None else None


def log_action(
    db: Session,
    *,
    user_id: int | None,
    action: str,
    request=None,  # noqa: ANN001
    commit: bool = False,
    username: str | None = None,
    category: str | None = None,
    outcome: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
) -> AuditLog:
    """Append an entry to the audit trail.

    The entry is added to the current transaction. Callers usually commit together with their own change;
    pass ``commit=True`` to commit immediately. Category, outcome and the affected record are derived from
    the action text unless given. ``username`` records the name typed at a failed sign-in.
    """
    auto_category, auto_outcome, auto_entity, auto_id = classify(action)
    entry = AuditLog(
        user_id=user_id,
        username=((username or _username(db, user_id)) or None),
        action_performed=action[:500],
        ip_address=client_ip(request),
        user_agent=user_agent(request),
        category=category or auto_category,
        outcome=outcome or auto_outcome,
        entity_type=entity_type or auto_entity,
        entity_id=entity_id if entity_id is not None else auto_id,
    )
    db.add(entry)
    if commit:
        db.commit()
    return entry
