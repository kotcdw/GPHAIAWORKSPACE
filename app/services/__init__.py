"""Shared services used by every domain: AI (optional), Analytics and Documents."""

from __future__ import annotations

NAME = "Services"
DESCRIPTION = (
    "AI Service (pluggable, off by default), Analytics Service and Documents Service."
)
MODULES = {
    "ai": "Optional AI drafting assistance; always produces drafts a person must accept",
    "analytics": "Dashboards, KPIs and insights over the shared data",
    "documents": "Word documents with letterhead and classification, encrypted file storage",
    "results": "Results, Storyboards and Robots: analytic tables, charts and scheduled checks on GIAW data",
}


def routers() -> list:
    from app.services.ai.router import router as ai
    from app.services.analytics.router import router as analytics
    from app.services.results.router import router as results

    return [analytics, ai, results]
