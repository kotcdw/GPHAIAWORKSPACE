"""Phase 4 tests: tasks, generic approvals, record history, backups."""

from __future__ import annotations

from app.core.enums import Role
from tests.conftest import csrf_headers, login, make_user

PASSWORD = "Passw0rd!"


def test_task_center_flow(client, db):
    make_user(db, "task_owner", Role.Auditor)
    csrf = login(client, "task_owner")

    created = client.post(
        "/api/tasks",
        json={"title": "Review audit findings", "description": "check"},
        headers=csrf_headers(csrf),
    )
    assert created.status_code == 201, created.text
    task = created.json()
    assert task["status"] == "Open"
    assert task["assignor_id"] is not None

    mine = client.get("/api/tasks", params={"assigned_to_me": "true"})
    assert mine.status_code == 200

    by_me = client.get("/api/tasks", params={"by_me": "true"})
    assert by_me.json()["total"] >= 1

    closed = client.patch(f"/api/tasks/{task['id']}", json={"status": "Closed"}, headers=csrf_headers(csrf))
    assert closed.status_code == 200
    assert closed.json()["status"] == "Closed"
    assert closed.json()["completed_at"] is not None

    fetched = client.get(f"/api/tasks/{task['id']}")
    assert fetched.status_code == 200


def test_generic_approval_records_cycle_and_history(client, client2, db):
    make_user(db, "approver", Role.Admin)
    admin = login(client, "approver")
    make_user(db, "preparer", Role.Auditor)
    prep = login(client2, "preparer")
    audit_id = client2.post("/api/audits", json={"title": "Generic sign"}, headers=csrf_headers(prep)).json()["id"]

    missing = client.post(
        "/api/approvals/sign",
        json={"record_type": "audit", "record_id": 999999, "decision": "Approve", "password": PASSWORD},
        headers=csrf_headers(admin),
    )
    assert missing.status_code == 404

    signed = client.post(
        "/api/approvals/sign",
        json={
            "record_type": "audit",
            "record_id": audit_id,
            "decision": "Approve",
            "comment": "ok",
            "password": PASSWORD,
        },
        headers=csrf_headers(admin),
    )
    assert signed.status_code == 200, signed.text
    assert signed.json()["cycle_no"] == 1
    assert signed.json()["decision"] == "Approve"

    cycles = client.get(f"/api/records/audit/{audit_id}/approval-cycles")
    assert cycles.status_code == 200
    assert len(cycles.json()) == 1

    history = client.get(f"/api/records/audit/{audit_id}/history")
    assert history.status_code == 200
    assert any("E-SIGN Approve" in h["action"] for h in history.json())


def test_backup_create_list_delete(client, db):
    make_user(db, "backup_admin", Role.Admin)
    csrf = login(client, "backup_admin")

    made = client.post("/api/admin/backup", headers=csrf_headers(csrf))
    assert made.status_code == 200, made.text
    filename = made.json()["filename"]
    assert filename.startswith("backup_")

    listing = client.get("/api/admin/backups")
    assert listing.status_code == 200
    assert any(b["filename"] == filename for b in listing.json())

    deleted = client.delete(f"/api/admin/backups/{filename}", headers=csrf_headers(csrf))
    assert deleted.status_code == 200

    traversal = client.delete("/api/admin/backups/..%2Fsecret", headers=csrf_headers(csrf))
    assert traversal.status_code in (400, 404)