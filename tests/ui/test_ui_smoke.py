"""Browser tests for the shell, the shared components and every screen (Playwright).

These start the real app on a free port against the pytest MySQL database and drive it with Chromium.
They are skipped when Playwright or a browser is not installed:

    uv sync --group ui
    uv run --group ui playwright install chromium
    uv run --group ui pytest tests/ui

GPHA_UI_BROWSER=<path to chrome> uses an already-installed Chromium instead of the downloaded one.
GPHA_UI_SHOTS=<folder> saves a screenshot of every screen there (desktop, tablet and phone widths).
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

ADMIN = ("ui_superadmin", "Passw0rd!")
IGNORED_HTTP = ("/api/auth/me", "/api/drafts/")  # 401 before sign-in, 404 when no draft exists


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def base_url():
    from app.core.database import SessionLocal
    from app.core.enums import Role
    from app.core.security import hash_password
    from app.platform.users.models import User

    db = SessionLocal()
    try:
        if db.query(User).filter(User.username == ADMIN[0]).first() is None:
            db.add(User(username=ADMIN[0], password_hash=hash_password(ADMIN[1]), email="ui@example.com",
                        full_name="UI Super Administrator", role=Role.Admin, job_role="super_admin", is_active=True))
            db.commit()
    finally:
        db.close()
    port = _free_port()
    root = Path(__file__).resolve().parents[2]
    cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)]
    proc = subprocess.Popen(cmd, cwd=root, env=os.environ.copy(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never route localhost via a proxy
    try:
        deadline = time.time() + 60
        while True:
            try:
                direct.open(f"{url}/health", timeout=2)
                break
            except OSError:
                if proc.poll() is not None:
                    pytest.fail("the app server stopped during start-up")
                if time.time() > deadline:
                    pytest.fail("the app server did not start")
                time.sleep(0.5)
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            exe = os.environ.get("GPHA_UI_BROWSER")
            b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - no browser installed on this machine
            pytest.skip(f"Chromium is not available: {exc}")
        yield b
        b.close()


class Watch:
    """Collects JavaScript errors and failed API calls on a page."""

    def __init__(self, page):
        self.errors: list[str] = []
        page.on("pageerror", lambda e: self.errors.append(f"JS error: {e}"))
        page.on("response", self._response)

    def _response(self, r):
        if r.status >= 400 and "/api/" in r.url and not any(x in r.url for x in IGNORED_HTTP):
            self.errors.append(f"HTTP {r.status} {r.request.method} {r.url}")

    def take(self) -> list[str]:
        out, self.errors = self.errors, []
        return out


def _signed_in(browser, base_url, width=1440, height=900):
    ctx = browser.new_context(viewport={"width": width, "height": height})
    page = ctx.new_page()
    watch = Watch(page)
    page.goto(base_url)
    page.fill("#loginUser", ADMIN[0])
    page.fill("#loginPass", ADMIN[1])
    page.keyboard.press("Enter")
    page.wait_for_selector("#appView:not(.hidden)", timeout=20000)
    page.wait_for_load_state("networkidle")
    return ctx, page, watch


def _wait_for(page, expression, timeout=5.0):
    # The app's Content Security Policy forbids eval, so poll with evaluate instead of wait_for_function.
    deadline = time.time() + timeout
    while not page.evaluate(f"() => {expression}"):
        if time.time() > deadline:
            raise AssertionError(f"timed out waiting for {expression}")
        page.wait_for_timeout(50)


def _shot(page, name):
    folder = os.environ.get("GPHA_UI_SHOTS")
    if folder:
        Path(folder).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(folder) / f"{name}.png"))


def _ensure_audit(page) -> int:
    return page.evaluate("""async () => {
        const reg = await API.get('/api/audits/register?page_size=1');
        if (reg.items.length) return reg.items[0].id;
        const a = await API.post('/api/audits', {title: 'UI test - revenue assurance', scope: 'Q3 tolls'});
        return a.id;
    }""")


def test_every_screen_opens_without_errors(browser, base_url):
    ctx, page, watch = _signed_in(browser, base_url)
    views = page.evaluate("[...new Set([...document.querySelectorAll('#sidebarNav button[data-view]')]"
                          ".filter(b => !b.classList.contains('hidden')).map(b => b.dataset.view)"
                          ".concat(HOST_GROUPS.flatMap(g => hostTabsAllowed(g).map(t => t[0]))))]")
    sidebar = page.evaluate("document.querySelectorAll('#sidebarNav button[data-view]:not(.hidden)').length")
    assert sidebar <= 30 and len(views) >= 40, (sidebar, views)
    problems = {}
    for view in views:
        page.evaluate(f"navigate('{view}')")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(150)
        errs = watch.take()
        heading = page.evaluate("(document.querySelector('#viewRoot h1, #viewRoot h2') || {}).innerText || ''")
        if errs or not heading.strip():
            problems[view] = errs or ["no page heading"]
        _shot(page, f"desktop-{view}")
    ctx.close()
    assert not problems, problems


def test_shell_breadcrumbs_groups_and_scope(browser, base_url):
    ctx, page, watch = _signed_in(browser, base_url)
    page.evaluate("navigate('audits')")
    page.wait_for_load_state("networkidle")
    assert page.inner_text("#crumbs") .replace("\n", " ").strip().startswith("Audit management")
    assert page.get_attribute('#sidebarNav button[data-view="audits"]', "aria-current") == "page"
    # Groups collapse and expand, and the state survives a reload.
    head = page.locator('.nav-group[data-group="risk"] .nav-group-head')
    head.click()
    assert page.get_attribute('.nav-group[data-group="risk"] .nav-group-head', "aria-expanded") == "false"
    page.reload()
    page.wait_for_selector("#appView:not(.hidden)")
    assert "collapsed" in (page.get_attribute('.nav-group[data-group="risk"]', "class") or "")
    page.locator('.nav-group[data-group="risk"] .nav-group-head').click()
    # Scope chip opens a panel that Escape closes.
    page.click("#scopeChip")
    assert page.is_visible("#scopePanel")
    page.keyboard.press("Escape")
    assert not page.is_visible("#scopePanel")
    assert not watch.take()
    ctx.close()


def test_register_search_sort_columns_and_paging(browser, base_url):
    ctx, page, watch = _signed_in(browser, base_url)
    for i in range(3):
        page.evaluate(f"API.post('/api/audits', {{title: 'Register paging check {i}', scope: 'x'}})")
    page.evaluate("navigate('audits')")
    page.wait_for_selector(".register table")
    total = page.evaluate("API.get('/api/audits/register?page_size=1').then(r => r.total)")
    assert f"{total} records" in page.inner_text(".fb-count")
    # Search runs on the server; no match shows the filtered empty state.
    page.fill(".fb-search", "zzz-no-such-audit")
    page.wait_for_selector(".state-empty")
    assert "No records match" in page.inner_text(".register")
    page.click(".filter-bar .link-btn")  # Clear
    page.wait_for_selector(".register table")
    # Sorting by Ref toggles aria-sort.
    page.click("th:has-text('Ref') button")
    page.wait_for_selector("th[aria-sort=ascending]")
    page.click("th:has-text('Ref') button")
    page.wait_for_selector("th[aria-sort=descending]")
    # Column chooser hides a column (remembered per device).
    page.click("text=Columns")
    page.locator(".side-panel label.check", has_text="Stream").locator("input").uncheck()
    page.keyboard.press("Escape")
    assert page.locator("th", has_text="Stream").count() == 0
    # Paging: 1 row per page through the page-size control is not offered, so use 10 and check the footer.
    page.select_option(".table-foot select", "10")
    page.wait_for_selector(".table-foot")
    assert "of" in page.inner_text(".table-foot")
    assert not watch.take()
    ctx.close()


def test_record_page_tabs_sit_under_the_title(browser, base_url):
    ctx, page, watch = _signed_in(browser, base_url)
    audit_id = _ensure_audit(page)
    page.evaluate(f"openAudit({audit_id})")
    page.wait_for_selector(".rec-tabs [role=tab].active")
    box = page.locator(".rec-tabs").bounding_box()
    assert box["y"] < 220, box  # tabs are visible without scrolling
    assert page.inner_text(".rec-tabs [role=tab].active") == "Dashboard"
    side_titles = page.locator(".rec-side .card h3").all_inner_texts()
    assert "Engagement" in side_titles and "Engagement team" in side_titles
    assert "Audits" in page.inner_text("#crumbs")
    # Keyboard: arrow right moves to the next tab.
    page.focus(".rec-tabs [role=tab].active")
    page.keyboard.press("ArrowRight")
    page.wait_for_load_state("networkidle")
    assert page.inner_text(".rec-tabs [role=tab].active") != "Dashboard"
    _shot(page, "desktop-audit-record")
    assert not watch.take()
    ctx.close()


def test_shared_components(browser, base_url):
    ctx, page, watch = _signed_in(browser, base_url)
    # Confirm dialog: a reason is required, Cancel resolves ok=false.
    page.evaluate("() => { window._c = null; "
                  "confirmDialog({title: 'Withdraw', reason: true}).then(r => { window._c = r; }); }")
    page.click(".modal .btn:not(.secondary)")
    assert "at least 10 characters" in page.inner_text(".modal")
    page.fill(".modal textarea", "No longer needed for this plan")
    page.click(".modal .btn:not(.secondary)")
    _wait_for(page, "window._c !== null")
    assert page.evaluate("window._c") == {"ok": True, "reason": "No longer needed for this plan"}
    page.evaluate("() => { window._c = null; confirmDialog({title: 'Sure?'}).then(r => { window._c = r; }); }")
    page.click(".modal .btn.secondary")
    _wait_for(page, "window._c !== null")
    assert page.evaluate("window._c") == {"ok": False}
    # Side panel closes with Escape.
    page.evaluate("detailPanel({title: 'Details', body: el('p', null, 'Body text')})")
    assert page.is_visible(".side-panel")
    page.keyboard.press("Escape")
    assert page.locator(".side-panel").count() == 0
    # States and the save indicator render text, not only colour.
    texts = page.evaluate("""() => {
        const s = saveState(); s.set('saved');
        return [emptyState({title: 'Nothing'}).innerText, errorState({message: 'Boom', status: 500}).innerText,
                errorState({message: 'No', status: 403}).innerText, s.node.innerText,
                activityTimeline([{at: '2026-10-15T10:00:00', who: 'Ama', text: 'Signed off'}]).innerText];
    }""")
    assert "Nothing" in texts[0] and "Boom" in texts[1] and "do not have access" in texts[2]
    assert "Saved" in texts[3] and "Signed off" in texts[4]
    assert not watch.take()
    ctx.close()


def test_form_panel_stays_open_and_survives_refresh(browser, base_url):
    """Creators open in a right-hand panel: no outside-click/Esc close, reopen after refresh, stay open after save."""
    ctx, page, watch = _signed_in(browser, base_url)
    tag = str(int(time.time() * 1000))[-7:]
    page.evaluate("navigate('users')")
    page.click("button:has-text('Add user')")
    page.wait_for_selector(".form-panel")
    page.fill(".form-panel input[name=full_name]", f"Panel User {tag}")
    page.mouse.click(400, 500)
    page.keyboard.press("Escape")
    assert page.is_visible(".form-panel")
    assert page.evaluate("document.body.classList.contains('has-form-panel')")
    page.wait_for_timeout(300)
    page.reload()
    page.wait_for_selector(".form-panel", timeout=15000)
    _wait_for(page, f"document.querySelector('.form-panel input[name=full_name]').value === 'Panel User {tag}'")
    page.fill(".form-panel input[name=username]", f"panel{tag}")
    page.fill(".form-panel input[name=email]", f"panel{tag}@example.com")
    page.fill(".form-panel input[type=password]", "Panel-Pass-2026")
    page.click(".form-panel .actions .btn:not(.secondary)")
    page.wait_for_selector(".form-panel .form-banner.ok")
    assert "Saved" in page.inner_text(".form-panel .form-banner")
    assert page.is_disabled(".form-panel input[name=full_name]")
    page.click(".form-panel .modal-close")
    assert page.locator(".form-panel").count() == 0
    page.reload()
    page.wait_for_load_state("networkidle")
    assert page.locator(".form-panel").count() == 0
    assert not watch.take()
    ctx.close()


@pytest.mark.parametrize("width,label", [(768, "tablet"), (375, "phone")])
def test_small_screens(browser, base_url, width, label):
    ctx, page, watch = _signed_in(browser, base_url, width=width, height=900)
    page.evaluate("navigate('audits')")
    page.wait_for_selector(".register")
    assert page.is_visible("#navToggle")
    assert not page.locator("#sidebar").is_visible() or page.locator("#sidebar").bounding_box()["x"] < 0
    page.click("#navToggle")
    page.wait_for_timeout(300)
    assert page.locator("#sidebar").bounding_box()["x"] >= 0
    page.evaluate("document.body.classList.remove('nav-open')")
    no_hscroll = page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    assert no_hscroll, "page scrolls sideways"
    _shot(page, f"{label}-audits")
    assert not watch.take()
    ctx.close()


def test_workplan_execute_and_issue_tracker(browser, base_url):
    """HighBond Workplan screens: project plan, execute procedures in the side panel, Issue Tracker donuts."""
    ctx, page, watch = _signed_in(browser, base_url)
    audit_id = page.evaluate("""async () => {
        const a = await API.post('/api/audits', {title: 'UI test - workplan', scope: 'x', workflow: 'Workplan'});
        const o = await API.post(`/api/audits/${a.id}/objectives`, {title: 'Revenue is banked'});
        const r = await API.post(`/api/objectives/${o.id}/risks`, {title: 'Cash not banked', likelihood: 4, impact: 5});
        await API.post(`/api/objectives/${o.id}/procedures`, {title: 'Vouch takings to bank', risk_ids: [r.id]});
        await API.post(`/api/audits/${a.id}/findings`, {title: 'Takings banked late', risk_rating: 'High'});
        return a.id;
    }""")
    page.evaluate(f"state.fwSub = {{{audit_id}: 'plan'}}; openAudit({audit_id}, 'fieldwork')")
    page.wait_for_selector(".plan-matrix")
    assert page.inner_text(".subnav-item.active") == "Project plan"
    assert "Vouch takings to bank" in page.inner_text(".plan-matrix")
    assert page.locator(".rec-side").is_hidden()  # work screens use the full width
    page.click(".subnav-item:has-text('Execute procedures')")
    page.wait_for_selector("table.dense tbody tr")
    page.click("table.dense tbody tr")
    page.wait_for_selector(".side-panel")
    page.fill(".side-panel textarea", "2 of 25 days banked late")
    page.check(".side-panel input[value='Issue(s) noted']")
    page.click(".side-panel button:has-text('Save and sign-off')")
    page.wait_for_selector(".side-panel", state="detached")
    _wait_for(page, "document.querySelector('table.dense tbody') && "
                    "document.querySelector('table.dense tbody').innerText.includes('Prepared')")
    _shot(page, "desktop-execute-procedures")
    page.evaluate("navigate('issues')")
    page.wait_for_selector(".chart-row .chart-card")
    page.wait_for_selector(".register thead th")
    captions = page.locator(".chart-card figcaption").all_inner_texts()
    assert "By Issue Type" in captions and "By Severity" in captions
    headers = page.locator(".register thead th").all_inner_texts()
    for col in ("Issue", "Status", "Severity", "Owner", "Remediation deadline", "Issue type", "Published", "Sign-offs"):
        assert any(h.strip().startswith(col) for h in headers), (col, headers)
    _shot(page, "desktop-issue-tracker")
    assert not watch.take()
    ctx.close()


def test_org_structure_define_universe_and_risk_assessment(browser, base_url):
    """Org Structure -> Audit universe (units, processes, new entity) -> Audit risk assessment settings."""
    ctx, page, watch = _signed_in(browser, base_url)
    ids = page.evaluate("""async () => {
        const tag = Math.random().toString(36).slice(2, 7);
        const port = await API.post('/api/organizations', {name: `UI Port ${tag}`, category: 'Port'});
        const dept = await API.post('/api/organizations',
            {name: `UI Finance ${tag}`, category: 'Department', parent_id: port.id});
        const proc = await API.post('/api/processes', {name: `UI Revenue ${tag}`, org_ids: [dept.id]});
        return {port: port.id, dept: dept.id, proc: proc.id, tag};
    }""")
    page.evaluate("navigate('orgstructure')")
    page.wait_for_selector(".tree-table tbody tr")
    assert f"UI Finance {ids['tag']}" in page.inner_text(".tree-table")
    page.evaluate("navigate('universe')")
    page.wait_for_selector(".u-flow .u-step")
    assert page.locator(".host-tabs .tab").count() == 5
    page.evaluate("navigate('universe_units')")
    page.wait_for_selector(".u-table tbody tr")
    page.fill(".fb-search", f"UI Finance {ids['tag']}")
    _wait_for(page, "document.querySelectorAll('.u-table tbody tr').length === 1")
    page.locator(".u-table tbody tr input[type=checkbox]").check()
    page.click("button:has-text('Include selected')")
    _wait_for(page, "(document.querySelector('.u-table') || {innerText: ''}).innerText.includes('Included')")
    page.evaluate("navigate('universe_processes')")
    page.wait_for_selector(".u-table tbody tr")
    page.evaluate(f"openEntityForm(null, {{process_ids: [{ids['proc']}]}})")
    page.wait_for_selector(".u-form input[name=name]")
    page.fill(".u-form input[name=name]", f"UI entity {ids['tag']}")
    _wait_for(page, f"document.querySelector('.u-preview').innerText.includes('UI Finance {ids['tag']}')")
    _shot(page, "desktop-new-entity")
    page.click("button:has-text('Save entity')")
    page.wait_for_selector(".record .rec-title")
    assert f"UI entity {ids['tag']}" in page.inner_text(".rec-title")
    page.click(".tabs button:has-text('Assurance'), [role=tab]:has-text('Assurance')")
    page.wait_for_selector("h3:has-text('Assurance providers')")
    page.evaluate("navigate('universe_assurance')")
    page.wait_for_selector("h3:has-text('Providers')")
    assert f"UI entity {ids['tag']}" in page.inner_text(".u-table")
    _shot(page, "desktop-assurance-map")
    # Leave the rest of the suite's universe as it was: no Define here, only the scoring matrix of a fresh assessment.
    page.evaluate("navigate('riskassess')")
    page.wait_for_selector("#viewRoot h2")
    page.evaluate("renderRiskAssessments('settings')")
    page.wait_for_selector("input[name=araScale]")
    assert page.locator("input[name=araScale]").count() == 2  # Low- to High-risk, Very low- to Very high-risk
    assert "Assessment factors" in page.inner_text("#viewRoot")
    assert not watch.take()
    ctx.close()
