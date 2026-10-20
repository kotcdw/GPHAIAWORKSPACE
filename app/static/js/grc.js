// Risk & compliance apps: Risk Manager & Strategy, Compliance Maps, Policy Manager, Asset Inventory.
// Loaded after resources.js and before app.js. Uses el/modal/openForm/dataTable/badge helpers.

const GRC = { people: null, entities: null };

async function grcPeople(fresh = false) {
  if (!GRC.people || fresh) GRC.people = await safeGet("/api/grc/people", { people: [], job_roles: [] });
  return GRC.people;
}
async function grcEntities() {
  if (!GRC.entities) GRC.entities = await safeGet("/api/organizations/entities", []);
  return GRC.entities;
}
function personOptions(p) { return p.people.map((u) => ({ value: u.id, label: `${u.name}${u.job_role ? ` · ${u.job_role}` : ""}` })); }
function entityOptions(list) { return list.map((o) => ({ value: o.id, label: o.port_name && o.port_name !== o.name ? `${o.name} (${o.port_name})` : o.name })); }
// Records opened from the Task Tracker return there; otherwise to their app's list.
function grcOpened(view) { setActiveNav(state.fromPortal ? "portal" : view); state.view = state.fromPortal ? "portal" : view; }
function grcBack(fallback) { return () => { if (state.fromPortal) { state.fromPortal = false; navigate("portal"); } else fallback(); }; }
function grcAfter(fallback) { if (state.fromPortal) { state.fromPortal = false; navigate("portal"); } else fallback(); }
function numOrNull(v) { return v === "" || v === null || v === undefined ? null : Number(v); }
function dateOnly(v) { return v ? String(v).slice(0, 10) : "-"; }
function ragBadge(v) { return el("span", { class: `badge badge-rag-${String(v).toLowerCase().replace(/\s+/g, "-")}` }, v); }
function levelChip(level, score) { return el("span", { class: `badge badge-${String(level).toLowerCase()}` }, `${level}${score !== undefined ? ` · ${score}` : ""}`); }
const SCORE_OPTS = [1, 2, 3, 4, 5].map((n) => ({ value: n, label: String(n) }));

// Links panel shared by every GRC record: chips grouped by type, add / remove when allowed.
const LINK_LABEL = { risk: "Risks", control: "Controls", requirement: "Requirements", policy: "Policies", asset: "Assets", unit: "Audit universe", objective: "Objectives" };
function linksCard(kind, id, items, types, canEdit, refresh) {
  const body = el("div");
  types.forEach((t) => {
    const mine = items.filter((x) => x.type === t);
    body.append(el("div", { class: "lnk-row" }, el("span", { class: "muted small lnk-type" }, LINK_LABEL[t] || t),
      el("div", { class: "chips" }, ...(mine.length ? mine.map((x) => el("span", { class: "chip" }, el("span", { class: "ref" }, x.ref), ` ${x.title}`,
        canEdit ? el("button", { class: "chip-x", title: "Remove link", "aria-label": `Remove ${x.ref}`, onclick: async () => {
          try { await API.del(`/api/grc/links/${x.link_id}`); toast("Link removed"); refresh(); } catch (err) { toast(err.message, "error"); }
        } }, "×") : null)) : [el("span", { class: "muted small" }, "None")]),
      canEdit ? el("button", { class: "btn tiny secondary", onclick: () => linkPickerDialog(kind, id, t, refresh) }, el("i", { class: "bi bi-plus" }), " Link") : null)));
  });
  return panel("Linked records", body);
}

function linkPickerDialog(kind, id, other, refresh) {
  const search = el("input", { type: "search", placeholder: `Search ${LINK_LABEL[other] || other}`, "aria-label": "Search" });
  const list = el("div", { class: "pick-list" });
  async function load() {
    clear(list);
    const rows = await safeGet(`/api/grc/lookup/${other}?q=${encodeURIComponent(search.value.trim())}`, []);
    if (!rows.length) { list.append(el("div", { class: "muted small" }, "Nothing found.")); return; }
    rows.forEach((r) => list.append(el("button", { class: "pick-item", type: "button", onclick: async () => {
      try { await API.post("/api/grc/links", { from_type: kind, from_id: id, to_type: other, to_id: r.id }); toast(`${r.ref} linked`); m.close(); refresh(); } catch (err) { toast(err.message, "error"); }
    } }, el("span", { class: "ref" }, r.ref), el("span", null, r.title), r.extra ? el("span", { class: "muted small" }, r.extra) : null)));
  }
  search.addEventListener("input", () => { clearTimeout(search._t); search._t = setTimeout(load, 250); });
  const m = modal({ drawer: true, title: `Link ${(LINK_LABEL[other] || other).toLowerCase()}`, width: 640, body: el("div", null, search, list),
    footer: el("div", { class: "form-foot-wrap" }, el("button", { class: "btn secondary", onclick: () => m.close() }, "Close")) });
  load();
  search.focus();
}

function heatGrid(grid, titles, label, onPick) {
  const g = el("div", { class: "heatmap", role: "group", "aria-label": label });
  for (let im = 5; im >= 1; im -= 1) {
    g.append(el("div", { class: "hm-axis", "aria-hidden": "true" }, String(im)));
    for (let lk = 1; lk <= 5; lk += 1) {
      const ids = grid[im - 1][lk - 1];
      const score = im * lk;
      const band = score >= (GRC.thr?.high || 15) ? "high" : score >= (GRC.thr?.medium || 8) ? "med" : "low";
      const tip = `Likelihood ${lk} × Impact ${im} = ${score} · ${ids.length} risk${ids.length === 1 ? "" : "s"}`;
      g.append(el("button", { class: `hm-cell hm-${band} ${ids.length ? "" : "empty"}`, type: "button", "aria-label": tip,
        title: ids.length ? `${tip}\n${ids.map((i) => titles[i]).join("\n")}` : tip, onclick: () => onPick(ids, tip) }, ids.length ? String(ids.length) : ""));
    }
  }
  g.append(el("div", { class: "hm-axis" }), ...[1, 2, 3, 4, 5].map((n) => el("div", { class: "hm-axis" }, String(n))));
  return el("div", null, el("div", { class: "hm-wrap" }, el("div", { class: "hm-ylabel" }, "Impact"), g), el("div", { class: "hm-xlabel" }, "Likelihood"));
}

// ==================================================================== Risk Manager & Strategy

// Overview: key figures, risk breakdown by category, inherent / residual heat map, my tasks, my unit, quick actions.
async function renderRiskOverview(body, reg) {
  state.riskOverview = state.riskOverview || { category: "", heat: "residual" };
  const v = state.riskOverview;
  body.append(loadingState());
  let d;
  try { d = await API.get(`/api/grc/risks/dashboard${v.category ? `?category=${encodeURIComponent(v.category)}` : ""}`); }
  catch (err) { clear(body); body.append(errorState(err)); return; }
  clear(body);
  GRC.thr = d.thresholds;
  const go = (filters) => renderRiskManager("register", { ...(v.category ? { category: v.category } : {}), ...filters });
  const cat = el("select", { class: "compact", "aria-label": "Risk category" }, el("option", { value: "" }, "All risk categories"),
    ...d.categories.map((c) => el("option", { value: c, selected: c === v.category ? "1" : null }, c)));
  cat.addEventListener("change", () => { v.category = cat.value; renderRiskManager("overview"); });
  const tile = (label, value, sub, onClick, tone = "") => el("button", { class: `kpi kpi-btn ${tone}`, type: "button", onclick: onClick },
    el("div", { class: "kpi-l" }, label), el("div", { class: "kpi-v" }, el("strong", null, String(value)), sub ? el("span", { class: "kpi-s" }, sub) : null));

  // Risk breakdown: residual level by category (stacked bars with a count axis).
  const cats = Object.entries(d.by_category).sort((a, b) => (b[1].High + b[1].Medium + b[1].Low) - (a[1].High + a[1].Medium + a[1].Low));
  const maxN = Math.max(1, ...cats.map(([, n]) => n.High + n.Medium + n.Low));
  const breakdown = el("div", { class: "card" }, el("h3", null, "Risk breakdown"),
    cats.length ? el("div", { class: "rb-chart", role: "img", "aria-label": `Residual risk by category: ${cats.map(([c, n]) => `${c} ${n.High} high, ${n.Medium} medium, ${n.Low} low`).join("; ")}` },
      ...cats.map(([c, n]) => el("button", { class: "rb-row", type: "button", title: `${c}: High ${n.High} · Medium ${n.Medium} · Low ${n.Low}`, onclick: () => go({ category: c }) },
        el("span", { class: "rb-l" }, c),
        el("span", { class: "rb-track" }, el("span", { class: "rb-bar", style: `width:${(100 * (n.High + n.Medium + n.Low)) / maxN}%` },
          ...["Low", "Medium", "High"].filter((k) => n[k]).map((k) => el("span", { class: `rb-seg r-${k === "Medium" ? "med" : k.toLowerCase()}`, style: `flex:${n[k]}` })))),
        el("span", { class: "rb-n" }, String(n.High + n.Medium + n.Low)))),
      el("div", { class: "rb-legend" }, ...[["High", "high"], ["Medium", "med"], ["Low", "low"]].map(([l, k]) => el("span", null, el("i", { class: `r-${k}` }), ` ${l}`))))
      : el("p", { class: "muted small" }, "No active risks yet."));

  const kind = el("select", { class: "compact", "aria-label": "Heat map" }, ...[["residual", "Residual"], ["inherent", "Inherent"]].map(([k, l]) => el("option", { value: k, selected: k === v.heat ? "1" : null }, l)));
  kind.addEventListener("change", () => { v.heat = kind.value; renderRiskManager("overview"); });
  const info = el("div", { class: "heat-info muted small", "aria-live": "polite" }, "Select a cell to list its risks.");
  const pick = (ids, tip) => { clear(info); info.append(el("div", null, tip), ...ids.map((i) => el("div", null, el("button", { class: "linkish", onclick: () => openRisk(i) }, d.titles[i])))); };
  const heat = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, "Risk heat map"), kind),
    heatGrid(v.heat === "inherent" ? d.inherent_grid : d.residual_grid, d.titles, `${v.heat} risk heat map`, pick), info);

  const num = (n, onClick, tone = "") => el("button", { class: `task-n ${tone} ${n ? "" : "zero"}`, type: "button", onclick: onClick, disabled: n ? null : "1" }, String(n));
  const my = el("div", { class: "card task-card" }, el("h4", null, "My risks and indicators"),
    el("div", { class: "task-grid" },
      el("div", null, el("div", { class: "muted small" }, "Risks I own"), num(d.my.owned, () => go({ mine: "true" }))),
      el("div", null, el("div", { class: "muted small" }, "Review due in 30 days"), num(d.my.review_due, () => go({ mine: "true" }))),
      el("div", null, el("div", { class: "muted small" }, "Review overdue"), num(d.my.overdue, () => go({ mine: "true", overdue: "true" }), "warn")),
      el("div", null, el("div", { class: "muted small" }, "Indicators to record"), num(d.my.kris_to_record, () => renderRiskManager("kris"), "warn")),
      el("div", null, el("div", { class: "muted small" }, "My indicator breaches"), num(d.my.kri_breaches, () => renderRiskManager("kris"), "danger"))));
  const group = d.group ? el("div", { class: "card task-card" }, el("h4", null, `My unit's risks${d.group.unit ? ` · ${d.group.unit}` : ""}`),
    el("div", { class: "task-grid" },
      el("div", null, el("div", { class: "muted small" }, "Open"), num(d.group.open, () => go({ my_unit: "true" }))),
      el("div", null, el("div", { class: "muted small" }, "No owner"), num(d.group.unassigned, () => go({ my_unit: "true", unassigned: "true" }), "warn")),
      el("div", null, el("div", { class: "muted small" }, "Review overdue"), num(d.group.overdue, () => go({ my_unit: "true", overdue: "true" }), "warn"))))
    : el("div", { class: "card task-card" }, el("h4", null, "My unit's risks"), el("p", { class: "muted small" }, "Set Where I work on your profile to see your unit's risks."));
  const quick = el("div", { class: "card" }, el("h4", null, "Quick actions"),
    el("div", { class: "quick-actions" },
      d.can_edit ? btn("+ New risk", () => riskForm(null, reg)) : null,
      d.can_edit ? btn("+ Strategic objective", () => strategicObjectiveForm(null), "secondary") : null,
      btn("Record indicator readings", () => renderRiskManager("kris"), "secondary"),
      btn("Risk register", () => renderRiskManager("register", {}), "secondary"),
      btn("Strategy map", () => renderRiskManager("strategy"), "secondary")));

  body.append(el("div", { class: "risk-home" },
    el("section", { class: "risk-main" },
      el("div", { class: "risk-main-head" }, el("h3", null, "Overview"), cat),
      el("div", { class: "kpi-row" },
        tile("Entities at highest risk", d.entities_high, d.entities.length ? ` · ${d.entities[0].name}` : "", () => go({ level: "High" }), d.entities_high ? "danger" : ""),
        tile("Above target", d.above_target, " residual over target", () => go({}), d.above_target ? "warn" : ""),
        tile("KRI breaches", d.kri_breaches, d.kri_amber ? ` · ${d.kri_amber} amber` : "", () => renderRiskManager("kris"), d.kri_breaches ? "danger" : "")),
      el("div", { class: "two-col-even" }, breakdown, heat)),
    el("aside", { class: "risk-side", "aria-label": "Tasks" }, el("div", { class: "risk-side-head" }, el("h3", null, "Tasks"),
      el("button", { class: "link-btn", type: "button", onclick: () => navigate("mywork") }, "View all tasks")), my, group, quick)));
}

