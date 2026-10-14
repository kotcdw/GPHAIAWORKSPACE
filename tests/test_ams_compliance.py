"""AMS compliance: MoF/IAA follow-up returns, Audit Committee register, report distribution, charter, EQA,
declarations, CPD, automation rules and custom fields on audits, findings and actions."""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from datetime import datetime, timedelta

from app.core.config import settings
from app.core.enums import ReportStatus, ReviewLevel, Role, ValidationResult, utcnow
from app.core.workdays import add_working_days
from app.domains.issues.capa.models import Capa
from app.platform.notifications.models import Notification
from tests.conftest import csrf_headers, login, make_user


def _u(db, prefix, role=Role.Auditor, job=None, email=None):
    from app.core import permissions as perms

    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role, email=email)
    if job:
        r = perms.JOB_ROLES_BY_CODE[job]
        user.job_role, user.role, user.review_level = r.code, r.tier, r.review_level
        db.commit()
    return user


def _set(client, h, **values):
    r = client.put("/api/config", json={"values": values}, headers=h)
    assert r.status_code == 200, r.text


def _reset(client, h, *keys):
    for k in keys:
        client.post(f"/api/config/{k}/reset", headers=h)


def _notes(db, user_id):
    db.rollback()
    return db.query(Notification).filter(Notification.user_id == user_id).all()


def test_working_days_skip_weekends_and_holidays(client, db):
    admin = _u(db, "wdadm", Role.Admin)
    h = csrf_headers(login(client, admin.username))
    friday = datetime(2026, 10, 9, 15, 0)  # a Friday
    assert add_working_days(friday, 10).date() == datetime(2026, 10, 23).date()
    _set(client, h, public_holidays=["2026-10-12"])
    try:
        assert add_working_days(friday, 10).date() == datetime(2026, 10, 26).date()
    finally:
        _reset(client, h, "public_holidays")


def test_draft_report_response_deadline_and_register(client, client2, db):
    prep = _u(db, "rdprep")
    auditee = _u(db, "rdaud", Role.Auditee)
    h = csrf_headers(login(client, prep.username))
    audit = client.post("/api/audits", json={"title": "Stores"}, headers=h).json()
    client.post(f"/api/audits/{audit['id']}/auditees", json={"user_id": auditee.id}, headers=h)
    rid = client.post(f"/api/audits/{audit['id']}/report", headers=h).json()["id"]
    client.patch(f"/api/reports/{rid}", json={"overall_rating": "Needs Improvement", "executive_summary": "Sum."},
                 headers=h)
    sent = client.post(f"/api/reports/{rid}/send-to-management", headers=h).json()
    assert sent["response_due_at"] and sent["response_received_at"] is None
    due = datetime.fromisoformat(sent["response_due_at"])
    assert due.weekday() < 5 and (due - datetime.fromisoformat(sent["draft_sent_at"])).days >= 12
    assert any("working days" in n.body for n in _notes(db, auditee.id))
    ah = csrf_headers(login(client2, auditee.username))
    client2.put(f"/api/reports/{rid}/management-comments", json={"management_comments": "Agreed."}, headers=ah)
    assert client.get(f"/api/reports/{rid}").json()["response_received_at"]
    reg = client.get("/api/reports/register").json()
    row = next(r for r in reg if r["id"] == rid)
    assert row["status"] == "Management Review" and row["response_received_at"]
    assert client.get("/api/reports/register.xlsx").status_code == 200


