"""Platform Settings & Administration: invitations that the person activates with their own password, licensed
seats per role, giving a group's members a role, a personal language, and the year-end closeout summary."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core import permissions as perms
from app.core.enums import Role
from app.platform.history.models import AuditLog
from app.platform.users.models import User, UserInvitation
from tests.conftest import csrf_headers, login, make_user


def _u(db, prefix, job, role=Role.Auditor):
    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    r = perms.JOB_ROLES_BY_CODE[job]
    user.job_role, user.role, user.review_level = r.code, r.tier, r.review_level
    db.commit()
    return user


def _mail():
    return f"inv.{uuid.uuid4().hex[:8]}@gpha.example"


def test_invitation_is_activated_once_by_the_invited_person(client, client2, db):
    adm = _u(db, "invadm", "admin", Role.Admin)
    aud = _u(db, "invaud", "auditor")
    ah = csrf_headers(login(client, adm.username))
    email = _mail()

    # Only account administrators invite.
    sh = csrf_headers(login(client2, aud.username))
    denied = client2.post("/api/users/invite", json={"email": email, "job_role": "auditor"}, headers=sh)
    assert denied.status_code == 403

    g = client.post("/api/groups", json={"name": f"Inv readers {uuid.uuid4().hex[:4]}"}, headers=ah).json()
    r = client.post("/api/users/invite", json={"email": email, "job_role": "auditor", "group_ids": [g["id"]]},
                    headers=ah)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["emailed"] is False and "#activate/" in body["link"]  # no SMTP in tests: the link is shown once
    assert body["user"]["is_active"] is False and body["user"]["job_role"] == "auditor"
    token = body["link"].rsplit("/", 1)[1]
    inv = db.execute(select(UserInvitation).where(UserInvitation.user_id == body["user"]["id"])).scalar_one()
    assert token not in inv.token_hash and len(inv.token_hash) == 64  # only the hash is stored
    assert client.get(f"/api/groups/{g['id']}").json()["members"] == 1
    # The same e-mail cannot be invited twice; an administrator role needs a Super Administrator.
    assert client.post("/api/users/invite", json={"email": email, "job_role": "auditor"}, headers=ah).status_code == 409
    assert client.post("/api/users/invite", json={"email": _mail(), "job_role": "admin"}, headers=ah).status_code == 403
    pending = client.get("/api/users/invitations").json()
    assert any(p["email"] == email and p["state"] == "open" for p in pending)

    # The invited person sees their username, then chooses a password; the link then stops working.
    client2.post("/api/auth/logout", headers=sh)
    anon = client2
    d = anon.post("/api/auth/invitation", json={"token": token})
    assert d.status_code == 200 and d.json()["email"] == email
    assert anon.post("/api/auth/activate", json={"token": token, "full_name": "New Auditor",
                                                  "password": "12345678"}).status_code == 422
    ok = anon.post("/api/auth/activate", json={"token": token, "full_name": "New Auditor", "password": "Harbour#2026"})
    assert ok.status_code == 200, ok.text
    assert anon.post("/api/auth/activate", json={"token": token, "full_name": "X",
                                                  "password": "Harbour#2026"}).status_code == 404
    db.rollback()  # end the read snapshot taken before the activation
    user = db.get(User, body["user"]["id"])
    assert user.is_active and user.full_name == "New Auditor"
    assert anon.post("/api/auth/login", json={"username": user.username, "password": "Harbour#2026"}).status_code == 200
    actions = [a.action_performed for a in db.execute(select(AuditLog).where(
        AuditLog.action_performed.like(f"%username={user.username}%"))).scalars()]
    assert any(a.startswith("USER_INVITE ") for a in actions)
    assert any(a.startswith("ACCOUNT_ACTIVATED") for a in actions)


def test_resend_replaces_the_link_and_withdraw_kills_it(client, db):
    adm = _u(db, "invadm2", "admin", Role.Admin)
    ah = csrf_headers(login(client, adm.username))
    first = client.post("/api/users/invite", json={"email": _mail(), "job_role": "read_only"}, headers=ah).json()
    inv_id = next(i["id"] for i in client.get("/api/users/invitations").json() if i["user_id"] == first["user"]["id"])
    again = client.post(f"/api/users/invitations/{inv_id}/resend", headers=ah)
    assert again.status_code == 200
    old_token = first["link"].rsplit("/", 1)[1]
    new_token = again.json()["link"].rsplit("/", 1)[1]
    assert client.post("/api/auth/invitation", json={"token": old_token}, headers=ah).status_code == 404
    assert client.post("/api/auth/invitation", json={"token": new_token}, headers=ah).status_code == 200
    new_id = next(i["id"] for i in client.get("/api/users/invitations").json() if i["user_id"] == first["user"]["id"])
    assert client.delete(f"/api/users/invitations/{new_id}", headers=ah).status_code == 200
    assert client.post("/api/auth/invitation", json={"token": new_token}, headers=ah).status_code == 404


def test_licensed_seats_cap_new_and_moved_accounts(client, db):
    adm = _u(db, "licadm", "admin", Role.Admin)
    ah = csrf_headers(login(client, adm.username))
    used = next(r for r in client.get("/api/users/licenses").json()["roles"] if r["code"] == "read_only")
    limit = used["active"] + used["invited"] + 1
    assert client.put("/api/config", json={"values": {"license_seats": ["Auditor=x"]}}, headers=ah).status_code == 422
    r = client.put("/api/config", json={"values": {"license_seats": [f"Read-only User={limit}"]}}, headers=ah)
    assert r.status_code == 200, r.text
    try:
        row = next(r for r in client.get("/api/users/licenses").json()["roles"] if r["code"] == "read_only")
        assert row["seats"] == limit and row["available"] == 1
        assert client.post("/api/users/invite", json={"email": _mail(), "job_role": "read_only"},
                           headers=ah).status_code == 201
        full = client.post("/api/users/invite", json={"email": _mail(), "job_role": "read_only"}, headers=ah)
        assert full.status_code == 409 and "seat" in full.json()["detail"]
        mover = _u(db, "licmove", "auditor")
        assert client.patch(f"/api/users/{mover.id}", json={"job_role": "read_only"}, headers=ah).status_code == 409
    finally:
        client.post("/api/config/license_seats/reset", headers=ah)


def test_group_role_changes_each_member_but_never_the_caller(client, db):
    adm = _u(db, "grpadm", "admin", Role.Admin)
    a1, a2 = _u(db, "grpm1", "read_only"), _u(db, "grpm2", "read_only")
    ah = csrf_headers(login(client, adm.username))
    g = client.post("/api/groups", json={"name": f"Field team {uuid.uuid4().hex[:4]}"}, headers=ah).json()
    client.put(f"/api/groups/{g['id']}/members", json={"user_ids": [a1.id, a2.id, adm.id]}, headers=ah)
    assert client.post(f"/api/groups/{g['id']}/role", json={"job_role": "super_admin"}, headers=ah).status_code == 403
    r = client.post(f"/api/groups/{g['id']}/role", json={"job_role": "auditor"}, headers=ah)
    assert r.status_code == 200, r.text
    assert sorted(r.json()["changed"]) == sorted([a1.username, a2.username]) and adm.username in r.json()["unchanged"]
    db.expire_all()
    assert perms.job_role_of(db.get(User, a1.id)) == "auditor" and perms.job_role_of(db.get(User, adm.id)) == "admin"


def test_personal_language_and_closeout_summary(client, db):
    adm = _u(db, "clsadm", "admin", Role.Admin)
    ah = csrf_headers(login(client, adm.username))
    assert client.patch("/api/auth/me", json={"locale": "Klingon"}, headers=ah).status_code == 422
    me = client.patch("/api/auth/me", json={"locale": "English"}, headers=ah)
    assert me.status_code == 200 and me.json()["user"]["locale"] == "English"
    c = client.get("/api/admin/closeout")
    assert c.status_code == 200, c.text
    d = c.json()
    assert d["fiscal_year_end"].startswith(str(d["fiscal_year"] + (1 if d["fiscal_year_start_month"] > 1 else 0)))
    for k in ("audits", "issues", "actions", "people"):
        assert k in d
    staff = _u(db, "clsaud", "auditor")
    sh = csrf_headers(login(client, staff.username))
    assert sh and client.get("/api/admin/closeout").status_code == 403
