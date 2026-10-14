"""Business domains: Audit, Assurance (planning and governance) and Issues (findings follow-up).

Domains share one database through ``app.core.database`` and talk to each other only through
their models and service functions, never through HTTP.
"""

from __future__ import annotations


def layers() -> list:
    from app.domains import assurance, audit, issues

    return [audit, assurance, issues]
