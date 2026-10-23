"""Documents Service: one place that produces GPHA documents (Word) and stores evidence files.

Every Word output - audit report, engagement letter, planning memo, QAIP report,
controlled copies of the Assurance Plan - is built with the same letterhead, classification footer and
download response (``word``). Uploaded evidence and working papers are stored encrypted with an integrity
hash (``storage``). ``CATALOGUE`` lists the document types for the platform map.
"""

from app.services.documents.excel import XLSX_MEDIA_TYPE, workbook, xlsx_response
from app.services.documents.word import DOCX_MEDIA_TYPE, add_table, docx_response, new_document, to_bytes

CATALOGUE = [
    {"name": "Audit report", "domain": "audit", "endpoint": "/api/reports/{id}/export.docx"},
    {"name": "Engagement letter", "domain": "audit", "endpoint": "/api/audits/{id}/engagement-letter.docx"},
    {"name": "Planning memorandum", "domain": "audit", "endpoint": "/api/audits/{id}/planning-memo/export.docx"},
    {"name": "Internal quality assessment (QAIP) report", "domain": "assurance", "endpoint": "/api/qaip/report.docx"},
    {"name": "Assurance Plan controlled copy (per version / destination)", "domain": "assurance",
     "endpoint": "/api/assurance-plans/{id}/versions/{n}/export.docx"},
    {"name": "Quarterly follow-up report (Audit Committee / IAA)", "domain": "issues",
     "endpoint": "/api/follow-up/quarterly.docx|.xlsx"},
    {"name": "Annual statement on implementation of recommendations (Act 921 s.88)", "domain": "issues",
     "endpoint": "/api/follow-up/annual.docx|.xlsx"},
    {"name": "Register of audit reports and distribution", "domain": "audit", "endpoint": "/api/reports/register.xlsx"},
    {"name": "Internal audit charter", "domain": "assurance", "endpoint": "/api/charter/{id}/export.docx"},
    {"name": "Working papers and evidence files (encrypted, SHA-256)", "domain": "audit",
     "endpoint": "/api/working-papers/{id}/download, /api/evidence-files/{id}/download"},
]

__all__ = ["CATALOGUE", "DOCX_MEDIA_TYPE", "XLSX_MEDIA_TYPE", "add_table", "docx_response", "new_document",
           "to_bytes", "workbook", "xlsx_response"]
