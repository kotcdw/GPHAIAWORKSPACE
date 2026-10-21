"""PROJECTBLUEPRINT administration: user groups are managed by account administrators, logged, deactivated
rather than erased, and never grant permissions."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core import permissions as perms
from app.core.enums import Role
from app.platform.history.models import AuditLog
from tests.conftest import csrf_headers, login, make_user


def _u(db, prefix, job, role=Role.Auditor):
    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    r = perms.JOB_ROLES_BY_CODE[job]
    user.job_role, user.role, user.review_level = r.code, r.tier, r.review_level
    db.commit()
    return user


def test_groups_admin_only_membership_and_soft_delete(client, client2, db):
    adm = _u(db, "gradm", "admin", Role.Admin)
    aud = _u(db, "graud", "auditor")
    client_user = _u(db, "grcli", "audit_client", Role.Auditee)
    ah = csrf_headers(login(client, adm.username))
    name = f"Audit committee readers {uuid.uuid4().hex[:4]}"

    g = client.post("/api/groups", json={"name": name, "description": "Readers"}, headers=ah)
    assert g.status_code == 201, g.text
    g = g.json()
    assert client.post("/api/groups", json={"name": name.upper()}, headers=ah).status_code == 409
    m = client.put(f"/api/groups/{g['id']}/members", json={"user_ids": [aud.id, client_user.id]}, headers=ah)
    assert m.status_code == 200 and m.json()["members"] == 2
    assert client.put(f"/api/groups/{g['id']}/members", json={"user_ids": [999_999_999]},
                      headers=ah).status_code == 422

    # Staff can list groups (to share with them) but cannot change them; auditees cannot list them.
    h = csrf_headers(login(client2, aud.username))
    assert name in {x["name"] for x in client2.get("/api/groups").json()}
    assert client2.post("/api/groups", json={"name": "Mine"}, headers=h).status_code == 403
    assert client2.get(f"/api/groups/{g['id']}").status_code == 403
    before = perms.permissions_of(aud)
    from app.platform.groups.router import groups_of

    assert g["id"] in groups_of(db, aud.id)
    assert perms.permissions_of(aud) == before  # membership grants nothing
    ch = csrf_headers(login(client2, client_user.username))
    assert client2.get("/api/groups", headers=ch).status_code == 403

    # Deactivated, not erased.
    gone = client.delete(f"/api/groups/{g['id']}", headers=ah)
    assert gone.status_code == 200 and gone.json()["is_active"] is False
    assert name not in {x["name"] for x in client.get("/api/groups").json()}
    assert name in {x["name"] for x in client.get("/api/groups?include_inactive=true").json()}
    db.rollback()  # end the test session's snapshot so the request's writes are visible
    logged = list(db.execute(select(AuditLog.action_performed)
                             .where(AuditLog.action_performed.like(f"GROUP_% id={g['id']}%"))).scalars())
    assert {x.split()[0] for x in logged} >= {"GROUP_CREATE", "GROUP_MEMBERS", "GROUP_DEACTIVATE"}
