"""Admin-managed business rules (System Configuration).

Each rule has a default taken from ``app.core.config.settings`` (and so from
``.env``); an administrator can override it on the Configuration screen. Code
reads rules with ``cfg("key")`` - the database value when one is saved,
otherwise the live default.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.core.database import Base, SessionLocal
from app.core.enums import utcnow


class AppConfig(Base):
    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


@dataclass(frozen=True)
class Rule:
    key: str
    label: str
    group: str
    kind: str  # int | bool | text | longtext | roles | list
    help: str = ""
    default_attr: str | None = None  # settings attribute supplying the default
    default: Any = None
    min: int | None = None
    max: int | None = None
    options: list[str] = field(default_factory=list)

    def default_value(self) -> Any:
        if self.default_attr:
            value = getattr(settings, self.default_attr)
            if self.kind == "roles":
                return [r.strip() for r in str(value).split(",") if r.strip()]
            return value
        return self.default


RULES: list[Rule] = [
    # --- audit workflow
    Rule("require_report_to_close", "Require an issued report before an audit can be closed", "Audit workflow", "bool",
         "IIA GIAS 15.1: every engagement ends with a final communication.", default_attr="require_report_to_close"),
    Rule("require_findings_actioned_to_close", "Require every finding to have a management response and, for High "
         "and Medium risk, an agreed action before closing", "Audit workflow", "bool",
         default_attr="require_findings_actioned_to_close"),
    Rule("require_management_response_for_review", "Require a management response on every finding before the "
         "report goes to Audit Manager review", "Audit workflow", "bool", default=True),
    Rule("require_memo_approval_for_fieldwork", "Require an approved planning memo before fieldwork starts",
         "Audit workflow", "bool", "IIA GIAS 13.6: the engagement work programme is approved before it is "
         "implemented.", default_attr="require_memo_approval_for_fieldwork"),
    Rule("survey_on_close", "Send the post-audit satisfaction survey to auditees when an audit closes",
         "Audit workflow", "bool", default=True),
    Rule("notify_auditees_on_fieldwork", "Notify auditees when fieldwork starts (audit moves to In Progress)",
         "Audit workflow", "bool", default=True),
    # --- action plans
    Rule("capa_due_days_high", "Default due date for High-risk actions (days)", "Action plans", "int",
         "Used when an action is raised without a due date.", default=30, min=1, max=730),
    Rule("capa_due_days_medium", "Default due date for Medium-risk actions (days)", "Action plans", "int",
         default=60, min=1, max=730),
    Rule("capa_due_days_low", "Default due date for Low-risk actions (days)", "Action plans", "int",
         default=90, min=1, max=730),
    Rule("escalation_enabled", "Escalate overdue actions automatically", "Action plans", "bool", default=True),
    Rule("escalate_manager_days", "Days overdue before Audit Managers are notified", "Action plans", "int",
         default_attr="escalate_manager_days", min=1, max=365),
    Rule("escalate_cae_days", "Days overdue before the CAE is notified", "Action plans", "int",
         default_attr="escalate_cae_days", min=1, max=730),
    Rule("escalate_committee_days", "Days overdue before an action is reported to the Audit Committee",
         "Action plans", "int", "The CAE and Admins are notified and the action is listed in the Committee pack.",
         default_attr="escalate_committee_days", min=1, max=1095),
    # --- performance targets (KPIs on the Analytics page)
    Rule("kpi_plan_completion_pct", "Target: Assurance Plan engagements started or completed (%)", "KPI targets",
         "int", default=90, min=0, max=100),
    Rule("kpi_actions_on_time_pct", "Target: remediation actions closed by their due date (%)", "KPI targets", "int",
         default=80, min=0, max=100),
    Rule("kpi_survey_score", "Target: average post-audit survey score (out of 5, x10 - e.g. 40 = 4.0)",
         "KPI targets", "int", default=40, min=10, max=50),
    Rule("kpi_report_days", "Target: days from fieldwork start to report issued", "KPI targets", "int",
         default=60, min=1, max=365),
    Rule("kpi_utilisation_pct", "Target: auditor time charged to audit work (%)", "KPI targets", "int",
         default=70, min=0, max=100),
    # --- organizations / entities
    Rule("organization_categories", "Entity types users can choose for an organization", "Organizations", "list",
         "One per line. Ports, offices, departments and units describe GPHA itself; the rest are external parties.",
         default=["Port", "Head Office", "Department", "Unit", "Section", "Vendor", "Regulator",
                  "Government agency", "Shipping line / Customer", "Other"]),
    Rule("port_categories", "Entity types that count as a port or site", "Organizations", "list",
         "One per line. Users pick one of these as where they work; every entity is filed under the port it sits in.",
         default=["Port", "Head Office"]),
    # --- security
    Rule("mfa_required_roles", "Roles that must use two-step verification", "Security", "roles",
         "Users in these roles are asked to set it up at their next sign-in.", default_attr="mfa_required_roles",
         options=["Admin", "Auditor", "Auditee"]),
    Rule("login_rate_limit_per_minute", "Sign-in attempts allowed per computer per minute (0 = no limit)",
         "Security", "int", default_attr="login_rate_limit_per_minute", min=0, max=1000),
    # --- reports
    Rule("org_name", "Organisation name on reports", "Reports", "text",
         default="Ghana Ports and Harbours Authority"),
    Rule("department_name", "Department name on reports", "Reports", "text", default="Internal Audit Department"),
    Rule("report_methodology", "Default methodology paragraph for new reports", "Reports", "longtext",
         default=("The audit was performed in accordance with the IIA Global Internal Audit Standards. Work included "
                  "walkthroughs, assessment of control design and testing of operating effectiveness on a sample "
                  "basis.")),
]
RULES_BY_KEY = {r.key: r for r in RULES}

_CACHE: dict[str, Any] = {}
_CACHE_AT = 0.0
_LOCK = threading.Lock()
_TTL = 30.0


def invalidate() -> None:
    global _CACHE_AT
    with _LOCK:
        _CACHE.clear()
        _CACHE_AT = 0.0


def _load() -> dict[str, Any]:
    global _CACHE_AT
    with _LOCK:
        if _CACHE_AT and time.monotonic() - _CACHE_AT < _TTL:
            return dict(_CACHE)
    db = SessionLocal()
    try:
        rows = db.execute(select(AppConfig)).scalars().all()
        values = {}
        for row in rows:
            try:
                values[row.key] = json.loads(row.value)
            except ValueError:
                continue
    except Exception:  # noqa: BLE001 - table missing or database down: fall back to defaults
        values = {}
    finally:
        db.close()
    with _LOCK:
        _CACHE.clear()
        _CACHE.update(values)
        _CACHE_AT = time.monotonic()
    return values


def cfg(key: str) -> Any:
    rule = RULES_BY_KEY[key]
    saved = _load()
    return saved[key] if key in saved else rule.default_value()


def validate(rule: Rule, value: Any) -> Any:
    """Coerce and check a submitted value; raise ValueError with a plain message."""
    if rule.kind == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in ("true", "false", "1", "0", "yes", "no"):
            return value.lower() in ("true", "1", "yes")
        raise ValueError("must be yes or no")
    if rule.kind == "int":
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise ValueError("must be a whole number") from None
        if rule.min is not None and number < rule.min:
            raise ValueError(f"must be at least {rule.min}")
        if rule.max is not None and number > rule.max:
            raise ValueError(f"must be at most {rule.max}")
        return number
    if rule.kind == "roles":
        items = value if isinstance(value, list) else [v.strip() for v in str(value or "").split(",") if v.strip()]
        bad = [v for v in items if v not in rule.options]
        if bad:
            raise ValueError(f"unknown role(s): {', '.join(bad)}")
        return list(dict.fromkeys(items))
    if rule.kind == "list":
        items = value if isinstance(value, list) else str(value or "").splitlines()
        clean: list[str] = []
        for item in items:
            item = str(item).strip()
            if len(item) > 100:
                raise ValueError("each entry must be 100 characters or fewer")
            if item and item.lower() not in [c.lower() for c in clean]:
                clean.append(item)
        if not clean:
            raise ValueError("enter at least one entry")
        if len(clean) > 50:
            raise ValueError("enter at most 50 entries")
        return clean
    text = str(value or "").strip()
    if rule.kind == "text" and (not text or len(text) > 200):
        raise ValueError("enter 1 to 200 characters")
    if rule.kind == "longtext" and len(text) > 5000:
        raise ValueError("enter at most 5000 characters")
    return text
