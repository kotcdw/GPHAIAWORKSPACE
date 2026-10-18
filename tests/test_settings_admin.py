"""Administration phase 4: application settings. Regional settings (time zone, date and time format, fiscal year,
working days, language), the append-only settings history, and the settings summary on the Administration page."""

from __future__ import annotations

import uuid
from datetime import date, datetime

import pytest
from sqlalchemy import select, text

from app.core.enums import Role
from tests.conftest import csrf_headers, login, make_user


def _u(db, prefix, role=Role.Auditor, job=None):
    from app.core import permissions as perms

    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    if job:
        r = perms.JOB_ROLES_BY_CODE[job]
        user.job_role, user.role, user.review_level = r.code, r.tier, r.review_level
    db.commit()
    return user


@pytest.fixture
def admin(client2, db):
    root = _u(db, "st_root", Role.Admin, job="super_admin")
    h = csrf_headers(login(client2, root.username))
    yield client2, h, root
    for key in ("date_format", "time_format", "fiscal_year_start_month", "working_days", "time_zone"):
        client2.post(f"/api/config/{key}/reset", headers=h)


def test_regional_defaults_reach_every_user(client, db, admin):
    aud = _u(db, "st_aud", job="auditor")
    login(client, aud.username)
    me = client.get("/api/auth/me").json()
    assert me["regional"]["time_zone"] == "Africa/Accra" and me["regional"]["date_format"] == "DD/MM/YYYY"
    assert me["regional"]["fiscal_year_start_month"] == 1 and me["regional"]["language"] == "English"
    assert client.get("/api/config/regional").json()["working_days"] == ["Monday", "Tuesday", "Wednesday", "Thursday",
                                                                         "Friday"]
    # Only the listed choices are accepted.
    c2, h, _ = admin
    bad = c2.put("/api/config", json={"values": {"time_zone": "Mars/Olympus", "date_format": "YY.M.D",
                                                  "fiscal_year_start_month": 13, "working_days": ["Funday"]}},
                 headers=h)
    assert bad.status_code == 422
    assert {e["field"] for e in bad.json()["errors"]} >= {"time_zone", "date_format", "fiscal_year_start_month",
                                                          "working_days"}


def test_changes_are_kept_with_reason_and_reset(admin, db):
    from app.core.appconfig import AppConfigHistory

    c2, h, root = admin
    r = c2.put("/api/config", json={"values": {"date_format": "DD MMM YYYY"}, "reason": "Board asked for long dates"},
               headers=h)
    assert r.status_code == 200, r.text
    row = next(x for x in r.json() if x["key"] == "date_format")
    assert row["value"] == "DD MMM YYYY" and row["updated_by"] == root.full_name and row["updated_at"]
    assert c2.post("/api/config/date_format/reset", params={"reason": "Back to standard"}, headers=h).status_code == 200
    hist = c2.get("/api/config/history?key=date_format").json()
    assert hist[0]["action"] == "reset" and hist[0]["old"] == "DD MMM YYYY" and hist[0]["new"] == "DD/MM/YYYY"
    assert hist[0]["reason"] == "Back to standard"
    assert hist[1]["action"] == "update" and hist[1]["old"] == "DD/MM/YYYY" and hist[1]["reason"].startswith("Board")
    assert hist[1]["by"] == root.full_name
    # Saving the same value again records nothing.
    c2.put("/api/config", json={"values": {"date_format": "DD/MM/YYYY"}}, headers=h)
    assert len(c2.get("/api/config/history?key=date_format").json()) == 2
    # The history cannot be rewritten.
    rid = db.execute(select(AppConfigHistory.id).where(AppConfigHistory.key == "date_format")).scalars().first()
    with pytest.raises(Exception):  # noqa: B017 - the database trigger refuses
        db.execute(text("UPDATE app_config_history SET reason='x' WHERE id=:i"), {"i": rid})
    db.rollback()
    with pytest.raises(Exception):  # noqa: B017
        db.execute(text("DELETE FROM app_config_history WHERE id=:i"), {"i": rid})
    db.rollback()


def test_history_follows_the_settings_each_role_manages(client, db, admin):
    c2, h, _ = admin
    c2.put("/api/config", json={"values": {"time_format": "12-hour"}}, headers=h)
    aud = _u(db, "st_aud2", job="auditor")
    login(client, aud.username)
    assert client.get("/api/config/history").status_code == 403
    mgr = _u(db, "st_mgr", job="manager")
    login(client, mgr.username)
    assert client.get("/api/config/history").status_code == 403
    # An Administrator sees the history of exactly the settings it may change.
    adm = _u(db, "st_adm", Role.Admin, job="admin")
    login(client, adm.username)
    mine = {r["key"] for r in client.get("/api/config").json()}
    rows = client.get("/api/config/history?limit=500").json()
    assert rows and {r["key"] for r in rows} <= mine and "time_format" in mine


def test_working_days_and_fiscal_year_follow_the_settings(admin):
    from app.core import appconfig
    from app.core.regional import fiscal_year_bounds, fiscal_year_of, fmt_date, fmt_datetime
    from app.core.workdays import add_working_days, working_days_between

    c2, h, _ = admin
    friday = datetime(2026, 10, 16, 9, 0)
    assert add_working_days(friday, 1).date() == date(2026, 10, 19)  # Monday
    c2.put("/api/config", json={"values": {"working_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                                                            "Saturday"], "fiscal_year_start_month": 7,
                                           "date_format": "YYYY-MM-DD", "time_format": "12-hour"}}, headers=h)
    appconfig.invalidate()
    assert add_working_days(friday, 1).date() == date(2026, 10, 17)  # Saturday now counts
    assert working_days_between(friday, datetime(2026, 10, 19, 9, 0)) == 2
    assert fiscal_year_of(date(2026, 3, 1)) == 2025 and fiscal_year_of(date(2026, 7, 1)) == 2026
    assert fiscal_year_bounds(2026) == (date(2026, 7, 1), date(2027, 6, 30))
    assert fmt_date(datetime(2026, 10, 18, 23, 30)) == "2026-10-18"
    assert fmt_datetime(datetime(2026, 10, 18, 14, 5)) == "2026-10-18 2:05 PM"
    # Lagos is an hour ahead of UTC: a late evening time moves to the next day.
    c2.put("/api/config", json={"values": {"time_zone": "Africa/Lagos"}}, headers=h)
    appconfig.invalidate()
    assert fmt_date(datetime(2026, 10, 18, 23, 30)) == "2026-10-19"


def test_admin_summary_and_app_customization_history(admin):
    c2, h, _ = admin
    c2.put("/api/config", json={"values": {"time_format": "12-hour"}, "reason": "Staff preference"}, headers=h)
    s = c2.get("/api/admin/overview").json()["settings"]
    assert s["changed_from_default"] >= 1 and s["total"] >= 90 and s["regional"]["time_zone"] == "Africa/Accra"
    assert s["last_change"]["label"] == "Time format"
    cat = c2.get("/api/apps").json()
    brand = {**cat["branding"], "sub": f"WORKSPACE {uuid.uuid4().hex[:3]}"}
    apps = {a["key"]: {"enabled": a["enabled"], "label": a["label"]} for a in cat["apps"]}
    r = c2.put("/api/apps", json={"apps": apps, "branding": brand}, headers=h)
    assert r.status_code == 200, r.text
    hist = c2.get("/api/config/history?key=app_customization").json()
    assert hist and hist[0]["label"] == "Apps and branding"
