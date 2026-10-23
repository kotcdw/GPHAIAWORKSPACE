"""Shared services used by every domain: AI (optional), Analytics and Documents."""

from __future__ import annotations

NAME = "Services"
DESCRIPTION = (
    "AI Service (pluggable, off by default), Analytics, Documents, Results and Reporting Services."
)
MODULES = {
    "ai": "Optional AI drafting assistance; always produces drafts a person must accept",
    "analytics": "Dashboards, KPIs and insights over the shared data",
    "documents": "Word documents with letterhead and classification, encrypted file storage",
    "results": "Results, Storyboards and Robots: analytic tables, charts and scheduled checks on workspace data",
    "reporting": "Reports, Dashboards, Presentations and AI Reporting over scoped Views, shared by access",
}


def routers() -> list:
    from app.services.ai.router import router as ai
    from app.services.analytics.router import router as analytics
    from app.services.reporting.ai_reporting import router as ai_reporting
    from app.services.reporting.broadcasts import router as broadcasts
    from app.services.reporting.media import router as media
    from app.services.reporting.present_export import router as present_export
    from app.services.reporting.router import router as reporting
    from app.services.results.router import router as results

    return [analytics, ai, results, reporting, ai_reporting, broadcasts, media, present_export]
