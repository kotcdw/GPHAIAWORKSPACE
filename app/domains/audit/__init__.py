"""Audit Domain Module: running engagements from programme to report."""

from __future__ import annotations

NAME = "Audit Domain Module"
DESCRIPTION = (
    "Engagements, risk and control matrices, programmes, working papers, evidence, findings, memos, "
    "methodology, capacity and reports."
)
MODULES = {
    "audits": "Engagements, lifecycle, findings, working papers, engagement letters",
    "rcm": "Risk and control matrices",
    "programs": "Audit programmes and procedures",
    "evidence": "Evidence requests and encrypted evidence files",
    "memos": "Planning memoranda",
    "methodology": "Methodology library",
    "capacity": "Auditor capacity and allocation",
    "reports": "Audit reports and management responses",
    "service_feedback": "Post-audit auditee feedback",
    "proficiency": "Independence and ethics declarations, CPD and certifications",
    "fieldwork": "Workplan procedures, walkthroughs and testing rounds (HighBond project workflows)",
    "frameworks": "Frameworks and the standard controls library used to build control matrices",
}


def routers() -> list:
    from app.domains.audit.audits.findings import router as findings
    from app.domains.audit.audits.issue_tracker import router as issue_tracker
    from app.domains.audit.audits.lifecycle import router as lifecycle
    from app.domains.audit.audits.router import router as audits
    from app.domains.audit.audits.working_papers import router as working_papers
    from app.domains.audit.capacity.router import router as capacity
    from app.domains.audit.evidence.router import router as evidence
    from app.domains.audit.fieldwork.router import router as fieldwork
    from app.domains.audit.frameworks.router import router as frameworks
    from app.domains.audit.memos.router import router as memos
    from app.domains.audit.methodology.router import router as methodology
    from app.domains.audit.proficiency.router import router as proficiency
    from app.domains.audit.programs.router import router as programs
    from app.domains.audit.rcm.router import router as rcm
    from app.domains.audit.reports.distribution import router as report_distribution
    from app.domains.audit.reports.router import router as reports
    from app.domains.audit.service_feedback.router import router as service_feedback

    # report_distribution before reports: /api/reports/register must win over /api/reports/{id}.
    # issue_tracker before findings: /api/findings/register must win over /api/findings/{id}.
    return [audits, issue_tracker, findings, working_papers, service_feedback, rcm, fieldwork, report_distribution,
            reports, lifecycle, memos, capacity, methodology, programs, evidence, proficiency, frameworks]
