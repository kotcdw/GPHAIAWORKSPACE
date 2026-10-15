"""The GPHA Working Paper Template (Working Paper Template.docx, Official GPHA).

Administrative details (audit title, reference, prepared/reviewed by and dates) come from the audit, the uploader
and the review trail; the auditor fills in the fields below. Values are kept as JSON on ``working_papers.template``.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.errors import field_error

# (key, label, kind, help). kind: "line" (one line), "text" (paragraphs), "date", "location".
ADMIN_FIELDS: list[tuple[str, str, str, str]] = [
    ("audit_period", "Audit period", "line", "For example: January - June 2026"),
    ("location", "Location", "location", "Headquarters, Tema Port or Takoradi Port"),
    ("audited_unit", "Audited unit", "line", "The department, section or unit audited"),
]
BODY_FIELDS: list[tuple[str, str, str, str]] = [
    ("objective", "Audit objective", "text", "What this piece of work sets out to confirm"),
    ("scope", "Audit scope", "text", "Period, transactions, systems and locations covered"),
    ("criteria", "Audit criteria", "text", "Policies, procedures, laws or standards tested against"),
    ("risk_statement", "Risk statement", "text", "What could go wrong if the controls fail"),
    ("control_objective", "Control objective", "text", "What the controls are meant to achieve"),
    ("key_controls", "Key controls expected", "text", "The controls that should be in place"),
    ("procedures", "Audit procedures performed", "text", "Tests, samples, walkthroughs and re-performance"),
    ("evidence", "Evidence obtained", "text", "Documents, reports, screenshots and records examined"),
    ("observations", "Audit observations / findings", "text",
     "Criteria, Condition, Cause, Effect/Risk - objectively based on the evidence"),
    ("recommendation", "Recommendation", "text", "Corrective action required"),
    ("client_response", "Audit client response", "text",
     "The Head of Department's response, as captured and confirmed at the exit meeting"),
    ("action_plan", "Management response - action plan", "text", "What management will do"),
    ("responsible_officer", "Management response - responsible officer", "line", "Who will do it"),
    ("target_date", "Management response - target date", "date", "By when"),
]
FIELDS = ADMIN_FIELDS + BODY_FIELDS
KEYS = {k for k, *_ in FIELDS}
_LIMITS = {"line": 255, "location": 120, "date": 10, "text": 20000}


def load(raw: str | None) -> dict[str, str]:
    try:
        data = json.loads(raw or "{}")
    except ValueError:
        return {}
    return {k: str(v) for k, v in data.items() if k in KEYS and v not in (None, "")} if isinstance(data, dict) else {}


def locations() -> list[str]:
    from app.core.appconfig import cfg

    return list(cfg("working_paper_locations") or [])


def clean(values: dict[str, Any]) -> dict[str, str]:
    """Validate submitted values: known keys only, length limits, ISO dates, a configured location."""
    out: dict[str, str] = {}
    kinds = {k: kind for k, _, kind, _ in FIELDS}
    for key, value in values.items():
        if key not in KEYS:
            raise field_error(key, "is not a field of the GPHA working paper template")
        text = ("" if value is None else str(value)).strip()
        if not text:
            continue
        kind = kinds[key]
        if len(text) > _LIMITS[kind]:
            raise field_error(key, f"must be at most {_LIMITS[kind]} characters")
        if kind == "date":
            from datetime import date

            try:
                date.fromisoformat(text)
            except ValueError as exc:
                raise field_error(key, "enter a date as YYYY-MM-DD") from exc
        if kind == "location" and locations() and text not in locations():
            raise field_error(key, f"choose one of: {', '.join(locations())}")
        out[key] = text
    return out


def dump(values: dict[str, str]) -> str:
    return json.dumps(values, ensure_ascii=False)


def completeness(values: dict[str, str]) -> tuple[int, int]:
    return sum(1 for k, *_ in FIELDS if values.get(k)), len(FIELDS)