def test_report_distribution_register(client, db):
    from app.domains.audit.reports.models import AuditReport

    prep = _u(db, "distp")
    h = csrf_headers(login(client, prep.username))
    audit = client.post("/api/audits", json={"title": "Dist"}, headers=h).json()
    rid = client.post(f"/api/audits/{audit['id']}/report", headers=h).json()["id"]
    early = client.post(f"/api/reports/{rid}/distribution",
                        json={"recipient": "Audit Committee", "sent_at": utcnow().isoformat()}, headers=h)
    assert early.status_code == 409
    db.rollback()
    rep = db.get(AuditReport, rid)
    rep.status, rep.issued_at = ReportStatus.Issued, utcnow() - timedelta(days=10)
    db.commit()
    dist = client.get(f"/api/reports/{rid}/distribution").json()
    assert "Internal Audit Agency (Director-General)" in dist["missing"]
    ok = client.post(f"/api/reports/{rid}/distribution",
                     json={"recipient": "Internal Audit Agency (Director-General)", "channel": "Letter",
                           "sent_at": (utcnow() - timedelta(days=1)).isoformat(), "reference": "GPHA/IA/12"},
                     headers=h)
    assert ok.status_code == 201, ok.text
    assert "Internal Audit Agency (Director-General)" not in ok.json()["missing"]
    future = client.post(f"/api/reports/{rid}/distribution",
                         json={"recipient": "Auditor-General", "sent_at": (utcnow() + timedelta(days=2)).isoformat()},
                         headers=h)
    assert future.status_code == 422