async function renderRiskManager(tab = state.riskTab || "overview", filters = state.riskFilters || {}) {
  state.riskTab = tab; state.riskFilters = filters;
  clear(viewRoot);
  const msg = el("div");
  let reg; let sum;
  try {
    const qs = new URLSearchParams(Object.entries(filters).filter(([, v]) => v));
    [reg, sum] = await Promise.all([API.get(`/api/grc/risks?${qs}`), API.get("/api/grc/risks/summary")]);
  } catch (err) { viewRoot.append(viewHeader("Risk Manager"), msg); notify(msg, err.message, "error"); return; }
  GRC.thr = sum.thresholds;
  viewRoot.append(viewHeader("Risk Manager", reg.can_edit ? [
    el("button", { class: "btn small secondary", onclick: () => strategicObjectiveForm(null) }, el("i", { class: "bi bi-flag" }), " Objective"),
    el("button", { class: "btn small", onclick: () => riskForm(null, reg) }, el("i", { class: "bi bi-plus-lg" }), " Risk"),
  ] : null, { sub: `Welcome, ${state.user.full_name || state.user.username}. Enterprise risks, strategic objectives and key risk indicators; risk owners keep their assessments current.` }), msg);
  viewRoot.append(tabBar([{ key: "overview", label: "Overview" }, { key: "register", label: "Register" }, { key: "heat", label: "Heat maps" }, { key: "strategy", label: "Strategy" }, { key: "kris", label: "Indicators" }],
    tab, (k) => renderRiskManager(k, k === "register" ? filters : {})));
  const body = el("div");
  viewRoot.append(body);

  if (tab === "overview") { renderRiskOverview(body, reg); return; }

  if (tab === "register") {
    const sel = (name, label, opts) => {
      const s = el("select", { class: "compact", "aria-label": label }, el("option", { value: "" }, label), ...opts.map((o) => el("option", { value: o, selected: filters[name] === o ? "1" : null }, o)));
      s.addEventListener("change", () => renderRiskManager("register", { ...filters, [name]: s.value }));
      return s;
    };
    const q = el("input", { type: "search", class: "compact", placeholder: "Search risks", value: filters.q || "", "aria-label": "Search risks" });
    q.addEventListener("keydown", (e) => { if (e.key === "Enter") renderRiskManager("register", { ...filters, q: q.value.trim() }); });
    const quick = { mine: "Owned by me", overdue: "Review overdue", unassigned: "No owner", my_unit: "My unit" };
    const on = Object.keys(quick).filter((k) => filters[k]);
    if (on.length) body.append(el("div", { class: "filter-chips" }, el("span", { class: "muted small" }, "Showing:"),
      ...on.map((k) => el("span", { class: "chip" }, quick[k], el("button", { class: "chip-x", type: "button", "aria-label": `Remove ${quick[k]}`,
        onclick: () => { const f = { ...filters }; delete f[k]; renderRiskManager("register", f); } }, "×")))));
    body.append(el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, `Risks (${reg.items.length})`),
      el("div", { class: "actions" }, sel("category", "All categories", reg.categories), sel("level", "All levels", ["High", "Medium", "Low"]),
        sel("status", "All statuses", ["Draft", "Active", "Closed"]), q)),
    dataTable(reg.items, [
      { key: "ref", label: "Ref", render: (r) => el("span", { class: "ref" }, r.ref) },
      { key: "title", label: "Risk" }, { key: "category", label: "Category" }, { key: "owner", label: "Owner" },
      { key: "inherent_score", label: "Inherent", num: true, render: (r) => levelChip(r.inherent_level, r.inherent_score) },
      { key: "residual_score", label: "Residual", num: true, render: (r) => levelChip(r.residual_level, r.residual_score) },
      { key: "treatment", label: "Treatment" },
      { key: "next_review_date", label: "Next review", render: (r) => (r.review_overdue ? el("span", { class: "chip-mini warn" }, `Overdue ${dateOnly(r.next_review_date)}`) : dateOnly(r.next_review_date)) },
      { key: "status", label: "Status", render: (r) => badge(r.status) },
    ], { onRow: (r) => openRisk(r.id), pageSize: 25, exportName: "risk-register", emptyText: "No risks match." })));
  } else if (tab === "heat") {
    const info = el("div", { class: "heat-info muted small", "aria-live": "polite" }, "Select a cell to list its risks.");
    const pick = (ids, tip) => { clear(info); info.append(el("div", null, tip), ...ids.map((i) => el("div", null, el("button", { class: "linkish", onclick: () => openRisk(i) }, sum.titles[i])))); };
    body.append(el("div", { class: "two-cols" },
      panel("Inherent risk", heatGrid(sum.inherent_grid, sum.titles, "Inherent risk heat map", pick)),
      panel("Residual risk (after controls)", heatGrid(sum.residual_grid, sum.titles, "Residual risk heat map", pick))),
    el("div", { class: "card" }, info),
    panel("Residual risk by category", el("div", { class: "hbars" }, ...Object.entries(sum.by_category).map(([cat, n]) => {
      const total = n.High + n.Medium + n.Low;
      return el("div", { class: "grc-bar-row" }, el("span", { class: "small" }, cat),
        el("div", { class: "grc-stack", title: `High ${n.High} · Medium ${n.Medium} · Low ${n.Low}` },
          ...["High", "Medium", "Low"].filter((k) => n[k]).map((k) => el("span", { class: `grc-seg r-${k === "Medium" ? "med" : k.toLowerCase()}`, style: `flex:${n[k]}` }))),
        el("span", { class: "small muted" }, String(total)));
    }))));
  } else if (tab === "strategy") {
    const objs = await safeGet("/api/grc/objectives", []);
    if (!objs.length) body.append(el("div", { class: "card empty-state" }, el("i", { class: "bi bi-flag big-icon" }), el("h3", null, "No strategic objectives yet"),
      el("p", { class: "muted" }, "Record GPHA's strategic objectives, then link each enterprise risk to the objective it threatens.")));
    body.append(el("div", { class: "fw-grid" }, ...objs.map((o) => el("div", { class: `fw-card ${o.status === "Active" ? "" : "retired"}` },
      el("span", { class: "ref" }, o.ref), el("strong", null, o.title),
      el("span", { class: "muted small" }, [o.period, o.owner, o.entity].filter(Boolean).join(" · ") || "-"),
      el("span", { class: "small" }, `${o.risks} risk${o.risks === 1 ? "" : "s"}${o.high_risks ? ` · ${o.high_risks} high` : ""}`),
      el("div", { class: "inline-actions" },
        el("button", { class: "linkish small", onclick: () => renderRiskManager("register", { objective_id: o.id }) }, "Show risks"),
        reg.can_edit ? el("button", { class: "linkish small", onclick: () => strategicObjectiveForm(o) }, "Edit") : null)))));
  } else {
    const kris = await safeGet("/api/grc/kris", []);
    body.append(el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, `Key risk indicators (${kris.length})`)),
      dataTable(kris, [
        { key: "rag", label: "Status", render: (k) => ragBadge(k.rag) }, { key: "name", label: "Indicator" }, { key: "risk", label: "Risk" },
        { key: "latest", label: "Latest", render: (k) => (k.latest ? `${k.latest.value} ${k.unit} (${dateOnly(k.latest.period_date)})` : "-") },
        { key: "amber_at", label: "Amber / red", render: (k) => `${k.higher_is_worse ? "≥" : "≤"} ${k.amber_at} / ${k.red_at}` },
        { key: "frequency", label: "Frequency" }, { key: "owner", label: "Owner" },
      ], { onRow: (k) => openRisk(k.risk_id), exportName: "key-risk-indicators", emptyText: "No indicators yet. Add them on a risk." })));
  }
}

