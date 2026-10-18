"""Phase 1 of the end-to-end automation: workflow engine (transition log), work items (My work) and the SLA clock."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, text

from app.core.enums import Role, utcnow
from app.core.workdays import working_days_between
from tests.conftest import csrf_headers, login, make_user


def _u(db, prefix, role=Role.Auditor, job=None):
    from app.core import permissions as perms

    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    if job:
        r = perms.JOB_ROLES_BY_CODE[job]
        user.job_role, user.role, user.review_level = r.code, r.tier, r.review_level
        db.commit()
    return user


@pytest.fixture
def setup(client, client2, db):
    lead = _u(db, "wflead")
    member = _u(db, "wfmem")
    h = csrf_headers(login(client, lead.username))
    audit = client.post("/api/audits", json={"title": f"WF {uuid.uuid4().hex[:5]}", "scope": "x",
                                             "audit_type": "Operational"}, headers=h).json()
    for u, role in ((member, "Auditor"),):
        r = client.post(f"/api/audits/{audit['id']}/team", json={"user_id": u.id, "team_role": role}, headers=h)
        assert r.status_code in (200, 201), r.text
    o = client.post(f"/api/audits/{audit['id']}/objectives", json={"title": "Revenue is complete"}, headers=h).json()
    return {"lead": lead, "member": member, "h": h, "audit": audit, "objective": o}


def _items(db, **where):
    from app.platform.workflow.models import WorkItem

    db.rollback()
    stmt = select(WorkItem)
    for k, v in where.items():
        stmt = stmt.where(getattr(WorkItem, k) == v)
    return list(db.execute(stmt).scalars())


def _transitions(db, rt, rid):
    from app.platform.workflow.models import WorkflowTransition

    db.rollback()
    return list(db.execute(select(WorkflowTransition).where(WorkflowTransition.record_type == rt,
                                                            WorkflowTransition.record_id == rid)
                           .order_by(WorkflowTransition.id)).scalars())


def test_assignment_opens_a_prepare_item_with_working_day_due_date(client, client2, db, setup):
    s = setup
    p = client.post(f"/api/objectives/{s['objective']['id']}/procedures",
                    json={"title": "Vouch receipts", "assigned_to": s["member"].id}, headers=s["h"]).json()
    items = _items(db, record_type="procedure", record_id=p["id"], status="open")
    assert [(i.kind, i.assignee_id) for i in items] == [("prepare", s["member"].id)]
    item = items[0]
    assert item.sla_key == "prepare" and not item.due_from_record
    assert working_days_between(item.opened_at, item.due_at) == 5  # SLA default: prepare in 5 working days

    # It shows in the member's My work, with counts.
    mh = csrf_headers(login(client2, s["member"].username))
    mine = client2.get("/api/my-work").json()
    row = next(i for i in mine["items"] if i["record_type"] == "procedure" and i["record_id"] == p["id"])
    assert row["kind"] == "prepare" and row["group"] == "prepare" and row["audit_id"] == s["audit"]["id"]
    assert row["link"] == {"type": "audit", "id": s["audit"]["id"], "tab": "fieldwork"}
    assert mine["counts"]["by_group"]["prepare"] >= 1
    assert client2.get("/api/my-work?group=review").json()["items"] == [] or all(
        i["group"] == "review" for i in client2.get("/api/my-work?group=review").json()["items"])

    # Re-assigning moves the item; a due date on the record wins over the SLA.
    due = (utcnow() + timedelta(days=20)).date().isoformat()
    r = client.patch(f"/api/procedures/{p['id']}", json={"assigned_to": s["lead"].id, "due_date": due},
                     headers=s["h"])
    assert r.status_code == 200, r.text
    open_now = _items(db, record_type="procedure", record_id=p["id"], status="open")
    assert [(i.assignee_id, i.due_from_record) for i in open_now] == [(s["lead"].id, True)]
    assert _items(db, record_type="procedure", record_id=p["id"], assignee_id=s["member"].id)[0].status == "done"

    # Starting the work through the generic transition endpoint is recorded with the actor.
    st = client.post(f"/api/workflow/procedure/{p['id']}/transition", json={"action": "start"}, headers=s["h"])
    assert st.status_code == 200, st.text
    assert st.json()["state"] == "In Progress"
    trail = _transitions(db, "procedure", p["id"])
    assert [(t.from_state, t.to_state) for t in trail] == [(None, "Not Started"), ("Not Started", "In Progress")]
    assert trail[-1].user_id == s["lead"].id and trail[-1].action == "start" and trail[-1].source == "api"
    assert trail[-1].allowed and trail[-1].audit_id == s["audit"]["id"]
    hist = client.get(f"/api/workflow/procedure/{p['id']}/history").json()
    assert hist[-1]["to"] == "In Progress" and hist[-1]["user"]
    # Steps with checks of their own stay on their own screens.
    acts = client.get(f"/api/workflow/procedure/{p['id']}/actions").json()
    assert acts["state"] == "In Progress" and any(a["action"] == "prepare" and not a["generic"]
                                                  for a in acts["actions"])
    nope = client.post(f"/api/workflow/procedure/{p['id']}/transition", json={"action": "prepare"},
                       headers=s["h"])
    assert nope.status_code == 409
    del mh


def test_next_reviewer_opens_review_item_and_signing_closes_it(client, client2, db, setup):
    from app.domains.audit.rcm.models import Signoff, SignoffReviewer

    s = setup
    reviewer = _u(db, "wfrev", job="manager")
    client.post(f"/api/audits/{s['audit']['id']}/team", json={"user_id": reviewer.id, "team_role": "Reviewer"},
                headers=s["h"])
    p = client.post(f"/api/objectives/{s['objective']['id']}/procedures",
                    json={"title": "Count cash", "assigned_to": s["member"].id}, headers=s["h"]).json()
    db.rollback()
    db.add(Signoff(target_type="procedure", target_id=p["id"], audit_id=s["audit"]["id"], level=1,
                   user_id=s["member"].id, signed_at=utcnow()))
    db.commit()
    r = client.put(f"/api/signoffs/procedure/{p['id']}/next-reviewer", json={"reviewer_id": reviewer.id},
                   headers=s["h"])
    assert r.status_code == 200, r.text
    review = _items(db, record_type="procedure", record_id=p["id"], kind="review", status="open")
    assert [i.assignee_id for i in review] == [reviewer.id]
    assert working_days_between(review[0].opened_at, review[0].due_at) == 3  # review in 3 working days
    rh = csrf_headers(login(client2, reviewer.username))
    assert any(i["kind"] == "review" for i in client2.get("/api/my-work?group=review").json()["items"])
    signed = client2.post(f"/api/signoffs/procedure/{p['id']}", json={}, headers=rh)
    assert signed.status_code == 200, signed.text
    db.rollback()
    assert db.get(SignoffReviewer, ("procedure", p["id"])) is None
    assert _items(db, record_type="procedure", record_id=p["id"], kind="review", status="open") == []
    assert _items(db, record_type="procedure", record_id=p["id"], kind="review")[0].status == "done"


def test_evidence_request_and_review_note_items(client, client2, db, setup):
    s = setup
    ee = _u(db, "wfee", Role.Auditee)
    client.post(f"/api/audits/{s['audit']['id']}/auditees", json={"user_id": ee.id}, headers=s["h"])
    due = (utcnow() + timedelta(days=6)).date().isoformat()
    req = client.post(f"/api/audits/{s['audit']['id']}/evidence-requests",
                      json={"title": "Bank statements", "assignee_id": ee.id, "due_date": due}, headers=s["h"])
    assert req.status_code == 201, req.text
    rid = req.json()["id"]
    items = _items(db, record_type="evidence_request", record_id=rid, status="open")
    assert [(i.kind, i.assignee_id, i.due_from_record) for i in items] == [("provide_evidence", ee.id, True)]
    eh = csrf_headers(login(client2, ee.username))
    mine = client2.get("/api/my-work").json()["items"]
    assert any(i["record_type"] == "evidence_request" and i["group"] == "respond" for i in mine)
    sub = client2.post(f"/api/evidence-requests/{rid}/submit", json={"response": "Attached"}, headers=eh)
    assert sub.status_code in (200, 201), sub.text
    items = _items(db, record_type="evidence_request", record_id=rid, status="open")
    assert [(i.kind, i.assignee_id) for i in items] == [("accept_evidence", s["lead"].id)]
    assert [(t.from_state, t.to_state, t.user_id) for t in _transitions(db, "evidence_request", rid)][-1] == \
        ("Requested", "Submitted", ee.id)

    # A review note on a test goes to the test's preparer.
    ctl_audit = client.post("/api/audits", json={"title": f"WF IC {uuid.uuid4().hex[:4]}", "scope": "x"},
                            headers=s["h"]).json()
    client.post(f"/api/audits/{ctl_audit['id']}/team", json={"user_id": s["member"].id, "team_role": "Auditor"},
                headers=s["h"])
    o = client.post(f"/api/audits/{ctl_audit['id']}/objectives", json={"title": "O"}, headers=s["h"]).json()
    c = client.post(f"/api/objectives/{o['id']}/controls", json={"title": "C"}, headers=s["h"]).json()
    t = client.post(f"/api/controls/{c['id']}/tests", json={"test_type": "Design", "assigned_to": s["member"].id},
                    headers=s["h"])
    assert t.status_code == 201, t.text
    t = t.json()
    assert [i.kind for i in _items(db, record_type="control_test", record_id=t["id"], status="open")] == ["prepare"]
    reviewer = _u(db, "wfnoter", job="manager")
    client.post(f"/api/audits/{ctl_audit['id']}/team", json={"user_id": reviewer.id, "team_role": "Reviewer"},
                headers=s["h"])
    rh = csrf_headers(login(client2, reviewer.username))
    note = client2.post(f"/api/audits/{ctl_audit['id']}/review-notes",
                        json={"target_type": "control_test", "target_id": t["id"], "note": "Sample size?"},
                        headers=rh)
    assert note.status_code in (200, 201), note.text
    nid = note.json()["id"]
    assert [(i.kind, i.assignee_id) for i in _items(db, record_type="review_note", record_id=nid,
                                                     status="open")] == [("answer_note", s["member"].id)]


def test_sla_clock_warns_then_escalates_to_the_lead(client, client2, db, setup):
    from app.platform.notifications.models import Notification
    from app.platform.workflow.workitems import run_sla_clock

    s = setup
    p = client.post(f"/api/objectives/{s['objective']['id']}/procedures",
                    json={"title": "Reconcile", "assigned_to": s["member"].id}, headers=s["h"]).json()
    item = _items(db, record_type="procedure", record_id=p["id"], status="open")[0]
    # Due tomorrow -> warning.
    item.due_at = utcnow() + timedelta(hours=20)
    db.commit()
    run_sla_clock(db)
    db.refresh(item)
    assert item.sla_state == "warning" and item.warned_at is not None
    notes = list(db.execute(select(Notification).where(Notification.user_id == s["member"].id)).scalars())
    assert any(n.title.startswith("Due soon") for n in notes)
    # Past due -> breached once, assignee and lead told, priority high.
    item.due_at = utcnow() - timedelta(hours=1)
    db.commit()
    first = run_sla_clock(db)
    again = run_sla_clock(db)
    db.refresh(item)
    assert item.sla_state == "breached" and item.priority == "high"
    assert first["breached"] >= 1 and again["breached"] == 0
    lead_notes = list(db.execute(select(Notification).where(Notification.user_id == s["lead"].id)).scalars())
    assert any(n.title.startswith("Overdue in your audit") for n in lead_notes)
    mh = csrf_headers(login(client2, s["member"].username))
    counts = client2.get("/api/my-work/counts").json()
    assert counts["overdue"] >= 1
    assert all(i["sla_state"] == "breached" for i in client2.get("/api/my-work?due=overdue").json()["items"])
    del mh


def test_unlisted_status_change_is_recorded_and_flagged(client, db, setup):
    from app.domains.audit.rcm.models import Procedure

    s = setup
    p = client.post(f"/api/objectives/{s['objective']['id']}/procedures", json={"title": "Odd"}, headers=s["h"])
    pid = p.json()["id"]
    db.rollback()
    row = db.get(Procedure, pid)
    row.status = "Reviewed"  # Not Started -> Reviewed skips preparation: not in the workflow
    db.commit()
    last = _transitions(db, "procedure", pid)[-1]
    assert (last.from_state, last.to_state, last.allowed, last.source, last.user_id) == \
        ("Not Started", "Reviewed", False, "system", None)


def test_transitions_are_append_only(db, client, setup):
    s = setup
    p = client.post(f"/api/objectives/{s['objective']['id']}/procedures", json={"title": "AO"}, headers=s["h"])
    tid = _transitions(db, "procedure", p.json()["id"])[0].id
    with pytest.raises(Exception):  # noqa: B017 - the database trigger refuses
        db.execute(text("UPDATE workflow_transitions SET to_state='X' WHERE id=:i"), {"i": tid})
    db.rollback()
    with pytest.raises(Exception):  # noqa: B017
        db.execute(text("DELETE FROM workflow_transitions WHERE id=:i"), {"i": tid})
    db.rollback()


def test_sla_policies_are_configurable_by_workflow_admins_only(client, client2, db):
    staff = _u(db, "wfstaff")
    admin = _u(db, "wfadm", Role.Admin)
    sh = csrf_headers(login(client, staff.username))
    pols = {p["key"]: p for p in client.get("/api/sla-policies").json()}
    assert (pols["prepare"]["working_days"], pols["review"]["working_days"],
            pols["client_response"]["working_days"], pols["validate"]["working_days"]) == (5, 3, 10, 10)
    body = {"working_days": 4, "warn_before_days": 1, "escalate_on_breach": True, "active": True}
    assert client.put("/api/sla-policies/prepare", json=body, headers=sh).status_code == 403
    ah = csrf_headers(login(client2, admin.username))
    bad = client2.put("/api/sla-policies/prepare", json={**body, "warn_before_days": 4}, headers=ah)
    assert bad.status_code == 422
    ok = client2.put("/api/sla-policies/prepare", json=body, headers=ah)
    assert ok.status_code == 200 and ok.json()["working_days"] == 4
    client2.put("/api/sla-policies/prepare", json={**body, "working_days": 5}, headers=ah)
    assert client2.get("/api/workflows").status_code == 200
    ee = _u(db, "wfee2", Role.Auditee)
    login(client, ee.username)
    assert client.get("/api/workflows").status_code == 403
    assert client.get("/api/sla-policies").status_code == 403


def test_full_resync_rebuilds_missing_items_and_auditees_cannot_read_history(client, client2, db, setup):
    from app.platform.workflow.models import WorkItem
    from app.platform.workflow.workitems import full_resync

    s = setup
    p = client.post(f"/api/objectives/{s['objective']['id']}/procedures",
                    json={"title": "Rebuild", "assigned_to": s["member"].id}, headers=s["h"]).json()
    db.rollback()
    for item in db.execute(select(WorkItem).where(WorkItem.record_type == "procedure",
                                                  WorkItem.record_id == p["id"])).scalars():
        db.delete(item)
    db.commit()
    assert _items(db, record_type="procedure", record_id=p["id"]) == []
    full_resync(db)
    db.commit()
    assert [i.kind for i in _items(db, record_type="procedure", record_id=p["id"], status="open")] == ["prepare"]
    outsider = _u(db, "wfout", Role.Auditee)
    login(client2, outsider.username)
    assert client2.get(f"/api/workflow/procedure/{p['id']}/history").status_code in (403, 404)