def test_external_recommendation_progress_withdrawal_and_committee(client, client2, db):
    gm = _u(db, "acgm", job="gm_audit")
    owner = _u(db, "acown", Role.Auditee, email=f"own{uuid.uuid4().hex[:5]}@gpha.gov.gh")
    h = csrf_headers(login(client, gm.username))
    lists = client.get("/api/config/lists").json()
    ag = lists["recommendation_sources"][1]
    bad = client.post("/api/capa", json={"title": "Reconcile fixed asset register", "source_body": "Nobody"},
                      headers=h)
    assert bad.status_code == 422
    ext = client.post("/api/capa", json={
        "title": "Reconcile fixed asset register", "source_body": ag, "source_reference": "AG/ML/2025/14",
        "timeframe": lists["action_timeframes"][1], "owner_email": owner.email, "severity": "High",
        "corrective_action": "Reconcile and update the register"}, headers=h)
    assert ext.status_code == 201, ext.text
    ext = ext.json()
    assert ext["implementation_status"] == "Not Implemented" and ext["source_body"] == ag

    oh = csrf_headers(login(client2, owner.username))
    prog = client2.post(f"/api/capa/{ext['id']}/progress",
                        json={"status": "Partially Implemented", "note": "Two of five sites reconciled."}, headers=oh)
    assert prog.status_code == 200 and prog.json()["implementation_status"] == "Partially Implemented"
    full = client2.post(f"/api/capa/{ext['id']}/progress",
                        json={"status": "Fully Implemented", "note": "All done now really."}, headers=oh)
    assert full.status_code == 422

    internal = client.post("/api/capa", json={"title": "Obsolete recommendation on telex"}, headers=h).json()
    assert internal["source_body"] == lists["recommendation_sources"][0]
    wd = client.post(f"/api/capa/{internal['id']}/propose-withdrawal",
                     json={"reason": "The telex system was decommissioned in 2025."}, headers=h)
    assert wd.status_code == 200 and wd.json()["withdrawal_proposed_at"]

    # External recommendation cannot be closed by e-signature without the external body's closure reference.
    db.rollback()
    c = db.get(Capa, ext["id"])
    c.status, c.validation_result, c.implemented_at = "Review", ValidationResult.Effective, utcnow()
    c.implemented_by = owner.id
    db.commit()
    from fastapi.testclient import TestClient

    from app.main import app

    adm = _u(db, "acadm", Role.Admin)
    with TestClient(app) as c3:
        closed = c3.post(f"/api/capa/{ext['id']}/close", json={"password": "Passw0rd!x"},
                         headers=csrf_headers(login(c3, adm.username)))
    assert closed.status_code == 409 and "closure reference" in closed.json()["detail"]

    # Audit Committee meeting: decisions only once held; decisions applied to the actions.
    m = client.post("/api/committee/meetings", json={"meeting_date": (utcnow() - timedelta(days=1)).isoformat(),
                                                     "meeting_type": "Ordinary", "venue": "Boardroom"}, headers=h)
    assert m.status_code == 201, m.text
    mid = m.json()["id"]
    assert m.json()["meeting_ref"].startswith("ACM-")
    early = client.post(f"/api/committee/meetings/{mid}/decisions",
                        json={"subject_id": internal["id"], "decision": "Withdraw"}, headers=h)
    assert early.status_code == 409
    queue = client.get("/api/committee/for-decision").json()
    assert {q["id"] for q in queue} >= {internal["id"], ext["id"]}
    client.patch(f"/api/committee/meetings/{mid}", json={"status": "Held", "attendees": "Chair; Members; GM Audit",
                                                         "quorum": True, "followup_report_considered": True},
                 headers=h)
    w = client.post(f"/api/committee/meetings/{mid}/decisions",
                    json={"subject_id": internal["id"], "decision": "Withdraw"}, headers=h)
    assert w.status_code == 201, w.text
    noref = client.post(f"/api/committee/meetings/{mid}/decisions",
                        json={"subject_id": ext["id"], "decision": "Close"}, headers=h)
    assert noref.status_code == 422
    ok = client.post(f"/api/committee/meetings/{mid}/decisions",
                     json={"subject_id": ext["id"], "decision": "Close", "reference": "AG/CL/2026/3"}, headers=h)
    assert ok.status_code == 201
    got = client.get(f"/api/capa/{internal['id']}").json()
    assert got["status"] == "Closed" and got["implementation_status"] == "Withdrawn"
    got = client.get(f"/api/capa/{ext['id']}").json()
    assert got["implementation_status"] == "Fully Implemented" and got["external_closure_ref"] == "AG/CL/2026/3"
    assert client.post(f"/api/committee/meetings/{mid}/approve-minutes", headers=h).status_code == 422
    client.patch(f"/api/committee/meetings/{mid}", json={"minutes": "The Committee considered the Q3 follow-up "
                                                                    "report and took the decisions below."}, headers=h)
    assert client.post(f"/api/committee/meetings/{mid}/approve-minutes", headers=h).json()["status"] == \
        "Minutes approved"
    assert client.patch(f"/api/committee/meetings/{mid}", json={"venue": "x"}, headers=h).status_code == 409
    docx = client.get(f"/api/committee/meetings/{mid}/minutes.docx")
    with zipfile.ZipFile(io.BytesIO(docx.content)) as zf:
        assert "Withdraw" in zf.read("word/document.xml").decode()

    # Quarterly report and annual statement with the MoF columns; submission register keeps a frozen copy.
    now = utcnow()
    q = (now.month - 1) // 3 + 1
    rep = client.get(f"/api/follow-up/quarterly?year={now.year}&quarter={q}").json()
    refs = {r["ref"]: r for r in rep["rows"]}
    assert refs[ext["capa_ref"]]["source"] == ag and refs[ext["capa_ref"]]["status"] == "Fully Implemented"
    assert rep["summary"]["by_status"]["Withdrawn"] >= 1
    assert rep["recipients"] == ["Audit Committee", "Internal Audit Agency"]
    for fmt in ("docx", "xlsx"):
        assert client.get(f"/api/follow-up/quarterly.{fmt}?year={now.year}&quarter={q}").status_code == 200
    ann = client.get(f"/api/follow-up/annual?year={now.year}").json()
    assert ann["due_date"].startswith(f"{now.year + 1}-06-30")
    sub = client.post("/api/follow-up/submissions", json={
        "kind": "quarterly", "year": now.year, "quarter": q, "recipients": rep["recipients"],
        "submitted_at": now.isoformat(), "reference": "GPHA/IA/Q"}, headers=h)
    assert sub.status_code == 201, sub.text
    assert client.get(f"/api/follow-up/submissions/{sub.json()['id']}/export.docx").status_code == 200
    assert any(s["id"] == sub.json()["id"] for s in client.get("/api/follow-up/submissions").json())
    pack = client.get("/api/committee/summary").json()
    assert "Withdrawn" in pack["implementation_status"] and pack["conformance"]["statement"]


def test_committee_closes_internal_recommendations_when_configured(client, db):
    admin = _u(db, "cladm", Role.Admin)
    h = csrf_headers(login(client, admin.username))
    capa = client.post("/api/capa", json={"title": "Fix cash count"}, headers=h).json()
    db.rollback()
    c = db.get(Capa, capa["id"])
    c.status, c.validation_result, c.implemented_at = "Review", ValidationResult.Effective, utcnow()
    db.commit()
    _set(client, h, committee_closes_recommendations=True)
    try:
        r = client.post(f"/api/capa/{capa['id']}/close", json={"password": "Passw0rd!x"}, headers=h)
        assert r.status_code == 409 and "Audit Committee decision" in r.json()["detail"]
    finally:
        _reset(client, h, "committee_closes_recommendations")


