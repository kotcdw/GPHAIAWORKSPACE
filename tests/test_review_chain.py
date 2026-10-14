"""GPHA review chain: Unit Head -> Audit Manager -> PIA -> GM Audit on reports and working papers."""

from __future__ import annotations

import io
import uuid

from fastapi.testclient import TestClient

from app.core.enums import ReviewLevel, Role
from app.main import app
from tests.conftest import DEFAULT_PASSWORD, csrf_headers, login, make_user

CHAIN_KEYS = ("report_review_chain", "workpaper_review_chain", "review_higher_level_may_cover")


def _u(db, prefix, role=Role.Auditor, level=None):
    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    if level:
        user.job_role, user.review_level = "manager", level
        db.commit()
    return user


def _sign(user, path):
    with TestClient(app) as c:
        h = csrf_headers(login(c, user.username))
        return c.post(path, json={"password": DEFAULT_PASSWORD}, headers=h)


def test_report_and_working_paper_pass_each_level_in_order(client, client2, db):
    root = _u(db, "rcroot", Role.Admin)
    prep = _u(db, "rcprep")
    uh = _u(db, "rcuh", level=ReviewLevel.UnitHead)
    am = _u(db, "rcam", level=ReviewLevel.Manager)
    pia = _u(db, "rcpia", level=ReviewLevel.PIA)
    gm = _u(db, "rcgm", level=ReviewLevel.CAE)
    rh = csrf_headers(login(client2, root.username))
    bad = client2.put("/api/config", json={"values": {"report_review_chain": ["Unit Head", "Deputy"]}}, headers=rh)
    assert bad.status_code == 422
    set_cfg = client2.put("/api/config", json={"values": {
        "report_review_chain": ["PIA", "Unit Head", "Audit Manager"],  # stored in GPHA order
        "workpaper_review_chain": ["Unit Head", "Audit Manager"], "review_higher_level_may_cover": False}},
        headers=rh)
    assert set_cfg.status_code == 200, set_cfg.text
    try:
        stored = {r["key"]: r["value"] for r in set_cfg.json()}
        assert stored["report_review_chain"] == ["Unit Head", "Audit Manager", "PIA"]

        ph = csrf_headers(login(client, prep.username))
        audit = client.post("/api/audits", json={"title": "Revenue - tolls", "scope": "Q2"}, headers=ph).json()
        rid = client.post(f"/api/audits/{audit['id']}/report", headers=ph).json()["id"]
        client.patch(f"/api/reports/{rid}", json={"overall_rating": "Satisfactory", "executive_summary": "Fine.",
                                                  "overall_opinion": "Effective.", "distribution_list": "DG"},
                     headers=ph)
        sub = client.post(f"/api/reports/{rid}/submit-for-review", headers=ph)
        assert sub.status_code == 200, sub.text
        assert sub.json()["review_stage_label"] == "Unit Head"
        assert sub.json()["review_chain"] == ["Unit Head", "Audit Manager", "PIA"]

        # Out of order: the Audit Manager cannot sign the Unit Head stage (no cover allowed).
        early = _sign(am, f"/api/reports/{rid}/manager-review")
        assert early.status_code == 403 and "Unit Head" in early.json()["detail"]
        s1 = _sign(uh, f"/api/reports/{rid}/manager-review")
        assert s1.status_code == 200 and s1.json()["status"] == "Manager Review"
        assert s1.json()["review_stage_label"] == "Audit Manager"
        assert _sign(uh, f"/api/reports/{rid}/manager-review").status_code == 403  # one stage per person
        assert _sign(am, f"/api/reports/{rid}/manager-review").json()["review_stage_label"] == "PIA"
        s3 = _sign(pia, f"/api/reports/{rid}/manager-review")
        assert s3.status_code == 200 and s3.json()["status"] == "CAE Approval"
        issued = _sign(gm, f"/api/reports/{rid}/cae-approve")
        assert issued.status_code == 200 and issued.json()["status"] == "Issued"
        roles = [s["role"] for s in issued.json()["signoffs"]]
        assert roles == ["Prepared by", "Reviewed by (Unit Head)", "Reviewed by (Audit Manager)",
                         "Reviewed by (PIA)", "Approved by (GM Audit)"]
        assert all(s["name"] for s in issued.json()["signoffs"])

        # Working paper: Unit Head then Audit Manager; with cover on, the PIA may sign for an absent manager.
        client2.put("/api/config", json={"values": {"review_higher_level_may_cover": True}}, headers=rh)
        audit2 = client.post("/api/audits", json={"title": "Payroll", "scope": "x"}, headers=ph).json()
        up = client.post(f"/api/audits/{audit2['id']}/working-papers", data={"title": "Payroll test"},
                         files={"file": ("wp.txt", io.BytesIO(b"tested 25 items"), "text/plain")}, headers=ph)
        assert up.status_code == 201, up.text
        wp = up.json()
        assert client.post(f"/api/working-papers/{wp['id']}/review", headers=ph).status_code == 403  # preparer
        w1 = _sign(uh, f"/api/working-papers/{wp['id']}/review")
        assert w1.status_code == 200 and w1.json()["review_stage"] == "Audit Manager" and not w1.json()["reviewed_at"]
        w2 = _sign(pia, f"/api/working-papers/{wp['id']}/review")
        assert w2.status_code == 200 and w2.json()["reviewed_at"]
        assert w2.json()["review_trail"][1]["acting_as"] == "PIA"
        papers = client.get(f"/api/audits/{audit2['id']}/working-papers").json()
        assert len(papers[0]["review_trail"]) == 2 and papers[0]["reviewed_at"]
    finally:
        for key in CHAIN_KEYS:
            client2.post(f"/api/config/{key}/reset", headers=rh)


def test_managers_get_one_of_four_approval_levels(client, db):
    root = _u(db, "rlroot", Role.Admin)
    target = _u(db, "rltarget")
    h = csrf_headers(login(client, root.username))
    for level in ("Unit Head", "Manager", "PIA", "CAE"):
        res = client.patch(f"/api/users/{target.id}/job-role", json={"job_role": "manager", "approval_level": level},
                           headers=h)
        assert res.status_code == 200 and res.json()["review_level"] == level
    assert client.patch(f"/api/users/{target.id}/job-role", json={"job_role": "auditor", "approval_level": "PIA"},
                        headers=h).status_code == 422
    from app.core import permissions as perms

    db.rollback()
    db.refresh(target)
    assert perms.is_cae(target) and perms.has_perm(target, "report.approve")
    client.patch(f"/api/users/{target.id}/job-role", json={"job_role": "manager", "approval_level": "PIA"}, headers=h)
    db.rollback()
    db.refresh(target)
    assert not perms.has_perm(target, "report.approve") and perms.has_perm(target, "report.review")
