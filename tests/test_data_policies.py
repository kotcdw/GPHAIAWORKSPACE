"""Administration phase 7: data and attachment policies, plus refused import files kept in the import history."""

from __future__ import annotations

import io
import uuid

import pytest

from app.core.enums import Role
from tests.conftest import csrf_headers, login, make_user
from tests.test_controls import _audit


def _u(db, prefix, role=Role.Auditor, job=None):
    from app.core import permissions as perms

    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    if job:
        r = perms.JOB_ROLES_BY_CODE[job]
        user.job_role, user.role, user.review_level = r.code, r.tier, r.review_level
    db.commit()
    return user


@pytest.fixture
def root(client2, db):
    admin = _u(db, "dp_root", Role.Admin, job="super_admin")
    h = csrf_headers(login(client2, admin.username))
    yield client2, h
    for key in ("attachment_file_types", "attachment_max_mb", "attachment_check_content", "login_max_attempts",
                "password_min_length", "import_max_rows"):
        client2.post(f"/api/config/{key}/reset", headers=h)


def test_unreadable_import_files_are_kept_in_the_history(client, db):
    mgr = _u(db, "dp_mgr", job="manager")
    h = csrf_headers(login(client, mgr.username))
    r = client.post("/api/import/risks", files={"file": ("notes.csv", b"a,b,c\n1,2,3", "text/csv")}, headers=h)
    assert r.status_code == 422
    from tests.test_integrated_universe import _xlsx

    wrong = _xlsx(["Name", "Something"], [["x", "y"]])
    r = client.post("/api/import/risks", files={"file": ("wrong.xlsx", wrong, "application/octet-stream")},
                    headers=h)
    assert r.status_code == 422 and "Missing column" in r.json()["detail"]
    runs = client.get("/api/import/history").json()["items"]
    assert [x["filename"] for x in runs[:2]] == ["wrong.xlsx", "notes.csv"]
    assert all(x["outcome"] == "rejected" for x in runs[:2])
    detail = client.get(f"/api/import/history/{runs[1]['id']}").json()
    assert "not a valid Excel workbook" in detail["problems"][0]["message"]


def test_attachment_types_and_content_follow_the_policy(client, db, root):
    c2, h = root
    aud = _u(db, "dp_aud", job="auditor")
    ah = login(client, aud.username)
    url = f"/api/audits/{_audit(client, ah)}/working-papers"
    send = lambda name, data: client.post(url, data={"title": name}, files={"file": (name, io.BytesIO(data), "x")},  # noqa: E731
                                          headers=csrf_headers(ah))
    assert send("ok.pdf", b"%PDF-1.7 report").status_code == 201
    # A program renamed to .pdf is refused by the content check.
    fake = send("invoice.pdf", b"MZ\x90\x00 this is a program")
    assert fake.status_code == 415 and "does not match" in fake.json()["detail"]
    # The administrator narrows the types: .txt is no longer accepted.
    assert c2.put("/api/config", json={"values": {"attachment_file_types": [".pdf", ".docx"]}},
                  headers=h).status_code == 200
    refused = send("notes.txt", b"plain text")
    assert refused.status_code == 415 and ".pdf" in refused.json()["detail"]
    # Content checking can be switched off; the extension list still applies.
    c2.put("/api/config", json={"values": {"attachment_check_content": False}}, headers=h)
    assert send("other.pdf", b"not really a pdf").status_code == 201


def test_limits_stay_within_the_server_ceiling(client, db, root):
    from app.core.config import settings

    c2, h = root
    r = c2.put("/api/config", json={"values": {"attachment_max_mb": settings.max_upload_mb + 1}}, headers=h)
    assert r.status_code == 422 and "server limit" in r.text
    assert c2.put("/api/config", json={"values": {"attachment_max_mb": 1}}, headers=h).status_code == 200
    aud = _u(db, "dp_big", job="auditor")
    ah = login(client, aud.username)
    url = f"/api/audits/{_audit(client, ah)}/working-papers"
    big = client.post(url, data={"title": "big"}, files={"file": ("big.txt", io.BytesIO(b"x" * (1024 * 1024 + 5)),
                                                                   "text/plain")}, headers=csrf_headers(ah))
    assert big.status_code == 413 and "1 MB" in big.json()["detail"]
    pol = c2.get("/api/admin/policies").json()
    assert pol["attachments"]["max_upload_mb"] == 1 and ".exe" in pol["attachments"]["never_allowed"]


def test_sign_in_rules_follow_the_settings(client, db, root):
    from sqlalchemy import select

    from app.platform.users.models import User

    c2, h = root
    assert c2.put("/api/config", json={"values": {"login_max_attempts": 3, "password_min_length": 12}},
                  headers=h).status_code == 200
    victim = _u(db, "dp_lock")
    for _ in range(3):
        client.post("/api/auth/login", json={"username": victim.username, "password": "wrong-password-x"})
    db.expire_all()
    assert db.execute(select(User).where(User.id == victim.id)).scalar_one().locked_until is not None
    person = _u(db, "dp_pw")
    ph = csrf_headers(login(client, person.username))
    from tests.conftest import DEFAULT_PASSWORD

    short = client.post("/api/auth/me/password", json={"current_password": DEFAULT_PASSWORD,
                                                       "new_password": "Short-pass9"}, headers=ph)
    assert short.status_code == 422 and "12 characters" in short.text
    pol = c2.get("/api/admin/policies").json()["sessions"]
    assert pol["max_failed_sign_ins"] == 3 and pol["password_min_length"] == 12


def test_storage_figures(client, db, root):
    c2, _ = root
    s = c2.get("/api/admin/storage").json()
    assert s["files"] >= 0 and isinstance(s["by_type"], list)
    aud = _u(db, "dp_store", job="auditor")
    login(client, aud.username)
    assert client.get("/api/admin/storage").status_code == 403
