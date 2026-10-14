"""Optional Active Directory / LDAP authentication.

Enabled by setting ``GPHA_LDAP_URL``. The user's password is checked by binding to
the directory; it is never stored. Name and e-mail are read when a base DN is set.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from app.core.config import settings

logger = logging.getLogger("gpha.directory")


@dataclass
class DirectoryUser:
    username: str
    full_name: str = ""
    email: str = ""


def enabled() -> bool:
    return bool(settings.ldap_url)


def _escape(value: str) -> str:
    """RFC 4515 filter escaping."""
    out = []
    for ch in value:
        if ch in "\\*()\x00":
            out.append(f"\\{ord(ch):02x}")
        else:
            out.append(ch)
    return "".join(out)


def _default_connection(bind_user: str, password: str):  # noqa: ANN202
    from ldap3 import Connection, Server

    server = Server(settings.ldap_url, connect_timeout=settings.ldap_timeout_seconds, get_info=None)
    return Connection(server, user=bind_user, password=password, receive_timeout=settings.ldap_timeout_seconds)


# Tests replace this with a factory returning an ldap3 MOCK_SYNC connection.
connection_factory: Callable = _default_connection


def authenticate(username: str, password: str) -> DirectoryUser | None:
    """Return the directory user when ``password`` is correct, else None (never raises)."""
    if not enabled() or not username or not password:
        return None
    if any(c in username for c in "\\*()\x00,=+<>;\"") or len(username) > 100:
        return None
    bind_user = settings.ldap_bind_template.format(username=username)
    try:
        conn = connection_factory(bind_user, password)
        if not conn.bind():
            return None
        found = DirectoryUser(username=username)
        if settings.ldap_base_dn:
            conn.search(settings.ldap_base_dn, settings.ldap_user_filter.format(username=_escape(username)),
                        attributes=["displayName", "cn", "mail", "userPrincipalName"])
            if conn.entries:
                e = conn.entries[0]
                attrs = e.entry_attributes_as_dict

                def pick(k: str, attrs: dict = attrs) -> str:
                    return (attrs.get(k) or [""])[0] or ""

                found.full_name = str(pick("displayName") or pick("cn"))
                found.email = str(pick("mail") or pick("userPrincipalName"))
        conn.unbind()
        return found
    except Exception:  # noqa: BLE001 - directory down: treat as failed sign-in, log for the admin
        logger.exception("Directory sign-in failed for %s", username)
        return None
