"""Administration phase 2: user search and access history, server-side permission checks, the last-administrator
guard, the Read-only User role, the export permission, the access matrix and the idle sign-out."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core.enums import Role, utcnow
from app.platform.auth.models import Session as UserSession
from app.platform.history.models import AuditLog
from tests.conftest import csrf_headers, login, make_user


def _u(db, prefix, role=Role.Auditor, job=None, active=True):
    from app.core import permissions as perms

    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    if job:
        r = perms.JOB_ROLES_BY_CODE[job]
        user.job_role, user.role, user.review_level = r.code, r.tier, r.review_level
    user.is_active = active
    db.commit()
    return user


def test_user_search_filters_sorting_and_paging(client, db):
    admin = _u(db, "ua_adm", Role.Admin, job="admin")
    tag = uuid.uuid4().hex[:5]
    a = _u(db, f"ua_a{tag}")
    b = _u(db, f"ua_b{tag}", job="read_only")
    pending = _u(db, f"ua_p{tag}", Role.Auditee, job="audit_client", active=False)
    login(client, admin.username)
    r = client.get(f"/api/users/search?q={tag}").json()
    assert {x["id"] for x in r["items"]} == {a.id, b.id, pending.id} and r["total"] == 3
    assert {x["id"] for x in client.get(f"/api/users/search?q={tag}&status=pending").json()["items"]} == {pending.id}
    assert [x["id"] for x in client.get(f"/api/users/search?q={tag}&job_role=read_only").json()["items"]] == [b.id]
    paged = client.get(f"/api/users/search?q={tag}&page_size=5&page=1&sort=username").json()
    assert [x["username"] for x in paged["items"]] == sorted(x["username"] for x in paged["items"])
    assert "counts" in r and r["items"][0]["status"] in ("active", "pending", "locked", "deactivated")


def test_user_endpoints_need_the_manage_users_permission(client, db):
    from app.platform.roles.models import RolePermission

    auditor = _u(db, "ua_aud", job="auditor")
    login(client, auditor.username)
    assert client.get("/api/users/search").status_code == 403
    assert client.get("/api/users").status_code == 403
    assert client.get("/api/audit-logs/register").status_code == 403
    assert client.get("/api/admin/backups").status_code == 403
    # An Administrator whose "Manage user accounts" permission was removed loses user administration.
    admin = _u(db, "ua_adm2", Role.Admin, job="admin")
    db.add(RolePermission(job_role="admin", permission="system.users", granted=False))
    db.commit()
    from app.core import permissions as perms

    perms.invalidate()
    try:
        login(client, admin.username)
        assert client.get("/api/users/search").status_code == 403
    finally:
        db.query(RolePermission).filter_by(job_role="admin", permission="system.users").delete()
        db.commit()
        perms.invalidate()


def test_last_active_administrator_cannot_be_removed(client, db):
    from app.platform.roles import service

    root = _u(db, "ua_root", Role.Admin, job="super_admin")
    h = csrf_headers(login(client, root.username))
    others = service.active_admins(db, excluding=None)
    # Deactivate every other administrator for the test, keep a second admin to act on.
    sole = _u(db, "ua_sole", Role.Admin, job="admin")
    keep_active = [u for u in others if u.id not in (root.id, sole.id)]
    for u in keep_active:
        u.is_active = False
    db.commit()
    try:
        # root and sole are the only active administrators: removing sole is fine while root remains.
        r = client.patch(f"/api/users/{sole.id}/job-role", json={"job_role": "auditor"}, headers=h)
        assert r.status_code == 200, r.text
        # Now root is the last: it cannot be deactivated or demoted by anyone (here via the guard directly).
        import pytest
        from fastapi import HTTPException

        db.expire_all()
        with pytest.raises(HTTPException) as exc:
            service.guard_last_super_admin(db, root, deactivating=True)
        assert "last active administrator" in exc.value.detail
        with pytest.raises(HTTPException):
            service.guard_last_super_admin(db, root, new_code="manager")
    finally:
        for u in keep_active:
            u.is_active = True
        db.commit()


def test_read_only_user_can_read_but_never_change(client, db):
    viewer = _u(db, "ua_ro", job="read_only")
    h = csrf_headers(login(client, viewer.username))
    me = client.get("/api/auth/me").json()
    assert me["user"]["job_role"] == "read_only" and "data.export" not in me["permissions"]
    assert client.get("/api/audits").status_code == 200
    blocked = client.post("/api/audits", json={"title": "Not allowed", "scope": "x"}, headers=h)
    assert blocked.status_code == 403 and "read-only" in blocked.json()["detail"]
    assert client.post("/api/tasks", json={"title": "x"}, headers=h).status_code == 403
    # Own sign-in matters still work.
    assert client.patch("/api/auth/me", json={"full_name": "Viewer Person"}, headers=h).status_code == 200
    assert client.post("/api/export.log", json={"title": "x", "rows": 1}, headers=h).status_code == 403


def test_export_permission_is_enforced(client, db):
    aud = _u(db, "ua_exp", job="auditor")
    h = csrf_headers(login(client, aud.username))
    ok = client.post("/api/export.xlsx", json={"title": "T", "columns": ["a"], "rows": [["1"]]}, headers=h)
    assert ok.status_code == 200
    assert client.post("/api/export.log", json={"title": "T", "rows": 1}, headers=h).status_code == 204
    cli = _u(db, "ua_cli", Role.Auditee, job="audit_client")
    h2 = csrf_headers(login(client, cli.username))
    assert client.post("/api/export.xlsx", json={"title": "T", "columns": ["a"], "rows": [["1"]]},
                       headers=h2).status_code == 200  # auditees keep exporting their own lists
    viewer = _u(db, "ua_view", job="read_only")
    h2 = csrf_headers(login(client, viewer.username))
    assert client.post("/api/export.xlsx", json={"title": "T", "columns": ["a"], "rows": [["1"]]},
                       headers=h2).status_code == 403


def test_access_history_sessions_and_sign_out_everywhere(client, client2, db):
    admin = _u(db, "ua_hist", Role.Admin, job="super_admin")
    person = _u(db, "ua_person")
    login(client2, person.username)
    h = csrf_headers(login(client, admin.username))
    client.patch(f"/api/users/{person.id}", json={"full_name": "Person Renamed"}, headers=h)
    acc = client.get(f"/api/users/{person.id}/access").json()
    assert acc["last_sign_in"] and any(s["action"] == "LOGIN" for s in acc["sign_ins"])
    assert any(c["action"].startswith("USER_UPDATE") for c in acc["changes"])
    assert len(acc["sessions"]) >= 1
    r = client.post(f"/api/users/{person.id}/sessions/revoke", headers=h)
    assert r.status_code == 200
    assert client2.get("/api/auth/me").status_code == 401
    assert client.get(f"/api/users/{person.id}/access").json()["sessions"] == []


def test_access_matrix(client, db):
    admin = _u(db, "ua_mx", Role.Admin, job="admin")
    login(client, admin.username)
    m = client.get("/api/roles/matrix").json()
    codes = [r["code"] for r in m["roles"]]
    assert "read_only" in codes and "manager_cae" in codes
    eng = next(r for r in m["rows"] if r["module"].startswith("Audit engagements"))
    assert "read_only" in eng["cells"]["view"]["roles"] and "read_only" not in eng["cells"]["create"]["roles"]
    rep = next(r for r in m["rows"] if r["module"] == "Audit reports")
    assert "manager_cae" in rep["cells"]["approve"]["roles"]


def test_idle_sessions_are_signed_out(client, db):
    user = _u(db, "ua_idle")
    login(client, user.username)
    assert client.get("/api/auth/me").json()["idle_timeout_minutes"] == 10
    db.rollback()
    sess = db.execute(select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked.is_(False))
                      .order_by(UserSession.id.desc())).scalars().first()
    # Background refreshes do not count as activity.
    before = sess.last_activity_at
    client.get("/api/notifications?unread_only=true&limit=1", headers={"X-Background": "1"})
    db.refresh(sess)
    assert sess.last_activity_at == before
    sess.last_activity_at = utcnow() - timedelta(minutes=11)
    db.commit()
    r = client.get("/api/auth/me")
    assert r.status_code == 401 and "inactivity" in r.json()["detail"]
    db.refresh(sess)
    assert sess.revoked
    assert db.execute(select(AuditLog).where(AuditLog.user_id == user.id,
                                             AuditLog.action_performed.like("SESSION_IDLE_TIMEOUT%"))).first()
