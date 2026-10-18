"""Reusable, accuracy-focused field types for request schemas.

* ``Title`` - required single-line text: surrounding whitespace removed, must
  not be blank, max 255 characters, no line breaks.
* ``OptEmail`` - optional e-mail address: blank becomes ``None``, otherwise it
  must look like ``name@domain.tld`` (internal domains such as ``gpha.local``
  are accepted) and is stored lower-case.
* ``Code`` - short reference code: upper-cased, letters/digits/``-``/``_``.
* ``Text`` - free text with surrounding whitespace removed (max 20,000 chars).
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, StringConstraints

_EMAIL = re.compile(r"^[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")


def _single_line(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError("must be a single line")
    return value


def _blank_to_none(value):  # noqa: ANN001, ANN202
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _email(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip().lower()
    if len(value) > 255 or not _EMAIL.match(value):
        raise ValueError("must be a valid e-mail address, e.g. name@gpha.gov.gh")
    return value


Title = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255), AfterValidator(_single_line)
]
OptEmail = Annotated[str | None, BeforeValidator(_blank_to_none), AfterValidator(_email)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=20000)]


def not_in_past(value: datetime | None) -> datetime | None:
    """Reject due dates before today (UTC); today itself is allowed."""
    if value is None:
        return None
    day = value.date() if isinstance(value, datetime) else value
    if day < datetime.now(UTC).date():
        raise ValueError("must be today or a future date")
    return value


FutureDate = Annotated[datetime | None, AfterValidator(not_in_past)]

__all__ = ["FutureDate", "OptEmail", "Text", "Title", "date", "not_in_past"]


_COMMON_PASSWORDS = {
    "password", "password1", "password12", "password123", "passw0rd", "p@ssw0rd", "p@ssword",
    "12345678", "123456789", "1234567890", "87654321", "11111111", "00000000", "12341234",
    "qwerty", "qwerty12", "qwerty123", "qwertyuiop", "asdfghjk", "abc12345", "abcd1234",
    "admin123", "admin1234", "administrator", "letmein", "letmein1", "welcome", "welcome1",
    "iloveyou", "changeme", "default1", "gpha1234", "ghana123", "football", "sunshine",
}


def password_problems(password: str, username: str | None = None) -> str | None:
    """Return why ``password`` is too weak, or None. Matches the sign-up hints."""
    try:
        from app.core.appconfig import cfg

        shortest = max(8, int(cfg("password_min_length")))
    except Exception:  # noqa: BLE001 - settings unavailable (e.g. before the database exists)
        shortest = 8
    if len(password) < shortest:
        return f"must be at least {shortest} characters"
    if password.isdigit():
        return "must not be entirely numeric"
    if password.lower() in _COMMON_PASSWORDS:
        return "is too common; choose a less predictable password"
    if username and len(username) >= 3 and username.lower() in password.lower():
        return "must not contain your username"
    return None
