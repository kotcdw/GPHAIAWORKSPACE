// Interface walkthroughs in the app: the step tabs, Previous / Next, "Step n of N", click sequence and note of each
// walkthrough, in the order of the assurance cycle (plan -> projects -> reports -> dashboards & presentations -> issue
// follow-up -> strategy -> risk-based planning -> back to the plan). Each step opens the real screen with real
// records and highlights the control to use. Content: guide-data.js. Loaded after the screens it opens.

const WT = { key: null, step: 0, panel: null, cache: {} };
const WT_ORDER = ["admin", "plans", "projects", "reports", "dashboards", "issues", "strategy", "riskplanning"];
// Application frame name -> walkthrough shown by its title-bar "Walkthrough" link.
const WT_APPS = {
  "Assurance Plans": "plans", Audits: "projects", Projects: "projects", "Audit universe": "projects",
  Reports: "reports", "Report Builder": "reports", "AI Reporting": "reports",
  "Dashboard Builder": "dashboards", "Present Builder": "dashboards",
  "Activity Center": "issues", "Issue Tracker": "issues", Issues: "issues", Actions: "issues", "Risk Manager": "strategy",
  Administration: "admin", "Users & access": "admin", "Roles & permissions": "admin", Configuration: "admin", "Org Structure": "admin",
  Backups: "admin", "My profile": "admin", "Risk & Compliance": "strategy",
};

function wtModule(key) { return WALKTHROUGHS.find((m) => m.key === key); }

// First record of a kind the viewer can open (cached for the session of the guide).
async function wtFirst(kind) {
  if (WT.cache[kind] !== undefined) return WT.cache[kind];
  let v = null;
  if (kind === "plan" || kind === "draftPlan") {
    const ps = await safeGet("/api/assurance-plans", []);
    v = (kind === "draftPlan" ? ps.find((p) => p.status === "Draft") : ps.find((p) => p.status !== "Draft")) || ps[0] || null;
  } else if (kind === "audit" || kind === "icAudit") {
    // Projects in progress first: they carry fieldwork, tests and issues to show.
    const rank = { "In Progress": 0, Review: 1, Planned: 2 };
    const as = (await safeGet("/api/audits", [])).filter((a) => a.status !== "Closed").sort((a, b) => (rank[a.status] ?? 3) - (rank[b.status] ?? 3));
    v = (kind === "icAudit" ? as.find((a) => (a.workflow || "") === "Internal Control") : null) || as[0] || null;
  } else if (kind === "finding") {
    const r = await safeGet("/api/findings/register?page_size=1&sort=-updated_at", { items: [] });
    v = (r.items || [])[0] || null;
  } else if (kind === "risk") {
    const rs = await safeGet("/api/grc/risks", []);
    v = (Array.isArray(rs) ? rs : rs.items || [])[0] || null;
  } else if (kind === "capa") {
    const r = await safeGet("/api/capa?page_size=1", []);
    v = (Array.isArray(r) ? r : r.items || [])[0] || null;
  } else if (["report", "dashboard", "presentation"].includes(kind)) {
    const its = await safeGet(`/api/reporting/items?kind=${kind}`, []);
    v = its.find((i) => i.status === "Active" && i.can_edit) || its.find((i) => i.can_edit) || its[0] || null;
  }
  WT.cache[kind] = v;
  return v;
}

const wtWait = (ms = 350) => new Promise((r) => { setTimeout(r, ms); });

async function wtClick(label) {
  for (let i = 0; i < 20; i += 1) {
    const n = wtFind(label);
    if (n) { n.click(); await wtWait(); return true; }
    await wtWait(200);
  }
  return false;
}

