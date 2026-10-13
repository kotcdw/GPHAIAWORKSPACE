"""Human-readable record reference generator.

References look like ``NC-0001``, ``CAPA-0012``, ``ORG-0003``. Numbers come from
the ``reference_sequences`` table, incremented under a row lock, so concurrent
writers never collide.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.models import ReferenceSequence

DEFAULT_WIDTH = 4


def format_reference(prefix: str, number: int, width: int = DEFAULT_WIDTH) -> str:
    return f"{prefix}-{number:0{width}d}"


def next_reference(db: DBSession, prefix: str, width: int = DEFAULT_WIDTH) -> str:
    """Reserve and return the next reference for ``prefix`` (e.g. ``NC-0007``).

    The reserved value is flushed within the caller's transaction; commit (or
    roll back) it together with the record being created.
    """
    row = db.execute(
        select(ReferenceSequence).where(ReferenceSequence.prefix == prefix).with_for_update()
    ).scalar_one_or_none()
    if row is None:  # defensive: prefix not pre-seeded
        row = ReferenceSequence(prefix=prefix, next_value=0)
        db.add(row)
        db.flush()
    row.next_value += 1
    db.flush()
    return format_reference(prefix, row.next_value, width)