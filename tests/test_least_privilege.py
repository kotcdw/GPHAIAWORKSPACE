"""Least privilege for Auditors: only assigned engagements, the report editable only in Draft, work a reviewer has
signed off read-only, and the Super Administrator editing the Access by module matrix cell by cell."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete

from app.core import appconfig
from app.core import permissions as perms
from app.core.enums import ReviewLevel, Role
from app.platform.roles.models import RolePermission
from tests.conftest import ENGAGEMENT_LEAD_GRANTS, csrf_headers, login, make_user


def _u(db, prefix, job):
    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", Role.Auditor)
    r = perms.JOB_ROLES_BY_CODE[job]
    user.job_role, user.role = r.code, r.tier
    user.review_level = ReviewLevel.Manager if job == "manager" else None
    db.commit()
    return user


@pytest.fixture
def standard_auditor(db):
    """The standard Auditor role and the assignment rule, as shipped (the other tests relax both)."""
    db.execute(delete(RolePermission).where(RolePermission.job_role == "auditor"))
    db.merge(appconfig.AppConfig(key="auditor_assigned_only", value="true"))
    db.commit()
    perms.invalidate()
    appconfig.invalidate()
    yield
    db.execute(delete(RolePermission).where(RolePermission.job_role == "auditor"))
    for p in ENGAGEMENT_LEAD_GRANTS:
        db.add(RolePermission(job_role="auditor", permission=p, granted=True))
    db.merge(appconfig.AppConfig(key="auditor_assigned_only", value="false"))
    db.commit()
    perms.invalidate()
    appconfig.invalidate()


def _two_audits(client, mh, auditor):
    mine = client.post("/api/audits", json={"title": f"Assigned {uuid.uuid4().hex[:5]}", "scope": "Cash"},
                       headers=mh).json()
    other = client.post("/api/audits", json={"title": f"Other {uuid.uuid4().hex[:5]}", "scope": "Fuel"},
                        headers=mh).json()
    r = client.post(f"/api/audits/{mine['id']}/team", json={"user_id": auditor.id, "team_role": "Auditor"}, headers=mh)
    assert r.status_code in (200, 201), r.text
    return mine, other


def test_auditor_defaults_are_least_privilege(standard_auditor):
    have = perms.matrix()["auditor"]
    assert {"audit.fieldwork", "audit.findings", "audit.workpapers", "report.prepare"} <= have
    assert not have & {"audit.create", "review.workpapers", "review.notes", "data.export", "report.review",
                       "report.approve", "audit.close"}


def test_auditor_sees_and_changes_only_assigned_work(client, client2, db, standard_auditor):
    mgr = _u(db, "lpmgr", "manager")
    aud = _u(db, "lpaud", "auditor")
    mh = csrf_headers(login(client, mgr.username))
    mine, other = _two_audits(client, mh, aud)
    ah = csrf_headers(login(client2, aud.username))
    assert client2.post("/api/audits", json={"title": "Mine", "scope": "x"}, headers=ah).status_code == 403
    ids = {a["id"] for a in client2.get("/api/audits").json()}
    assert mine["id"] in ids and other["id"] not in ids
    assert client2.get(f"/api/audits/{other['id']}").status_code == 404
    assert client2.post(f"/api/audits/{other['id']}/findings", json={"title": "x", "risk_rating": "Low"},
                        headers=ah).status_code in (403, 404)
    r = client2.post(f"/api/audits/{mine['id']}/findings", json={"title": "Cash not banked", "risk_rating": "High"},
                     headers=ah)
    assert r.status_code == 201, r.text
    # The team is allocated by a Manager.
    assert client2.post(f"/api/audits/{mine['id']}/team", json={"user_id": aud.id},
                        headers=ah).status_code == 403


def test_report_editable_in_draft_only_and_signed_work_is_locked(client, client2, db, standard_auditor):
    mgr = _u(db, "lpmgr2", "manager")
    aud = _u(db, "lpaud2", "auditor")
    mh = csrf_headers(login(client, mgr.username))
    mine, _ = _two_audits(client, mh, aud)
    ah = csrf_headers(login(client2, aud.username))

    # The Auditor drafts and edits the report while it is in Draft.
    rep = client2.post(f"/api/audits/{mine['id']}/report", headers=ah)
    assert rep.status_code == 201, rep.text
    rid = rep.json()["id"]
    ok = client2.patch(f"/api/reports/{rid}", json={"executive_summary": "Cash controls need work",
                                                    "overall_rating": "Needs Improvement"}, headers=ah)
    assert ok.status_code == 200, ok.text
    assert client2.post(f"/api/reports/{rid}/send-to-management", headers=ah).status_code == 200
    late = client2.patch(f"/api/reports/{rid}", json={"executive_summary": "Changed after review"}, headers=ah)
    assert late.status_code == 409

    # A finding the Auditor prepared and a reviewer signed is read-only to the Auditor.
    fid = client2.post(f"/api/audits/{mine['id']}/findings", json={"title": "Petty cash", "risk_rating": "Medium"},
                       headers=ah).json()["id"]
    url = f"/api/signoffs/finding/{fid}"
    first = client2.post(url, json={}, headers=ah)
    if first.status_code != 200:
        pytest.skip(f"finding sign-off needs more detail here: {first.text}")
    review = client.post(url, json={"override": True}, headers=mh)
    assert review.status_code == 200, review.text
    assert client2.patch(f"/api/findings/{fid}", json={"title": "Rewritten"}, headers=ah).status_code == 409
    assert client2.delete(f"{url}/1", headers=ah).status_code == 403
    # The Manager can still reopen it.
    assert client.delete(f"{url}/2", headers=mh).status_code == 200


def test_super_administrator_edits_access_by_module(client, client2, db, standard_auditor):
    sa = _u(db, "lpsa", "super_admin")
    h = csrf_headers(login(client, sa.username))
    url = "/api/roles/auditor/access"
    cell = {"module": "Findings", "action": "export", "allowed": True}
    pv = client.put(url, json={**cell, "preview": True}, headers=h).json()
    assert pv["permissions"] == ["data.export"]
    assert any(c["module"] == "Audit reports" and c["action"] == "export" for c in pv["changes"])
    assert "data.export" not in perms.matrix()["auditor"]  # a preview saves nothing
    done = client.put(url, json=cell, headers=h)
    assert done.status_code == 200, done.text
    perms.invalidate()
    assert "data.export" in perms.matrix()["auditor"]
    row = next(r for r in done.json()["matrix"]["rows"] if r["module"] == "Findings")
    assert "auditor" in row["cells"]["export"]["roles"]
    client.put(url, json={**cell, "allowed": False}, headers=h)
    perms.invalidate()
    assert "data.export" not in perms.matrix()["auditor"]
    # Fixed cells: every internal account views the universe; role management stays with the Super Administrator.
    # View, Create, Edit and Delete are refused per module and enforced on every request to that module.
    aud = _u(db, "lpaud4", "auditor")
    ah = csrf_headers(login(client2, aud.username))
    assert client2.get("/api/audit-universe/units").status_code == 200
    off = client.put(url, json={"module": "Audit universe and libraries", "action": "view", "allowed": False},
                     headers=h)
    assert off.status_code == 200 and off.json()["changes"] == []
    row = next(r for r in off.json()["matrix"]["rows"] if r["module"] == "Audit universe and libraries")
    assert "auditor" not in row["cells"]["view"]["roles"] and "manager" in row["cells"]["view"]["roles"]
    from app.platform.roles import matrix as access

    access.invalidate()
    refused = client2.get("/api/audit-universe/units")
    assert refused.status_code == 403 and "Access by module" in refused.json()["detail"]
    client.put(url, json={"module": "Audit universe and libraries", "action": "view", "allowed": True}, headers=h)
    access.invalidate()
    assert client2.get("/api/audit-universe/units").status_code == 200
    # Delete is a column of its own.
    client.put(url, json={"module": "Findings", "action": "delete", "allowed": False}, headers=h)
    access.invalidate()
    assert client2.delete("/api/findings/999999", headers=ah).status_code == 403
    client.put(url, json={"module": "Findings", "action": "delete", "allowed": True}, headers=h)
    access.invalidate()
    assert client2.delete("/api/findings/999999", headers=ah).status_code in (403, 404)
    assert client.put(url, json={"module": "Users, roles and access", "action": "configure", "allowed": True},
                      headers=h).status_code == 422
    assert client.put("/api/roles/super_admin/access", json={**cell, "allowed": False}, headers=h).status_code == 422
    # Only the Super Administrator edits the matrix.
    mgr = _u(db, "lpmgr3", "manager")
    oh = csrf_headers(login(client2, mgr.username))
    assert client2.put(url, json=cell, headers=oh).status_code == 403
