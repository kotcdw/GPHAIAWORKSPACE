"""Administration phase 8: backup and recovery. Backup sets with the attachments and a manifest, automatic and
on-request checks kept in an append-only history, settings-driven schedule and retention, set-wide delete, and the
attachments restore used on the server."""

from __future__ import annotations

import io
import json
import tarfile
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select, text

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
    admin = _u(db, "bk_root", Role.Admin, job="super_admin")
    h = csrf_headers(login(client2, admin.username))
    yield client2, h
    for key in ("backup_include_attachments", "backup_retention", "backup_interval_hours"):
        client2.post(f"/api/config/{key}/reset", headers=h)


def _attach(client, db):
    aud = _u(db, "bk_aud", job="auditor")
    ah = login(client, aud.username)
    url = f"/api/audits/{_audit(client, ah)}/working-papers"
    r = client.post(url, data={"title": "wp"}, files={"file": ("wp.pdf", io.BytesIO(b"%PDF-1.7 wp"), "x")},
                    headers=csrf_headers(ah))
    assert r.status_code == 201


def test_backup_set_includes_attachments_and_is_checked(client, db, root):
    from app.platform.backups.service import backup_root

    _attach(client, db)
    c2, h = root
    made = c2.post("/api/admin/backup", headers=h).json()
    stamp = made["stamp"]
    assert made["files_name"] == f"backup_{stamp}.files.tar.gz" and made["file_count"] >= 1
    failed = [c for c in made["verified"]["checks"] if not c["ok"]]
    assert made["has_manifest"] and made["verified"]["outcome"] == "passed", failed
    manifest = json.loads((backup_root() / f"backup_{stamp}.manifest.json").read_text())
    assert manifest["database"]["row_counts"]["users"] >= 1 and "password" not in json.dumps(manifest).lower()
    with tarfile.open(backup_root() / made["files_name"]) as tar:
        names = tar.getnames()
    assert len(names) == made["file_count"] and all(n.endswith(".enc") for n in names)
    listed = next(b for b in c2.get("/api/admin/backups").json() if b["stamp"] == stamp)
    assert listed["verified"]["outcome"] == "passed" and {c["name"] for c in listed["verified"]["checks"]} >= {
        "Database file intact", "Decrypts with the current key", "Attachments archive intact"}
    status = c2.get("/api/admin/backups/status").json()
    assert status["includes_attachments"] and status["verified"]["outcome"] == "passed"


def test_damaged_or_unreadable_backups_fail_the_check(client, db, root, monkeypatch):
    from app.core.crypto import InvalidToken
    from app.platform.backups import service

    c2, h = root
    made = c2.post("/api/admin/backup", headers=h).json()
    archive = service.backup_root() / made["files_name"]
    archive.write_bytes(archive.read_bytes() + b"tampered")
    r = c2.post(f"/api/admin/backups/{made['stamp']}/verify", headers=h).json()
    assert r["ok"] is False and any(c["name"] == "Attachments archive intact" and not c["ok"] for c in r["checks"])

    def wrong_key(_raw):
        raise InvalidToken

    monkeypatch.setattr(service, "decrypt", wrong_key)
    r = c2.post(f"/api/admin/backups/{made['filename']}/verify", headers=h).json()
    assert any(c["name"] == "Decrypts with the current key" and not c["ok"] for c in r["checks"])
    history = c2.get("/api/admin/backups/checks").json()["items"]
    assert history[0]["outcome"] == "failed" and history[0]["backup"] == made["stamp"]
    assert c2.get("/api/admin/overview").json()["backups"]["verified"]["outcome"] == "failed"
    # The check history cannot be altered.
    with pytest.raises(Exception):  # noqa: B017 - the database trigger refuses
        db.execute(text("DELETE FROM backup_checks"))
        db.commit()
    db.rollback()