def test_charter_and_external_assessment(client, client2, db):
    gm = _u(db, "chgm", job="gm_audit")
    aud = _u(db, "chaud", job="auditor")
    h = csrf_headers(login(client, gm.username))
    tmpl = client.get("/api/charter").json()["template"]
    ah = csrf_headers(login(client2, aud.username))
    assert client2.post("/api/charter", json={"title": "Charter", "content": tmpl}, headers=ah).status_code == 403
    c = client.post("/api/charter", json={"title": "Internal Audit Charter", "content": tmpl,
                                          "change_summary": "First issue"}, headers=h)
    assert c.status_code == 201, c.text
    cid = c.json()["id"]
    assert client.post("/api/charter", json={"title": "Another", "content": tmpl}, headers=h).status_code == 409
    assert client.post(f"/api/charter/{cid}/approve", json={"approved_at": utcnow().isoformat(),
                                                            "approval_reference": "AC/2026/4"},
                       headers=h).status_code == 409
    client.post(f"/api/charter/{cid}/submit", headers=h)
    ok = client.post(f"/api/charter/{cid}/approve", json={"approved_at": utcnow().isoformat(),
                                                          "approval_reference": "AC/2026/4"}, headers=h)
    assert ok.status_code == 200 and ok.json()["status"] == "Approved" and ok.json()["next_review_due"]
    assert client.get("/api/charter").json()["current"]["id"] == cid
    assert client.get(f"/api/charter/{cid}/export.docx").status_code == 200

    e = client.post("/api/quality/external-assessments", json={
        "assessment_type": "Self-assessment with independent validation", "assessor": "IIA Ghana validation team",
        "completed_at": "2024-03-15T00:00:00", "conclusion": "Generally conforms"}, headers=h)
    assert e.status_code == 201 and e.json()["next_due"].startswith("2029-03-15")
    not_indep = client.post("/api/quality/external-assessments", json={
        "assessment_type": "Full external assessment", "assessor": "Our own staff", "assessor_independent": False,
        "completed_at": "2025-01-01T00:00:00", "conclusion": "Generally conforms"}, headers=h)
    assert not_indep.status_code == 422
    conf = client.get("/api/quality/conformance").json()
    assert "Version" in conf["charter"] and "2029" in conf["external_assessment"]


