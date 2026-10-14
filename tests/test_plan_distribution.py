"""GPHA plan distribution: approved plan -> GM Audit -> HQ, PIA Tema, PIA Takoradi (by responsible site)."""

from __future__ import annotations

import io
import uuid
import zipfile

from app.core import permissions as perms
from app.core.enums import AuditStatus, Role, utcnow
from tests.conftest import DEFAULT_PASSWORD, csrf_headers, login, make_user, walk_plan_to_review

_YEARS = iter(range(2024, 2031))


def _u(db, prefix, job, role=Role.Auditor, site=None):
    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    r = perms.JOB_ROLES_BY_CODE[job]
    user.job_role, user.role, user.review_level = r.code, r.tier, r.review_level
    user.work_entity_id = site
    db.commit()
    return user


def test_distribution_to_hq_and_port_pias(client, client2, db):
    adm = _u(db, "dsadm", "platform_admin", Role.Admin)
    ah = csrf_headers(login(client2, adm.username))
    tag = uuid.uuid4().hex[:4]
    hq = client2.post(
        "/api/organizations", json={"name": f"GPHA Head Office {tag}", "category": "Head Office"}, headers=ah
    ).json()
    tema = client2.post("/api/organizations", json={"name": f"Tema{tag} Port", "category": "Port"}, headers=ah).json()
    tadi = client2.post(
        "/api/organizations", json={"name": f"Takoradi{tag} Port", "category": "Port"}, headers=ah
    ).json()
    gm = _u(db, "dsgm", "gm_audit", site=hq["id"])
    mgr_hq = _u(db, "dsmgr", "audit_manager", site=hq["id"])
    pia_tema = _u(db, "dspiat", "pia", site=tema["id"])
    pia_tadi = _u(db, "dspiak", "pia", site=tadi["id"])

    mh = csrf_headers(login(client, mgr_hq.username))
    for fy in _YEARS:
        created = client.post("/api/assurance-plans", json={"fiscal_year": fy, "title": "Plan"}, headers=mh)
        if created.status_code == 201:
            break
    pid = created.json()["id"]
    base = f"/api/assurance-plans/{pid}"
    bad = client.post(f"{base}/engagements", json={"title": "x site", "site_entity_id": 999999}, headers=mh)
    assert bad.status_code in (404, 422)
    engs = {}
    for title, site, hours in (("Procurement HQ", hq, 100), ("Tema revenue", tema, 150), ("Takoradi fuel", tadi, 90)):
        r = client.post(
            f"{base}/engagements",
            json={"title": title, "site_entity_id": site["id"], "budget_hours": hours},
            headers=mh,
        )
        assert r.status_code == 201, r.text
        engs[title] = r.json()
    assert engs["Tema revenue"]["site_name"] == tema["name"]

    walk_plan_to_review(client, pid, mh)
    gh = csrf_headers(login(client2, gm.username))
    assert client2.post(f"{base}/approve", json={"password": DEFAULT_PASSWORD}, headers=gh).status_code == 200
    now = utcnow().isoformat()
    client2.post(f"{base}/cycle/submit-authority", json={"submitted_on": now}, headers=gh)
    client2.post(
        f"{base}/cycle/committee-decision",
        json={"decision": "Approved", "meeting_date": now, "reference": "AC/D"},
        headers=gh,
    )

    dests = {d["id"]: d for d in client2.get(f"{base}/cycle/destinations").json()}
    assert next(d for d in dests.values() if d["id"] == hq["id"])["recipients"][0]["id"] == mgr_hq.id
    tema_dest = next(d for d in dests.values() if d["id"] == tema["id"])
    assert tema_dest["destination"] == f"PIA Tema{tag}" and tema_dest["engagements"] == 1
    assert [r["id"] for r in tema_dest["recipients"]] == [pia_tema.id]

    # Only the GM Audit distributes.
    ph = csrf_headers(login(client, pia_tema.username))
    assert client.post(f"{base}/cycle/distribute", json={"site_ids": [tema["id"]]}, headers=ph).status_code == 403
    cyc = client2.post(
        f"{base}/cycle/distribute",
        json={"site_ids": [hq["id"], tema["id"], tadi["id"]], "note": "FY plan for execution"},
        headers=gh,
    ).json()
    rows = {d["user_id"]: d for d in cyc["distribution"]}
    assert rows[pia_tema.id]["site"] == f"PIA Tema{tag}" and rows[mgr_hq.id]["site"] == "HQ"
    assert rows[pia_tadi.id]["site"] == f"PIA Takoradi{tag}"
    assert cyc["stage"] == "execution"

    # Each destination's controlled copy contains its own engagements.
    doc = client2.get(f"{base}/versions/1/export.docx?site_id={tema['id']}")
    with zipfile.ZipFile(io.BytesIO(doc.content)) as zf:
        text = zf.read("word/document.xml").decode()
    assert "Tema revenue" in text and "Takoradi fuel" not in text and f"PIA Tema{tag}" in text

    # PIA Tema acknowledges and executes: the audit belongs to the Tema port.
    assert client.post(f"{base}/cycle/acknowledge", headers=ph).status_code == 200
    started = client.post(f"/api/plan-engagements/{engs['Tema revenue']['id']}/start", headers=ph)
    assert started.status_code == 200, started.text
    audit = client.get(f"/api/audits/{started.json()['audit_id']}").json()
    assert audit["port_entity_id"] == tema["id"] and audit["status"] == AuditStatus.Planned.value
    by_site = client.get(f"{base}/cycle").json()["execution"]["by_site"]
    assert by_site[f"PIA Tema{tag}"]["started"] == 1

    # A site with nobody registered cannot be sent a copy.
    empty = client2.post(
        "/api/organizations",
        json={"name": f"Kpone{tag} Port", "category": "Port"},
        headers=csrf_headers(login(client2, adm.username)),
    ).json()
    gh = csrf_headers(login(client2, gm.username))
    r = client2.post(f"{base}/cycle/distribute", json={"site_ids": [empty["id"]]}, headers=gh)
    assert r.status_code == 422 and "Where I work" in r.text
