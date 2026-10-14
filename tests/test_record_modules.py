"""Record-module tests: organizations, stakeholders, NC, CAPA, service feedback."""

from __future__ import annotations

from sqlalchemy import select

from app.core.enums import Role
from app.modules.tasks.models import Task
from tests.conftest import csrf_headers, login, make_user

PASSWORD = "Passw0rd!"


def _login(client, db, name, role=Role.Auditor):
    make_user(db, name, role)
    return login(client, name)


def test_organization_lifecycle_with_esign(client, client2, db):
    auditor = _login(client, db, "org_auditor", Role.Auditor)
    admin = _login(client2, db, "org_admin", Role.Admin)

    created = client.post(
        "/api/organizations",
        json={"name": "Acme Ltd", "category": "Vendor", "contact_email": "ops@acme.example"},
        headers=csrf_headers(auditor),
    )
    assert created.status_code == 201, created.text
    org = created.json()
    assert org["org_ref"].startswith("ORG-")
    assert org["status"] == "Pending"

    copied = client.post(f"/api/organizations/{org['id']}/copy", headers=csrf_headers(auditor))
    assert copied.status_code == 201
    assert copied.json()["org_ref"].startswith("ORG-")
    assert copied.json()["name"].endswith("(Copy)")

    approved = client2.post(
        f"/api/organizations/{org['id']}/approve",
        json={"password": PASSWORD, "comment": "ok"},
        headers=csrf_headers(admin),
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "Approved"
    assert approved.json()["approved_by"] is not None

    pending = client2.post(f"/api/organizations/{org['id']}/set-pending", headers=csrf_headers(admin))
    assert pending.status_code == 200
    assert pending.json()["status"] == "Pending"

    # Auditor cannot approve (admin-only tier).
    forbidden = client.post(
        f"/api/organizations/{org['id']}/approve",
        json={"password": PASSWORD},
        headers=csrf_headers(auditor),
    )
    assert forbidden.status_code == 403


def test_organization_approve_rejects_bad_password(client, client2, db):
    admin = _login(client, db, "org_admin2", Role.Admin)
    auditor = _login(client2, db, "org_preparer2", Role.Auditor)
    created = client2.post("/api/organizations", json={"name": "Bad Pass Co"}, headers=csrf_headers(auditor))
    org_id = created.json()["id"]
    bad = client.post(
        f"/api/organizations/{org_id}/approve",
        json={"password": "not-my-password"},
        headers=csrf_headers(admin),
    )
    assert bad.status_code == 400


def test_stakeholder_crud(client, db):
    csrf = _login(client, db, "sh_user", Role.Auditor)
    created = client.post(
        "/api/stakeholders",
        json={"name": "Ministry of Health", "stakeholder_type": "Regulator"},
        headers=csrf_headers(csrf),
    )
    assert created.status_code == 201, created.text
    sh = created.json()
    assert sh["sh_ref"].startswith("SH-")
    assert sh["status"] == "Active"

    patched = client.patch(f"/api/stakeholders/{sh['id']}", json={"status": "Inactive"}, headers=csrf_headers(csrf))
    assert patched.status_code == 200
    assert patched.json()["status"] == "Inactive"

    listing = client.get("/api/stakeholders", params={"status": "Inactive"})
    assert listing.status_code == 200
    assert listing.json()["total"] >= 1


def test_nonconformance_auto_task_and_link_capa(client, db):
    make_user(db, "nc_user", Role.Auditor, email="owner@example.com")
    csrf = login(client, "nc_user")

    nc = client.post(
        "/api/nonconformances",
        json={"title": "Missing signature", "severity": "High", "owner_email": "owner@example.com"},
        headers=csrf_headers(csrf),
    )
    assert nc.status_code == 201, nc.text
    nc_body = nc.json()
    assert nc_body["nc_ref"].startswith("NC-")
    assert nc_body["status"] == "Open"

    # A system task was auto-generated and assigned to the matched owner.
    # End the test session's transaction first: MySQL REPEATABLE READ would
    # otherwise keep the snapshot taken before the API committed.
    db.rollback()
    tasks = list(db.execute(select(Task).where(Task.source_type == "nonconformance")).scalars().all())
    assert any(t.source_id == nc_body["id"] and t.system_generated for t in tasks)

    capa = client.post(
        "/api/capa",
        json={"title": "Add required signature step", "severity": "High"},
        headers=csrf_headers(csrf),
    )
    assert capa.status_code == 201, capa.text
    capa_id = capa.json()["id"]

    linked = client.post(
        f"/api/nonconformances/{nc_body['id']}/link-capa",
        json={"capa_id": capa_id},
        headers=csrf_headers(csrf),
    )
    assert linked.status_code == 200, linked.text
    assert linked.json()["linked_capa_id"] == capa_id
    assert linked.json()["status"] == "Remediating"


def test_capa_close_with_esign(client, client2, db):
    csrf = _login(client, db, "capa_user", Role.Auditor)
    admin = _login(client2, db, "capa_admin", Role.Admin)

    created = client.post("/api/capa", json={"title": "Retrain staff"}, headers=csrf_headers(csrf))
    assert created.status_code == 201
    capa_id = created.json()["id"]
    assert created.json()["capa_ref"].startswith("REM-")

    # Not in Review yet -> cannot be signed off.
    early = client2.post(
        f"/api/capa/{capa_id}/close", json={"password": PASSWORD}, headers=csrf_headers(admin)
    )
    assert early.status_code == 409
    # Closing through PATCH is not allowed (e-sign only).
    patched = client.patch(f"/api/capa/{capa_id}", json={"status": "Closed"}, headers=csrf_headers(csrf))
    assert patched.status_code == 400
    # Follow-up: the owner records what was done, a different auditor validates it.
    done = client.post(
        f"/api/capa/{capa_id}/implement",
        json={"evidence": "All 14 cashiers retrained on 12 Oct; attendance sheet uploaded."},
        headers=csrf_headers(csrf),
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "Review"
    unvalidated = client2.post(f"/api/capa/{capa_id}/close", json={"password": PASSWORD}, headers=csrf_headers(admin))
    assert unvalidated.status_code == 409 and "validate" in unvalidated.json()["detail"]
    own = client.post(f"/api/capa/{capa_id}/validate", json={"result": "Effective"}, headers=csrf_headers(csrf))
    assert own.status_code == 403, "the implementer cannot validate their own work"
    untested = client2.post(f"/api/capa/{capa_id}/validate", json={"result": "Effective"}, headers=csrf_headers(admin))
    assert untested.status_code == 422, "follow-up testing must be described"
    ok = client2.post(f"/api/capa/{capa_id}/validate", headers=csrf_headers(admin),
                      json={"result": "Effective", "procedures": "Re-performed March reconciliation; agreed to GL"})
    assert ok.status_code == 200, ok.text

    closed = client2.post(
        f"/api/capa/{capa_id}/close",
        json={"password": PASSWORD, "comment": "verified"},
        headers=csrf_headers(admin),
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "Closed"
    assert closed.json()["closed_by"] is not None


def test_service_feedback_link(client, db):
    csrf = _login(client, db, "sf_user", Role.Auditor)
    nc = client.post("/api/nonconformances", json={"title": "NC for link"}, headers=csrf_headers(csrf))
    nc_id = nc.json()["id"]

    sf = client.post(
        "/api/service-feedback",
        json={"subject": "Late report", "source": "Phone"},
        headers=csrf_headers(csrf),
    )
    assert sf.status_code == 201, sf.text
    sf_body = sf.json()
    assert sf_body["sf_ref"].startswith("SF-")

    linked = client.post(
        f"/api/service-feedback/{sf_body['id']}/link",
        json={"nc_id": nc_id},
        headers=csrf_headers(csrf),
    )
    assert linked.status_code == 200, linked.text
    assert linked.json()["linked_nc_id"] == nc_id
    assert linked.json()["status"] == "In Progress"