async function strategicObjectiveForm(o) {
  const [p, ents] = await Promise.all([grcPeople(), grcEntities()]);
  openForm({
    title: o ? `Edit ${o.ref}` : "New strategic objective", key: o ? `obj:${o.id}` : "obj:new", width: 720, draftable: !o,
    fields: [
      { name: "title", label: "Objective", required: true, maxLength: 255, singleLine: true, full: true },
      { name: "period", label: "Strategy period", maxLength: 40, singleLine: true, help: "e.g. 2026-2028" },
      { name: "status", label: "Status", type: "select", required: true, options: ["Active", "Achieved", "Retired"] },
      { name: "owner_id", label: "Owner", type: "select", options: personOptions(p) },
      { name: "entity_id", label: "Division / entity", type: "select", options: entityOptions(ents) },
      { name: "description", label: "Description and measures of success", type: "textarea", rows: 4, full: true },
    ],
    initial: o ? { ...o, owner_id: o.owner_id || "", entity_id: o.entity_id || "" } : { status: "Active" },
    submitLabel: o ? "Save" : "Create",
    onSubmit: (v) => { const b = { ...v, owner_id: numOrNull(v.owner_id), entity_id: numOrNull(v.entity_id), description: v.description || "", period: v.period || "" };
      return o ? API.put(`/api/grc/objectives/${o.id}`, b) : API.post("/api/grc/objectives", b); },
    onDone: () => { toast("Objective saved"); renderRiskManager("strategy"); },
  });
}

async function riskForm(r, reg) {
  const [p, ents, objs] = await Promise.all([grcPeople(), grcEntities(), safeGet("/api/grc/objectives", [])]);
  reg = reg || await API.get("/api/grc/risks?status=__none__");
  openForm({
    title: r ? `Edit ${r.ref}` : "New enterprise risk", key: r ? `erm:${r.id}` : "erm:new", width: 900, draftable: !r,
    fields: [
      { name: "title", label: "Risk (event)", required: true, maxLength: 255, singleLine: true, full: true, help: "What could happen, e.g. 'Quay crane failure halts container operations'" },
      { name: "category", label: "Category", type: "select", options: reg.categories, emptyLabel: "-" },
      { name: "objective_id", label: "Strategic objective", type: "select", options: objs.map((o) => ({ value: o.id, label: `${o.ref} ${o.title}` })) },
      { name: "owner_id", label: "Risk owner", type: "select", options: personOptions(p) },
      { name: "entity_id", label: "Division / entity", type: "select", options: entityOptions(ents) },
      { name: "cause", label: "Causes", type: "textarea", rows: 2 }, { name: "consequence", label: "Consequences", type: "textarea", rows: 2 },
      { type: "heading", label: "Scores (1 = lowest, 5 = highest)" },
      { name: "inherent_likelihood", label: "Inherent likelihood", type: "select", required: true, options: SCORE_OPTS },
      { name: "inherent_impact", label: "Inherent impact", type: "select", required: true, options: SCORE_OPTS },
      { name: "residual_likelihood", label: "Residual likelihood", type: "select", required: true, options: SCORE_OPTS },
      { name: "residual_impact", label: "Residual impact", type: "select", required: true, options: SCORE_OPTS },
      { name: "target_likelihood", label: "Target likelihood", type: "select", options: SCORE_OPTS },
      { name: "target_impact", label: "Target impact", type: "select", options: SCORE_OPTS },
      { type: "heading", label: "Response" },
      { name: "appetite", label: "Risk appetite", type: "select", options: reg.appetites, emptyLabel: "-" },
      { name: "treatment", label: "Treatment", type: "select", options: reg.treatments, emptyLabel: "-" },
      { name: "status", label: "Status", type: "select", required: true, options: ["Draft", "Active", "Closed"] },
      { name: "treatment_plan", label: "Treatment plan (actions, owners, dates)", type: "textarea", rows: 3, full: true },
      { name: "description", label: "Further description", type: "textarea", rows: 3, full: true },
    ],
    initial: r ? Object.fromEntries(Object.entries(r).map(([k, v]) => [k, v ?? ""])) : { status: "Active", inherent_likelihood: 3, inherent_impact: 3, residual_likelihood: 3, residual_impact: 3 },
    submitLabel: r ? "Save" : "Create",
    validate: (v) => (Number(v.residual_likelihood) * Number(v.residual_impact) > Number(v.inherent_likelihood) * Number(v.inherent_impact)
      ? { residual_impact: "Residual risk cannot be higher than inherent risk" } : null),
    onSubmit: (v) => {
      const b = { ...v };
      ["inherent_likelihood", "inherent_impact", "residual_likelihood", "residual_impact"].forEach((k) => { b[k] = Number(v[k]); });
      ["target_likelihood", "target_impact", "owner_id", "entity_id", "objective_id"].forEach((k) => { b[k] = numOrNull(v[k]); });
      ["category", "appetite", "treatment", "cause", "consequence", "treatment_plan", "description"].forEach((k) => { b[k] = v[k] || ""; });
      return r ? API.put(`/api/grc/risks/${r.id}`, b) : API.post("/api/grc/risks", b);
    },
    onDone: (rec) => { toast(`${rec.ref} saved`); openRisk(rec.id); },
  });
}

async function openRisk(id) {
  clear(viewRoot);
  let r;
  try { r = await API.get(`/api/grc/risks/${id}`); } catch (err) { toast(err.message, "error"); return; }
  grcOpened("risk");
  const back = grcBack(() => renderRiskManager());
  viewRoot.append(viewHeader(`${r.ref} · ${r.title}`, [
    r.can_assess && r.status !== "Closed" ? el("button", { class: "btn small", onclick: () => assessRiskForm(r) }, el("i", { class: "bi bi-speedometer2" }), " Assess") : null,
    r.can_edit ? el("button", { class: "btn small secondary", onclick: () => riskForm(r) }, el("i", { class: "bi bi-pencil" }), " Edit") : null,
  ].filter(Boolean), { back, meta: el("span", { class: "chips" }, badge(r.status), r.category ? el("span", { class: "chip static" }, r.category) : null,
    r.review_overdue ? el("span", { class: "chip-mini warn" }, "Review overdue") : null) }));
  const pos = (lk, im, label) => el("div", { class: "score-box" }, el("div", { class: "muted small" }, label),
    lk ? levelChip(GRC_band(lk * im), lk * im) : el("span", { class: "muted" }, "-"), lk ? el("div", { class: "muted small" }, `L${lk} × I${im}`) : null);
  viewRoot.append(el("div", { class: "two-cols" },
    panel("Risk", el("dl", { class: "kv" },
      el("dt", null, "Owner"), el("dd", null, r.owner || "-"), el("dt", null, "Objective"), el("dd", null, r.objective || "-"),
      el("dt", null, "Entity"), el("dd", null, r.entity || "-"), el("dt", null, "Causes"), el("dd", { class: "pre" }, r.cause || "-"),
      el("dt", null, "Consequences"), el("dd", { class: "pre" }, r.consequence || "-"), el("dt", null, "Appetite"), el("dd", null, r.appetite || "-"),
      el("dt", null, "Treatment"), el("dd", null, r.treatment || "-"), el("dt", null, "Treatment plan"), el("dd", { class: "pre" }, r.treatment_plan || "-"),
      el("dt", null, "Last assessed"), el("dd", null, fmtDate(r.last_assessed_at)), el("dt", null, "Next review"), el("dd", null, dateOnly(r.next_review_date)))),
    panel("Scores", el("div", null, el("div", { class: "score-row" }, pos(r.inherent_likelihood, r.inherent_impact, "Inherent"),
      el("i", { class: "bi bi-arrow-right muted" }), pos(r.residual_likelihood, r.residual_impact, "Residual"),
      el("i", { class: "bi bi-arrow-right muted" }), pos(r.target_likelihood, r.target_impact, "Target")),
    r.above_target ? el("div", { class: "callout warn" }, el("i", { class: "bi bi-exclamation-triangle" }), el("div", null, "Residual risk is above the target: the treatment plan needs to go further.")) : null,
    r.description ? longBlock("Description", r.description) : null))));

  // KRIs
  const kriBody = el("div");
  if (!r.kris.length) kriBody.append(el("p", { class: "muted small" }, "No indicators yet."));
  r.kris.forEach((k) => kriBody.append(el("div", { class: "kri-item" },
    el("div", { class: "kri-head" }, ragBadge(k.rag), el("strong", null, k.name),
      el("span", { class: "muted small" }, `Amber ${k.higher_is_worse ? "≥" : "≤"} ${k.amber_at} · Red ${k.higher_is_worse ? "≥" : "≤"} ${k.red_at} ${k.unit} · ${k.frequency}${k.owner ? ` · ${k.owner}` : ""}`),
      el("span", { class: "spacer" }),
      (r.can_assess || k.owner_id === state.user.id) ? el("button", { class: "btn tiny secondary", onclick: () => kriReadingForm(k, r.id) }, "Record reading") : null,
      r.can_edit ? el("button", { class: "btn tiny secondary", onclick: () => kriForm(r.id, k) }, "Edit") : null),
    k.readings.length ? el("div", { class: "kri-spark", "aria-label": `Readings of ${k.name}` }, ...[...k.readings].reverse().map((x) => el("span", { class: `kri-dot rag-${x.rag.toLowerCase()}`, title: `${dateOnly(x.period_date)}: ${x.value} ${k.unit}${x.comment ? ` · ${x.comment}` : ""}` }, String(x.value)))) : null)));
  viewRoot.append(panel("Key risk indicators", kriBody, r.can_edit ? el("button", { class: "btn small secondary", onclick: () => kriForm(r.id, null) }, el("i", { class: "bi bi-plus" }), " Indicator") : null));
  viewRoot.append(linksCard("risk", r.id, r.links, ["control", "requirement", "asset", "unit", "policy"], r.can_edit, () => openRisk(r.id)));
  viewRoot.append(panel("Assessment history", dataTable(r.assessments, [
    { key: "at", label: "When", render: (a) => fmtDate(a.at) }, { key: "by", label: "By" },
    { key: "inherent_score", label: "Inherent", num: true }, { key: "residual_score", label: "Residual", num: true },
    { key: "control_effectiveness", label: "Controls" }, { key: "comment", label: "Comment" },
  ], { pageSize: 10 })));
}

