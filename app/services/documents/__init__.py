"""Documents Service: one place that produces GPHA documents (Word) and stores evidence files.

Every Word output - audit report, engagement letter, planning memo, Audit Committee pack, QAIP report,
controlled copies of the Assurance Plan - is built with the same letterhead, classification footer and
download response (``word``). Uploaded evidence and working papers are stored encrypted with an integrity
hash (``storage``). ``CATALOGUE`` lists the document types for the platform map.
"""

from app.services.documents.word import DOCX_MEDIA_TYPE, add_table, docx_response, new_document, to_bytes

CATALOGUE = [
    {"name": "Audit report", "domain": "audit", "endpoint": "/api/reports/{id}/export.docx"},
    {"name": "Engagement letter", "domain": "audit", "endpoint": "/api/audits/{id}/engagement-letter.docx"},
    {"name": "Planning memorandum", "domain": "audit", "endpoint": "/api/audits/{id}/planning-memo/export.docx"},
    {"name": "Audit Committee pack", "domain": "assurance", "endpoint": "/api/committee/pack.docx"},
    {"name": "Internal quality assessment (QAIP) report", "domain": "assurance", "endpoint": "/api/qaip/report.docx"},
    {"name": "Assurance Plan controlled copy (per version / destination)", "domain": "assurance",
     "endpoint": "/api/assurance-plans/{id}/versions/{n}/export.docx"},
    {"name": "Working papers and evidence files (encrypted, SHA-256)", "domain": "audit",
     "endpoint": "/api/working-papers/{id}/download, /api/evidence-files/{id}/download"},
]

__all__ = ["CATALOGUE", "DOCX_MEDIA_TYPE", "add_table", "docx_response", "new_document", "to_bytes"]