// Each route opens the screen of one step. A route returns a short message when a record it needs does not exist.
const WT_ROUTES = {
  plans: async () => { navigate("plans"); },
  plansStart: async () => { navigate("plans"); await wtWait(400); await renderPlansGettingStarted(); },
  planCreate: async () => { planCreatePage(); },
  planOverviewNew: async () => { const p = await wtFirst("draftPlan"); if (!p) { navigate("plans"); return "Create a plan first (step 2)."; } state.lastPlanTab = { id: p.id, key: "overview" }; await openPlan(p.id); return null; },
  planOverview: async () => { const p = await wtFirst("plan"); if (!p) { navigate("plans"); return "Create a plan first (Assurance Plans step 2)."; } state.lastPlanTab = { id: p.id, key: "overview" }; await openPlan(p.id); return null; },
  planAdd: async () => { const p = await wtFirst("draftPlan"); if (!p) { navigate("plans"); return "Create a plan first."; } await addToPlan(await API.get(`/api/assurance-plans/${p.id}`)); return null; },
  newProject: async () => { const p = await wtFirst("draftPlan"); if (!p) { navigate("plans"); return "Create a plan first."; } await newProjectPage(await API.get(`/api/assurance-plans/${p.id}`)); return null; },
  newProjectObjectives: async () => {
    const msg = await WT_ROUTES.newProject();
    if (msg) return msg;
    const name = document.querySelector(".ws input[name=title]");
    if (name && !name.value) name.value = "Walkthrough project";
    await wtClick("Continue");
    return null;
  },
  planLink: async () => { const p = await wtFirst("draftPlan"); if (!p) { navigate("plans"); return "Create a plan first."; } await linkProjectsPage(await API.get(`/api/assurance-plans/${p.id}`), "link"); return null; },
  planCoverage: async () => { const p = await wtFirst("plan"); if (!p) { navigate("plans"); return "Create a plan first."; } state.lastPlanTab = { id: p.id, key: "coverage" }; await openPlan(p.id); return null; },
  planRisks: async () => { const p = await wtFirst("plan"); if (!p) { navigate("plans"); return "Create a plan first."; } state.lastPlanTab = { id: p.id, key: "risks" }; await openPlan(p.id); return null; },
  audits: async () => { navigate("audits"); },
  // Platform Settings & Administration
  admin: async () => { navigate("admin"); },
  organization: async () => { navigate("organization"); },
  orgstructure: async () => { navigate("orgstructure"); },
  usersAdd: async () => { navigate("users"); await wtWait(500); if (!hasPerm("system.users")) return "Adding users needs the Manage user accounts permission."; await newUserForm(); return null; },
  roles: async () => { navigate("roles"); },
  profile: async () => { navigate("profile"); },
  appsettings: async () => { navigate("appsettings"); },
  imports: async () => { navigate("imports"); },
  logs: async () => { navigate("logs"); },
  closeout: async () => { navigate("closeout"); },
  projectSettings: async () => { const a = await wtFirst("audit"); if (!a) { navigate("audits"); return "Open or create a project first."; } await openAudit(a.id, "settings"); return null; },
  objectiveList: async () => { const a = await wtFirst("audit"); if (!a) { navigate("audits"); return "Open or create a project first."; } goFieldwork(a.id, "objs"); return null; },
  narratives: async () => { const a = await wtFirst("icAudit"); if (!a) { navigate("audits"); return "Narratives need an Internal Control project."; } goFieldwork(a.id, "narr"); return null; },
  testing: async () => {
    const rank = { "In Progress": 0, Review: 1, Planned: 2 };
    const as = (await safeGet("/api/audits", [])).filter((x) => x.status !== "Closed" && (x.workflow || "") === "Internal Control")
      .sort((a, b) => (rank[a.status] ?? 3) - (rank[b.status] ?? 3)).slice(0, 12);
    if (!as.length) { navigate("audits"); return "Testing needs an Internal Control project."; }
    for (const a of as) {
      const rd = await safeGet(`/api/audits/${a.id}/testing/1`, { rows: [] });
      const row = rd.rows.find((r) => r.test);
      if (row) { goFieldwork(a.id, `testview:${row.test.id}`); return null; }
    }
    goFieldwork(as[0].id, "test");
    return "No test prepared yet: prepare the testing round first.";
  },
  requests: async () => { const a = await wtFirst("audit"); if (!a) { navigate("audits"); return "Open a project first."; } await openAudit(a.id, "evidence"); return null; },
  issuesPanel: async () => {
    const a = await wtFirst("audit");
    if (!a) { navigate("audits"); return "Open a project first."; }
    goFieldwork(a.id, "objs");
    await wtWait(1200);
    issuesSidePanel(await API.get(`/api/audits/${a.id}`), canWriteModule("audits"));
    return null;
  },
  signoffs: async () => {
    const a = await wtFirst("audit");
    if (!a) { navigate("audits"); return "Open a project first."; }
    const objs = await safeGet(`/api/audits/${a.id}/objective-list`, []);
    if (!objs.length) { goFieldwork(a.id, "objs"); return "Add an objective first."; }
    goFieldwork(a.id, `objview:${objs[0].id}`);
    await wtWait(1200);
    const so = document.querySelector(".obj-signoffs");
    if (so) so.scrollIntoView({ block: "center" });
    return null;
  },
  results: async () => { const a = await wtFirst("audit"); if (!a) { navigate("audits"); return "Open a project first."; } await openAudit(a.id, "report"); return null; },
  activity: async () => { navigate("activity"); },
  activityFollowUp: async () => { navigate("activity"); await wtWait(900); const t = document.querySelector(".ac-followup"); if (t) t.scrollIntoView({ block: "start" }); },
  issueTracker: async () => { state.issueTab = "list"; navigate("issues"); },
  issueRemediation: async () => { const f = await wtFirst("finding"); if (!f) { navigate("issues"); return "No issue yet: record one in a project first."; } await openIssue(f.id, "remediation"); return null; },
  issueActions: async () => { const msg = await WT_ROUTES.issueRemediation(); if (msg) return msg; await wtClick("Add"); return null; },
  issueRetest: async () => { const f = await wtFirst("finding"); if (!f) { navigate("issues"); return "No issue yet."; } await openIssue(f.id, "retest"); return null; },
  issueSignoff: async () => { const f = await wtFirst("finding"); if (!f) { navigate("issues"); return "No issue yet."; } await openIssue(f.id, "verify"); return null; },
  actionFollowUp: async () => { const c = await wtFirst("capa"); if (!c) { navigate("capa"); return "No action yet: add one on an issue (step 4)."; } state.recordTab = { key: "capa", id: c.id, tab: "followup" }; await openRecord("capa", c.id); return null; },
  riskProfile: async () => { await renderRiskManager("register"); },
  riskLibrary: async () => { await renderRiskManager("library"); },
  heatmaps: async () => { await renderRiskManager("heat"); },
  planningFeedback: async () => { await renderRiskManager("planning"); },
  riskDetails: async () => WT_ROUTES.riskTab("details"),
  riskAssessment: async () => WT_ROUTES.riskTab("assessment"),
  riskTreatment: async () => WT_ROUTES.riskTab("treatment"),
  riskMetrics: async () => WT_ROUTES.riskTab("metrics"),
  riskAssurance: async () => WT_ROUTES.riskTab("assurance"),
  riskTab: async (tab) => { const r = await wtFirst("risk"); if (!r) { await renderRiskManager("register"); return "Add a risk first (+ Add or Risk Library)."; } await openRisk(r.id, tab); return null; },
  reportsBrowse: async () => { await renderReportsApp("browse"); },
  reportsTemplates: async () => { await renderBrowse({ key: "templates", label: "Templates" }); },
  builderReport: async () => { await reportBuilder(null, "report"); },
  builderData: async () => WT_ROUTES.builder("data"),
  builderCharts: async () => WT_ROUTES.builder("charts"),
  builderDesign: async () => WT_ROUTES.builder("design"),
  builderPublish: async () => WT_ROUTES.builder("publish"),
  builder: async (page) => {
    const r = await wtFirst("report");
    if (r && r.can_edit) { await reportBuilder(r, page); return null; }
    const vs = await repViews();
    await reportBuilder(vs.length ? { kind: "report", name: "", description: "", folder: "My Reports", access: "Private", user_ids: [], group_ids: [], definition: { view: vs[0].key, columns: [], filters: [] } } : null, page);
    return null;
  },
  reportView: async () => { const r = await wtFirst("report"); if (!r) { await renderReportsApp("browse"); return "Save and activate a report first (step 7)."; } await openReportItem(r.id); return null; },
  aiNew: async () => { await renderAiReporting("new"); },
  dashCreate: async () => { createBoardPage("dashboard"); },
  dashReports: async () => WT_ROUTES.board("dashboard", { panel: "reports" }),
  dashFilters: async () => WT_ROUTES.board("dashboard", { panel: "filters" }),
  dashPreview: async () => WT_ROUTES.board("dashboard", { panel: "properties", preview: true }),
  dashPublish: async () => WT_ROUTES.board("dashboard", { publish: true }),
  presentCreate: async () => { createBoardPage("presentation"); },
  presentSlides: async () => WT_ROUTES.board("presentation", { panel: "slides" }),
  presentPublish: async () => WT_ROUTES.board("presentation", { publish: true }),
  board: async (kind, opts) => {
    const it = await wtFirst(kind);
    if (!it || !it.can_edit) { createBoardPage(kind); return `Create a ${kind === "dashboard" ? "dashboard" : "presentation"} first.`; }
    await boardBuilder(await API.get(`/api/reporting/items/${it.id}`), opts);
    return null;
  },
};

