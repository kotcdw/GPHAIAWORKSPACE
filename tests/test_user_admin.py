"""User accounts page: edit details, reset password and delete (Settings > User accounts)."""

from __future__ import annotations

import uuid

from app.core import permissions as perms
from app.core.enums import Role
from tests.conftest import csrf_headers, login, make_user

NEW_PASSWORD = "Harbour-Gate-2026"


def _u(db, prefix, role=Role.Auditor, job=None):
    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    if job:
        r = perms.JOB_ROLES_BY_CODE[job]
        user.job_role, user.role, user.review_level = r.code, r.tier, r.review_level
        db.commit()
    return user


def test_edit_user_details(client, db):
    root = _u(db, "uaroot", Role.Admin)
    target = _u(db, "uaedit")
    h = csrf_headers(login(client, root.username))
    r = client.patch(f"/api/users/{target.id}", json={"full_name": "  Ama Mensah  ", "email": "ama@giaw-qa.com",
                                                     "company": "Tema Port"}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["full_name"], body["email"], body["company"]) == ("Ama Mensah", "ama@giaw-qa.com", "Tema Port")
    assert client.patch(f"/api/users/{target.id}", json={"full_name": "   "}, headers=h).status_code == 422
    assert client.patch(f"/api/users/{target.id}", json={"email": "not-an-email"}, headers=h).status_code == 422


def test_reset_password_ends_sessions_and_unlocks(client, client2, db):
    root = _u(db, "uarst", Role.Admin)
    target = _u(db, "uarstu")
    target.failed_login_count, target.locked_until = 3, None
    db.commit()
    h = csrf_headers(login(client, root.username))
    th = csrf_headers(login(client2, target.username))
    assert client2.get("/api/auth/me", headers=th).status_code == 200

    weak = client.patch(f"/api/users/{target.id}", json={"password": f"{target.username}99"}, headers=h)
    assert weak.status_code == 422 and "username" in weak.text

    r = client.patch(f"/api/users/{target.id}", json={"password": NEW_PASSWORD}, headers=h)
    assert r.status_code == 200, r.text
    assert client2.get("/api/auth/me").status_code == 401  # old session revoked
    login(client2, target.username, NEW_PASSWORD)
    db.refresh(target)
    assert target.failed_login_count == 0


def test_delete_rules(client, db):
    root = _u(db, "uadel", Role.Admin)
    h = csrf_headers(login(client, root.username))
    pending = make_user(db, f"uapend_{uuid.uuid4().hex[:6]}", Role.Auditee, active=False)
    assert client.delete(f"/api/users/{pending.id}", headers=h).status_code == 200
    assert client.get(f"/api/users/{pending.id}", headers=h).status_code == 404
    assert client.delete(f"/api/users/{root.id}", headers=h).status_code == 400  # not yourself


def test_only_super_admin_edits_resets_or_deletes_administrators(client, client2, db):
    root = _u(db, "uasup", Role.Admin)
    admin = _u(db, "uaadm", Role.Admin, job="admin")
    other_admin = _u(db, "uaadm2", Role.Admin, job="admin")
    auditor = _u(db, "uaaud")
    ah = csrf_headers(login(client2, admin.username))

    for target in (root, other_admin):
        assert client2.patch(f"/api/users/{target.id}", json={"full_name": "X Y"}, headers=ah).status_code == 403
        assert client2.patch(f"/api/users/{target.id}", json={"password": NEW_PASSWORD}, headers=ah).status_code == 403
        assert client2.delete(f"/api/users/{target.id}", headers=ah).status_code == 403
    # An Administrator still manages ordinary accounts and their own details.
    assert client2.patch(f"/api/users/{auditor.id}", json={"password": NEW_PASSWORD}, headers=ah).status_code == 200
    assert client2.patch(f"/api/users/{admin.id}", json={"full_name": "Admin Two"}, headers=ah).status_code == 200

    rh = csrf_headers(login(client, root.username))
    assert client.patch(f"/api/users/{other_admin.id}", json={"full_name": "Kofi Admin"}, headers=rh).status_code == 200
    assert client.delete(f"/api/users/{other_admin.id}", headers=rh).status_code == 200
