"""Architecture: router registry by layer, the platform map, and the pluggable AI Service (off by default)."""

from __future__ import annotations

import json
import uuid

import pytest

from app.core.enums import Role
from app.services.ai import providers
from tests.conftest import csrf_headers, login, make_user


def _login(client, db, role=Role.Auditor):
    name = f"arch_{uuid.uuid4().hex[:8]}"
    make_user(db, name, role)
    return csrf_headers(login(client, name))


def _set(client, admin, **values):
    r = client.put("/api/config", json={"values": values}, headers=admin)
    assert r.status_code == 200, r.text


@pytest.fixture
def fake_provider(monkeypatch):
    calls = []

    def fake(cfg, system, prompt):
        calls.append({"cfg": cfg, "system": system, "prompt": prompt})
        if "5C structure" in prompt:
            return "Here it is:\n" + json.dumps({"condition": "Fuel cards were not reconciled for 3 months.",
                                                 "criteria": "Fleet policy 4.2", "cause": "No owner",
                                                 "effect": "Undetected misuse", "recommendation": "Assign owner"})
        if "JSON array" in prompt:
            return json.dumps([{"risk": "Unauthorised fuel use", "likelihood": 9, "impact": 4,
                                "controls": ["Monthly reconciliation", "Card limits"]}])
        return "The audit found that fuel card controls need strengthening."

    monkeypatch.setattr(providers, "complete", fake)
    return calls


def test_every_layer_registers_its_routers_and_platform_map(client, db):
    from app import main, platform, services
    from app.domains import layers

    assert [layer.NAME for layer in main.LAYERS] == [
        "API / Platform Core", "Audit Domain Module", "Assurance Domain Module", "Issues Domain Module",
        "Risk & Compliance Domain Module", "Services"]
    registered = {id(r) for r in main._ROUTERS}
    for layer in (platform, *layers(), services):
        assert all(id(r) in registered for r in layer.routers())
    # Every API route belongs to exactly one layer package.
    owners = {"app.platform", "app.domains.audit", "app.domains.assurance", "app.domains.issues", "app.domains.grc",
              "app.services"}
    for router in main._ROUTERS:
        for route in router.routes:
            assert any(route.endpoint.__module__.startswith(o) for o in owners), route.path

    auditor = _login(client, db)
    assert client.get("/api/platform").status_code == 403
    client.post("/api/auth/logout", headers=auditor)
    _login(client, db, Role.Admin)
    m = client.get("/api/platform").json()
    assert m["platform"]["name"] == "API / Platform Core"
    assert [d["name"] for d in m["domains"]] == ["Audit Domain Module", "Assurance Domain Module",
                                                 "Issues Domain Module", "Risk & Compliance Domain Module"]
    tables = {mod["code"]: mod["tables"] for d in m["domains"] for mod in d["modules"]}
    assert "findings" in tables["audits"] and "plan_versions" in tables["plancycle"] and "capa" in tables["capa"]
    assert m["shared_data"]["tables"] > 30
    svc = {mod["code"]: mod for mod in m["services"]["modules"]}
    assert set(svc) == {"ai", "analytics", "documents", "results", "reporting"}
    assert {"report_items", "ai_report_workstreams"} <= set(svc["reporting"]["tables"])
    assert svc["ai"]["status"]["enabled"] is False  # off by default
    assert any(d["name"] == "Audit report" for d in svc["documents"]["status"]["documents"])
    assert "ai_requests" in svc["ai"]["tables"] and "ai" in svc["ai"]["endpoints"]
    auth = next(mod for mod in m["platform"]["modules"] if mod["code"] == "auth")
    assert auth["endpoints"] == ["auth"]


def test_ai_is_off_by_default_and_drafts_only(client, client2, db, fake_provider):
    aud = _login(client, db)
    audit = client.post("/api/audits", json={"title": "Fleet fuel", "scope": "Fuel cards"}, headers=aud).json()
    finding = client.post(f"/api/audits/{audit['id']}/findings",
                          json={"title": "Fuel cards unreconciled", "risk_rating": "High"}, headers=aud).json()
    status = client.get("/api/ai/status").json()
    assert status["enabled"] is False and status["can_use"] is False and "endpoint" not in status
    off = client.post(f"/api/ai/findings/{finding['id']}/draft", json={"notes": "x"}, headers=aud)
    assert off.status_code == 409 and "turned off" in off.json()["detail"]
    assert fake_provider == []

    admin = csrf_headers(login(client2, make_user(db, f"aiadm_{uuid.uuid4().hex[:6]}", Role.Admin).username))
    _set(client2, admin, ai_enabled=True, ai_provider="openai_compatible", ai_model="llama3.1")
    try:
        assert client.get("/api/ai/status").json()["can_use"] is True
        notes = "Spoke to j.mensah@gpha.gov.gh on 024 412 3456 about the reconciliations."
        r = client.post(f"/api/ai/findings/{finding['id']}/draft", json={"notes": notes}, headers=aud)
        assert r.status_code == 200, r.text
        assert r.json()["accept_required"] is True
        assert r.json()["draft"]["recommendation"] == "Assign owner"
        sent = fake_provider[-1]["prompt"]
        assert "j.mensah@gpha.gov.gh" not in sent and "412 3456" not in sent and "[e-mail removed]" in sent
        # Draft only: the finding itself is unchanged.
        assert client.get(f"/api/findings/{finding['id']}").json().get("condition") in ("", None)

        obj = client.post(f"/api/audits/{audit['id']}/objectives", json={"title": "Fuel is controlled"},
                          headers=aud).json()
        risks = client.post(f"/api/ai/objectives/{obj['id']}/risks", headers=aud).json()["draft"]["risks"]
        assert risks[0]["likelihood"] == 5 and risks[0]["controls"] == ["Monthly reconciliation", "Card limits"]

        # Auditees have no ai.use permission; other auditors cannot reach audits they are not on.
        auditee = _login(client, db, Role.Auditee)
        assert client.post(f"/api/ai/findings/{finding['id']}/draft", json={}, headers=auditee).status_code == 403

        st = client2.get("/api/ai/status").json()
        assert st["requests"]["ok"] >= 2 and st["api_key_set"] is False
    finally:
        _set(client2, admin, ai_enabled=False)


def test_ai_provider_errors_are_logged(client, db, monkeypatch):
    from app.services.ai.models import AiRequest

    def boom(cfg, system, prompt):
        raise providers.AiError("Could not reach the AI provider: connection refused")

    monkeypatch.setattr(providers, "complete", boom)
    admin = _login(client, db, Role.Admin)
    _set(client, admin, ai_enabled=True)
    try:
        audit = client.post("/api/audits", json={"title": "Stores"}, headers=admin).json()
        f = client.post(f"/api/audits/{audit['id']}/findings", json={"title": "Stock", "risk_rating": "Low"},
                        headers=admin).json()
        r = client.post(f"/api/ai/findings/{f['id']}/draft", json={}, headers=admin)
        assert r.status_code == 503 and "connection refused" in r.json()["detail"]
        db.rollback()  # new snapshot (REPEATABLE READ)
        row = db.query(AiRequest).filter_by(record_type="finding", record_id=f["id"]).one()
        assert row.status == "error" and "connection refused" in row.error
    finally:
        _set(client, admin, ai_enabled=False)


def test_unknown_provider_is_reported():
    with pytest.raises(providers.AiError, match="Unknown AI provider"):
        providers.complete(providers.ProviderConfig("bogus", "m", "http://x", "", 5), "s", "p")