function wtNorm(s) { return String(s || "").replace(/[▾›→…]/g, " ").replace(/\s+/g, " ").trim().toLowerCase(); }

// The control a step points at: a button, side page, choice card, select or field with that label.
function wtFind(label) {
  if (!label) return null;
  const want = wtNorm(label);
  const root = viewRoot;
  const nodes = [...root.querySelectorAll("button, a, select, [role=tab], .ws-choice, input[type=search]")].filter((n) => n.offsetParent !== null);
  const text = (n) => wtNorm(n.getAttribute("aria-label") || n.textContent || n.getAttribute("placeholder"));
  return nodes.find((n) => text(n) === want) || nodes.find((n) => text(n).startsWith(want)) || nodes.find((n) => text(n).includes(want)) || null;
}

function wtHighlight(label) {
  document.querySelectorAll(".wt-focus").forEach((n) => n.classList.remove("wt-focus"));
  const n = wtFind(label);
  if (!n) return false;
  n.classList.add("wt-focus");
  n.scrollIntoView({ block: "center", behavior: "smooth" });
  return true;
}

// Close side panels, form panels and dialogs a previous step opened, so the next screen is visible.
function wtCloseOverlays() {
  document.querySelectorAll(".side-panel-wrap, .modal-backdrop").forEach((n) => n.remove());
  document.querySelectorAll(".form-panel").forEach((n) => { const c = n.querySelector(".modal-close, [aria-label=Close]"); if (c) c.click(); else n.remove(); });
}

