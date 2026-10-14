"""Automation engine: admin-defined rules of the form *when <trigger> [and <conditions>] then <actions>*.

* Event triggers fire from the workflow (``emit``), e.g. a High-risk finding is raised.
* Scheduled triggers are evaluated by the background job (``run_scheduled``), e.g. an action due in 7 days,
  a draft report whose management response is overdue, a charter review falling due.
* Actions: in-app (and e-mail) notifications and tasks, addressed by role, permission or the record's people.
* Each rule fires at most once per record and period (``automation_runs``), so the job can run often.

Nothing here changes audit records: automations remind, route and escalate; people decide.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.core.enums import CapaStatus, ReportStatus, Role, utcnow
from app.platform.automations.models import AutomationRule, AutomationRun

logger = logging.getLogger("gpha")


# ---------------------------------------------------------------- catalogue

@dataclass(frozen=True)
class Trigger:
    key: str
    label: str
    kind: str  # event | schedule
    record_type: str
    fields: dict[str, str]
    offset_help: str = ""
    people: tuple[str, ...] = ()


_ACTION_FIELDS = {"ref": "Reference", "title": "Title", "severity": "Severity", "source_body": "Source",
                  "timeframe": "Timeframe", "implementation_status": "Implementation status",
                  "owner_email": "Owner e-mail", "due_date": "Due date", "days": "Days (before/after)"}
_REPORT_FIELDS = {"ref": "Reference", "title": "Title", "overall_rating": "Overall rating",
                  "due_date": "Response due", "days": "Days overdue", "missing": "Missing recipients"}

TRIGGERS: dict[str, Trigger] = {t.key: t for t in [
    Trigger("finding.created", "A finding is raised", "event", "finding",
            {"ref": "Reference", "title": "Title", "risk_rating": "Risk rating", "audit_title": "Audit"},
            people=("creator",)),
    Trigger("report.sent_to_management", "A draft report is sent to management", "event", "audit_report",
            _REPORT_FIELDS, people=("creator", "auditees")),
    Trigger("report.issued", "An audit report is issued", "event", "audit_report", _REPORT_FIELDS,
            people=("creator", "auditees")),
    Trigger("action.created", "An action / recommendation is recorded", "event", "capa", _ACTION_FIELDS,
            people=("owner", "creator")),
    Trigger("action.implemented", "Management records implementation", "event", "capa", _ACTION_FIELDS,
            people=("owner", "creator")),
    Trigger("action.reopened", "An auditor finds an action not effective", "event", "capa", _ACTION_FIELDS,
            people=("owner", "creator")),
    Trigger("action.withdrawal_proposed", "Withdrawal of a recommendation is proposed", "event", "capa",
            _ACTION_FIELDS, people=("owner", "creator")),
    Trigger("declaration.conflict", "An auditor declares a conflict of interest", "event", "declaration",
            {"user": "Auditor", "audit_title": "Engagement", "details": "Details"}, people=("subject_user",)),
    Trigger("action.due_soon", "An action falls due within N days", "schedule", "capa", _ACTION_FIELDS,
            "days before the due date", people=("owner", "creator")),
    Trigger("action.overdue", "An action is N days overdue", "schedule", "capa", _ACTION_FIELDS,
            "days after the due date", people=("owner", "creator")),
    Trigger("report.response_overdue", "Management has not responded to a draft report in time", "schedule",
            "audit_report", _REPORT_FIELDS, "days after the response due date", people=("creator", "auditees")),
    Trigger("report.distribution_incomplete", "An issued report has not reached every required recipient",
            "schedule", "audit_report", _REPORT_FIELDS, "days after issue", people=("creator",)),
    Trigger("charter.review_due", "The internal audit charter is due for review", "schedule", "charter",
            {"title": "Charter", "due_date": "Review due"}, "days before the review date"),
    Trigger("eqa.due", "An external quality assessment is due", "schedule", "eqa",
            {"due_date": "Due"}, "days before the due date"),
    Trigger("certification.expiring", "A staff certification is about to expire", "schedule", "certification",
            {"title": "Certification", "user": "Holder", "due_date": "Expires"}, "days before expiry",
            people=("subject_user",)),
    Trigger("declaration.annual_missing", "An auditor has no annual declaration for the year", "schedule", "user",
            {"user": "Auditor"}, "days into the year", people=("subject_user",)),
    Trigger("cpd.below_target", "An auditor is below the CPD target", "schedule", "user",
            {"user": "Auditor", "hours": "Hours this year", "target": "Target"}, "days before the year ends",
            people=("subject_user",)),
    Trigger("followup.quarter_ended", "A quarter ended without a follow-up report submitted", "schedule",
            "quarter", {"title": "Quarter"}, "days after the quarter ends"),
    Trigger("annual_statement.due", "The annual implementation statement is due and not submitted", "schedule",
            "year", {"title": "Year", "due_date": "Due"}, "days before the due date"),
]}

RECIPIENT_TOKENS = {
    "owner": "The action owner",
    "creator": "Whoever created the record",
    "auditees": "The audit's auditees",
    "subject_user": "The person the record is about",
}
OPS = {"eq": "is", "ne": "is not", "in": "is one of", "contains": "contains", "gte": "at least", "lte": "at most"}


# ---------------------------------------------------------------- built-in rules (editable by admins)

def _n(to: list[str], title: str, body: str) -> dict:
    return {"type": "notify", "to": to, "title": title, "body": body, "email": True}


BUILTINS: list[dict[str, Any]] = [
    {"key": "action_due_soon", "name": "Remind the owner 7 days before an action is due", "trigger":
     "action.due_soon", "offset_days": 7,
     "actions": [_n(["owner"], "Action {ref} is due on {due_date}",
                    "{title}\nPlease record the implementation, with evidence, before the due date.")]},
    {"key": "report_response_overdue", "name": "Draft report response overdue (L.I. 1994 reg. 43(2))",
     "trigger": "report.response_overdue", "offset_days": 0,
     "actions": [_n(["auditees", "creator", "role:gm_audit"], "Management response overdue: {ref}",
                    "The management response to the draft report \"{title}\" was due on {due_date}.")]},
    {"key": "report_distribution", "name": "Issued report not yet sent to every required recipient",
     "trigger": "report.distribution_incomplete", "offset_days": 5,
     "actions": [_n(["creator", "role:gm_audit"], "Report {ref} not yet distributed to: {missing}",
                    "Record the copies sent under the report's Distribution section.")]},
    {"key": "declaration_conflict", "name": "Send declared conflicts of interest to the GM Audit",
     "trigger": "declaration.conflict", "offset_days": 0,
     "actions": [_n(["perm:proficiency.manage"], "Conflict of interest declared by {user}",
                    "{user} declared a possible conflict for {audit_title}: {details}\nReview it before fieldwork.")]},
    {"key": "annual_declaration", "name": "Remind auditors to sign the annual declaration",
     "trigger": "declaration.annual_missing", "offset_days": 14,
     "actions": [_n(["subject_user"], "Please sign your annual declaration",
                    "Open Professional practice and sign the annual independence and ethics declaration.")]},
    {"key": "cpd_target", "name": "Warn auditors below the CPD target 60 days before year end",
     "trigger": "cpd.below_target", "offset_days": 60,
     "actions": [_n(["subject_user"], "CPD: {hours} of {target} hours recorded this year",
                    "Record your continuing professional development under Professional practice.")]},
    {"key": "cert_expiring", "name": "Certification expiring in 60 days", "trigger": "certification.expiring",
     "offset_days": 60, "actions": [_n(["subject_user"], "{title} expires on {due_date}",
                                       "Renew it and update your record under Professional practice.")]},
    {"key": "charter_review", "name": "Charter review due in 30 days", "trigger": "charter.review_due",
     "offset_days": 30, "actions": [_n(["perm:governance.charter"], "Internal audit charter review due {due_date}",
                                       "Prepare the revised charter for the Audit Committee (IIA GIAS 6.2).")]},
    {"key": "eqa_due", "name": "External quality assessment due within 6 months", "trigger": "eqa.due",
     "offset_days": 180, "actions": [_n(["perm:governance.charter"], "External quality assessment due {due_date}",
                                        "Plan the external quality assessment (IIA GIAS 8.4).")]},
    {"key": "quarterly_report", "name": "Quarterly follow-up report not yet submitted",
     "trigger": "followup.quarter_ended", "offset_days": 10,
     "actions": [_n(["perm:followup.report"], "Submit the follow-up report for {title}",
                    "Prepare it under Remediation > Reports and record its submission to the Audit Committee and "
                    "the Internal Audit Agency.")]},
    {"key": "annual_statement", "name": "Annual implementation statement due in 30 days",
     "trigger": "annual_statement.due", "offset_days": 30,
     "actions": [_n(["perm:followup.report", "role:gm_audit"], "Annual statement for {title} due {due_date}",
                    "Act 921 s.88(1)(b). Prepare it under Remediation > Reports.")]},
    {"key": "high_risk_finding", "name": "Tell the GM Audit about every High-risk finding",
     "trigger": "finding.created", "offset_days": 0, "conditions": [{"field": "risk_rating", "op": "eq",
                                                                      "value": "High"}],
     "actions": [_n(["role:gm_audit"], "High-risk finding raised: {title}", "Audit: {audit_title}")]},
]


def ensure_builtins(db: DBSession) -> None:
    have = set(db.execute(select(AutomationRule.builtin_key).where(AutomationRule.builtin_key.is_not(None)))
               .scalars())
    added = False
    for b in BUILTINS:
        if b["key"] in have:
            continue
        db.add(AutomationRule(name=b["name"], trigger=b["trigger"], offset_days=b["offset_days"],
                              conditions=json.dumps(b.get("conditions", [])), actions=json.dumps(b["actions"]),
                              active=True, builtin_key=b["key"],
                              description="Built-in rule. You can change or switch it off."))
        added = True
    if added:
        try:
            db.commit()
        except IntegrityError:  # another worker seeded them at the same moment
            db.rollback()


# ---------------------------------------------------------------- evaluation helpers

class _Safe(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def render(template: str, ctx: dict) -> str:
    return str(template or "").format_map(_Safe({k: ("" if v is None else v) for k, v in ctx.items()}))


def _matches(cond: dict, ctx: dict) -> bool:
    value = ctx.get(cond.get("field"))
    target = cond.get("value")
    op = cond.get("op", "eq")
    sval, starget = str(value if value is not None else "").lower(), str(target if target is not None else "").lower()
    if op == "eq":
        return sval == starget
    if op == "ne":
        return sval != starget
    if op == "in":
        return sval in [x.strip().lower() for x in starget.split(",")]
    if op == "contains":
        return starget in sval
    try:
        num, ref = float(value), float(target)
    except (TypeError, ValueError):
        return False
    return num >= ref if op == "gte" else num <= ref if op == "lte" else False


def conditions_met(rule: AutomationRule, ctx: dict) -> bool:
    try:
        conds = json.loads(rule.conditions or "[]")
    except ValueError:
        return False
    return all(_matches(c, ctx) for c in conds)


def resolve_recipients(db: DBSession, tokens: list[str], ctx: dict) -> list[int]:
    from app.core.permissions import has_perm, job_role_of
    from app.platform.users.models import User

    people: dict[str, list[int | None]] = ctx.get("_people", {})
    out: list[int] = []
    staff: list[User] | None = None
    for token in tokens:
        if token in RECIPIENT_TOKENS:
            out += [u for u in people.get(token, []) if u]
            continue
        kind, _, value = token.partition(":")
        if kind == "user" and value.isdigit():
            out.append(int(value))
            continue
        if staff is None:
            staff = list(db.execute(select(User).where(User.is_active.is_(True))).scalars())
        if kind == "role":
            out += [u.id for u in staff if job_role_of(u) == value]
        elif kind == "perm":
            out += [u.id for u in staff if u.role != Role.Auditee and has_perm(u, value)]
        elif kind == "tier":
            out += [u.id for u in staff if u.role.value == value]
    return list(dict.fromkeys(out))


def _execute(db: DBSession, rule: AutomationRule, ctx: dict, *, dry_run: bool = False) -> str:
    from app.core.tasksvc import create_task
    from app.platform.notifications.service import notify_many

    try:
        actions = json.loads(rule.actions or "[]")
    except ValueError:
        return "invalid actions"
    done = []
    for action in actions:
        recipients = resolve_recipients(db, action.get("to") or [], ctx)
        title = render(action.get("title") or rule.name, ctx)[:255]
        body = render(action.get("body") or "", ctx)
        if dry_run:
            done.append(f"{action.get('type')} -> {len(recipients)}")
            continue
        if action.get("type") == "task":
            due = utcnow() + timedelta(days=int(action.get("due_days") or 7))
            for uid in recipients:
                create_task(db, title=title, description=body, assignee_id=uid, due_date=due,
                            source_type=ctx.get("_link_type"), source_id=ctx.get("_link_id"), system_generated=True)
            done.append(f"{len(recipients)} task(s)")
        else:
            sent = notify_many(db, recipients, title, body, link_type=ctx.get("_link_type"),
                               link_id=ctx.get("_link_id"), email=bool(action.get("email", True)))
            done.append(f"{sent} notified")
    return ", ".join(done) or "no actions"


def _fire(db: DBSession, rule: AutomationRule, record_type: str, record_id: int, period: str, ctx: dict) -> bool:
    """Run the rule once for this record and period. Returns True when it ran."""
    exists = db.execute(select(AutomationRun.id).where(
        AutomationRun.rule_id == rule.id, AutomationRun.record_type == record_type,
        AutomationRun.record_id == record_id, AutomationRun.period_key == period)).first()
    if exists:
        return False
    if not conditions_met(rule, ctx):
        return False
    savepoint = db.begin_nested()
    try:
        run = AutomationRun(rule_id=rule.id, record_type=record_type, record_id=record_id, period_key=period[:40])
        db.add(run)
        db.flush()
        run.outcome = _execute(db, rule, ctx)[:255]
        savepoint.commit()
        return True
    except IntegrityError:
        savepoint.rollback()
        return False
    except Exception:  # noqa: BLE001 - an automation must never break the user's own work
        savepoint.rollback()
        logger.exception("Automation rule %s failed", rule.id)
        return False


# ---------------------------------------------------------------- contexts

def _fmt(d: datetime | None) -> str:
    return f"{d:%d %b %Y}" if d else ""


def capa_context(db: DBSession, capa, days: int | None = None) -> dict:  # noqa: ANN001
    from app.platform.notifications.service import user_id_by_email

    return {"ref": capa.capa_ref, "title": capa.title, "severity": getattr(capa.severity, "value", capa.severity),
            "source_body": capa.source_body or "", "timeframe": capa.timeframe or "",
            "implementation_status": capa.implementation_status, "owner_email": capa.owner_email or "",
            "due_date": _fmt(capa.due_date), "days": days if days is not None else "",
            "_link_type": "capa", "_link_id": capa.id,
            "_people": {"owner": [user_id_by_email(db, capa.owner_email)], "creator": [capa.created_by]}}


def _auditee_ids(db: DBSession, audit_id: int) -> list[int]:
    from app.domains.audit.audits.models import AuditAuditee

    return list(db.execute(select(AuditAuditee.user_id).where(AuditAuditee.audit_id == audit_id)).scalars())


def report_context(db: DBSession, report, days: int | None = None, missing: str = "") -> dict:  # noqa: ANN001
    return {"ref": report.report_ref, "title": report.title,
            "overall_rating": getattr(report.overall_rating, "value", report.overall_rating) or "",
            "due_date": _fmt(report.response_due_at), "days": days if days is not None else "", "missing": missing,
            "_link_type": "audit_report", "_link_id": report.id,
            "_people": {"creator": [report.created_by], "auditees": _auditee_ids(db, report.audit_id)}}


def finding_context(db: DBSession, finding) -> dict:  # noqa: ANN001
    audit = finding.audit
    return {"ref": f"F-{finding.id}", "title": finding.title,
            "risk_rating": getattr(finding.risk_rating, "value", finding.risk_rating),
            "audit_title": audit.title if audit else "", "_link_type": "finding", "_link_id": finding.id,
            "_people": {"creator": [finding.created_by], "auditees": _auditee_ids(db, finding.audit_id)}}


def _user_name(db: DBSession, user_id: int) -> str:
    from app.platform.users.models import User

    u = db.get(User, user_id)
    return (u.full_name or u.username) if u else "unknown"


# ---------------------------------------------------------------- event entry point

def emit(db: DBSession, trigger: str, record_type: str, record_id: int, ctx: dict, period: str = "once") -> int:
    """Fire every active rule for an event (inside the caller's transaction). Never raises."""
    try:
        rules = db.execute(select(AutomationRule).where(AutomationRule.trigger == trigger,
                                                        AutomationRule.active.is_(True))).scalars().all()
        return sum(1 for rule in rules if _fire(db, rule, record_type, record_id, period, ctx))
    except Exception:  # noqa: BLE001
        logger.exception("Automation emit failed for %s", trigger)
        return 0


# ---------------------------------------------------------------- scheduled evaluators

@dataclass
class Hit:
    record_type: str
    record_id: int
    period: str
    ctx: dict = field(default_factory=dict)


def _staff(db: DBSession) -> list:
    from app.platform.users.models import User

    return list(db.execute(select(User).where(User.is_active.is_(True),
                                              User.role.in_((Role.Admin, Role.Auditor)))).scalars())


def _scan(db: DBSession, trigger: str, offset: int, now: datetime) -> Iterator[Hit]:  # noqa: C901, PLR0912
    from app.core.appconfig import cfg
    from app.domains.issues.capa.models import Capa

    if trigger in ("action.due_soon", "action.overdue"):
        rows = db.execute(select(Capa).where(Capa.status != CapaStatus.Closed, Capa.due_date.is_not(None))).scalars()
        for capa in rows:
            if trigger == "action.due_soon":
                days = (capa.due_date.date() - now.date()).days
                if 0 <= days <= offset:
                    yield Hit("capa", capa.id, f"due:{capa.due_date:%Y%m%d}", capa_context(db, capa, days))
            else:
                days = (now.date() - capa.due_date.date()).days
                if days >= max(offset, 1):
                    yield Hit("capa", capa.id, f"over{offset}:{capa.due_date:%Y%m%d}", capa_context(db, capa, days))
    elif trigger == "report.response_overdue":
        from app.domains.audit.reports.models import AuditReport

        rows = db.execute(select(AuditReport).where(AuditReport.status == ReportStatus.ManagementReview,
                                                    AuditReport.response_received_at.is_(None),
                                                    AuditReport.response_due_at.is_not(None))).scalars()
        for r in rows:
            days = (now - r.response_due_at).days
            if now > r.response_due_at + timedelta(days=offset):
                yield Hit("audit_report", r.id, f"resp:{r.response_due_at:%Y%m%d}", report_context(db, r, max(days, 0)))
    elif trigger == "report.distribution_incomplete":
        from app.domains.audit.reports.distribution import missing_recipients
        from app.domains.audit.reports.models import AuditReport

        rows = db.execute(select(AuditReport).where(AuditReport.status == ReportStatus.Issued,
                                                    AuditReport.issued_at.is_not(None))).scalars()
        for r in rows:
            if now >= r.issued_at + timedelta(days=offset):
                missing = missing_recipients(db, r)
                if missing:
                    yield Hit("audit_report", r.id, "dist", report_context(db, r, missing=", ".join(missing)))
    elif trigger == "charter.review_due":
        from app.domains.assurance.conformance.models import InternalAuditCharter

        c = db.execute(select(InternalAuditCharter).where(InternalAuditCharter.status == "Approved")
                       .order_by(InternalAuditCharter.version.desc())).scalars().first()
        if c is not None and c.next_review_due and now >= c.next_review_due - timedelta(days=offset):
            yield Hit("charter", c.id, f"rev:{c.next_review_due:%Y%m%d}",
                      {"title": c.title, "due_date": _fmt(c.next_review_due)})
        elif c is None:
            yield Hit("charter", 0, f"none:{now:%Y%m}", {"title": "No approved charter", "due_date": "now"})
    elif trigger == "eqa.due":
        from app.domains.assurance.conformance.models import ExternalAssessment

        e = db.execute(select(ExternalAssessment).order_by(ExternalAssessment.completed_at.desc())).scalars().first()
        if e is not None and now >= e.next_due - timedelta(days=offset):
            yield Hit("eqa", e.id, f"due:{e.next_due:%Y%m%d}", {"due_date": _fmt(e.next_due)})
        elif e is None:
            yield Hit("eqa", 0, f"none:{now:%Y}", {"due_date": "no external assessment recorded"})
    elif trigger == "certification.expiring":
        from app.domains.audit.proficiency.models import Certification

        rows = db.execute(select(Certification).where(Certification.expires_on.is_not(None))).scalars()
        for c in rows:
            if c.expires_on - timedelta(days=offset) <= now <= c.expires_on + timedelta(days=30):
                yield Hit("certification", c.id, f"exp:{c.expires_on:%Y%m%d}",
                          {"title": c.name, "user": _user_name(db, c.user_id), "due_date": _fmt(c.expires_on),
                           "_people": {"subject_user": [c.user_id]}})
    elif trigger in ("declaration.annual_missing", "cpd.below_target"):
        from app.domains.audit.proficiency.service import annual_declared, cpd_hours

        year = now.year
        if trigger == "declaration.annual_missing" and (now - datetime(year, 1, 1)).days < offset:
            return
        if trigger == "cpd.below_target" and (datetime(year, 12, 31) - now).days > offset:
            return
        target = int(cfg("cpd_target_hours"))
        for u in _staff(db):
            ctx = {"user": u.full_name or u.username, "_people": {"subject_user": [u.id]}}
            if trigger == "declaration.annual_missing" and not annual_declared(db, u.id, year):
                yield Hit("user", u.id, f"decl:{year}", ctx)
            if trigger == "cpd.below_target" and target:
                hours = cpd_hours(db, u.id, year)
                if hours < target:
                    yield Hit("user", u.id, f"cpd:{year}", {**ctx, "hours": f"{hours:g}", "target": target})
    elif trigger == "followup.quarter_ended":
        from app.domains.issues.followup.models import FollowupSubmission

        q = (now.month - 1) // 3  # previous quarter number (0 = Q4 of last year)
        year, quarter = (now.year, q) if q else (now.year - 1, 4)
        end = datetime(year + (quarter == 4), 1 if quarter == 4 else quarter * 3 + 1, 1)
        if now >= end + timedelta(days=offset):
            done = db.execute(select(FollowupSubmission.id).where(FollowupSubmission.kind == "quarterly",
                                                                  FollowupSubmission.year == year,
                                                                  FollowupSubmission.quarter == quarter)).first()
            if not done:
                yield Hit("quarter", year * 10 + quarter, "once", {"title": f"Q{quarter} {year}"})
    elif trigger == "annual_statement.due":
        from app.domains.issues.followup.models import FollowupSubmission
        from app.domains.issues.followup.statements import annual_due_date

        year = now.year - 1
        due = annual_due_date(year)
        if now >= due - timedelta(days=offset):
            done = db.execute(select(FollowupSubmission.id).where(FollowupSubmission.kind == "annual",
                                                                  FollowupSubmission.year == year)).first()
            if not done:
                yield Hit("year", year, "once", {"title": str(year), "due_date": _fmt(due)})


def preview(db: DBSession, rule: AutomationRule, now: datetime | None = None) -> list[dict]:
    """What the rule would do right now (scheduled rules only), without sending anything."""
    now = now or utcnow()
    out = []
    for hit in _scan(db, rule.trigger, rule.offset_days, now):
        if not conditions_met(rule, hit.ctx):
            continue
        already = db.execute(select(AutomationRun.id).where(
            AutomationRun.rule_id == rule.id, AutomationRun.record_type == hit.record_type,
            AutomationRun.record_id == hit.record_id, AutomationRun.period_key == hit.period[:40])).first()
        out.append({"record_type": hit.record_type, "record_id": hit.record_id,
                    "title": render(_first_title(rule), hit.ctx), "already_sent": bool(already),
                    "plan": _execute(db, rule, hit.ctx, dry_run=True)})
        if len(out) >= 200:
            break
    return out


def _first_title(rule: AutomationRule) -> str:
    try:
        acts = json.loads(rule.actions or "[]")
        return acts[0].get("title") or rule.name
    except (ValueError, IndexError, AttributeError):
        return rule.name


def run_scheduled(db: DBSession, now: datetime | None = None, rule_id: int | None = None) -> int:
    """Evaluate every active scheduled rule; returns how many times rules fired."""
    now = now or utcnow()
    ensure_builtins(db)
    q = select(AutomationRule).where(AutomationRule.active.is_(True))
    if rule_id is not None:
        q = select(AutomationRule).where(AutomationRule.id == rule_id)
    fired = 0
    for rule in db.execute(q).scalars().all():
        trig = TRIGGERS.get(rule.trigger)
        if trig is None or trig.kind != "schedule":
            continue
        try:
            for hit in _scan(db, rule.trigger, rule.offset_days, now):
                if _fire(db, rule, hit.record_type, hit.record_id, hit.period, hit.ctx):
                    fired += 1
            rule.last_run_at = now
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.exception("Scheduled automation %s failed", rule.id)
    return fired
