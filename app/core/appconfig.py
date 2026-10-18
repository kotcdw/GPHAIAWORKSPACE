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


class AppConfigHistory(Base):
    """Every change to a setting: old and new value (JSON), who, when and why. Append-only (database triggers)."""

    __tablename__ = "app_config_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(10), nullable=False)  # update | reset
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    changed_by: Mapped[int | None] = mapped_column(nullable=True)
    changed_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, index=True)


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
    allow_empty: bool = False  # list rules: an empty list is a valid value

    def default_value(self) -> Any:
        if self.default_attr:
            value = getattr(settings, self.default_attr)
            if self.kind in ("roles", "list"):
                return [r.strip() for r in str(value).split(",") if r.strip()]
            return value
        return self.default


# Regional settings: chosen lists (never free text) so every screen, export and report can rely on them.
TIME_ZONES = ["Africa/Accra", "Africa/Abidjan", "Africa/Lagos", "Africa/Lome", "Africa/Johannesburg",
              "Africa/Nairobi", "Europe/London", "UTC"]
DATE_FORMATS = ["DD/MM/YYYY", "DD MMM YYYY", "DD-MM-YYYY", "YYYY-MM-DD", "MM/DD/YYYY"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

RULES: list[Rule] = [
    # --- regional settings
    Rule("time_zone", "Time zone", "Regional", "text",
         "Used for every date and time shown in the workspace, in exports and in reports. Ghana: Africa/Accra "
         "(GMT, no daylight saving).", default="Africa/Accra", options=TIME_ZONES),
    Rule("date_format", "Date format", "Regional", "text",
         "How dates are written everywhere, e.g. 18/10/2026 (DD/MM/YYYY) or 18 Oct 2026 (DD MMM YYYY).",
         default="DD/MM/YYYY", options=DATE_FORMATS),
    Rule("time_format", "Time format", "Regional", "text", "24-hour (14:30) or 12-hour (2:30 PM).",
         default="24-hour", options=["24-hour", "12-hour"]),
    Rule("fiscal_year_start_month", "First month of the fiscal year", "Regional", "int",
         "1 = January. GPHA follows the calendar year (January to December). A fiscal year is named after the "
         "calendar year in which it starts.", default=1, min=1, max=12),
    Rule("working_days", "Working days", "Regional", "list",
         "Days counted for working-day deadlines and SLA time limits (public holidays are listed under Follow-up "
         "& reporting).", default=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"], options=WEEKDAYS),
    Rule("language", "Language", "Regional", "text", "The workspace is available in English.",
         default="English", options=["English"]),
    # --- data and attachments (the server settings in .env remain the ceiling; administrators can tighten them)
    Rule("attachment_max_mb", "Largest file that can be attached (MB)", "Data & attachments", "int",
         "Working papers, evidence, remediation evidence and policy files. Cannot exceed the server limit.",
         default_attr="max_upload_mb", min=1, max=500),
    Rule("attachment_file_types", "File types that can be attached", "Data & attachments", "list",
         "Only these types are accepted. Programs and scripts are never accepted.",
         default_attr="upload_allowed_extensions", options=sorted(settings.allowed_extensions)),
    Rule("attachment_check_content", "Check that each file's content matches its type", "Data & attachments", "bool",
         "Refuses, for example, a program renamed to .pdf.", default=True),
    Rule("import_max_rows", "Most rows in one import file", "Data & attachments", "int", default=2000, min=10,
         max=5000),
    Rule("import_max_mb", "Largest import file (MB)", "Data & attachments", "int", default=5, min=1, max=20),
    # --- backups (the server setting GPHA_BACKUP_INTERVAL_HOURS=0 switches the schedule off entirely)
    Rule("backup_interval_hours", "Hours between automatic backups (0 = paused)", "Backups", "int",
         "Each backup is checked automatically when it finishes.", default_attr="backup_interval_hours", min=0,
         max=168),
    Rule("backup_retention", "Backups to keep", "Backups", "int", "Older backups are removed automatically.",
         default_attr="backup_retention", min=1, max=90),
    Rule("backup_include_attachments", "Include attachments", "Backups", "bool",
         "Working papers, evidence and other uploaded files. They stay encrypted in the backup.", default=True),
    # --- audit workflow
    Rule("require_report_to_close", "Require an issued report before an audit can be closed", "Audit workflow", "bool",
         "IIA GIAS 15.1: every engagement ends with a final communication.", default_attr="require_report_to_close"),
    Rule("require_findings_actioned_to_close", "Require every finding to have a management response and, for High "
         "and Medium risk, an agreed action before closing", "Audit workflow", "bool",
         default_attr="require_findings_actioned_to_close"),
    Rule("low_findings_close_without_action", "Low-rated findings may be closed without a remediation action",
         "Audit workflow", "bool", "Medium and High findings always close through a remediation action that "
         "Internal Audit validates as Effective.", default=True),
    Rule("management_response_requires_owner_and_date", "A management response must name the responsible officer "
         "and a target date", "Audit workflow", "bool", "As in the GPHA working paper template: Action Plan, "
         "Responsible Officer and Target Date.", default=True),
    Rule("require_management_response_for_review", "Require a management response on every finding before the "
         "report goes to Audit Manager review", "Audit workflow", "bool", default=True),
    Rule("require_memo_approval_for_fieldwork", "Require an approved planning memo before fieldwork starts",
         "Audit workflow", "bool", "IIA GIAS 13.6: the engagement work programme is approved before it is "
         "implemented.", default_attr="require_memo_approval_for_fieldwork"),
    Rule("report_review_chain", "Review chain for audit reports (before GM Audit approval)", "Audit workflow", "list",
         "In order, one per line: Unit Head, Audit Manager, PIA. Each level signs in turn; the GM Audit (CAE) then "
         "approves and issues. Leave empty to go straight to the GM Audit.", default_attr="report_review_chain",
         options=["Unit Head", "Audit Manager", "PIA"], allow_empty=True),
    Rule("workpaper_review_chain", "Review chain for working papers", "Audit workflow", "list",
         "In order, one per line: Unit Head, Audit Manager, PIA. A working paper is reviewed when every level has "
         "signed it off. Leave empty to let any reviewer sign it off once.", default_attr="workpaper_review_chain",
         options=["Unit Head", "Audit Manager", "PIA"], allow_empty=True),
    Rule("working_paper_locations", "Working paper locations", "Audit workflow", "list",
         "The sites offered in the Location field of the GPHA working paper template, one per line.",
         default_attr="working_paper_locations"),
    Rule("review_higher_level_may_cover", "A higher review level may sign for an absent lower level", "Audit workflow",
         "bool", "For example a PIA may sign the Unit Head stage when a unit has no Unit Head. Nobody signs two "
         "stages of the same document.", default=True),
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
    # --- audit methodology (Audit Administrator)
    Rule("audit_types", "Audit types", "Audit methodology", "list",
         "One per line. Used on audits, programmes and in analytics.",
         default=["Financial", "Compliance", "Operational", "Information Technology", "Performance / Value for Money",
                  "Special investigation", "Follow-up"]),
    Rule("workplan_audit_types", "Audit types that use the Workplan workflow", "Audit methodology", "list",
         "One per line. New audits of these types run on procedures (Objectives > Risks > Procedures > Execute). "
         "Other types use the Internal Control workflow (risk & control matrix, walkthroughs, testing rounds). The "
         "lead can switch an audit's workflow while it has no procedures or controls.",
         default=["Financial", "Operational", "Performance / Value for Money", "Special investigation", "Follow-up"],
         allow_empty=True),
    Rule("sample_sizes_by_frequency", "Default sample size for tests of operating effectiveness, by control frequency",
         "Audit methodology", "list", "One per line as Frequency=Size, for example Monthly=3. Used as the suggested "
         "sample in testing rounds and when drawing a sample; the auditor can change it on each test.",
         default=["Annual=1", "Quarterly=2", "Monthly=3", "Weekly=10", "Daily=25", "Multiple Daily=40", "Ad Hoc=25"]),
    Rule("audit_risk_scale", "Default rating scale for audit risk assessments", "Audit methodology", "text",
         "Used for new audit risk assessments (each assessment keeps the scale it was created with).",
         default="Low- to High-risk", options=["Low- to High-risk", "Very low- to Very high-risk"]),
    Rule("finding_issue_types", "Issue types", "Audit methodology", "list",
         "One per line. Offered on every finding and used by the Issue Tracker charts.",
         default=["Deficiency", "Significant Deficiency", "Material Weakness", "Management Recommendation"]),
    Rule("signoff_levels", "Sign-off levels on fieldwork pages", "Audit methodology", "list",
         "One per line, in order, up to five. The first is the preparer; the others are reviewers who sign after "
         "being set as the Next Reviewer. Applies to procedures, narratives, walkthroughs, test plans, tests, the "
         "risk control matrix and issues.",
         default=["Preparer", "Detail Reviewer", "General Reviewer", "Supplemental Reviewer", "Specialty Reviewer"]),
    Rule("signoff_preparer_required", "Reviewers sign only after the preparer has signed off", "Audit methodology",
         "bool", "When off, an Audit Manager may sign a reviewer level before the preparer.", default=True),
    Rule("signoff_requires_password", "Ask for the password on every sign-off (electronic signature)",
         "Audit methodology", "bool", "Off by default; switch on when sign-offs must be e-signed.", default=False),
    Rule("risk_high_threshold", "Inherent risk score (likelihood x impact) from which a unit is High risk",
         "Plan configuration", "int", default=15, min=2, max=25),
    Rule("risk_medium_threshold", "Inherent risk score from which a unit is Medium risk", "Plan configuration", "int",
         default=8, min=1, max=24),
    Rule("audit_cycle_high_years", "Audit High-risk units at least every (years)", "Plan configuration", "int",
         "Units not audited within their cycle are flagged as due on the Assurance Plan.", default=1, min=1, max=10),
    Rule("audit_cycle_medium_years", "Audit Medium-risk units at least every (years)", "Plan configuration", "int",
         default=2, min=1, max=10),
    Rule("audit_cycle_low_years", "Audit Low-risk units at least every (years)", "Plan configuration", "int",
         default=3, min=1, max=15),
    Rule("plan_cycle_enforced", "Follow the annual planning cycle: the plan can be approved only after preparation, "
         "the risk / universe review, the Audit Managers' planning meeting and submission for internal review are "
         "recorded", "Plan configuration", "bool", default=True),
    Rule("plan_distribution_before_execution", "Engagements can start only after the GM Audit has distributed the "
         "approved plan", "Plan configuration", "bool", default=True),
    Rule("plan_change_significant_hours_pct", "A plan change is significant (needs Audit Committee approval) when it "
         "moves planned hours by at least this % ", "Plan configuration", "int",
         "Adding or cancelling an engagement, leaving a high-risk unit uncovered or exceeding the budget is always "
         "significant (IIA GIAS 9.4: significant changes to the plan are approved by the board).", default=10, min=1,
         max=100),
    Rule("default_engagement_hours", "Default budget hours for a new engagement", "Plan configuration", "int",
         default=120, min=0, max=5000),
    # --- organizations / entities
    Rule("organization_categories", "Entity types users can choose for an organization", "Organizations", "list",
         "One per line. Ports, offices, departments and units describe GPHA itself; the rest are external parties.",
         default=["Port", "Head Office", "Department", "Unit", "Section", "Vendor", "Regulator",
                  "Government agency", "Shipping line / Customer", "Other"]),
    Rule("org_structure_categories", "Entity types that make up the Org Structure", "Organizations", "list",
         "One per line. Organizations of these types form the org tree used to define the audit universe; the rest "
         "(vendors, regulators and other external parties) stay out of it.",
         default=["Port", "Head Office", "Department", "Unit", "Section"]),
    Rule("universe_entity_types", "Auditable entity types", "Audit methodology", "list",
         "One per line. Offered when an auditable entity is defined.",
         default=["Org unit", "Process", "Process + unit", "IT system", "Third party", "Project / programme"]),
    Rule("port_categories", "Entity types that count as a port or site", "Organizations", "list",
         "One per line. Users pick one of these as where they work; every entity is filed under the port it sits in.",
         default=["Port", "Head Office"]),
    # --- security
    Rule("mfa_required_roles", "Roles that must use two-step verification", "Security", "roles",
         "Users in these roles are asked to set it up at their next sign-in.", default_attr="mfa_required_roles",
         options=["Admin", "Auditor", "Auditee"]),
    Rule("port_scope_enforced", "Restrict audit staff to their port and their engagement teams", "Security", "bool",
         "On: staff based at a port see that port's audits plus audits whose team they are on; HQ staff and the "
         "GM Audit see every port. Administrators always see everything. Off: all audit staff see every audit.",
         default_attr="port_scope_enforced"),
    Rule("authority_wide_categories", "Workplace types whose audit staff see every port (HQ)", "Security", "list",
         "One per line, from the entity types under Organizations. Staff based in one of these (or in a unit under "
         "it) see every port's audits; leave empty to limit HQ staff to their engagement teams too.",
         default=["Head Office"], allow_empty=True),
    Rule("mfa_enforced", "Enforce two-step verification for the roles above", "Security", "bool",
         "Off during development: nobody is forced to set it up. Turn it on when the workspace is ready for use; "
         "users in the roles above are then asked to set it up at their next sign-in. Anyone can still turn it "
         "on for themselves in their profile.", default_attr="mfa_enforced"),
    Rule("login_rate_limit_per_minute", "Sign-in attempts allowed per computer per minute (0 = no limit)",
         "Security", "int", default_attr="login_rate_limit_per_minute", min=0, max=1000),
    Rule("session_max_hours", "Longest sign-in session (hours)", "Security", "int",
         "After this, everyone signs in again even when active.", default_attr="session_ttl_hours", min=1, max=72),
    Rule("login_max_attempts", "Failed sign-ins before an account locks", "Security", "int",
         default_attr="login_max_attempts", min=3, max=20),
    Rule("login_lockout_minutes", "Lockout period (minutes)", "Security", "int",
         default_attr="login_lockout_minutes", min=1, max=1440),
    Rule("password_min_length", "Shortest password allowed", "Security", "int", default=8, min=8, max=64),
    Rule("session_idle_minutes", "Sign users out after this many minutes without activity (0 = never)", "Security",
         "int", "Applies to every account. A warning appears one minute before the sign-out. Background refreshes "
         "(notification counts) do not count as activity.", default=10, min=0, max=480),
    Rule("framework_types", "Kinds of framework in the Frameworks & controls library", "Audit methodology", "list",
         default=["Control framework (e.g. COSO)", "Risk management standard (e.g. ISO 31000)",
                  "IT governance framework (e.g. COBIT)", "Law or regulation", "GPHA policy or procedure"]),
    Rule("schedule_daily_hours", "Working hours per day (scheduler workload)", "Audit methodology", "int",
         "Used to compare booked engagement hours with the days available.", default=8, min=1, max=24),
    # --- follow-up of recommendations (MoF Audit Recommendations Implementation and Follow-up Instructions)
    Rule("draft_report_response_working_days", "Working days management has to respond to a draft audit report",
         "Follow-up & reporting", "int", "Internal Audit Regulations, 2011 (L.I. 1994) reg. 43(2): ten working days. "
         "The due date is set when the draft goes to management; weekends and the public holidays below are skipped.",
         default=10, min=1, max=90),
    Rule("public_holidays", "Public holidays (not counted as working days)", "Follow-up & reporting", "list",
         "One date per line as YYYY-MM-DD.", default=[], allow_empty=True),
    Rule("recommendation_sources", "Where recommendations come from", "Follow-up & reporting", "list",
         "The first entry is used for recommendations raised from internal audit findings. Others cover the "
         "Auditor-General's management letter, PAC and Parliament decisions (PFM Act 2016, Act 921, s.88).",
         default=["Internal Audit", "Auditor-General (Management Letter)", "Public Accounts Committee",
                  "Parliament", "Audit Committee", "Regulator / other body"]),
    Rule("action_timeframes", "Implementation timeframes for management action plans", "Follow-up & reporting",
         "list", default=["Short term (within 3 months)", "Medium term (3 to 12 months)",
                          "Long term (over 12 months)"]),
    Rule("committee_closes_recommendations", "Internal audit recommendations are closed by an Audit Committee "
         "decision (not by e-signature alone)", "Follow-up & reporting", "bool",
         "MoF instructions s.7.7: the Audit Committee closes internal audit recommendations once the evidence is "
         "sufficient. Recommendations from external bodies always need the external body's closure reference.",
         default=False),
    Rule("quarterly_report_recipients", "Recipients of the quarterly follow-up report", "Follow-up & reporting",
         "list", "Act 921 s.83(5)(e); MoF instructions s.6.1(3).",
         default=["Audit Committee", "Internal Audit Agency"]),
    Rule("annual_statement_recipients", "Recipients of the annual statement on implementation of recommendations",
         "Follow-up & reporting", "list", "Act 921 s.88(1)(b).",
         default=["Minister for Finance", "Parliament", "Office of the President", "Auditor-General",
                  "Internal Audit Agency"]),
    Rule("annual_statement_due", "Annual statement due date (MM-DD of the following year)", "Follow-up & reporting",
         "text", "Act 921 s.88(1)(b): not later than 30 June.", default="06-30"),
    Rule("report_statutory_recipients", "Who must receive a copy of every issued audit report",
         "Follow-up & reporting", "list",
         "Internal Audit Agency Act, 2003 (Act 658) s.16(3)-(5). Adjust to GPHA's reporting route.",
         default=["Director-General (Management)", "Audit Committee", "Internal Audit Agency (Director-General)",
                  "Auditor-General"]),
    # --- professional practice (IIA GIAS Domains II and III)
    Rule("require_engagement_declaration", "Require independence / conflict-of-interest declarations before "
         "fieldwork starts", "Professional practice", "bool",
         "IIA GIAS 2.1-2.3 and 7.1: the GM Audit, the engagement creator and the lead auditor must hold a current "
         "annual declaration and have declared for this engagement.", default_attr="require_engagement_declaration"),
    Rule("declaration_text_annual", "Annual declaration text", "Professional practice", "longtext",
         default=("I confirm that during this year I will comply with the IIA Code of Ethics and the Global Internal "
                  "Audit Standards (integrity, objectivity, competency, due professional care and confidentiality), "
                  "and with sections 18 to 20 of the Internal Audit Agency Act, 2003 (Act 658). I will keep "
                  "information obtained in the course of my work confidential, and I will disclose promptly any "
                  "relationship, interest or circumstance that could impair, or appear to impair, my objectivity.")),
    Rule("declaration_text_engagement", "Engagement declaration text", "Professional practice", "longtext",
         default=("For this engagement I confirm that I have no personal, financial or professional relationship "
                  "with the area under review, I have not been responsible for the activities under review in the "
                  "past 12 months, and I am not aware of anything that impairs my objectivity. Any conflict is "
                  "disclosed below.")),
    Rule("cpd_target_hours", "Continuing professional development hours expected per auditor per year",
         "Professional practice", "int", "IIA GIAS 3.2.", default=40, min=0, max=200),
    Rule("cpd_ethics_hours", "Of which ethics hours", "Professional practice", "int", default=2, min=0, max=40),
    Rule("charter_review_months", "Review the internal audit charter every (months)", "Professional practice",
         "int", "IIA GIAS 6.2: the charter is reviewed with the board periodically.", default=12, min=1, max=60),
    Rule("eqa_interval_years", "External quality assessment at least every (years)", "Professional practice", "int",
         "IIA GIAS 8.4.", default=5, min=1, max=5),
    Rule("conformance_statement", "Conformance statement for Audit Committee reports", "Professional practice",
         "longtext", "Shown in the Committee pack with the latest internal and external assessment results "
         "(IIA GIAS 8.3, 15.1).",
         default=("The Internal Audit Department conducts its work in conformance with the IIA Global Internal Audit "
                  "Standards and the standards and procedures of the Internal Audit Agency, as confirmed by the "
                  "results of the quality assurance and improvement programme summarised below.")),
    Rule("retention_years", "Keep closed audit files for (years) before review for disposal", "Professional practice",
         "int", "Set according to GPHA's records management policy. Nothing is deleted automatically; records past "
         "this period are listed for review.", default=7, min=1, max=50),
    # --- AI service (pluggable, off by default)
    Rule("ai_enabled", "Allow AI drafting assistance", "AI", "bool",
         "Off by default. When on, users with the 'Use AI drafting assistance' permission can ask for drafts of "
         "findings, executive summaries and risks/controls. Drafts are never saved until a person accepts them, and "
         "every request is logged. Auditors remain responsible for their work (IIA GIAS 4.2 due professional care).",
         default=False),
    Rule("ai_provider", "AI provider", "AI", "text",
         "anthropic, azure_openai, or openai_compatible (any OpenAI-style endpoint, e.g. a model hosted on GPHA's own "
         "server with Ollama or LM Studio, so no data leaves the network). The API key is read from GPHA_AI_API_KEY "
         "on the server.", default="openai_compatible",
         options=["anthropic", "azure_openai", "openai_compatible"]),
    Rule("ai_model", "AI model name", "AI", "text",
         "The model or deployment name at the provider, e.g. a Claude model id, an Azure deployment name or a local "
         "model such as llama3.1.", default="llama3.1"),
    Rule("ai_base_url", "AI endpoint address", "AI", "text",
         "e.g. https://api.anthropic.com, https://<resource>.openai.azure.com, or http://localhost:11434 for Ollama.",
         default="http://localhost:11434"),
    Rule("ai_redact_personal_data", "Remove e-mail addresses and phone numbers before text is sent to the AI", "AI",
         "bool", "Supports the Data Protection Act, 2012 (Act 843).", default=True),
    Rule("ai_max_input_chars", "Maximum characters of record text sent per AI request", "AI", "int",
         default=12000, min=1000, max=100000),
    Rule("ai_timeout_seconds", "Seconds to wait for the AI provider", "AI", "int", default=60, min=5, max=300),
    # --- reports
    Rule("org_name", "Organisation name on reports", "Reports", "text",
         default="Ghana Ports and Harbours Authority"),
    Rule("department_name", "Department name on reports", "Reports", "text", default="Internal Audit Department"),
    Rule("document_classification", "Classification printed in the footer of every Word document", "Reports",
         "text", "e.g. CONFIDENTIAL, RESTRICTED or INTERNAL.", default="CONFIDENTIAL"),
    Rule("report_methodology", "Default methodology paragraph for new reports", "Reports", "longtext",
         default=("The audit was performed in accordance with the IIA Global Internal Audit Standards. Work included "
                  "walkthroughs, assessment of control design and testing of operating effectiveness on a sample "
                  "basis.")),
    # --- risk & compliance apps (Risk Manager, Compliance Maps, Policy Manager, Asset Inventory)
    Rule("erm_risk_categories", "Enterprise risk categories", "Risk & compliance", "list",
         default=["Strategic", "Operational", "Financial", "Compliance / Regulatory", "Safety, Health & Environment",
                  "Security", "Information Technology", "Reputational", "Project"]),
    Rule("erm_appetite_levels", "Risk appetite levels", "Risk & compliance", "list",
         "From the most cautious to the most open.", default=["Averse", "Minimal", "Cautious", "Open", "Hungry"]),
    Rule("erm_treatments", "Risk treatment options", "Risk & compliance", "list",
         default=["Mitigate", "Accept", "Transfer", "Avoid"]),
    Rule("erm_review_months", "Review each enterprise risk at least every (months)", "Risk & compliance", "int",
         "Risks not assessed within this period are flagged as overdue for review.", default=3, min=1, max=24),
    Rule("regulation_types", "Kinds of obligation in Compliance Maps", "Risk & compliance", "list",
         default=["Law / Act", "Regulation / L.I.", "Directive / Instruction", "Standard", "Contract / Licence",
                  "GPHA policy"]),
    Rule("policy_categories", "Policy categories", "Risk & compliance", "list",
         default=["Governance", "Finance", "Procurement", "Human Resources", "Information Technology",
                  "Marine & Operations", "Safety & Security", "Estates", "Legal & Compliance"]),
    Rule("policy_review_months", "Default policy review cycle (months)", "Risk & compliance", "int",
         default=24, min=1, max=120),
    Rule("asset_types", "Asset and third-party types", "Risk & compliance", "list",
         "Entries that contain 'Third party' show the contract and due-diligence fields.",
         default=["IT system / Application", "IT infrastructure", "Data set", "Facility / Building",
                  "Vessel / Equipment", "Third party / Vendor", "Third party / Contractor", "Business process"]),
    Rule("data_classifications", "Information classifications", "Risk & compliance", "list",
         default=["Public", "Internal", "Confidential", "Restricted"]),
    Rule("third_party_review_months", "Re-assess critical and high third parties every (months)",
         "Risk & compliance", "int", default=12, min=1, max=60),
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


def parse_sample_sizes(entries: list[str]) -> dict[str, int]:
    """Read "Frequency=Size" lines; raise ValueError naming the first bad line."""
    from app.core.enums import ControlFrequency

    names = {f.value.lower(): f.value for f in ControlFrequency}
    sizes: dict[str, int] = {}
    for entry in entries:
        name, sep, size = entry.partition("=")
        key = names.get(name.strip().lower())
        if not sep or key is None or not size.strip().isdigit() or not 1 <= int(size) <= 1000:
            raise ValueError(f"'{entry}' must look like Monthly=3 (frequencies: {', '.join(names.values())}; "
                             "sizes 1 to 1000)")
        sizes[key] = int(size)
    return sizes


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
        if not clean and not rule.allow_empty:
            raise ValueError("enter at least one entry")
        if rule.options:
            canon = {o.lower(): o for o in rule.options}
            bad = [c for c in clean if c.lower() not in canon]
            if bad:
                raise ValueError(f"unknown entr{'y' if len(bad) == 1 else 'ies'}: {', '.join(bad)} "
                                 f"(use {', '.join(rule.options)})")
            clean = sorted((canon[c.lower()] for c in clean), key=rule.options.index)
        if rule.key == "sample_sizes_by_frequency":
            parse_sample_sizes(clean)
        if len(clean) > 100:
            raise ValueError("enter at most 100 entries")
        return clean
    text = str(value or "").strip()
    if rule.kind == "text" and (not text or len(text) > 200):
        raise ValueError("enter 1 to 200 characters")
    if rule.kind == "text" and rule.options and text not in rule.options:
        raise ValueError(f"must be one of: {', '.join(rule.options)}")
    if rule.kind == "longtext" and len(text) > 5000:
        raise ValueError("enter at most 5000 characters")
    return text