function openWalkthrough(key = WT.key || "plans", step = 0) {
  WT.key = key;
  WT.step = step;
  WT.cache = {};
  wtPaint(true);
}

function closeWalkthrough() {
  if (WT.panel) WT.panel.remove();
  WT.panel = null;
  document.body.classList.remove("wt-open");
  document.querySelectorAll(".wt-focus").forEach((n) => n.classList.remove("wt-focus"));
}

async function wtPaint(go) {
  const m = wtModule(WT.key);
  if (!m) return;
  const s = m.steps[WT.step];
  if (!WT.panel) {
    WT.panel = el("aside", { class: "wt-panel", role: "complementary", "aria-label": "Interface walkthrough" });
    document.body.append(WT.panel);
    document.body.classList.add("wt-open");
  }
  const p = WT.panel;
  const status = el("div", { class: "wt-status", "aria-live": "polite" });
  const idx = WT_ORDER.indexOf(m.key);
  const nextKey = WT_ORDER[(idx + 1) % WT_ORDER.length];
  const pick = el("select", { class: "ws-input compact", "aria-label": "Walkthrough module" },
    ...WT_ORDER.map((k, i) => el("option", { value: k, selected: k === m.key ? "1" : null }, `${i + 1}. ${wtModule(k).title}`)));
  pick.addEventListener("change", () => openWalkthrough(pick.value, 0));
  const tabs = el("div", { class: "wt-tabs", role: "tablist", "aria-label": `${m.title} steps` },
    ...m.steps.map((x, i) => el("button", { type: "button", role: "tab", class: i === WT.step ? "on" : "", "aria-selected": i === WT.step ? "true" : "false",
      onclick: () => { WT.step = i; wtPaint(true); } }, x.tab)));
  const last = WT.step === m.steps.length - 1;
  p.replaceChildren(
    el("div", { class: "wt-head" }, el("b", null, "Walkthrough"), pick,
      el("button", { type: "button", class: "wt-close", "aria-label": p.classList.contains("min") ? "Expand walkthrough" : "Minimise walkthrough",
        onclick: () => { p.classList.toggle("min"); } }, el("i", { class: `bi bi-${p.classList.contains("min") ? "chevron-up" : "dash-lg"}`, "aria-hidden": "true" })),
      el("button", { type: "button", class: "wt-close", "aria-label": "Close walkthrough", onclick: closeWalkthrough }, el("i", { class: "bi bi-x-lg", "aria-hidden": "true" }))),
    tabs,
    el("div", { class: "wt-step" },
      el("h3", null, s.title),
      el("strong", null, "Click sequence"),
      el("ol", null, ...s.how.map((h) => el("li", null, h))),
      s.note ? el("div", { class: "ws-note" }, s.note) : null,
      status,
      s.focus ? el("button", { type: "button", class: "ws-action", onclick: () => { if (!wtHighlight(s.focus)) status.textContent = `"${s.focus}" is not on this screen for you.`; } }, "Show me") : null),
    el("div", { class: "wt-controls" },
      el("button", { type: "button", class: "ws-action", disabled: WT.step === 0 ? "1" : null, onclick: () => { WT.step -= 1; wtPaint(true); } }, "Previous"),
      el("span", { class: "ws-caption" }, `Step ${WT.step + 1} of ${m.steps.length}`),
      last ? el("button", { type: "button", class: "ws-action primary", onclick: () => openWalkthrough(nextKey, 0) }, `Next module: ${wtModule(nextKey).title}`)
        : el("button", { type: "button", class: "ws-action primary", onclick: () => { WT.step += 1; wtPaint(true); } }, "Next")));
  const tab = tabs.children[WT.step];
  if (tab) tab.scrollIntoView({ block: "nearest", inline: "center" });
  if (!go) return;
  status.textContent = "Opening the screen…";
  wtCloseOverlays();
  let msg = null;
  try { msg = await (WT_ROUTES[s.route] || (async () => null))(); } catch (err) { msg = err.message; }
  status.textContent = msg || "";
  if (s.focus) {
    for (let i = 0; i < 15 && !wtHighlight(s.focus); i += 1) await wtWait(250);
  }
}
