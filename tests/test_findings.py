"""Finding tests."""

from __future__ import annotations

from app.core.enums import Role
from tests.conftest import csrf_headers, login, make_user


def _setup_audit(client, db):
    make_user(db, "fauditor", Role.Auditor)
    csrf = login(client, "fauditor")
    audit = client.post("/api/audits", json={"title": "Audit for findings"}, headers=csrf_headers(csrf)).json()
    return csrf, audit["id"]


def test_create_and_update_finding(client, db):
    csrf, audit_id = _setup_audit(client, db)

    created = client.post(
        f"/api/audits/{audit_id}/findings",
        json={
            "title": "Missing sign-off",
            "description": "Evidence missing",
            "risk_rating": "High",
            "assigned_owner_email": "owner@example.com",
        },
        headers=csrf_headers(csrf),
    )
    assert created.status_code == 201, created.text
    finding = created.json()
    assert finding["risk_rating"] == "High"
    assert finding["status"] == "Open"

    updated = client.patch(
        f"/api/findings/{finding['id']}",
        json={"status": "Remediating"},
        headers=csrf_headers(csrf),
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "Remediating"

    listing = client.get(f"/api/audits/{audit_id}/findings")
    assert listing.status_code == 200
    assert len(listing.json()) == 1


def test_finding_requires_audit(client, db):
    make_user(db, "fauditor2", Role.Auditor)
    csrf = login(client, "fauditor2")
    response = client.post("/api/audits/9999/findings", json={"title": "Orphan"}, headers=csrf_headers(csrf))
    assert response.status_code == 404
