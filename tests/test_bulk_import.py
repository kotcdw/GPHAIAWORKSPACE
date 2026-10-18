"""Administration phase 6: bulk data import. Users (awaiting approval), remediation actions and external
recommendations, enterprise risks; the import catalogue and history (including rejected uploads)."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.enums import Role
from tests.conftest import csrf_headers, login, make_user
from tests.test_integrated_universe import _xlsx

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _u(db, prefix, role=Role.Auditor, job=None):
    from app.core import permissions as perms

    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    if job:
        r = perms.JOB_ROLES_BY_CODE[job]
        user.job_role, user.role, user.review_level = r.code, r.tier, r.review_level
    db.commit()
    return user


def _send(client, kind, headers, cols, rows, commit=False):
    from app.platform.dataio.router import TEMPLATES

    header = [c for c, _, _ in TEMPLATES[kind]] if cols is None else cols
    files = {"file": (f"{kind}.xlsx", _xlsx(header, rows), XLSX)}
    return client.post(f"/api/import/{kind}?commit={'true' if commit else 'false'}", files=files, headers=headers)


def test_users_are_created_awaiting_approval(client, db):
    from app.platform.users.models import User

    admin = _u(db, "bi_adm", Role.Admin, job="admin")
    h = csrf_headers(login(client, admin.username))
    unit = client.post("/api/organizations", json={"name": f"Import unit {uuid.uuid4().hex[:4]}",
                                                   "category": "Department"}, headers=h).json()
    tag = uuid.uuid4().hex[:5]
    rows = [[f"Kofi {tag}", f"kofi.{tag}", f"kofi.{tag}@gpha.test", "Auditor", "", unit["org_ref"]],
            [f"Esi {tag}", f"esi.{tag}", f"esi.{tag}@gpha.test", "Manager", "Unit Head", ""]]
    pre = _send(client, "users", h, None, rows).json()
    assert pre["to_create"] == 2 and not pre["errors"] and not pre["committed"]
    done = _send(client, "users", h, None, rows, commit=True).json()
    assert done["committed"], done
    db.expire_all()
    kofi = db.execute(select(User).where(User.username == f"kofi.{tag}")).scalar_one()
    esi = db.execute(select(User).where(User.username == f"esi.{tag}")).scalar_one()
    assert not kofi.is_active and kofi.job_role == "auditor" and kofi.work_entity_id == unit["id"]
    assert esi.job_role == "manager" and esi.review_level.value == "Unit Head"
    # They show as awaiting approval and cannot sign in yet.
    pending = client.get(f"/api/users/search?status=pending&q={tag}").json()["items"]
    assert {u["username"] for u in pending} == {f"kofi.{tag}", f"esi.{tag}"}
    # Duplicates, bad roles and administrators (for a non-super admin) are refused; nothing is written.
    bad = [[f"Kofi {tag}", f"kofi.{tag}", f"new.{tag}@gpha.test", "Auditor", "", ""],
           ["X", f"x.{tag}", f"kofi.{tag}@gpha.test", "Wizard", "", ""],
           ["Y", f"y.{tag}", f"y.{tag}@gpha.test", "Administrator", "", ""],
           ["Z", f"z.{tag}", "not-an-email", "Auditor", "PIA", "Nowhere"]]
    res = _send(client, "users", h, None, bad, commit=True).json()
    fields = {(e["row"], e["field"]) for e in res["errors"]}
    assert not res["committed"]
    assert {(2, "Username"), (3, "Email"), (3, "Role"), (4, "Role"), (5, "Email"), (5, "Approval level"),
            (5, "Workplace")} <= fields
    assert db.execute(select(User).where(User.username == f"z.{tag}")).first() is None


def test_remediation_and_external_recommendations(client, db):
    from app.domains.issues.capa.models import Capa

    mgr = _u(db, "bi_mgr", job="manager")
    h = csrf_headers(login(client, mgr.username))
    tag = uuid.uuid4().hex[:5]
    rows = [[f"Reconcile calls {tag}", "Internal Audit", "IA/2025/07", 2025, "High", "fm@gpha.test", "2025-03-31",
             "", "No reconciliation", "Assign a reviewer"],
            [f"Board minutes {tag}", "Internal Audit", "", "", "Low", "", "", "", "", ""]]
    done = _send(client, "remediation", h, None, rows, commit=True).json()
    assert done["committed"] and done["to_create"] == 2, done
    db.expire_all()
    first = db.execute(select(Capa).where(Capa.title == f"Reconcile calls {tag}")).scalar_one()
    assert first.due_date.date().isoformat() == "2025-03-31" and first.source_reference == "IA/2025/07"
    assert first.severity.value == "High" and first.source_year == 2025
    res = _send(client, "remediation", h, None,
                [[f"Bad {tag}", "Nobody", "", "twenty", "Huge", "x", "31/31/2025", "Never", "", ""]]).json()
    assert {e["field"] for e in res["errors"]} >= {"Source", "Source year", "Severity", "Due date", "Timeframe"}
    aud = _u(db, "bi_aud", job="auditor")
    h2 = csrf_headers(login(client, aud.username))
    assert _send(client, "remediation", h2, None, rows).status_code == 403


def test_risks_import_and_checks(client, db):
    from app.domains.grc.risk.models import EnterpriseRisk

    mgr = _u(db, "bi_risk", job="manager")
    owner = _u(db, "bi_owner")
    owner.email = f"{owner.username}@gpha.test"
    db.commit()
    h = csrf_headers(login(client, mgr.username))
    tag = uuid.uuid4().hex[:5]
    good = [[f"Revenue leakage {tag}", "", "", "Manual billing", "Loss", owner.email, "", 4, 4, 3, 3, "", "", ""]]
    done = _send(client, "risks", h, None, good, commit=True).json()
    assert done["committed"], done
    db.expire_all()
    risk = db.execute(select(EnterpriseRisk).where(EnterpriseRisk.title == f"Revenue leakage {tag}")).scalar_one()
    assert risk.owner_id == owner.id and risk.residual_likelihood == 3 and risk.inherent_impact == 4
    bad = [[f"Bad {tag}", "Weird", "", "", "", "ghost@nowhere.test", "Nowhere", 7, 2, 5, 5, "", "", ""]]
    res = _send(client, "risks", h, None, bad).json()
    assert {e["field"] for e in res["errors"]} >= {"Category", "Owner email", "Org unit", "Inherent likelihood"}


def test_history_catalogue_and_admin_summary(client, client2, db):
    admin = _u(db, "bi_hist", Role.Admin, job="super_admin")
    login(client2, admin.username)
    kinds = {c["kind"] for c in client2.get("/api/import/catalogue").json()}
    assert {"users", "orgunits", "processes", "remediation", "risks"} <= kinds
    mgr = _u(db, "bi_mgr2", job="manager")
    hm = csrf_headers(login(client, mgr.username))
    assert {c["kind"] for c in client.get("/api/import/catalogue").json()} == {"remediation", "risks"}
    # A rejected upload is kept with its problems; the manager sees only their own runs.
    _send(client, "risks", hm, None, [["", "", "", "", "", "", "", "", "", "", "", "", "", ""],
                                      ["Too high", "", "", "", "", "", "", 9, 9, "", "", "", "", ""]])
    mine = client.get("/api/import/history").json()["items"]
    assert mine and all(r["by"] == mgr.full_name for r in mine) and mine[0]["outcome"] == "rejected"
    detail = client.get(f"/api/import/history/{mine[0]['id']}").json()
    assert detail["problems"] and detail["problem_count"] == len(detail["problems"])
    everyone = client2.get("/api/import/history?limit=500").json()["items"]
    assert any(r["id"] == mine[0]["id"] for r in everyone)
    other = _u(db, "bi_other", job="manager")
    login(client, other.username)
    assert client.get(f"/api/import/history/{mine[0]['id']}").status_code == 404
    imp = client2.get("/api/admin/overview").json()["imports"]
    assert imp["failed"] >= 1 and isinstance(imp["completed"], int)
    # The template downloads for the new kinds.
    r = client2.get("/api/import/remediation/template.xlsx")
    assert r.status_code == 200 and r.headers["content-type"].startswith(XLSX)
