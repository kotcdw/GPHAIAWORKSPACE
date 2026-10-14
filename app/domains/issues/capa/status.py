"""Implementation status of a recommendation, in the categories used by the Ministry of Finance
Audit Recommendations Implementation and Follow-up Instructions (Fully / Partially / Not Implemented)."""

from __future__ import annotations

NOT_IMPLEMENTED = "Not Implemented"
PARTIALLY = "Partially Implemented"
FULLY = "Fully Implemented"
WITHDRAWN = "Withdrawn"
IMPLEMENTATION_STATUSES = (NOT_IMPLEMENTED, PARTIALLY, FULLY, WITHDRAWN)


def is_internal(capa) -> bool:  # noqa: ANN001
    """Raised by GPHA Internal Audit (a finding, or the first configured source)."""
    from app.core.appconfig import cfg

    sources = cfg("recommendation_sources") or []
    internal = sources[0] if sources else "Internal Audit"
    return capa.source_type == "finding" or not capa.source_body or capa.source_body == internal
