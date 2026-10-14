"""GIAS completion: committee plan approval + plan changes, criteria library, review notes and closure gate,
working-paper cross-references and sign-off, exit meeting, Audit Committee escalation, internal assessment report."""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import timedelta

from app.core.enums import ReviewLevel, Role, utcnow
from app.modules.capa.models import Capa
from app.modules.followup.service import due_level, run_escalations
from app.modules.notifications.models import Notification
from tests.conftest import DEFAULT_PASSWORD, csrf_headers, login, make_user, walk_plan_to_review

_YEARS = iter(range(2030, 2023, -1))


def _u(db, prefix, role, level=None):
    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    if level:
        user.review_level = level
        db.commit()
    return user


def _docx_text(content: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        return zf.read("word/document.xml").decode()


def test_committee_approval_and_documented_plan_changes(client, client2, db):
    auditor = _u(db, "gpaud", Role.Auditor)
    admin = _u(db, "gpadm", Role.Admin)
    h = csrf_headers(login(client, auditor.username))
    ah = csrf_headers(login(client2, admin.username))
    for fy in _YEARS:  # first fiscal year no other test has used
        created = client.post("/api/assurance-plans", json={"fiscal_year": fy, "title": "Plan",
                                                            "total_budget_hours": 900}, headers=h)
        if created.status_code == 201:
            break
    plan = created.json()
    eng = client.post(f"/api/assurance-plans/{plan['id']}/engagements", json={"title": "Payroll", "budget_hours": 120},
                      headers=h).json()
    early = client2.post(f"/api/assurance-plans/{plan['id']}/committee-approval",
                         json={"meeting_date": utcnow().isoformat(), "reference": "AC/2026/04"}, headers=ah)
    assert early.status_code == 409
    walk_plan_to_review(client2, plan["id"], ah)
    assert client2.post(f"/api/assurance-plans/{plan['id']}/approve", json={"password": DEFAULT_PASSWORD},
                        headers=ah).status_code == 200

    assert client.post(f"/api/assurance-plans/{plan['id']}/committee-approval",
                       json={"meeting_date": utcnow().isoformat(), "reference": "AC/1"}, headers=h).status_code == 403
    future = (utcnow() + timedelta(days=3)).isoformat()
    assert client2.post(f"/api/assurance-plans/{plan['id']}/committee-approval",
                        json={"meeting_date": future, "reference": "AC/1"}, headers=ah).status_code == 422
    ok = client2.post(f"/api/assurance-plans/{plan['id']}/committee-approval",
                      json={"meeting_date": utcnow().isoformat(), "reference": "AC/2026/04",
                            "notes": "Approved with comments on IT coverage"}, headers=ah)
    assert ok.status_code == 200, ok.text
    detail = client.get(f"/api/assurance-plans/{plan['id']}").json()
    assert detail["committee_reference"] == "AC/2026/04"

    # Changes to the approved plan go through change requests (reason, impact, review, approval, new version).
    assert client2.post(f"/api/assurance-plans/{plan['id']}/amendments",
                        json={"title": "Fraud investigation", "reason": "Requested by the Board"},
                        headers=ah).status_code == 409
    reviewer = _u(db, "gprev", Role.Auditor, ReviewLevel.Manager)
    rh = csrf_headers(login(client, reviewer.username))

    def change(items, reason):
        cr = client2.post(f"/api/assurance-plans/{plan['id']}/change-requests",
                          json={"title": "Amendment", "reason": reason, "items": items}, headers=ah)
        assert cr.status_code == 201, cr.text
        cr = cr.json()
        assert client.post(f"/api/plan-change-requests/{cr['id']}/review", json={"decision": "Endorse"},
                           headers=rh).status_code == 200
        return cr

    cr1 = change([{"action": "add", "title": "Fraud investigation", "planned_quarter": "Q3", "budget_hours": 80},
                  {"action": "change", "engagement_id": eng["id"], "planned_quarter": "Q4", "budget_hours": 100}],
                 "Requested by the Board after whistleblower report")
    assert cr1["impact"]["resource"]["hours_delta"] == 60
    # The requester cannot approve; the GM Audit (another Admin here) e-signs.
    assert client2.post(f"/api/plan-change-requests/{cr1['id']}/approve", json={"password": DEFAULT_PASSWORD},
                        headers=ah).status_code == 403
    admin2 = _u(db, "gpadm2", Role.Admin)
    a2 = csrf_headers(login(client, admin2.username))
    cae = client.post(f"/api/plan-change-requests/{cr1['id']}/approve", json={"password": DEFAULT_PASSWORD},
                      headers=a2).json()
    assert cae["status"] == "Awaiting Committee"  # significant change: the Audit Committee approves (GIAS 9.4)
    done = client.post(f"/api/plan-change-requests/{cr1['id']}/committee-decision",
                       json={"decision": "Approved", "meeting_date": utcnow().isoformat(), "reference": "AC/2026/05"},
                       headers=a2).json()
    assert done["status"] == "Approved" and done["new_version"] == 2
    added_id = next(e["id"] for e in client.get(f"/api/assurance-plans/{plan['id']}").json()["engagements"]
                    if e["title"] == "Fraud investigation")
    rh = csrf_headers(login(client, reviewer.username))
    cr2 = change([{"action": "cancel", "engagement_id": added_id}], "Investigation handed to the police unit")
    a2 = csrf_headers(login(client, admin2.username))
    client.post(f"/api/plan-change-requests/{cr2['id']}/approve", json={"password": DEFAULT_PASSWORD}, headers=a2)
    assert client.post(f"/api/plan-change-requests/{cr2['id']}/committee-decision",
                       json={"decision": "Approved", "meeting_date": utcnow().isoformat(), "reference": "AC/2026/06"},
                       headers=a2).json()["new_version"] == 3

    log = client.get(f"/api/assurance-plans/{plan['id']}/changes").json()
    assert [c["change_type"] for c in log][-1] == "Committee"
    assert sorted(c["change_type"] for c in log[:-1]) == ["Added", "Cancelled", "Changed"]
    summary = client.get(f"/api/committee/summary?fiscal_year={fy}").json()
    assert summary["plan"]["committee_reference"] == "AC/2026/04" and len(summary["plan_changes"]) == 3
    pack = client.get(f"/api/committee/pack.docx?fiscal_year={fy}")
    text = _docx_text(pack.content)
    assert "Changes to the approved plan" in text and "AC/2026/04" in text


def test_criteria_library_and_finding_link(client, db):
    auditor = _u(db, "crau", Role.Auditor)
    h = csrf_headers(login(client, auditor.username))
    assert client.post("/api/criteria", json={"title": "x", "body": "y", "source_type": "Rumour"},
                       headers=h).status_code == 422
    c = client.post("/api/criteria", json={"title": "Procurement thresholds", "source_type": "Law / Regulation",
                                           "reference": "Act 663 s.21",
                                           "body": "Goods above GHS 50,000 require competitive tendering."},
                    headers=h).json()
    assert c["crit_ref"].startswith("CR-") and c["status"] == "Active"
    found = client.get("/api/criteria?q=tendering").json()
    assert any(x["id"] == c["id"] for x in found["items"])
    aid = client.post("/api/audits", json={"title": "Procurement", "scope": "x"}, headers=h).json()["id"]
    f = client.post(f"/api/audits/{aid}/findings", json={"title": "Split orders", "criterion_id": c["id"],
                                                         "criteria": c["body"]}, headers=h).json()
    assert f["criterion_id"] == c["id"]
    assert client.get(f"/api/criteria/{c['id']}").json()["used_in"] == 1
    retired = client.patch(f"/api/criteria/{c['id']}", json={"status": "Retired"}, headers=h).json()
    assert retired["status"] == "Retired"


def test_review_notes_workpaper_xref_and_closure_gate(client, client2, db):
    preparer = _u(db, "rnprep", Role.Auditor)
    manager = _u(db, "rnmgr", Role.Auditor, ReviewLevel.Manager)
    admin = _u(db, "rnadm", Role.Admin)
    h = csrf_headers(login(client, preparer.username))
    mh = csrf_headers(login(client2, manager.username))
    aid = client.post("/api/audits", json={"title": "Stores", "scope": "x"}, headers=h).json()["id"]
    fid = client.post(f"/api/audits/{aid}/findings", json={"title": "Bin cards"}, headers=h).json()["id"]
    wp = client.post(f"/api/audits/{aid}/working-papers", data={"title": "Stock count"},
                     files={"file": ("count.txt", io.BytesIO(b"counted 40 items"), "text/plain")}, headers=h).json()

    # Cross-reference and sign-off.
    x = client.patch(f"/api/working-papers/{wp['id']}/xref", json={"wp_ref": "C.1", "finding_id": fid}, headers=h)
    assert x.status_code == 200 and x.json()["wp_ref"] == "C.1"
    assert client.patch(f"/api/working-papers/{wp['id']}/xref", json={"finding_id": 999999},
                        headers=h).status_code == 422
    assert client.post(f"/api/working-papers/{wp['id']}/review", headers=h).status_code == 403
    assert client2.post(f"/api/working-papers/{wp['id']}/review", headers=mh).status_code == 200
    papers = client.get(f"/api/audits/{aid}/working-papers").json()
    assert papers[0]["wp_ref"] == "C.1" and papers[0]["reviewed_by"] == manager.id

    # Review notes: preparer cannot raise; manager raises; preparer answers; manager clears.
    assert client.post(f"/api/audits/{aid}/review-notes", json={"note": "Self check"}, headers=h).status_code == 403
    n = client2.post(f"/api/audits/{aid}/review-notes",
                     json={"target_type": "working_paper", "target_id": wp["id"],
                           "note": "Count sheet is not signed by the storekeeper"}, headers=mh).json()
    assert n["target_label"].startswith("Working paper C.1") and n["status"] == "Open"
    db.rollback()
    assert any("Review note" in x.title for x in db.query(Notification).filter_by(user_id=preparer.id))
    assert client2.post(f"/api/review-notes/{n['id']}/clear", headers=mh).status_code == 409

    client.patch(f"/api/audits/{aid}", json={"status": "In Progress"}, headers=h)
    client.patch(f"/api/audits/{aid}", json={"status": "Review"}, headers=h)
    check = {c["key"]: c for c in client.get(f"/api/audits/{aid}/closure-check").json()["checks"]}
    assert check["review_notes"]["ok"] is False and check["review_notes"]["required"]
    ah = csrf_headers(login(client2, admin.username))
    blocked = client2.post(f"/api/audits/{aid}/close", json={"password": DEFAULT_PASSWORD}, headers=ah)
    assert blocked.status_code == 409 and "review notes" in blocked.json()["detail"]

    mh = csrf_headers(login(client2, manager.username))
    answered = client.post(f"/api/review-notes/{n['id']}/respond",
                           json={"response": "Signed copy uploaded as v2"}, headers=h).json()
    assert answered["status"] == "Responded"
    assert client.post(f"/api/review-notes/{n['id']}/clear", headers=h).status_code == 403
    assert client2.post(f"/api/review-notes/{n['id']}/clear", headers=mh).json()["status"] == "Cleared"
    assert client.get(f"/api/audits/{aid}/closure-check").json()["ready"] is True


def test_exit_meeting_on_report(client, client2, db):
    auditor = _u(db, "exaud", Role.Auditor)
    h = csrf_headers(login(client, auditor.username))
    aid = client.post("/api/audits", json={"title": "Fleet", "scope": "x"}, headers=h).json()["id"]
    rep = client.post(f"/api/audits/{aid}/report", headers=h).json()
    assert client.put(f"/api/reports/{rep['id']}/exit-meeting", json={
        "meeting_date": (utcnow() + timedelta(days=2)).isoformat(), "attendees": "GM Fleet"},
        headers=h).status_code == 422
    ok = client.put(f"/api/reports/{rep['id']}/exit-meeting", json={
        "meeting_date": utcnow().isoformat(), "attendees": "GM Fleet; Fleet Manager; Audit team",
        "notes": "Management agreed with both findings."}, headers=h)
    assert ok.status_code == 200
    r = client.get(f"/api/reports/{rep['id']}").json()
    assert r["exit_meeting_attendees"].startswith("GM Fleet")
    assert "Exit meeting" in _docx_text(client.get(f"/api/reports/{rep['id']}/export.docx").content)


def test_escalation_to_audit_committee_and_internal_assessment_report(client, db):
    admin = _u(db, "ecadm", Role.Admin)
    h = csrf_headers(login(client, admin.username))
    assert due_level(61) == 4 and due_level(31) == 3 and due_level(15) == 2 and due_level(2) == 1
    c = client.post("/api/capa", json={"title": "Old action", "severity": "High"}, headers=h).json()
    db.rollback()
    row = db.get(Capa, c["id"])
    row.due_date = utcnow() - timedelta(days=70)
    db.commit()
    run_escalations(db)
    db.rollback()
    assert db.get(Capa, c["id"]).escalation_level == 4
    assert any(n.title.startswith("For the Audit Committee") for n in
               db.query(Notification).filter_by(user_id=admin.id))
    overdue = client.get("/api/followup/overdue").json()
    assert any(o["id"] == c["id"] and o["escalation_name"] == "Audit Committee" for o in overdue)

    rep = client.get(f"/api/qaip/report.docx?fiscal_year={utcnow().year}")
    assert rep.status_code == 200
    text = _docx_text(rep.content)
    assert "Internal Quality Assessment Report" in text and "Performance against targets" in text
