"""Frameworks & standard controls library, and the scheduler with double-booking warnings."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from app.core import permissions as perms
from app.core.enums import Role
from app.platform.notifications.models import Notification
from tests.conftest import csrf_headers, login, make_user


def _weekdays(a: date, b: date) -> int:
    return sum(1 for i in range((b - a).days + 1) if (a + timedelta(days=i)).weekday() < 5)


def _u(db, prefix, job=None, role=Role.Auditor):
    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    if job:
        r = perms.JOB_ROLES_BY_CODE[job]
        user.job_role, user.role, user.review_level = r.code, r.tier, r.review_level
        db.commit()
    return user


def test_framework_library_import_and_apply_to_matrix(client, client2, db):
    admin = _u(db, "fwaa", "audit_admin")
    aud = _u(db, "fwaud", "auditor")
    h = csrf_headers(login(client, admin.username))
    code = f"COSO{uuid.uuid4().hex[:4]}".upper()
    fw = client.post("/api/library/frameworks", json={"code": code, "name": "COSO Internal Control 2013",
                                                      "framework_type": "Control framework (e.g. COSO)",
                                                      "issuer": "COSO", "version": "2013"}, headers=h)
    assert fw.status_code == 201, fw.text
    fid = fw.json()["id"]
    assert client.post("/api/library/frameworks", json={"code": code.lower(), "name": "Dup"}, headers=h).status_code \
        == 409
    ctl = client.post("/api/library/controls", json={
        "framework_id": fid, "ref": "CA-10", "title": "Segregation of duties in payments",
        "process_area": "Treasury", "risk_statement": "Fraudulent payments", "control_type": "Preventive",
        "frequency": "Daily", "test_procedure": "Inspect the payment system role matrix for conflicting roles."},
        headers=h)
    assert ctl.status_code == 201, ctl.text
    csv_body = ("ref,title,process_area,control_type,nature,frequency,is_key,test_procedure\n"
                "CA-10,Segregation of duties in payments (updated),Treasury,Preventive,Automated,Daily,yes,Re-test\n"
                "IC-02,Bank reconciliations reviewed monthly,Treasury,Detective,Manual,Monthly,yes,Inspect sign-off\n"
                "XX-1,Bad row,Treasury,Sideways,Manual,Monthly,yes,\n")
    imp = client.post(f"/api/library/frameworks/{fid}/import", files={"file": ("c.csv", csv_body, "text/csv")},
                      headers=h)
    assert imp.status_code == 200, imp.text
    assert imp.json()["created"] == 1 and imp.json()["updated"] == 1 and "Sideways" in imp.json()["errors"][0]
    lib = client.get(f"/api/library/controls?framework_id={fid}").json()
    assert {c["ref"] for c in lib["items"]} == {"CA-10", "IC-02"} and "Treasury" in lib["process_areas"]
    found = client.get("/api/library/controls?q=reconciliations").json()["items"]
    assert any(c["ref"] == "IC-02" for c in found)

    # An auditor cannot change the library but can use it.
    ah = csrf_headers(login(client2, aud.username))
    assert client2.post("/api/library/frameworks", json={"code": "X1", "name": "Nope"}, headers=ah).status_code == 403
    audit = client2.post("/api/audits", json={"title": "Treasury"}, headers=ah).json()
    obj = client2.post(f"/api/audits/{audit['id']}/objectives", json={"title": "Payments are valid"}, headers=ah).json()
    risk = client2.post(f"/api/objectives/{obj['id']}/risks", json={"title": "Fraud", "likelihood": 3, "impact": 4},
                        headers=ah).json()
    ids = [c["id"] for c in lib["items"]]
    applied = client2.post(f"/api/objectives/{obj['id']}/controls/from-library",
                           json={"library_control_ids": ids, "risk_ids": [risk["id"]]}, headers=ah)
    assert applied.status_code == 201, applied.text
    rcm = client2.get(f"/api/audits/{audit['id']}/rcm").json()
    controls = [c for o in rcm["objectives"] for c in o["controls"]] if "objectives" in rcm else rcm
    assert len(controls) == 2 and all(c["library_control_id"] in ids for c in controls)
    assert all(risk["id"] in c["risk_ids"] for c in controls) and all(len(c["tests"]) == 1 for c in controls)
    used = client.get(f"/api/library/controls?framework_id={fid}").json()["items"]
    assert all(c["used_in"] == 1 for c in used)
    # Retired controls disappear from the picker but stay linked.
    upd = client.put(f"/api/library/controls/{ids[0]}", json={**{k: used[0][k] for k in (
        "framework_id", "ref", "title", "description", "process_area", "risk_statement", "control_type", "nature",
        "frequency", "is_key", "test_procedure", "criterion_id")}, "active": False}, headers=h)
    assert upd.status_code == 200
    assert len(client.get(f"/api/library/controls?framework_id={fid}").json()["items"]) == 1


def test_scheduler_dates_bookings_and_double_booking(client, client2, db):
    mgr = _u(db, "scmgr", "audit_manager")
    lead = _u(db, "sclead", "senior_auditor")
    h = csrf_headers(login(client, mgr.username))
    for fy in range(2024, 2037):
        created = client.post("/api/assurance-plans", json={"fiscal_year": fy, "title": "Sched plan"}, headers=h)
        if created.status_code == 201:
            break
    plan = created.json()
    fy = plan["fiscal_year"]
    url = f"/api/assurance-plans/{plan['id']}/engagements"
    e1 = client.post(url, json={"title": "Fuel management", "planned_quarter": "Q2", "budget_hours": 120,
                                "lead_auditor_id": lead.id}, headers=h).json()
    e2 = client.post(url, json={"title": "Stores", "planned_quarter": "Q2", "budget_hours": 80}, headers=h).json()

    q2 = {"start": f"{fy}-04-01", "end": f"{fy}-06-30"}
    t = client.get("/api/schedule", params=q2).json()
    assert {e["id"] for e in t["unscheduled"]} >= {e1["id"], e2["id"]} and t["working_days"] > 50

    outside = client.put(f"/api/schedule/engagements/{e1['id']}/dates",
                         json={"planned_start": f"{fy}-07-01", "planned_end": f"{fy}-07-20"}, headers=h)
    assert outside.status_code == 422 and "plan change request" in outside.json()["detail"]
    ok = client.put(f"/api/schedule/engagements/{e1['id']}/dates",
                    json={"planned_start": f"{fy}-05-04", "planned_end": f"{fy}-05-29"}, headers=h)
    assert ok.status_code == 200 and ok.json()["conflicts"] == []
    t = client.get("/api/schedule", params=q2).json()
    me = next(p for p in t["people"] if p["user_id"] == lead.id)
    assert me["bookings"][0]["role"] == "Lead auditor"
    assert me["engagement_days"] == _weekdays(date(fy, 5, 4), date(fy, 5, 29))

    client.put(f"/api/schedule/engagements/{e2['id']}/dates",
               json={"planned_start": f"{fy}-05-18", "planned_end": f"{fy}-06-05", "book_lead": False}, headers=h)
    double = client.post("/api/schedule/bookings", json={
        "user_id": lead.id, "kind": "Engagement", "plan_engagement_id": e2["id"], "role": "Team member",
        "start_date": f"{fy}-05-18", "end_date": f"{fy}-06-05"}, headers=h)
    assert double.status_code == 201 and len(double.json()["conflicts"]) == 1
    c = double.json()["conflicts"][0]
    assert c["from"] == f"{fy}-05-18" and c["to"] == f"{fy}-05-29"
    assert c["days"] == _weekdays(date(fy, 5, 18), date(fy, 5, 29))
    db.rollback()
    titles = [n.title for n in db.query(Notification).filter(Notification.user_id == mgr.id).all()]
    assert any(x.startswith("Double-booked") for x in titles)

    leave = client.post("/api/schedule/bookings", json={
        "user_id": lead.id, "kind": "Leave", "title": "Annual leave",
        "start_date": f"{fy}-06-22", "end_date": f"{fy}-06-26"}, headers=h)
    assert leave.status_code == 201 and leave.json()["conflicts"] == []
    bad = client.post("/api/schedule/bookings", json={
        "user_id": lead.id, "kind": "Leave", "start_date": f"{fy}-06-26", "end_date": f"{fy}-06-22"}, headers=h)
    assert bad.status_code == 422
    t = client.get("/api/schedule", params=q2).json()
    assert len([x for x in t["conflicts"] if x["user_id"] == lead.id]) == 1
    assert client.delete(f"/api/schedule/bookings/{double.json()['booking']['id']}", headers=h).status_code == 200
    assert client.get(f"/api/schedule/people/{lead.id}/conflicts").json() == []

    # Moving the engagement moves the lead's booking with it.
    client.put(f"/api/schedule/engagements/{e1['id']}/dates",
               json={"planned_start": f"{fy}-06-01", "planned_end": f"{fy}-06-12"}, headers=h)
    me = next(p for p in client.get("/api/schedule", params=q2).json()["people"] if p["user_id"] == lead.id)
    assert any(b["start_date"] == f"{fy}-06-01" and b["end_date"] == f"{fy}-06-12" for b in me["bookings"])

    # Auditors can view the scheduler but not change it.
    aud = _u(db, "scaud", "auditor")
    ah = csrf_headers(login(client2, aud.username))
    assert client2.get("/api/schedule", params=q2).status_code == 200
    assert client2.post("/api/schedule/bookings", json={"user_id": aud.id, "kind": "Leave", "start_date":
                                                        str(date(fy, 6, 1)), "end_date": str(date(fy, 6, 2))},
                        headers=ah).status_code == 403