function GRC_band(score) { return score >= (GRC.thr?.high || 15) ? "High" : score >= (GRC.thr?.medium || 8) ? "Medium" : "Low"; }

function assessRiskForm(r) {
  openForm({
    title: `Assess ${r.ref}`, key: `ermassess:${r.id}`, width: 720,
    fields: [
      { name: "inherent_likelihood", label: "Inherent likelihood", type: "select", required: true, options: SCORE_OPTS },
      { name: "inherent_impact", label: "Inherent impact", type: "select", required: true, options: SCORE_OPTS },
      { name: "residual_likelihood", label: "Residual likelihood", type: "select", required: true, options: SCORE_OPTS },
      { name: "residual_impact", label: "Residual impact", type: "select", required: true, options: SCORE_OPTS },
      { name: "control_effectiveness", label: "How well are the controls working?", type: "select", options: ["Effective", "Partially effective", "Ineffective", "Not tested"], emptyLabel: "-" },
      { name: "comment", label: "What changed and why", type: "textarea", rows: 3, full: true },
    ],
    initial: r,
    submitLabel: "Record assessment",
    validate: (v) => (Number(v.residual_likelihood) * Number(v.residual_impact) > Number(v.inherent_likelihood) * Number(v.inherent_impact)
      ? { residual_impact: "Residual risk cannot be higher than inherent risk" } : null),
    onSubmit: (v) => API.post(`/api/grc/risks/${r.id}/assess`, { inherent_likelihood: Number(v.inherent_likelihood), inherent_impact: Number(v.inherent_impact),
      residual_likelihood: Number(v.residual_likelihood), residual_impact: Number(v.residual_impact), control_effectiveness: v.control_effectiveness || "", comment: v.comment || "" }),
    onDone: () => { toast("Assessment recorded"); openRisk(r.id); },
  });
}

async function kriForm(riskId, k) {
  const p = await grcPeople();
  openForm({
    title: k ? `Edit indicator` : "New key risk indicator", key: k ? `kri:${k.id}` : `kri:new:${riskId}`, width: 720, draftable: false,
    fields: [
      { name: "name", label: "Indicator", required: true, maxLength: 200, singleLine: true, full: true, help: "e.g. Crane downtime hours per month" },
      { name: "unit", label: "Unit", maxLength: 40, singleLine: true, help: "e.g. hours, %, incidents" },
      { name: "frequency", label: "Frequency", type: "select", required: true, options: ["Monthly", "Quarterly", "Half-yearly", "Annually"] },
      { name: "higher_is_worse", label: "A higher value is worse", type: "checkbox" },
      { name: "amber_at", label: "Amber threshold", type: "number", required: true, step: "any" },
      { name: "red_at", label: "Red threshold", type: "number", required: true, step: "any" },
      { name: "owner_id", label: "Who records it", type: "select", options: personOptions(p) },
      { name: "active", label: "Active", type: "checkbox" },
    ],
    initial: k ? { ...k, owner_id: k.owner_id || "" } : { frequency: "Monthly", higher_is_worse: true, active: true },
    submitLabel: k ? "Save" : "Add indicator",
    onSubmit: (v) => { const b = { ...v, unit: v.unit || "", owner_id: numOrNull(v.owner_id) };
      return k ? API.put(`/api/grc/kris/${k.id}`, b) : API.post(`/api/grc/risks/${riskId}/kris`, b); },
    onDone: () => { toast("Indicator saved"); openRisk(riskId); },
  });
}

function kriReadingForm(k, riskId, after = null) {
  openForm({
    title: `Reading: ${k.name}`, key: `kriread:${k.id}`, width: 560,
    fields: [
      { name: "period_date", label: "Period (date)", type: "date", required: true },
      { name: "value", label: `Value${k.unit ? ` (${k.unit})` : ""}`, type: "number", required: true, step: "any" },
      { name: "comment", label: "Comment", type: "textarea", rows: 2, full: true },
    ],
    initial: { period_date: new Date().toISOString().slice(0, 10) },
    submitLabel: "Record",
    onSubmit: (v) => API.post(`/api/grc/kris/${k.id}/readings`, { period_date: v.period_date, value: Number(v.value), comment: v.comment || "" }),
    onDone: (res) => { toast(res.rag === "Red" ? "Recorded: the indicator is RED" : "Reading recorded", res.rag === "Red" ? "error" : "ok"); if (after) after(); else openRisk(riskId); },
  });
}

// ==================================================================== Compliance Maps

async function renderComplianceMaps(tab = state.cmTab || "obligations") {
  state.cmTab = tab;
  clear(viewRoot);
  const msg = el("div");
  let data;
  try { data = await API.get("/api/grc/regulations?include_inactive=true"); } catch (err) { viewRoot.append(viewHeader("Compliance Maps"), msg); notify(msg, err.message, "error"); return; }
  const t = data.totals;
  viewRoot.append(viewHeader("Compliance Maps", data.can_edit ? [
    el("button", { class: "btn small", onclick: () => regulationForm(null, data.types) }, el("i", { class: "bi bi-plus-lg" }), " Obligation")] : null,
  { sub: "Laws, regulations, standards and contracts GPHA must meet, broken into requirements and mapped to the controls that meet them." }), msg);
  viewRoot.append(el("div", { class: "stats" }, stat(data.items.filter((i) => i.active).length, "Obligations"), stat(t.applicable, "Applicable requirements"),
    stat(t.applicable ? `${Math.round((100 * t.covered) / t.applicable)}%` : "-", "Covered by controls", `${t.applicable - t.covered} gap(s)`, t.applicable - t.covered ? "warn" : ""),
    stat(t.applicable ? `${Math.round((100 * t.compliant) / t.applicable)}%` : "-", "Assessed compliant"),
    stat(t.review_required, "Review required", "After a change in the obligation", t.review_required ? "warn" : "")));
  viewRoot.append(tabBar([{ key: "obligations", label: "Obligations" }, { key: "map", label: "Common controls & gaps" }], tab, renderComplianceMaps));
  if (tab === "obligations") {
    if (!data.items.length) { viewRoot.append(el("div", { class: "card empty-state" }, el("i", { class: "bi bi-journal-check big-icon" }), el("h3", null, "No obligations yet"), el("p", { class: "muted" }, "Add the Acts, L.I.s, directives, standards and contracts that apply to GPHA, e.g. PFM Act 2016 (Act 921), Internal Audit Agency Act 2003 (Act 658), Public Procurement Act."))); return; }
    viewRoot.append(el("div", { class: "fw-grid" }, ...data.items.map((g) => {
      const s = g.stats;
      return el("button", { type: "button", class: `fw-card ${g.active ? "" : "retired"}`, onclick: () => openRegulation(g.id) },
        el("span", { class: "ref" }, g.code), el("strong", null, g.title), el("span", { class: "muted small" }, [g.reg_type, g.version, g.issuer].filter(Boolean).join(" · ") || "-"),
        el("div", { class: "progress", title: `${s.covered} of ${s.applicable} applicable requirements covered by controls` }, el("div", { class: "progress-fill", style: `width:${s.coverage_pct || 0}%` })),
        el("span", { class: "small" }, `${s.requirements} requirement(s) · coverage ${s.coverage_pct ?? "-"}% · compliant ${s.compliant_pct ?? "-"}%`),
        s.review_required ? el("span", { class: "chip-mini warn" }, `${s.review_required} to review`) : null);
    })));
  } else {
    const map = await safeGet("/api/grc/compliance/map", { common_controls: [], gaps: [] });
    viewRoot.append(el("div", { class: "two-cols" },
      panel(`Coverage gaps (${map.gaps.length})`, dataTable(map.gaps, [
        { key: "regulation", label: "Obligation" }, { key: "ref", label: "Ref" }, { key: "title", label: "Requirement" }, { key: "owner", label: "Owner" },
      ], { onRow: (g) => openRegulation(g.regulation_id), pageSize: 15, exportName: "compliance-gaps", emptyText: "Every applicable requirement has at least one control." })),
      panel("Common controls (one control, many obligations)", dataTable(map.common_controls, [
        { key: "ref", label: "Control" }, { key: "title", label: "Title" }, { key: "requirements", label: "Requirements", num: true },
        { key: "obligations", label: "Obligations", render: (c) => c.obligations.join(", ") },
      ], { pageSize: 15, exportName: "common-controls", emptyText: "No controls mapped yet." }))));
  }
}

async function regulationForm(g, types) {
  const p = await grcPeople();
  openForm({
    title: g ? `Edit ${g.code}` : "New obligation", key: g ? `reg:${g.id}` : "reg:new", width: 760, draftable: !g,
    fields: [
      { name: "code", label: "Code", required: true, maxLength: 40, singleLine: true, help: "Short, e.g. ACT921, LI1994, PPA663" },
      { name: "reg_type", label: "Kind", type: "select", options: types, emptyLabel: "-" },
      { name: "title", label: "Title", required: true, maxLength: 255, singleLine: true, full: true },
      { name: "issuer", label: "Issued by", maxLength: 160, singleLine: true }, { name: "version", label: "Version / year", maxLength: 40, singleLine: true, help: g ? "Changing the version flags every requirement for review" : "" },
      { name: "effective_date", label: "Effective from", type: "date" }, { name: "owner_id", label: "Compliance owner", type: "select", options: personOptions(p) },
      { name: "url", label: "Link to the text", maxLength: 500, singleLine: true, full: true, placeholder: "https://" },
      { name: "active", label: "Active", type: "checkbox" },
      { name: "description", label: "Scope and notes", type: "textarea", rows: 3, full: true },
    ],
    initial: g ? { ...g, owner_id: g.owner_id || "", effective_date: g.effective_date || "" } : { active: true },
    submitLabel: g ? "Save" : "Create",
    onSubmit: (v) => { const b = { ...v, owner_id: numOrNull(v.owner_id), effective_date: v.effective_date || null, reg_type: v.reg_type || "", issuer: v.issuer || "", version: v.version || "", url: v.url || "", description: v.description || "" };
      return g ? API.put(`/api/grc/regulations/${g.id}`, b) : API.post("/api/grc/regulations", b); },
    onDone: (res) => { toast(res.flagged ? `Saved: ${res.flagged} requirement(s) flagged for review` : "Obligation saved"); openRegulation(res.id); },
  });
}