def test_declarations_gate_fieldwork_and_cpd(client, client2, db, monkeypatch):
    monkeypatch.setattr(settings, "require_engagement_declaration", True)
    from app.core import appconfig

    appconfig.invalidate()
    lead = _u(db, "dclead", job="auditor")
    gm = _u(db, "dcgm", job="gm_audit")
    h = csrf_headers(login(client, lead.username))
    audit = client.post("/api/audits", json={"title": "Fuel"}, headers=h).json()
    blocked = client.patch(f"/api/audits/{audit['id']}", json={"status": "In Progress"}, headers=h)
    assert blocked.status_code == 409 and "annual declaration" in blocked.json()["detail"]
    base = {"independence_confirmed": True, "ethics_confirmed": True, "confidentiality_confirmed": True}
    assert client.post("/api/proficiency/declarations", json={"kind": "annual", **base}, headers=h).status_code == 201
    assert client.post("/api/proficiency/declarations", json={"kind": "annual", **base}, headers=h).status_code == 409
    conflict = client.post("/api/proficiency/declarations", json={
        "kind": "engagement", "audit_id": audit["id"], **base, "has_conflict": True,
        "conflict_details": "My brother manages the fuel depot."}, headers=h)
    assert conflict.status_code == 201 and conflict.json()["review_status"] == "Pending review"
    assert any("Conflict of interest" in n.title for n in _notes(db, gm.id))
    still = client.patch(f"/api/audits/{audit['id']}", json={"status": "In Progress"}, headers=h)
    assert still.status_code == 409 and "awaiting review" in still.json()["detail"]
    assert client.post(f"/api/proficiency/declarations/{conflict.json()['id']}/review",
                       json={"decision": "Cleared", "notes": "No impairment"}, headers=h).status_code == 403
    gh = csrf_headers(login(client2, gm.username))
    rv = client2.post(f"/api/proficiency/declarations/{conflict.json()['id']}/review",
                      json={"decision": "Cleared", "notes": "Depot excluded from his sample."}, headers=gh)
    assert rv.status_code == 200
    started = client.patch(f"/api/audits/{audit['id']}", json={"status": "In Progress"}, headers=h)
    assert started.status_code == 200, started.text

    cpd = client.post("/api/proficiency/cpd", json={"activity_date": "2026-03-01T00:00:00",
                                                    "activity": "IIA Ghana conference", "category":
                                                    "Conference / seminar", "hours": 16, "ethics_hours": 2},
                      headers=h)
    assert cpd.status_code == 201
    mine = client.get("/api/proficiency/cpd?year=2026").json()
    assert mine["hours"] == 16 and mine["target"] == 40
    assert client.post(f"/api/proficiency/cpd/{cpd.json()['id']}/verify", headers=h).status_code == 403
    assert client2.post(f"/api/proficiency/cpd/{cpd.json()['id']}/verify", headers=gh).status_code == 200
    team = client2.get("/api/proficiency/team?year=2026").json()
    row = next(s for s in team["staff"] if s["user_id"] == lead.id)
    assert row["cpd_hours"] == 16 and row["on_track"] is False


def test_automation_rules_event_schedule_and_admin(client, client2, db):
    admin = _u(db, "auadm", Role.Admin)
    gm = _u(db, "augm", job="gm_audit")
    owner = _u(db, "auown", Role.Auditee, email=f"o{uuid.uuid4().hex[:5]}@gpha.gov.gh")
    h = csrf_headers(login(client, admin.username))
    rules = client.get("/api/automations").json()
    keys = {r["name"] for r in rules}
    assert any("High-risk finding" in k for k in keys) and len(rules) >= 10
    cat = client.get("/api/automations/catalog").json()
    assert any(t["key"] == "action.due_soon" for t in cat["triggers"])

    # Built-in event rule: a High-risk finding notifies the GM Audit.
    audit = client.post("/api/audits", json={"title": "Marine"}, headers=h).json()
    client.post(f"/api/audits/{audit['id']}/findings", json={"title": "Tug logs missing", "risk_rating": "High"},
                headers=h)
    assert any("High-risk finding raised" in n.title for n in _notes(db, gm.id))

    # Custom rule: a task for the owner when a High action is recorded from the Auditor-General.
    src = client.get("/api/config/lists").json()["recommendation_sources"][1]
    rule = client.post("/api/automations", json={
        "name": "AG recommendations get a task", "trigger": "action.created",
        "conditions": [{"field": "source_body", "op": "eq", "value": src}],
        "actions": [{"type": "task", "to": ["owner"], "title": "Plan the response to {ref}", "due_days": 14}]},
        headers=h)
    assert rule.status_code == 201, rule.text
    bad = client.post("/api/automations", json={"name": "Bad one", "trigger": "action.created",
                                                "actions": [{"to": ["nobody"], "title": "x y z"}]}, headers=h)
    assert bad.status_code == 422
    client.post("/api/capa", json={"title": "Internal one", "owner_email": owner.email}, headers=h)
    capa = client.post("/api/capa", json={"title": "AG one", "owner_email": owner.email, "source_body": src},
                       headers=h).json()
    from app.platform.tasks.models import Task

    db.rollback()
    tasks = db.query(Task).filter(Task.assignee_id == owner.id).all()
    assert any(t.title == f"Plan the response to {capa['capa_ref']}" for t in tasks)
    assert not any("Internal one" in t.title for t in tasks if t.title.startswith("Plan the response"))

    # Scheduled rule: due in 7 days -> reminder, only once.
    db.rollback()
    c = db.get(Capa, capa["id"])
    c.due_date = utcnow() + timedelta(days=3)
    db.commit()
    due_rule = next(r for r in rules if r["trigger"] == "action.due_soon")
    preview = client.get(f"/api/automations/{due_rule['id']}/preview").json()
    assert any(m["record_id"] == capa["id"] for m in preview["matches"])
    first = client.post(f"/api/automations/run?rule_id={due_rule['id']}", headers=h).json()["fired"]
    second = client.post(f"/api/automations/run?rule_id={due_rule['id']}", headers=h).json()["fired"]
    assert first >= 1 and second == 0
    assert any(f"Action {capa['capa_ref']} is due" in n.title for n in _notes(db, owner.id))
    log = client.get(f"/api/automations/runs?rule_id={due_rule['id']}").json()
    assert any(r["record_id"] == capa["id"] for r in log)

    # Built-ins can be switched off but not deleted; auditors cannot manage automations.
    assert client.delete(f"/api/automations/{due_rule['id']}", headers=h).status_code == 409
    upd = client.put(f"/api/automations/{due_rule['id']}", json={**{k: due_rule[k] for k in (
        "name", "description", "trigger", "offset_days", "conditions", "actions")}, "active": False}, headers=h)
    assert upd.status_code == 200 and upd.json()["active"] is False
    aud = _u(db, "auaud", job="auditor")
    ah = csrf_headers(login(client2, aud.username))
    assert client2.get("/api/automations").status_code == 403
    client.put(f"/api/automations/{due_rule['id']}", json={**{k: due_rule[k] for k in (
        "name", "description", "trigger", "offset_days", "conditions", "actions")}, "active": True}, headers=h)
    assert ah


