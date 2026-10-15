"""Workspace: role defaults, favourites, recently opened apps and the administrator's defaults."""

from __future__ import annotations

import uuid

from app.core.enums import Role
from tests.conftest import csrf_headers, login, make_user


def test_workspace_favorites_recent_and_role_defaults(client, client2, db):
    tag = uuid.uuid4().hex[:6]
    auditor = make_user(db, f"wsaud_{tag}", Role.Auditor)
    h = csrf_headers(login(client, auditor.username))
    me = client.get("/api/workspace/me").json()
    assert me["favorites"] and me["recent"] == []  # role defaults on first use
    assert client.put("/api/workspace/me/favorites", json={"favorites": ["audits", "Bad View!"]},
                      headers=h).status_code == 422
    r = client.put("/api/workspace/me/favorites", json={"favorites": ["issues", "audits", "issues"]}, headers=h)
    assert r.json()["favorites"] == ["issues", "audits"]
    for v in ("audits", "plans", "audits"):
        client.post("/api/workspace/me/recent", json={"view": v}, headers=h)
    assert client.get("/api/workspace/me").json()["recent"][:2] == ["audits", "plans"]

    # Only the Super Administrator sets the defaults; a new person of that role starts from them.
    assert client.put("/api/workspace/defaults", json={"defaults": {"Auditor": ["plans"]}},
                      headers=h).status_code == 403
    sa = make_user(db, f"wssa_{tag}", Role.Admin)
    sa.job_role = "super_admin"
    db.commit()
    sh = csrf_headers(login(client2, sa.username))
    saved = client2.put("/api/workspace/defaults", json={"defaults": {"Auditor": ["plans", "audits"]}}, headers=sh)
    assert saved.status_code == 200, saved.text
    newbie = make_user(db, f"wsnew_{tag}", Role.Auditor)
    login(client2, newbie.username)
    assert client2.get("/api/workspace/me").json()["favorites"] == ["plans", "audits"]
    reset = client.post("/api/workspace/me/reset", headers=h).json()
    assert reset["favorites"] == ["plans", "audits"]
    client2.put("/api/workspace/defaults", json={"defaults": {"Auditor": []}},
                headers=csrf_headers(login(client2, sa.username)))