async function openRegulation(id) {
  clear(viewRoot);
  let g;
  try { g = await API.get(`/api/grc/regulations/${id}`); } catch (err) { toast(err.message, "error"); return; }
  grcOpened("compliance");
  const types = (await safeGet("/api/grc/regulations", { types: [] })).types;
  viewRoot.append(viewHeader(`${g.code} · ${g.title}`, g.can_edit ? [
    el("button", { class: "btn small secondary", onclick: () => regulationForm(g, types) }, el("i", { class: "bi bi-pencil" }), " Edit"),
    el("button", { class: "btn small secondary", onclick: () => requirementImport(g) }, el("i", { class: "bi bi-upload" }), " Import CSV"),
    el("button", { class: "btn small", onclick: () => requirementForm(g, null) }, el("i", { class: "bi bi-plus-lg" }), " Requirement"),
  ] : null, { back: grcBack(() => renderComplianceMaps("obligations")), sub: [g.reg_type, g.version && `version ${g.version}`, g.issuer, g.owner && `owner ${g.owner}`].filter(Boolean).join(" · ") }));
  const s = g.stats;
  viewRoot.append(el("div", { class: "stats" }, stat(s.applicable, "Applicable"), stat(`${s.coverage_pct ?? "-"}%`, "Coverage", `${s.gaps} gap(s)`, s.gaps ? "warn" : ""),
    stat(s.by_status.Compliant, "Compliant"), stat(s.by_status["Partially compliant"] + s.by_status["Non-compliant"], "Partly / non-compliant", null, s.by_status["Non-compliant"] ? "danger" : ""),
    stat(s.review_required, "Review required", null, s.review_required ? "warn" : "")));
  if (g.url) viewRoot.append(el("p", { class: "small" }, el("a", { href: g.url, target: "_blank", rel: "noopener" }, el("i", { class: "bi bi-box-arrow-up-right" }), " Read the text")));
  viewRoot.append(el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, `Requirements (${g.requirements.length})`)),
    dataTable(g.requirements, [
      { key: "ref", label: "Ref", render: (r) => el("span", { class: "ref" }, r.ref) }, { key: "title", label: "Requirement" },
      { key: "controls", label: "Controls", render: (r) => (r.controls.length ? el("div", { class: "chips" }, ...r.controls.map((c) => el("span", { class: "chip static" }, c.ref))) : (r.status === "Not applicable" ? "-" : el("span", { class: "chip-mini warn" }, "Gap"))) },
      { key: "owner", label: "Owner" },
      { key: "status", label: "Status", render: (r) => el("span", { class: "chips" }, badge(r.status), r.review_required ? el("span", { class: "chip-mini warn" }, "Review") : null) },
      { key: "last_assessed_at", label: "Assessed", render: (r) => (r.last_assessed_at ? dateOnly(r.last_assessed_at) : "-") },
    ], { onRow: (r) => requirementView(g, r), pageSize: 25, exportName: `${g.code}-requirements`, emptyText: "No requirements yet. Add them one by one or import a CSV." })));
}

async function requirementForm(g, r) {
  const [p, ents] = await Promise.all([grcPeople(), grcEntities()]);
  const lib = await safeGet("/api/library/controls", { items: [] });
  openForm({
    title: r ? `Edit ${g.code} ${r.ref}` : `New requirement in ${g.code}`, key: r ? `req:${r.id}` : `req:new:${g.id}`, width: 860, draftable: !r,
    fields: [
      { name: "ref", label: "Section / clause", required: true, maxLength: 40, singleLine: true, help: "e.g. s.16(1), reg. 43(2)" },
      { name: "owner_id", label: "Owner", type: "select", options: personOptions(p) },
      { name: "title", label: "Requirement", required: true, maxLength: 255, singleLine: true, full: true },
      { name: "entity_id", label: "Division / entity", type: "select", options: entityOptions(ents) },
      { name: "applicable", label: "Applies to GPHA", type: "checkbox" },
      { name: "text", label: "Text of the requirement", type: "textarea", rows: 4, full: true },
      { name: "control_ids", label: "Controls that meet it (standard controls library)", type: "checklist", full: true,
        options: lib.items.map((c) => ({ value: c.id, label: `${c.framework_code} ${c.ref} · ${c.title}` })), emptyLabel: "No standard controls yet: add them under Frameworks & controls." },
    ],
    initial: r ? { ...r, owner_id: r.owner_id || "", entity_id: r.entity_id || "", applicable: r.status !== "Not applicable", control_ids: r.controls.map((c) => c.id) } : { applicable: true, control_ids: [] },
    submitLabel: r ? "Save" : "Add requirement",
    onSubmit: (v) => { const b = { ...v, owner_id: numOrNull(v.owner_id), entity_id: numOrNull(v.entity_id), text: v.text || "", control_ids: (v.control_ids || []).map(Number) };
      return r ? API.put(`/api/grc/requirements/${r.id}`, b) : API.post(`/api/grc/regulations/${g.id}/requirements`, b); },
    onDone: () => { toast("Requirement saved"); openRegulation(g.id); },
  });
}

function requirementView(g, r) {
  const canAssess = g.can_edit || r.owner_id === state.user.id;
  const m = modal({ title: `${g.code} ${r.ref}`, width: 760,
    body: el("div", null, el("h3", null, r.title),
      el("div", { class: "chips" }, badge(r.status), r.review_required ? el("span", { class: "chip-mini warn" }, "Review required: the obligation changed") : null),
      longBlock("Text", r.text, "-"),
      el("dl", { class: "kv" }, el("dt", null, "Owner"), el("dd", null, r.owner || "-"), el("dt", null, "Entity"), el("dd", null, r.entity || "-"),
        el("dt", null, "Controls"), el("dd", null, r.controls.length ? r.controls.map((c) => `${c.ref} ${c.title}`).join("; ") : "None (gap)"),
        el("dt", null, "Policies"), el("dd", null, r.policies.length ? r.policies.map((c) => `${c.ref} ${c.title}`).join("; ") : "-"),
        el("dt", null, "Last assessment"), el("dd", null, r.last_assessed_at ? `${dateOnly(r.last_assessed_at)} by ${r.assessed_by}` : "Never"),
        el("dt", null, "Comment"), el("dd", { class: "pre" }, r.assessment_comment || "-"))),
    footer: el("div", { class: "form-foot-wrap" },
      g.can_edit ? el("button", { class: "btn secondary danger-text", onclick: async () => {
        if (!confirm(`Delete requirement ${r.ref}?`)) return;
        try { await API.del(`/api/grc/requirements/${r.id}`); m.close(); toast("Requirement deleted"); openRegulation(g.id); } catch (err) { toast(err.message, "error"); }
      } }, "Delete") : null,
      el("span", { class: "spacer" }),
      g.can_edit ? el("button", { class: "btn secondary", onclick: () => { m.close(); requirementForm(g, r); } }, "Edit") : null,
      canAssess ? el("button", { class: "btn", onclick: () => { m.close(); assessRequirementForm(g, r); } }, "Assess compliance") : null) });
}

function assessRequirementForm(g, r) {
  openForm({
    title: `Assess ${g.code} ${r.ref}`, key: `reqassess:${r.id}`, width: 640,
    fields: [
      { name: "status", label: "Status", type: "select", required: true, options: ["Compliant", "Partially compliant", "Non-compliant", "Not applicable"] },
      { name: "comment", label: "Evidence and gaps", type: "textarea", rows: 4, full: true, help: "Required for partial or non-compliance" },
    ],
    initial: { status: r.status === "Not assessed" ? "" : r.status, comment: r.assessment_comment },
    submitLabel: "Record assessment",
    onSubmit: (v) => API.post(`/api/grc/requirements/${r.id}/assess`, { status: v.status, comment: v.comment || "" }),
    onDone: () => { toast("Assessment recorded"); grcAfter(() => openRegulation(g.id)); },
  });
}

function requirementImport(g) {
  const file = el("input", { type: "file", accept: ".csv,text/csv", "aria-label": "CSV file" });
  const out = el("div");
  const m = modal({ drawer: true, title: `Import requirements into ${g.code}`, width: 640,
    body: el("div", null, el("p", { class: "muted small" }, "Columns: ref, title, text, owner_email, applicable (yes/no), control_refs (FRAMEWORK REF; separated by ;). An existing ref is updated."),
      el("a", { href: "/api/grc/requirements/template.csv" }, el("i", { class: "bi bi-download" }), " Download the template"), el("div", { class: "form-field" }, file), out),
    footer: el("div", { class: "form-foot-wrap" }, el("button", { class: "btn secondary", onclick: () => { m.close(); openRegulation(g.id); } }, "Close"),
      el("button", { class: "btn", onclick: async () => {
        if (!file.files.length) { toast("Choose a CSV file", "error"); return; }
        const fd = new FormData(); fd.append("file", file.files[0]);
        try {
          const r = await API.upload(`/api/grc/regulations/${g.id}/import`, fd);
          clear(out);
          out.append(el("div", { class: `callout ${r.errors.length ? "warn" : "ok"}` }, el("i", { class: "bi bi-check2-circle" }),
            el("div", null, `${r.created} added, ${r.updated} updated.`, r.errors.length ? el("ul", null, ...r.errors.map((x) => el("li", null, x))) : null)));
        } catch (err) { toast(err.message, "error"); }
      } }, "Import")) });
}

// ==================================================================== Policy Manager