def test_custom_fields_on_audits_findings_and_actions(client, db):
    admin = _u(db, "cfadm", Role.Admin)
    h = csrf_headers(login(client, admin.username))
    for module, label in (("audits", "Budget code"), ("findings", "Amount at risk (GHS)"), ("capa", "Ministry ref")):
        f = client.post("/api/custom-fields", json={"module": module, "label": f"{label} {uuid.uuid4().hex[:4]}",
                                                    "field_type": "number" if "Amount" in label else "text"},
                        headers=h)
        assert f.status_code == 201, f.text
    defs = {m: client.get(f"/api/custom-fields?module={m}").json()[-1]["key"] for m in ("audits", "findings", "capa")}
    audit = client.post("/api/audits", json={"title": "CF audit", "custom_fields": {defs["audits"]: "GPHA-001"}},
                        headers=h)
    assert audit.status_code == 201 and audit.json()["custom_fields"][defs["audits"]] == "GPHA-001"
    bad = client.post(f"/api/audits/{audit.json()['id']}/findings",
                      json={"title": "Loss", "custom_fields": {defs["findings"]: "lots"}}, headers=h)
    assert bad.status_code == 422
    good = client.post(f"/api/audits/{audit.json()['id']}/findings",
                       json={"title": "Loss", "custom_fields": {defs["findings"]: "1250.5"}}, headers=h)
    assert good.status_code == 201 and good.json()["custom_fields"][defs["findings"]] == 1250.5
    capa = client.post("/api/capa", json={"title": "CF action", "custom_fields": {defs["capa"]: "MoF/7"}}, headers=h)
    assert capa.json()["custom_fields"][defs["capa"]] == "MoF/7"
    upd = client.patch(f"/api/capa/{capa.json()['id']}", json={"custom_fields": {defs["capa"]: "MoF/8"}}, headers=h)
    assert json.loads(json.dumps(upd.json()["custom_fields"]))[defs["capa"]] == "MoF/8"


def test_mfa_waits_for_go_live_unless_admin_enforces(client, db, monkeypatch):
    user = _u(db, "mfadev", Role.Auditor)
    admin = _u(db, "mfaadm", Role.Admin)
    admin.review_level = ReviewLevel.CAE
    db.commit()
    monkeypatch.setattr(settings, "mfa_required_roles", "Auditor")
    login(client, user.username)
    assert client.get("/api/audits").status_code == 200
    monkeypatch.setattr(settings, "mfa_enforce_outside_production", True)
    from app.core import appconfig

    appconfig.invalidate()
    assert client.get("/api/audits").status_code == 403
