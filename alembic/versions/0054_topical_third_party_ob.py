"""Seed the Third-Party (in force 15 September 2026) and Organizational Behavior (in force 15 December 2026)
IIA Topical Requirements, worded briefly for the checklist. Administrators maintain the catalogue afterwards in
Configuration > Topical requirements.

Revision ID: 0054_topical_third_party_ob
Revises: 0053_role_module_access
Create Date: 2026-10-23
"""

from __future__ import annotations

from datetime import date

import sqlalchemy as sa

from alembic import op

revision: str = "0054_topical_third_party_ob"
down_revision: str | None = "0053_role_module_access"
branch_labels = None
depends_on = None

APPLIES = ("Applies when {topic} is the subject of a planned engagement, is identified during an engagement, or is "
           "the subject of an engagement request. Mandatory for assurance engagements, recommended for advisory ones. "
           "Each requirement is assessed; exclusions keep their rationale.")

THIRD_PARTY = [
    ("Governance", "G-A", "A formal, periodically reviewed approach decides when to use a third party, with criteria "
                          "for the resources needed and available."),
    ("Governance", "G-B", "Policies and procedures cover the whole third-party life cycle, follow laws and "
                          "regulations, and are updated regularly."),
    ("Governance", "G-C", "Roles for selecting, directing, managing, monitoring and being informed about third "
                          "parties are defined, and role holders are competent."),
    ("Governance", "G-D", "Stakeholders receive timely reports on the performance, risks and any legal or regulatory "
                          "breaches of risk-prioritised third parties."),
    ("Risk management", "R-A", "Third-party risk is managed through a standard process with defined roles, covering "
                               "the key risk categories, with deviations corrected."),
    ("Risk management", "R-B", "Third-party risks (including downstream parties) are assessed across the life cycle, "
                               "used to rank third parties, and reassessed periodically."),
    ("Risk management", "R-C", "Risk responses match each third party's ranking and are approved, implemented, "
                               "monitored and adjusted when needed."),
    ("Risk management", "R-D", "Third-party issues are escalated with clear accountability; unresolved escalations "
                               "lead to remediation or termination of the relationship."),
    ("Control processes", "C-A", "Sourcing and selection rely on due diligence and an approved business case for the "
                                 "relationship."),
    ("Control processes", "C-B", "Contracting and approval follow the third-party risk policies, with the relevant "
                                 "functions involved."),
    ("Control processes", "C-C", "Final contracts are reviewed (including legal and compliance), signed by authorised "
                                 "people, stored securely and given a contract manager."),
    ("Control processes", "C-D", "A complete, accurate and current inventory of third-party relationships is kept."),
    ("Control processes", "C-E", "Documented onboarding prepares each third party to meet the contract terms."),
    ("Control processes", "C-F", "Ongoing monitoring confirms performance and contractual obligations, checks the "
                                 "information relied on, and reassesses when agreements change."),
    ("Control processes", "C-G", "Under-performance or elevated risk triggers corrective action, escalation by "
                                 "severity, post-incident review and root-cause analysis."),
    ("Control processes", "C-H", "Contract expiry and renewal dates are tracked and acted on in time."),
    ("Control processes", "C-I", "A formal offboarding plan covers termination, replacement, return or destruction of "
                                 "data and removal of access."),
]

ORG_BEHAVIOR = [
    ("Governance", "G-A", "The board oversees, and senior management defines, roles and responsibilities so that "
                          "misaligned behaviour does not lead to conflicts of interest or unclear decisions."),
    ("Governance", "G-B", "Leaders hold individuals and teams accountable for expected behaviour, and roles are "
                          "understood and aligned to objectives."),
    ("Governance", "G-C", "Governance routinely checks and challenges whether behavioural insights match the "
                          "objectives, and acts on misalignment."),
    ("Governance", "G-D", "Behavioural risk policies exist, are reviewed periodically, communicated, and built into "
                          "daily operations and decisions."),
    ("Risk management", "R-A", "A defined approach to behavioural risk identifies the behaviours critical to "
                               "achieving the objectives."),
    ("Risk management", "R-B", "Behaviour is monitored adequately and in time, and the results are shared with "
                               "stakeholders."),
    ("Risk management", "R-C", "Gaps between expected and actual behaviour, and their root causes, are communicated "
                               "to stakeholders consistently."),
    ("Risk management", "R-D", "Gaps are addressed with stakeholder input, tracked to completion and measured to "
                               "confirm the action was enough."),
    ("Control processes", "C-A", "Behaviour patterns that could threaten objectives are identified and reduced, for "
                                 "example through performance or operational risk reviews."),
    ("Control processes", "C-B", "Leaders set a clear, consistent tone through trusted channels and use structured "
                                 "feedback to check it is understood."),
    ("Control processes", "C-C", "People are encouraged to report behaviour that conflicts with the objectives, are "
                                 "protected when they do, and reports are resolved under defined rules."),
    ("Control processes", "C-D", "Monetary and non-monetary incentives are communicated, aligned with objectives and "
                                 "regulations, and improper behaviour has consequences."),
    ("Control processes", "C-E", "An issue management process corrects misaligned behaviour patterns and escalates "
                                 "when necessary."),
    ("Control processes", "C-F", "Training and awareness that align behaviour with the objectives are delivered "
                                 "periodically and work."),
    ("Control processes", "C-G", "Recruitment and onboarding reflect the expected behaviours and behavioural "
                                 "competencies."),
]

SEED = [
    ("third_party", "Third-Party", "2025", date(2026, 9, 15), "third-party risk",
     "https://www.theiia.org/en/standards/2024-standards/topical-requirements/third-party/", THIRD_PARTY),
    ("organizational_behavior", "Organizational Behavior", "2025", date(2026, 12, 15), "organizational behavior",
     "https://www.theiia.org/en/standards/2024-standards/topical-requirements/organizational-behavior/", ORG_BEHAVIOR),
]


def upgrade() -> None:
    bind = op.get_bind()
    reqs = sa.table("topical_requirements", sa.column("id", sa.Integer), sa.column("code", sa.String),
                    sa.column("title", sa.String), sa.column("version", sa.String),
                    sa.column("effective_on", sa.Date), sa.column("description", sa.Text),
                    sa.column("source_url", sa.String), sa.column("is_active", sa.Boolean))
    items = sa.table("topical_requirement_items", sa.column("requirement_id", sa.Integer),
                     sa.column("area", sa.String), sa.column("ref", sa.String), sa.column("text", sa.Text),
                     sa.column("sort", sa.Integer))
    for code, title, version, effective, topic, url, rows in SEED:
        if bind.execute(sa.select(reqs.c.id).where(reqs.c.code == code)).first():
            continue
        bind.execute(reqs.insert().values(code=code, title=title, version=version, effective_on=effective,
                                          description=APPLIES.format(topic=topic), source_url=url, is_active=True))
        rid = bind.execute(sa.select(reqs.c.id).where(reqs.c.code == code)).scalar_one()
        bind.execute(items.insert(), [{"requirement_id": rid, "area": a, "ref": r, "text": t, "sort": i}
                                      for i, (a, r, t) in enumerate(rows)])


def downgrade() -> None:
    bind = op.get_bind()
    for code in ("third_party", "organizational_behavior"):
        bind.execute(sa.text("DELETE FROM topical_requirements WHERE code = :c"), {"c": code})