async function renderPolicies(filters = state.polFilters || {}) {
  state.polFilters = filters;
  clear(viewRoot);
  const msg = el("div");
  let data;
  try { data = await API.get(`/api/grc/policies?${new URLSearchParams(Object.entries(filters).filter(([, v]) => v))}`); } catch (err) { viewRoot.append(viewHeader("Policy Manager"), msg); notify(msg, err.message, "error"); return; }
  viewRoot.append(viewHeader("Policy Manager", data.can_edit ? [el("button", { class: "btn small", onclick: () => policyForm(null, data.categories) }, el("i", { class: "bi bi-plus-lg" }), " Policy")] : null,
    { sub: "Draft, review, approve and publish policies; ask staff to attest that they have read them; never miss a review date." }), msg);
  const s = data.summary;
  viewRoot.append(el("div", { class: "stats" }, stat(s.published, "Published"), stat(s.in_review, "Waiting for approval", null, s.in_review ? "warn" : ""),
    stat(s.drafts, "Drafts"), stat(s.review_overdue, "Review overdue", null, s.review_overdue ? "danger" : "")));
  const st = el("select", { class: "compact", "aria-label": "Status" }, el("option", { value: "" }, "All statuses"), ...["Draft", "In review", "Approved", "Published", "Retired"].map((x) => el("option", { value: x, selected: filters.status === x ? "1" : null }, x)));
  st.addEventListener("change", () => renderPolicies({ ...filters, status: st.value }));
  const cat = el("select", { class: "compact", "aria-label": "Category" }, el("option", { value: "" }, "All categories"), ...data.categories.map((x) => el("option", { value: x, selected: filters.category === x ? "1" : null }, x)));
  cat.addEventListener("change", () => renderPolicies({ ...filters, category: cat.value }));
  viewRoot.append(el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, `Policies (${data.items.length})`), el("div", { class: "actions" }, cat, st)),
    dataTable(data.items, [
      { key: "ref", label: "Ref", render: (p) => el("span", { class: "ref" }, p.ref) }, { key: "title", label: "Policy" }, { key: "category", label: "Category" },
      { key: "owner", label: "Owner" }, { key: "status", label: "Status", render: (p) => el("span", { class: "chips" }, badge(p.status), p.working_status && p.status === "Published" ? el("span", { class: "chip-mini" }, `v${p.working_version} ${p.working_status.toLowerCase()}`) : null) },
      { key: "published_version", label: "Version", render: (p) => (p.published_version ? `v${p.published_version}` : "-") },
      { key: "next_review_date", label: "Next review", render: (p) => (p.review_overdue ? el("span", { class: "chip-mini warn" }, `Overdue ${dateOnly(p.next_review_date)}`) : dateOnly(p.next_review_date)) },
      { key: "attestation", label: "Attestation", render: (p) => (p.attestation ? `${p.attestation.completion_pct}% (${p.attestation.attested}/${p.attestation.total})` : "-") },
    ], { onRow: (p) => openPolicy(p.id), exportName: "policies", emptyText: "No policies yet." })));
}

async function policyForm(p, categories) {
  const [people, ents] = await Promise.all([grcPeople(), grcEntities()]);
  openForm({
    title: p ? `Edit ${p.ref}` : "New policy", key: p ? `pol:${p.id}` : "pol:new", width: 860, draftable: !p,
    fields: [
      { name: "title", label: "Title", required: true, maxLength: 255, singleLine: true, full: true },
      { name: "category", label: "Category", type: "select", options: categories, emptyLabel: "-" },
      { name: "review_months", label: "Review every (months)", type: "number", min: 1, max: 120 },
      { name: "owner_id", label: "Policy owner", type: "select", options: personOptions(people) },
      { name: "approver_id", label: "Approver", type: "select", options: personOptions(people), help: "Cannot be the author of a draft" },
      { name: "entity_id", label: "Applies to (entity)", type: "select", options: entityOptions(ents), emptyLabel: "All of GPHA" },
      { name: "summary", label: "Purpose and scope", type: "textarea", rows: 3, full: true },
      ...(p ? [] : [{ name: "content", label: "Policy text (you can also attach the document after creating it)", type: "textarea", rows: 10, full: true, maxLength: 500000 }]),
    ],
    initial: p ? { ...p, owner_id: p.owner_id || "", approver_id: p.approver_id || "", entity_id: p.entity_id || "" } : { owner_id: state.user.id },
    submitLabel: p ? "Save" : "Create draft",
    onSubmit: (v) => { const b = { ...v, owner_id: numOrNull(v.owner_id), approver_id: numOrNull(v.approver_id), entity_id: numOrNull(v.entity_id), review_months: numOrNull(v.review_months), category: v.category || "", summary: v.summary || "", content: v.content || "" };
      return p ? API.put(`/api/grc/policies/${p.id}`, b) : API.post("/api/grc/policies", b); },
    onDone: (res) => { toast(`${res.ref} saved`); openPolicy(res.id); },
  });
}

async function openPolicy(id) {
  clear(viewRoot);
  let p;
  try { p = await API.get(`/api/grc/policies/${id}`); } catch (err) { toast(err.message, "error"); return; }
  grcOpened("policies");
  const can = p.can || {};
  const cats = can.edit ? (await safeGet("/api/grc/policies?status=__none__", { categories: [] })).categories : [];
  const working = p.versions.find((v) => v.version === p.working_version);
  const published = p.versions.find((v) => v.version === p.published_version);
  const act = (label, fn, cls = "btn small secondary", icon = null) => el("button", { class: cls, onclick: fn }, icon ? el("i", { class: `bi bi-${icon}` }) : null, icon ? ` ${label}` : label);
  const run = async (fn, okText) => { try { await fn(); toast(okText); openPolicy(id); } catch (err) { toast(err.message, "error"); } };
  viewRoot.append(viewHeader(`${p.ref} · ${p.title}`, [
    can.edit ? act("Edit details", () => policyForm(p, cats), "btn small secondary", "pencil") : null,
    can.draft ? act(working ? `Edit draft v${working.version}` : "Start a new version", () => policyDraftForm(p, working || published), "btn small secondary", "file-earmark-text") : null,
    can.submit ? act("Submit for approval", () => run(() => API.post(`/api/grc/policies/${id}/submit`, {}), "Submitted for approval"), "btn small", "send") : null,
    can.review ? act("Review", () => policyReviewForm(p, working), "btn small", "check2-square") : null,
    can.publish ? act("Publish", () => run(() => API.post(`/api/grc/policies/${id}/publish`, {}), "Published"), "btn small", "megaphone") : null,
    can.campaign ? act("Ask staff to attest", () => campaignForm(p), "btn small secondary", "people") : null,
    can.retire ? act("Retire", () => { if (confirm("Retire this policy? Open attestation campaigns are closed.")) run(() => API.post(`/api/grc/policies/${id}/retire`, {}), "Retired"); }, "btn small secondary") : null,
  ].filter(Boolean), { back: grcBack(() => renderPolicies()),
    meta: el("span", { class: "chips" }, badge(p.status), p.published_version ? el("span", { class: "chip static" }, `In force: v${p.published_version}`) : null,
      working ? el("span", { class: "chip-mini" }, `v${working.version} ${working.status.toLowerCase()}`) : null, p.review_overdue ? el("span", { class: "chip-mini warn" }, "Review overdue") : null) }));
  viewRoot.append(el("div", { class: "two-cols" },
    panel("Policy", el("dl", { class: "kv" }, el("dt", null, "Category"), el("dd", null, p.category || "-"), el("dt", null, "Owner"), el("dd", null, p.owner || "-"),
      el("dt", null, "Approver"), el("dd", null, p.approver || "-"), el("dt", null, "Applies to"), el("dd", null, p.entity || "All of GPHA"),
      el("dt", null, "Effective"), el("dd", null, dateOnly(p.effective_date)), el("dt", null, "Next review"), el("dd", null, `${dateOnly(p.next_review_date)} (every ${p.review_months} months)`),
      el("dt", null, "Purpose"), el("dd", { class: "pre" }, p.summary || "-"))),
    panel("Versions", el("div", null, ...p.versions.map((v) => el("div", { class: "ver-item" },
      el("div", { class: "ver-head" }, el("strong", null, `v${v.version}`), badge(v.status), el("span", { class: "muted small" }, [v.author && `by ${v.author}`, v.published_at && `published ${dateOnly(v.published_at)}`, v.reviewed_by && `reviewed by ${v.reviewed_by}`].filter(Boolean).join(" · "))),
      v.change_summary ? el("div", { class: "small" }, v.change_summary) : null,
      v.review_comment ? el("div", { class: "small muted" }, `Reviewer: ${v.review_comment}`) : null,
      el("div", { class: "inline-actions" }, el("button", { class: "linkish small", onclick: () => policyTextView(p, v) }, "Read"),
        v.file_name ? el("a", { class: "small", href: `/api/grc/policies/${p.id}/versions/${v.version}/file` }, el("i", { class: "bi bi-paperclip" }), ` ${v.file_name}`) : null)))))));
  if (p.campaigns.length) {
    viewRoot.append(panel("Attestation campaigns", dataTable(p.campaigns, [
      { key: "title", label: "Campaign" }, { key: "version", label: "Version", render: (c) => `v${c.version}` }, { key: "due_date", label: "Due", render: (c) => dateOnly(c.due_date) },
      { key: "completion_pct", label: "Completion", render: (c) => el("div", { class: "mini-progress", title: `${c.attested} attested, ${c.declined} declined, ${c.pending} pending` }, el("div", { class: "progress" }, el("div", { class: "progress-fill", style: `width:${c.completion_pct}%` })), el("span", { class: "small" }, `${c.completion_pct}% · ${c.attested}/${c.total}`)) },
      { key: "declined", label: "Declined", num: true }, { key: "status", label: "Status", render: (c) => el("span", { class: "chips" }, badge(c.status), c.overdue ? el("span", { class: "chip-mini warn" }, "Overdue") : null) },
    ], { onRow: (c) => campaignView(c.id, p), pageSize: 10 })));
  }
  if (p.links) viewRoot.append(linksCard("policy", p.id, p.links, ["requirement", "risk", "control", "asset"], can.edit, () => openPolicy(id)));
}

function policyTextView(p, v) {
  const m = modal({ title: `${p.ref} v${v.version}`, width: 860,
    body: el("div", null, el("h3", null, p.title), v.content ? el("div", { class: "policy-text pre" }, v.content) : el("p", { class: "muted" }, "The text is in the attached document."),
      v.file_name ? el("p", null, el("a", { href: `/api/grc/policies/${p.id}/versions/${v.version}/file` }, el("i", { class: "bi bi-paperclip" }), ` ${v.file_name}`)) : null),
    footer: el("div", { class: "form-foot-wrap" }, el("button", { class: "btn secondary", onclick: () => m.close() }, "Close")) });
}

