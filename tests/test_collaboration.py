"""Collaboration on records: the record's place in the data flow, comments, @mentions in My work, and scope."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.enums import Role
from app.platform.notifications.models import Notification
from tests.conftest import csrf_headers, login, make_user


def _u(db, prefix: str, role: Role):
    return make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)


def test_lineage_runs_from_audit_to_issue_to_action(client, db):
    auditor = _u(db, "lnaud", Role.Auditor)
    h = csrf_headers(login(client, auditor.username))
    aid = client.post("/api/audits", json={"title": "Stores audit", "scope": "Stores"}, headers=h).json()["id"]
    fid = client.post(f"/api/audits/{aid}/findings", json={"title": "Stock not counted", "risk_rating": "High"},
                      headers=h).json()["id"]
    raised = client.post(f"/api/findings/{fid}/raise-action", headers=h)
    a = client.get(f"/api/records/audit/{aid}/collab").json()
    assert {"type": "finding", "id": fid} in [{"type": n["type"], "id": n["id"]} for n in a["feeds_into"]]
    f = client.get(f"/api/records/finding/{fid}/collab").json()
    assert f["came_from"][0]["type"] == "audit" and f["came_from"][0]["id"] == aid
    if raised.status_code in (200, 201):
        cid = next(n["id"] for n in f["feeds_into"] if n["type"] == "capa")
        c = client.get(f"/api/records/capa/{cid}/collab").json()
        assert [n["type"] for n in c["came_from"]][:2] == ["finding", "audit"]
    assert client.get("/api/records/unknown/1/collab").status_code == 404


def test_comments_mentions_my_work_and_scope(client, client2, db):
    lead = _u(db, "cmlead", Role.Auditor)
    mate = _u(db, "cmmate", Role.Auditor)
    outsider = _u(db, "cmout", Role.Auditee)
    h = csrf_headers(login(client, lead.username))
    aid = client.post("/api/audits", json={"title": "Fuel audit", "scope": "Fuel"}, headers=h).json()["id"]
    d = client.get(f"/api/records/audit/{aid}/collab").json()
    ids = {p["id"] for p in d["mentionable"]}
    assert mate.id in ids and outsider.id not in ids  # the auditee cannot open this audit

    assert client.post(f"/api/records/audit/{aid}/comments", json={"body": "hi", "mention_ids": [outsider.id]},
                       headers=h).status_code == 422
    r = client.post(f"/api/records/audit/{aid}/comments",
                    json={"body": f"@{mate.username} please check the fuel reconciliation", "mention_ids": [mate.id]},
                    headers=h)
    assert r.status_code == 201, r.text
    db.rollback()
    assert db.execute(select(Notification).where(Notification.user_id == mate.id,
                                                 Notification.link_type == "audit")).scalars().first()

    mh = csrf_headers(login(client2, mate.username))
    work = client2.get("/api/my-work").json()["items"]
    mention = next(i for i in work if i["kind"] == "mention")
    assert mention["link"] == {"type": "audit", "id": aid, "comments": True}
    # Replying on the record handles the mention.
    client2.post(f"/api/records/audit/{aid}/comments", json={"body": "Done, reconciled"}, headers=mh)
    assert not [i for i in client2.get("/api/my-work").json()["items"] if i["kind"] == "mention"]

    # Only the author withdraws; the text disappears but the entry stays.
    cid = client.get(f"/api/records/audit/{aid}/collab").json()["comments"][0]["id"]
    assert client2.post(f"/api/comments/{cid}/withdraw", headers=mh).status_code == 403
    out = client.post(f"/api/comments/{cid}/withdraw", headers=h).json()["comments"]
    assert out[0]["withdrawn"] and out[0]["body"] == ""

    eh = csrf_headers(login(client2, outsider.username))
    assert client2.get(f"/api/records/audit/{aid}/collab").status_code == 404
    assert client2.post(f"/api/records/audit/{aid}/comments", json={"body": "x"}, headers=eh).status_code == 404


def test_home_pad_personal_and_organisation_default(client, client2, db):
    from app.core import permissions as perms
    from tests.conftest import csrf_headers as ch

    sa = _u(db, "padsa", Role.Admin)
    r = perms.JOB_ROLES_BY_CODE["super_admin"]
    sa.job_role, sa.role = r.code, r.tier
    db.commit()
    staff = _u(db, "padaud", Role.Auditor)
    sh = ch(login(client2, staff.username))
    first = client2.get("/api/home/pad").json()
    assert first["mine"] is None and first["can_set_default"] is False
    mine = client2.put("/api/home/pad", json={"tiles": ["audits", "issues", "audits", "Bad Key!", "policies"]},
                       headers=sh).json()
    assert mine["mine"] == ["audits", "issues", "policies"]  # duplicates and invalid keys dropped

    h = ch(login(client, sa.username))
    cat = client.get("/api/apps").json()
    apps = {a["key"]: {"enabled": a["enabled"], "label": ""} for a in cat["apps"]}
    try:
        assert client.put("/api/apps", json={"apps": apps, "branding": cat["branding"], "home": ["mywork", "audits"]},
                          headers=h).status_code == 200
        assert client2.get("/api/home/pad").json()["default"] == ["mywork", "audits"]
        # Saving apps without "home" keeps the default.
        client.put("/api/apps", json={"apps": apps, "branding": cat["branding"]}, headers=h)
        assert client.get("/api/apps").json()["home"] == ["mywork", "audits"]
        back = client2.put("/api/home/pad", json={"tiles": None}, headers=sh).json()
        assert back["mine"] is None and back["default"] == ["mywork", "audits"]
    finally:
        client.put("/api/apps", json={"apps": apps, "branding": cat["branding"], "home": []}, headers=h)
    assert client.get("/api/apps").json()["home"] is None
