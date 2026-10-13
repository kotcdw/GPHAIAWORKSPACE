"""Audit CRUD and workflow tests."""

from __future__ import annotations

from app.core.enums import Role
from tests.conftest import csrf_headers, login, make_user


def _auditor(client, db, name="auditor1"):
    make_user(db, name, Role.Auditor)
    return login(client, name)


def test_audit_lifecycle(client, client2, db):
    csrf = _auditor(client, db)
    make_user(db, "audit_signoff", Role.Admin)
    admin = login(client2, "audit_signoff")

    created = client.post(
        "/api/audits",
        json={"title": "Safety audit", "description": "d", "scope": "s"},
        headers=csrf_headers(csrf),
    )
    assert created.status_code == 201, created.text
    audit = created.json()
    assert audit["status"] == "Planned"
    audit_id = audit["id"]

    started = client.patch(f"/api/audits/{audit_id}", json={"status": "In Progress"}, headers=csrf_headers(csrf))
    assert started.status_code == 200
    assert started.json()["status"] == "In Progress"

    review = client.patch(f"/api/audits/{audit_id}", json={"status": "Review"}, headers=csrf_headers(csrf))
    assert review.status_code == 200

    # Closing is only possible through the e-signed sign-off, never PATCH.
    patched = client.patch(f"/api/audits/{audit_id}", json={"status": "Closed"}, headers=csrf_headers(csrf))
    assert patched.status_code == 400

    submitted = client.post(f"/api/audits/{audit_id}/in-approval", headers=csrf_headers(csrf))
    assert submitted.status_code == 200
    assert submitted.json()["approval_status"] == "In Approval"

    closed = client2.post(
        f"/api/audits/{audit_id}/close", json={"password": "Passw0rd!"}, headers=csrf_headers(admin)
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "Closed"
    assert closed.json()["approval_status"] == "Approved"

    # A closed audit is locked.
    invalid = client.patch(f"/api/audits/{audit_id}", json={"status": "In Progress"}, headers=csrf_headers(csrf))
    assert invalid.status_code == 409


def test_cannot_skip_from_planned_to_closed(client, db):
    csrf = _auditor(client, db, "auditor2")
    created = client.post("/api/audits", json={"title": "Audit X"}, headers=csrf_headers(csrf))
    audit_id = created.json()["id"]
    response = client.patch(f"/api/audits/{audit_id}", json={"status": "Closed"}, headers=csrf_headers(csrf))
    assert response.status_code == 400


def test_list_and_get_audit(client, db):
    csrf = _auditor(client, db, "auditor3")
    created = client.post("/api/audits", json={"title": "Audit Y"}, headers=csrf_headers(csrf))
    audit_id = created.json()["id"]

    listing = client.get("/api/audits")
    assert listing.status_code == 200
    assert any(a["id"] == audit_id for a in listing.json())

    fetched = client.get(f"/api/audits/{audit_id}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Audit Y"