function policyDraftForm(p, base) {
  const fileIn = el("input", { type: "file", "aria-label": "Policy document" });
  openForm({
    title: `${p.ref}: draft`, key: `poldraft:${p.id}`, width: 900,
    fields: [
      { name: "change_summary", label: "What changes in this version", maxLength: 5000, singleLine: true, full: true },
      { name: "content", label: "Policy text", type: "textarea", rows: 18, full: true, maxLength: 500000 },
    ],
    initial: { content: base ? base.content : "", change_summary: base && base.status !== "Published" ? base.change_summary : "" },
    submitLabel: "Save draft",
    extra: el("div", { class: "form-field" }, el("label", null, "Attach the Word / PDF document (optional)"), fileIn),
    onSubmit: async (v) => {
      const res = await API.put(`/api/grc/policies/${p.id}/draft`, { content: v.content || "", change_summary: v.change_summary || "" });
      if (fileIn.files.length) { const fd = new FormData(); fd.append("file", fileIn.files[0]); await API.upload(`/api/grc/policies/${p.id}/draft/file`, fd); }
      return res;
    },
    onDone: () => { toast("Draft saved"); openPolicy(p.id); },
  });
}

function policyReviewForm(p, v) {
  openForm({
    title: `Review ${p.ref} v${v.version}`, key: `polrev:${p.id}:${v.version}`, width: 720,
    fields: [
      { name: "decision", label: "Decision", type: "select", required: true, options: [{ value: "approve", label: "Approve" }, { value: "return", label: "Return for changes" }] },
      { name: "comment", label: "Comment", type: "textarea", rows: 4, full: true, help: "Required when you return the draft" },
    ],
    initial: { decision: "approve" },
    extra: el("div", null, el("button", { class: "btn small secondary", type: "button", onclick: () => policyTextView(p, v) }, el("i", { class: "bi bi-eye" }), " Read the draft")),
    submitLabel: "Record decision",
    onSubmit: (val) => API.post(`/api/grc/policies/${p.id}/review`, { decision: val.decision, comment: val.comment || "" }),
    onDone: () => { toast("Decision recorded"); openPolicy(p.id); },
  });
}

async function campaignForm(p) {
  const people = await grcPeople();
  const ents = await grcEntities();
  openForm({
    title: `Attestation: ${p.ref} v${p.published_version}`, key: `polcamp:${p.id}`, width: 860,
    fields: [
      { name: "title", label: "Title", maxLength: 255, singleLine: true, full: true, placeholder: `Attest to ${p.title}` },
      { name: "due_date", label: "Due by", type: "date" },
      { name: "tiers", label: "Everyone with access tier", type: "checklist", options: ["Auditor", "Auditee", "Committee"] },
      { name: "job_roles", label: "Everyone with these roles", type: "checklist", full: true, options: people.job_roles.map((r) => ({ value: r.code, label: r.name })) },
      { name: "entity_ids", label: "Only staff based at (leave empty for all)", type: "checklist", full: true, options: entityOptions(ents.filter((e) => e.is_port)) },
      { name: "user_ids", label: "And these people", type: "checklist", full: true, options: personOptions(people) },
      { name: "statement", label: "Statement they confirm", type: "textarea", rows: 3, full: true, placeholder: "I confirm that I have read and understood this policy and will comply with it." },
    ],
    initial: {},
    submitLabel: "Send",
    onSubmit: (v) => API.post(`/api/grc/policies/${p.id}/campaigns`, { title: v.title || "", statement: v.statement || "", due_date: v.due_date || null,
      tiers: v.tiers || [], job_roles: v.job_roles || [], user_ids: (v.user_ids || []).map(Number), entity_ids: (v.entity_ids || []).map(Number) }),
    onDone: (c) => { toast(`Sent to ${c.total} people`); openPolicy(p.id); },
  });
}

async function campaignView(cid, p) {
  let c;
  try { c = await API.get(`/api/grc/campaigns/${cid}`); } catch (err) { toast(err.message, "error"); return; }
  const m = modal({ title: c.title, width: 820,
    body: el("div", null, el("div", { class: "stats" }, stat(c.total, "People"), stat(c.attested, "Attested"), stat(c.declined, "Declined", null, c.declined ? "warn" : ""), stat(c.pending, "Pending")),
      dataTable(c.people, [{ key: "name", label: "Name" }, { key: "status", label: "Status", render: (a) => badge(a.status) },
        { key: "responded_at", label: "Responded", render: (a) => (a.responded_at ? fmtDate(a.responded_at) : "-") }, { key: "comment", label: "Comment" }], { pageSize: 15, exportName: `attestation-${c.id}` })),
    footer: el("div", { class: "form-foot-wrap" },
      c.status === "Open" && p.can?.campaign ? el("button", { class: "btn secondary", onclick: async () => { try { const r = await API.post(`/api/grc/campaigns/${cid}/close`, {}); m.close(); toast("Campaign closed"); openPolicy(p.id); return r; } catch (err) { toast(err.message, "error"); } return null; } }, "Close campaign") : null,
      el("span", { class: "spacer" }),
      c.status === "Open" && c.pending && p.can?.campaign ? el("button", { class: "btn", onclick: async () => { try { const r = await API.post(`/api/grc/campaigns/${cid}/remind`, {}); toast(`Reminded ${r.reminded} people`); } catch (err) { toast(err.message, "error"); } } }, "Remind pending") : null,
      el("button", { class: "btn secondary", onclick: () => m.close() }, "Close")) });
}

// ==================================================================== Asset Inventory

async function renderAssets(filters = state.assetFilters || {}) {
  state.assetFilters = filters;
  clear(viewRoot);
  const msg = el("div");
  let data;
  try { data = await API.get(`/api/grc/assets?${new URLSearchParams(Object.entries(filters).filter(([, v]) => v !== "" && v !== undefined))}`); } catch (err) { viewRoot.append(viewHeader("Asset Inventory"), msg); notify(msg, err.message, "error"); return; }
  viewRoot.append(viewHeader("Asset Inventory", data.can_edit ? [el("button", { class: "btn small", onclick: () => assetForm(null, data) }, el("i", { class: "bi bi-plus-lg" }), " Asset")] : null,
    { sub: "Systems, data, facilities, equipment and third parties: who owns them, how critical they are and the risks and controls around them." }), msg);
  const s = data.summary;
  viewRoot.append(el("div", { class: "stats" }, stat(s.active, "Active assets"), stat(s.critical, "Critical"), stat(s.third_parties, "Third parties"),
    stat(s.assessments_due, "Due-diligence due", null, s.assessments_due ? "warn" : ""), stat(s.contracts_expiring, "Contracts ending ≤ 90 days", s.contracts_expired ? `${s.contracts_expired} expired` : null, s.contracts_expired ? "danger" : s.contracts_expiring ? "warn" : "")));
  const sel = (name, label, opts) => {
    const x = el("select", { class: "compact", "aria-label": label }, el("option", { value: "" }, label), ...opts.map((o) => el("option", { value: o, selected: String(filters[name] ?? "") === String(o) ? "1" : null }, o)));
    x.addEventListener("change", () => renderAssets({ ...filters, [name]: x.value }));
    return x;
  };
  const tp = el("select", { class: "compact", "aria-label": "Third parties" }, el("option", { value: "" }, "Assets and third parties"),
    el("option", { value: "true", selected: filters.third_party === "true" ? "1" : null }, "Third parties only"), el("option", { value: "false", selected: filters.third_party === "false" ? "1" : null }, "Internal assets only"));
  tp.addEventListener("change", () => renderAssets({ ...filters, third_party: tp.value }));
  const q = el("input", { type: "search", class: "compact", placeholder: "Search", value: filters.q || "", "aria-label": "Search assets" });
  q.addEventListener("keydown", (e) => { if (e.key === "Enter") renderAssets({ ...filters, q: q.value.trim() }); });
  viewRoot.append(el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, `Inventory (${data.items.length})`),
    el("div", { class: "actions" }, tp, sel("asset_type", "All types", data.types), sel("criticality", "Any criticality", data.criticality), q)),
  dataTable(data.items, [
    { key: "ref", label: "Ref", render: (a) => el("span", { class: "ref" }, a.ref) }, { key: "name", label: "Name" }, { key: "asset_type", label: "Type" },
    { key: "criticality", label: "Criticality", render: (a) => badge(a.criticality) }, { key: "owner", label: "Owner" }, { key: "entity", label: "Entity" },
    { key: "due_diligence", label: "Due diligence", render: (a) => (a.is_third_party ? el("span", { class: "chips" }, badge(a.due_diligence), a.assessment_due ? el("span", { class: "chip-mini warn" }, "Due") : null) : "-") },
    { key: "contract_end", label: "Contract ends", render: (a) => (a.contract_end ? el("span", { class: a.contract_expired ? "txt-danger" : a.contract_expiring ? "txt-warn" : "" }, dateOnly(a.contract_end)) : "-") },
    { key: "status", label: "Status", render: (a) => badge(a.status) },
  ], { onRow: (a) => openAsset(a.id), exportName: "asset-inventory", emptyText: "No assets yet." })));
}

