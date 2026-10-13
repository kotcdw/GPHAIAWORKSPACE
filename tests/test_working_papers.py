"""Working paper upload / versioning / download tests."""

from __future__ import annotations

import io

from app.core.enums import Role
from tests.conftest import csrf_headers, login, make_user


def _setup_audit(client, db, auditor: str):
    make_user(db, auditor, Role.Auditor)
    csrf = login(client, auditor)
    audit = client.post("/api/audits", json={"title": "Audit for papers"}, headers=csrf_headers(csrf)).json()
    return csrf, audit["id"]


def test_upload_creates_versions(client, db):
    csrf, audit_id = _setup_audit(client, db, "wauditor1")

    first = client.post(
        f"/api/audits/{audit_id}/working-papers",
        data={"title": "Evidence"},
        files={"file": ("evidence.txt", io.BytesIO(b"first version"), "text/plain")},
        headers=csrf_headers(csrf),
    )
    assert first.status_code == 201, first.text
    assert first.json()["version_number"] == 1

    second = client.post(
        f"/api/audits/{audit_id}/working-papers",
        data={"title": "Evidence"},
        files={"file": ("evidence.txt", io.BytesIO(b"second version"), "text/plain")},
        headers=csrf_headers(csrf),
    )
    assert second.status_code == 201
    assert second.json()["version_number"] == 2


def test_download_returns_file(client, db):
    csrf, audit_id = _setup_audit(client, db, "wauditor2")
    uploaded = client.post(
        f"/api/audits/{audit_id}/working-papers",
        data={"title": "Report"},
        files={"file": ("report.txt", io.BytesIO(b"hello world"), "text/plain")},
        headers=csrf_headers(csrf),
    ).json()

    download = client.get(f"/api/working-papers/{uploaded['id']}/download")
    assert download.status_code == 200
    assert download.content == b"hello world"
