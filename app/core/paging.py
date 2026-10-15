"""Server-side pagination, sorting and search for registers (the shared DataTable on the screen).

Every register endpoint takes the same query parameters and returns the same envelope:

    GET /api/<register>?page=1&page_size=25&sort=-updated_at&q=text&<filters>
    {"items": [...], "total": 123, "page": 1, "page_size": 25, "sort": "-updated_at"}

``sort`` names one whitelisted column, with ``-`` for descending. Unknown sort keys are rejected (422) rather than
silently ignored. Authorization always happens before paging: callers filter the rows a user may read first, then
page them, so counts and pages never reveal records outside the user's access.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session as DBSession

from app.core.errors import field_error

T = TypeVar("T")
MAX_PAGE_SIZE = 100


class Page(BaseModel, Generic[T]):  # noqa: UP046 - pydantic generic model
    items: list[T]
    total: int
    page: int
    page_size: int
    sort: str | None = None


@dataclass(frozen=True)
class PageParams:
    page: int
    page_size: int
    sort: str | None
    q: str | None

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    def sort_key(self, allowed: Sequence[str], default: str) -> tuple[str, bool]:
        """(column key, descending) after checking the key against ``allowed``."""
        raw = self.sort or default
        desc = raw.startswith("-")
        key = raw[1:] if desc else raw
        if key not in allowed:
            raise field_error("sort", f"cannot sort by '{key}'; choose one of: {', '.join(allowed)}")
        return key, desc


def page_params(
    page: int = Query(1, ge=1, le=100000, description="Page number, starting at 1"),
    page_size: int = Query(25, ge=1, le=MAX_PAGE_SIZE, description=f"Rows per page (at most {MAX_PAGE_SIZE})"),
    sort: str | None = Query(None, max_length=40, pattern=r"^-?[a-z_]+$", description="Column, '-' for descending"),
    q: str | None = Query(None, max_length=120, description="Search text"),
) -> PageParams:
    return PageParams(page=page, page_size=page_size, sort=sort, q=(q or "").strip() or None)


def paginate_query(db: DBSession, stmt: Select, params: PageParams, sortable: dict[str, Any], default: str,
                   tiebreak: Any) -> tuple[list, int, str]:
    """Count, sort and page a SQL query. ``sortable`` maps sort keys to columns; ``tiebreak`` keeps order stable."""
    key, desc = params.sort_key(list(sortable), default)
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
    column = sortable[key]
    stmt = stmt.order_by(None).order_by(column.desc() if desc else column.asc(),
                                        tiebreak.desc() if desc else tiebreak.asc())
    rows = list(db.execute(stmt.limit(params.page_size).offset(params.offset)).scalars().all())
    return rows, total, ("-" if desc else "") + key


def paginate_rows(rows: list[dict], params: PageParams, sortable: dict[str, Callable[[dict], Any]],
                  default: str, first: Callable[[dict], bool] | None = None) -> tuple[list[dict], int, str]:
    """Sort and page rows that were already authorized in Python (records whose access rules are not SQL yet).

    Empty values always sort last; ``id`` breaks ties so pages are deterministic. ``first`` floats the rows it
    accepts to the top (keeping the sort within each part), e.g. "Show favorites first".
    """
    key, desc = params.sort_key(list(sortable), default)
    getter = sortable[key]

    def order(row: dict) -> tuple:
        v = getter(row)
        missing = v is None or v == ""
        if isinstance(v, str):
            v = v.lower()
        return (missing, v if not missing else 0)

    present = [r for r in rows if not order(r)[0]]
    missing = [r for r in rows if order(r)[0]]
    present.sort(key=lambda r: (order(r)[1], r.get("id", 0)), reverse=desc)
    missing.sort(key=lambda r: r.get("id", 0))
    ordered = present + missing
    if first is not None:
        ordered = [r for r in ordered if first(r)] + [r for r in ordered if not first(r)]
    return ordered[params.offset: params.offset + params.page_size], len(ordered), ("-" if desc else "") + key


def matches(q: str | None, *values: Any) -> bool:
    if not q:
        return True
    needle = q.lower()
    return any(needle in str(v).lower() for v in values if v not in (None, ""))