async function assetForm(a, meta) {
  const [p, ents] = await Promise.all([grcPeople(), grcEntities()]);
  meta = meta || await API.get("/api/grc/assets?status=__none__");
  openForm({
    title: a ? `Edit ${a.ref}` : "New asset or third party", key: a ? `asset:${a.id}` : "asset:new", width: 880, draftable: !a,
    fields: [
      { name: "name", label: "Name", required: true, maxLength: 255, singleLine: true, full: true },
      { name: "asset_type", label: "Type", type: "select", required: true, options: meta.types },
      { name: "criticality", label: "Criticality", type: "select", required: true, options: meta.criticality },
      { name: "classification", label: "Information classification", type: "select", options: meta.classifications, emptyLabel: "-" },
      { name: "status", label: "Status", type: "select", required: true, options: ["Planned", "Active", "Retired"] },
      { name: "owner_id", label: "Owner", type: "select", options: personOptions(p) },
      { name: "entity_id", label: "Entity", type: "select", options: entityOptions(ents) },
      { name: "location", label: "Location", maxLength: 160, singleLine: true },
      { name: "description", label: "Description", type: "textarea", rows: 3, full: true },
      { type: "heading", label: "Third parties: contract" },
      { name: "vendor_contact", label: "Contact (name, e-mail, phone)", maxLength: 255, singleLine: true, full: true },
      { name: "contract_ref", label: "Contract reference", maxLength: 80, singleLine: true },
      { name: "contract_start", label: "Contract start", type: "date" }, { name: "contract_end", label: "Contract end", type: "date" },
      { name: "services", label: "Services provided / data shared", type: "textarea", rows: 2, full: true },
    ],
    initial: a ? Object.fromEntries(Object.entries(a).map(([k, v]) => [k, v ?? ""])) : { criticality: "Medium", status: "Active" },
    submitLabel: a ? "Save" : "Create",
    onSubmit: (v) => { const b = { ...v };
      ["owner_id", "entity_id"].forEach((k) => { b[k] = numOrNull(v[k]); });
      ["contract_start", "contract_end"].forEach((k) => { b[k] = v[k] || null; });
      ["classification", "location", "description", "vendor_contact", "contract_ref", "services"].forEach((k) => { b[k] = v[k] || ""; });
      return a ? API.put(`/api/grc/assets/${a.id}`, b) : API.post("/api/grc/assets", b); },
    onDone: (res) => { toast(`${res.ref} saved`); openAsset(res.id); },
  });
}

async function openAsset(id) {
  clear(viewRoot);
  let a;
  try { a = await API.get(`/api/grc/assets/${id}`); } catch (err) { toast(err.message, "error"); return; }
  grcOpened("assets");
  viewRoot.append(viewHeader(`${a.ref} · ${a.name}`, [
    a.is_third_party && a.can_assess ? el("button", { class: "btn small", onclick: () => tpAssessForm(a) }, el("i", { class: "bi bi-clipboard-check" }), " Due-diligence assessment") : null,
    a.can_edit ? el("button", { class: "btn small secondary", onclick: () => assetForm(a) }, el("i", { class: "bi bi-pencil" }), " Edit") : null,
  ].filter(Boolean), { back: grcBack(() => renderAssets()), meta: el("span", { class: "chips" }, badge(a.status), badge(a.criticality), el("span", { class: "chip static" }, a.asset_type)) }));
  const kv = [["Owner", a.owner], ["Entity", a.entity], ["Location", a.location], ["Classification", a.classification], ["Description", a.description]];
  if (a.is_third_party) kv.push(["Contact", a.vendor_contact], ["Services", a.services], ["Contract", a.contract_ref], ["Contract period", `${dateOnly(a.contract_start)} to ${dateOnly(a.contract_end)}`],
    ["Due diligence", a.due_diligence], ["Risk rating", a.risk_rating], ["Next assessment", dateOnly(a.next_assessment_date)]);
  viewRoot.append(panel("Details", el("dl", { class: "kv" }, ...kv.flatMap(([k, v]) => [el("dt", null, k), el("dd", { class: "pre" }, v || "-")]))));
  if (a.contract_expired) viewRoot.append(el("div", { class: "callout danger" }, el("i", { class: "bi bi-exclamation-octagon" }), el("div", null, "The contract has expired but the third party is still active.")));
  if (a.is_third_party) viewRoot.append(panel("Due-diligence assessments", dataTable(a.assessments, [
    { key: "assessed_on", label: "Date", render: (t) => dateOnly(t.assessed_on) }, { key: "rating", label: "Rating", render: (t) => badge(t.rating) },
    { key: "outcome", label: "Outcome", render: (t) => badge(t.outcome) }, { key: "areas", label: "Areas reviewed" }, { key: "findings", label: "Findings" }, { key: "assessor", label: "By" },
  ], { pageSize: 10, emptyText: "Not assessed yet." })));
  viewRoot.append(linksCard("asset", a.id, a.links, ["risk", "control", "requirement", "policy"], a.can_edit, () => openAsset(id)));
}

function tpAssessForm(a) {
  openForm({
    title: `Due diligence: ${a.name}`, key: `tpa:${a.id}`, width: 760,
    fields: [
      { name: "assessed_on", label: "Assessed on", type: "date", required: true },
      { name: "rating", label: "Third-party risk rating", type: "select", required: true, options: ["Low", "Medium", "High", "Critical"] },
      { name: "outcome", label: "Outcome", type: "select", required: true, options: ["In progress", "Approved", "Approved with conditions", "Rejected"] },
      { name: "areas", label: "Areas reviewed", type: "textarea", rows: 2, full: true, placeholder: "Financial standing, information security, business continuity, legal and regulatory, ethics and anti-bribery, insurance" },
      { name: "findings", label: "Findings and conditions", type: "textarea", rows: 4, full: true },
    ],
    initial: { assessed_on: new Date().toISOString().slice(0, 10) },
    submitLabel: "Record",
    onSubmit: (v) => API.post(`/api/grc/assets/${a.id}/assessments`, { ...v, areas: v.areas || "", findings: v.findings || "" }),
    onDone: () => { toast("Assessment recorded"); openAsset(a.id); },
  });
}

// ==================================================================== Task Tracker: Priorities (everything waiting for a person)

async function renderPortal() {
  clear(viewRoot);
  const msg = el("div");
  let data;
  try { data = await API.get("/api/portal"); } catch (err) { viewRoot.append(viewHeader("Task Tracker"), msg); notify(msg, err.message, "error"); return; }
  viewRoot.append(viewHeader("Task Tracker", el("button", { class: "btn small secondary", onclick: renderPortal }, el("i", { class: "bi bi-arrow-clockwise" }), " Refresh"),
    { sub: `${greeting()}, ${data.user}. Everything waiting for you, in one place.` }), msg);
  viewRoot.append(el("div", { class: "stats" }, stat(data.total, "Waiting for you"), stat(data.overdue, "Overdue", null, data.overdue ? "danger" : ""),
    stat(data.due_this_week, "Due within 7 days", null, data.due_this_week ? "warn" : "")));
  if (!data.total) {
    viewRoot.append(el("div", { class: "card empty-state" }, el("i", { class: "bi bi-check2-circle big-icon" }), el("h3", null, "You're all caught up"),
      el("p", { class: "muted" }, "Requests, actions, attestations and reviews assigned to you will appear here.")));
    return;
  }
  const icon = { "Attest to policies": "file-earmark-check", "Questionnaires": "ui-checks", "Evidence requests": "inbox", "Agreed actions": "tools", "Exceptions to resolve": "exclamation-diamond",
    "Assess your risks": "shield-exclamation", "Record indicators": "speedometer2", "Assess compliance": "journal-check", "Third-party due diligence": "building-check", "Tasks": "check2-square" };
  data.sections.forEach((s) => {
    viewRoot.append(el("div", { class: "card portal-section" },
      el("div", { class: "card-head" }, el("h3", null, el("i", { class: `bi bi-${icon[s.name] || "dot"}` }), ` ${s.name}`), el("span", { class: "chip-count" }, String(s.items.length))),
      el("div", { class: "portal-list" }, ...s.items.map((it) => el("div", { class: `portal-item ${it.overdue ? "overdue" : ""}` },
        el("div", { class: "pi-main" }, el("div", null, el("span", { class: "ref" }, it.ref), " ", el("strong", null, it.title)),
          el("div", { class: "muted small" }, [it.detail, it.due ? `${it.overdue ? "Overdue since" : "Due"} ${it.due}` : null].filter(Boolean).join(" · "))),
        it.overdue ? el("span", { class: "chip-mini warn" }, "Overdue") : null,
        el("button", { class: "btn small", onclick: () => portalAction(it) }, it.action))))));
  });
}

function portalAction(it) {
  const back = () => renderPortal();
  state.fromPortal = ["erm_risk", "asset", "requirement"].includes(it.kind);
  switch (it.kind) {
    case "attestation": return attestDialog(it.data, back);
    case "erm_risk": return openRisk(it.id);
    case "kri": return kriReadingForm({ id: it.data.kri_id, name: it.title, unit: it.data.unit }, it.data.risk_id, back);
    case "requirement": return assessRequirementForm({ code: it.ref.split(" ")[0], id: it.data.regulation_id }, { id: it.id, ref: it.ref.split(" ").slice(1).join(" "), status: it.data.status, assessment_comment: it.data.comment });
    case "asset": return openAsset(it.id);
    case "evidence_request": return navigate("evidence");
    case "capa": return openRecord("capa", it.id);
    case "task": return navigate("tasks");
    default: return null;
  }
}

function attestDialog(a, after) {
  const comment = el("textarea", { rows: 2, placeholder: "Comment (required if you decline)", "aria-label": "Comment" });
  const send = async (status) => {
    try { await API.post(`/api/grc/attestations/${a.id}`, { status, comment: comment.value }); m.close(); toast(status === "Attested" ? "Thank you, attestation recorded" : "Recorded: the policy owner has been told"); after(); } catch (err) { toast(err.message, "error"); }
  };
  const m = modal({ title: `${a.policy_ref} · ${a.policy_title} (v${a.version})`, width: 860,
    body: el("div", null,
      a.content ? el("div", { class: "policy-text pre" }, a.content) : el("p", { class: "muted" }, "The policy is in the attached document."),
      a.file_name ? el("p", null, el("a", { href: `/api/grc/policies/${a.policy_id}/versions/${a.version}/file` }, el("i", { class: "bi bi-paperclip" }), ` ${a.file_name}`)) : null,
      el("div", { class: "callout ok" }, el("i", { class: "bi bi-pen" }), el("div", null, el("strong", null, "Statement"), el("div", null, a.statement))),
      comment),
    footer: el("div", { class: "form-foot-wrap" }, el("button", { class: "btn secondary", onclick: () => m.close() }, "Later"), el("span", { class: "spacer" }),
      el("button", { class: "btn secondary", onclick: () => send("Declined") }, "I cannot attest"),
      el("button", { class: "btn", onclick: () => send("Attested") }, el("i", { class: "bi bi-check2" }), " I confirm")) });
}

async function refreshPortalCount() {
  const node = document.querySelector("#portalCount");
  if (!node) return;
  const c = await safeGet("/api/portal/count", { total: 0, overdue: 0 });
  node.textContent = c.total ? String(c.total) : "";
  node.classList.toggle("hidden", !c.total);
  node.classList.toggle("alert", !!c.overdue);
}
