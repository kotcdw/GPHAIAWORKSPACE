"""Working-day arithmetic for statutory deadlines: only the configured working days count, and admin-configured
public holidays are skipped."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from app.core.appconfig import cfg


def holidays() -> set[date]:
    out = set()
    for item in cfg("public_holidays") or []:
        try:
            out.add(date.fromisoformat(str(item).strip()[:10]))
        except ValueError:
            continue
    return out


def is_working_day(day: date, hols: set[date] | None = None, weekdays: set[int] | None = None) -> bool:
    from app.core.regional import working_weekdays

    days = weekdays if weekdays is not None else working_weekdays()
    return day.weekday() in days and day not in (hols if hols is not None else holidays())


def add_working_days(start: datetime, days: int) -> datetime:
    """The end of the ``days``-th working day after ``start`` (the start day itself is not counted)."""
    from app.core.regional import working_weekdays

    hols, week = holidays(), working_weekdays()
    current = start.date()
    added = 0
    while added < days:
        current += timedelta(days=1)
        if is_working_day(current, hols, week):
            added += 1
    return datetime.combine(current, datetime.max.time()).replace(microsecond=0)


def working_days_between(start: datetime, end: datetime) -> int:
    """Working days from ``start`` (exclusive) to ``end`` (inclusive); negative when end is before start."""
    if end < start:
        return -working_days_between(end, start)
    from app.core.regional import working_weekdays

    hols, week = holidays(), working_weekdays()
    current, count = start.date(), 0
    while current < end.date():
        current += timedelta(days=1)
        if is_working_day(current, hols, week):
            count += 1
    return count
