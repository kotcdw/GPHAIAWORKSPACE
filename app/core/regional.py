"""Regional settings in one place: time zone, date and time format, fiscal year and working days.

Every value is an administrator setting (Configuration > Regional); nothing here is hard-coded for a country.
Datetimes are stored as naive UTC throughout the application and converted only for display.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.appconfig import WEEKDAYS, cfg
from app.core.enums import utcnow

_PATTERNS = {"DD/MM/YYYY": "%d/%m/%Y", "DD MMM YYYY": "%d %b %Y", "DD-MM-YYYY": "%d-%m-%Y",
             "YYYY-MM-DD": "%Y-%m-%d", "MM/DD/YYYY": "%m/%d/%Y"}


def zone() -> ZoneInfo:
    try:
        return ZoneInfo(cfg("time_zone"))
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def local(dt: datetime) -> datetime:
    """A stored (naive UTC) datetime in the configured time zone."""
    aware = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt
    return aware.astimezone(zone())


def today() -> date:
    return local(utcnow()).date()


def fmt_date(value: datetime | date | None) -> str:
    """A date in the configured format; datetimes are converted to the configured time zone first."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        value = local(value).date()
    return value.strftime(_PATTERNS.get(cfg("date_format"), "%d/%m/%Y"))


def fmt_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    lt = local(value)
    clock = lt.strftime("%I:%M %p").lstrip("0") if cfg("time_format") == "12-hour" else lt.strftime("%H:%M")
    return f"{fmt_date(value)} {clock}"


def fiscal_year_of(day: date) -> int:
    """Fiscal years are named after the calendar year in which they start."""
    start = int(cfg("fiscal_year_start_month") or 1)
    return day.year if day.month >= start else day.year - 1


def current_fiscal_year() -> int:
    return fiscal_year_of(today())


def fiscal_year_bounds(fy: int) -> tuple[date, date]:
    from datetime import timedelta

    start = int(cfg("fiscal_year_start_month") or 1)
    first = date(fy, start, 1)
    last = date(fy + 1, start, 1) - timedelta(days=1)
    return first, last


def working_weekdays() -> set[int]:
    """Weekday numbers (Monday = 0) that count as working days; Monday to Friday when nothing is set."""
    days = {WEEKDAYS.index(d) for d in (cfg("working_days") or []) if d in WEEKDAYS}
    return days or {0, 1, 2, 3, 4}