def test_settings_drive_attachments_and_retention(client, db, root):
    from app.platform.backups.service import list_backups

    c2, h = root
    assert c2.put("/api/config", json={"values": {"backup_include_attachments": False, "backup_retention": 2}},
                  headers=h).status_code == 200
    for _ in range(3):
        last = c2.post("/api/admin/backup", headers=h).json()
    assert last["files_name"] is None and last["verified"]["outcome"] == "passed"
    sets = list_backups()
    assert len(sets) == 2 and sets[0].stamp == last["stamp"]
    ov = c2.get("/api/admin/overview").json()["backups"]
    assert ov["retention"] == 2 and ov["includes_attachments"] is False
    # Only technical administrators manage backups.
    aud = _u(db, "bk_noaccess", job="auditor")
    ah = csrf_headers(login(client, aud.username))
    assert client.post(f"/api/admin/backups/{last['stamp']}/verify", headers=ah).status_code == 403
    assert client.put("/api/config", json={"values": {"backup_retention": 50}}, headers=ah).status_code == 403


def test_schedule_follows_the_setting(client, db, root, monkeypatch):
    from app.core.config import settings
    from app.main import _backup_due
    from app.platform.backups import service

    c2, h = root
    monkeypatch.setattr(settings, "backup_interval_hours", 24)  # server schedule on
    c2.post("/api/admin/backup", headers=h)
    c2.put("/api/config", json={"values": {"backup_interval_hours": 6}}, headers=h)
    assert _backup_due(service) is False  # a fresh backup exists
    monkeypatch.setattr(service, "list_backups", lambda: [])
    assert _backup_due(service) is True
    c2.put("/api/config", json={"values": {"backup_interval_hours": 0}}, headers=h)
    assert _backup_due(service) is False  # paused
    assert c2.get("/api/admin/overview").json()["backups"]["interval_hours"] == 0
    monkeypatch.setattr(settings, "backup_interval_hours", 0)
    c2.put("/api/config", json={"values": {"backup_interval_hours": 6}}, headers=h)
    assert service.interval_hours() == 0  # the server switch wins


def test_delete_removes_the_whole_set_and_attachments_restore(client, db, root, tmp_path, monkeypatch):
    from app.core.config import settings
    from app.platform.backups.service import backup_root
    from scripts.restore_backup import restore_attachments

    _attach(client, db)
    c2, h = root
    keep = c2.post("/api/admin/backup", headers=h).json()
    gone = c2.post("/api/admin/backup", headers=h).json()
    assert c2.delete("/api/admin/backups/..%2Fx", headers=h).status_code in (400, 404)
    assert c2.delete(f"/api/admin/backups/{gone['stamp']}", headers=h).status_code == 200
    assert not list(backup_root().glob(f"backup_{gone['stamp']}.*"))
    # Restoring attachments into an empty folder adds every file; existing files are never overwritten.
    target = tmp_path / "uploads"
    target.mkdir()
    with tarfile.open(backup_root() / keep["files_name"]) as tar:
        first = tar.getnames()[0]
    (target / first).parent.mkdir(parents=True, exist_ok=True)
    (target / first).write_bytes(b"newer copy")
    monkeypatch.setattr(settings, "upload_dir", str(target))
    restore_attachments(backup_root() / keep["files_name"], assume_yes=True)
    restored = [p for p in Path(target).rglob("*") if p.is_file()]
    assert len(restored) == keep["file_count"] and (target / first).read_bytes() == b"newer copy"
    from app.platform.backups.models import BackupCheck

    assert db.execute(select(BackupCheck).where(BackupCheck.backup == keep["stamp"])).first() is not None


def test_json_snapshot_is_checked_row_by_row(client, db, root, monkeypatch):
    from app.platform.backups import service

    c2, h = root
    monkeypatch.setattr(service, "_try_mysqldump", lambda _dest: False)
    made = c2.post("/api/admin/backup", headers=h).json()
    assert made["filename"].endswith(".json.enc") and made["method"] == "json"
    checks = {c["name"]: c for c in made["verified"]["checks"]}
    assert checks["All tables and rows present"]["ok"], checks
