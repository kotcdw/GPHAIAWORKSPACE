"""Assurance or advisory: the nature of an engagement (IIA GIAS Domain I and 13.1).

An engagement is advisory when its audit type is one of the configured ``advisory_audit_types``. Advisory work
reports observations without an overall assurance rating, management decides which suggestions to act on, and it
does not count as audit coverage of the auditable entities it touches.
"""

from __future__ import annotations

from app.core.appconfig import cfg


def advisory_types() -> set[str]:
    return {t.strip().lower() for t in (cfg("advisory_audit_types") or []) if t.strip()}


def is_advisory(audit) -> bool:  # noqa: ANN001
    return bool(audit is not None and audit.audit_type and audit.audit_type.strip().lower() in advisory_types())


def nature(audit) -> str:  # noqa: ANN001
    return "Advisory" if is_advisory(audit) else "Assurance"
