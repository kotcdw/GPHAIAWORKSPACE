// GPHA Audit Workspace - CAE insight and productivity screens:
// Analytics, Quality (QAIP), Capacity & time sheets, global search, in-app help,
// Excel import dialogs, Excel export and saved list views.
// Loaded after engagement.js and before app.js.

const RATING_ORDER = ["High", "Medium", "Low"];
const RATING_CLASS = { High: "r-high", Medium: "r-med", Low: "r-low" };

function fySelect(current, onChange) {
  const now = new Date().getFullYear();
  const sel = el("select", { class: "compact", "aria-label": "Fiscal year" },
    ...[now + 1, now, now - 1, now - 2, now - 3].map((y) => el("option", { value: y, selected: y === current ? "1" : null }, `FY${y}`)));
  sel.addEventListener("change", () => onChange(Number(sel.value)));
  return sel;
}

function legend(items) {
  return el("div", { class: "legend", "aria-hidden": "true" },
    ...items.map(([label, cls]) => el("span", { class: "legend-item" }, el("span", { class: `legend-swatch ${cls}` }), label)));
}

// ==================================================================== Analytics

async function renderAnalytics(fy = new Date().getFullYear()) {
  clear(viewRoot);
  const msg = el("div");
  viewRoot.append(viewHeader("Analytics", fySelect(fy, (y) => renderAnalytics(y)),
    { sub: "Risk heat map, finding trends, repeat findings and performance against the CAE's KPI targets" }), msg);
  let a;
  try { a = await API.get(`/api/analytics?fiscal_year=${fy}`); } catch (err) { notify(msg, err.message, "error"); return; }

  // KPI scorecard
  const icon = { ok: "check-circle-fill", warn: "exclamation-circle-fill", bad: "x-circle-fill", none: "dash-circle" };
  const word = { ok: "On target", warn: "Near target", bad: "Off target", none: "No data yet" };
  viewRoot.append(el("div", { class: "kpi-grid" }, ...a.kpis.map((k) => el("div", { class: `kpi ${k.status}` },
    el("div", { class: "kpi-label" }, k.label),
    el("div", { class: "kpi-value" }, k.actual === null || k.actual === undefined ? "-" : `${k.actual}${k.unit === "%" ? "%" : ""}`,
      k.unit && k.unit !== "%" && k.actual !== null ? el("span", { class: "kpi-unit" }, ` ${k.unit}`) : null),
    el("div", { class: "kpi-target" }, `Target ${k.better === "lower" ? "≤" : "≥"} ${k.target}${k.unit === "%" ? "%" : k.unit ? ` ${k.unit}` : ""}`),
    el("div", { class: "kpi-status" }, el("i", { class: `bi bi-${icon[k.status]}` }), ` ${word[k.status]}`),
    el("div", { class: "muted small" }, k.detail)))));

  const grid = el("div", { class: "dash-grid" });
  viewRoot.append(grid);

  // Heat map: impact (rows, 5 at top) x likelihood (columns)
  const cellInfo = el("div", { class: "muted small heat-info", "aria-live": "polite" }, "Select a cell to list its auditable units.");
  const heatGrid = el("div", { class: "heatmap", role: "group", "aria-label": "Inherent risk heat map: impact by likelihood" });
  for (let im = 5; im >= 1; im -= 1) {
    heatGrid.append(el("div", { class: "hm-axis", "aria-hidden": "true" }, String(im)));
    for (let lk = 1; lk <= 5; lk += 1) {
      const c = a.heat_map.find((x) => x.likelihood === lk && x.impact === im);
      const band = c.score >= 15 ? "high" : c.score >= 8 ? "med" : "low";
      const tip = `Likelihood ${lk} × Impact ${im} = ${c.score} · ${c.count} unit${c.count === 1 ? "" : "s"}`;
      heatGrid.append(el("button", { class: `hm-cell hm-${band} ${c.count ? "" : "empty"}`, type: "button",
        title: c.units.length ? `${tip}\n${c.units.join("\n")}` : tip, "aria-label": tip,
        onclick: () => { cellInfo.textContent = c.count ? `${tip}: ${c.units.join(", ")}` : `${tip}.`; } }, c.count ? String(c.count) : ""));
    }
  }
  heatGrid.append(el("div", { class: "hm-axis" }), ...[1, 2, 3, 4, 5].map((n) => el("div", { class: "hm-axis" }, String(n))));
  grid.append(panel("Inherent risk heat map", el("div", null,
    el("div", { class: "hm-wrap" }, el("div", { class: "hm-ylabel" }, "Impact"), heatGrid),
    el("div", { class: "hm-xlabel" }, "Likelihood"),
    legend([["Low (1-7)", "r-low"], ["Medium (8-14)", "r-med"], ["High (15-25)", "r-high"]]), cellInfo),
  el("button", { class: "btn small secondary", onclick: () => navigate("universe") }, "Audit Universe")));

  // Findings trend (stacked by rating)
  const max = Math.max(1, ...a.findings_trend.map((m) => m.High + m.Medium + m.Low));
  const bars = el("div", { class: "stack-chart", role: "img", "aria-label": "Findings raised per month by risk rating" },
    ...a.findings_trend.map((m) => {
      const total = m.High + m.Medium + m.Low;
      const label = new Date(`${m.month}-01T00:00:00`).toLocaleDateString(undefined, { month: "short" });
      return el("div", { class: "sc-col", title: `${m.month}: ${total} finding(s) · High ${m.High} · Medium ${m.Medium} · Low ${m.Low}` },
        el("div", { class: "sc-bar", style: `height:${(total / max) * 100}%` },
          ...RATING_ORDER.filter((r) => m[r]).map((r) => el("div", { class: `sc-seg ${RATING_CLASS[r]}`, style: `flex:${m[r]}` }))),
        el("div", { class: "sc-n" }, total ? String(total) : ""),
        el("div", { class: "sc-l" }, label));
    }));
  const trendTable = el("details", { class: "table-toggle" }, el("summary", null, "Show as table"),
    el("table", null, el("thead", null, el("tr", null, el("th", null, "Month"), ...RATING_ORDER.map((r) => el("th", { class: "num" }, r)))),
      el("tbody", null, ...a.findings_trend.map((m) => el("tr", { class: "no-click" }, el("td", null, m.month),
        ...RATING_ORDER.map((r) => el("td", { class: "num" }, String(m[r]))))))));
  grid.append(panel("Findings raised (last 12 months)", el("div", null, bars,
    legend(RATING_ORDER.map((r) => [r, RATING_CLASS[r]])), trendTable,
    el("div", { class: "muted small" }, `Open now: ${RATING_ORDER.map((r) => `${a.open_by_rating[r]} ${r}`).join(" · ")}`))));

  // Repeat findings
  const rep = a.repeat_findings.length
    ? el("div", { class: "table-wrap" }, el("table", null,
      el("thead", null, el("tr", null, el("th", null, "Recurring issue"), el("th", { class: "num" }, "Times"), el("th", null, "Audits"))),
      el("tbody", null, ...a.repeat_findings.map((r) => el("tr", { class: "no-click" },
        el("td", null, r.title), el("td", { class: "num" }, el("strong", null, String(r.occurrences))),
        el("td", null, el("div", { class: "chips" }, ...r.audits.map((x) => el("button", { class: "chip link", type: "button",
          title: `${x.rating} · ${x.status} · ${x.date}`, onclick: () => openAudit(x.audit_id, "findings") },
        badge(x.rating), ` ${x.audit_title || `AUD-${x.audit_id}`}`)))))))))
    : el("div", { class: "empty" }, "No repeat findings detected.");
  viewRoot.append(panel("Repeat findings", el("div", null,
    el("p", { class: "muted small" }, "Issues found again in a later audit (similar wording, weighted towards the same unit or organisation). Repeat findings point to remediation that did not hold."), rep)));

  if (a.themes.length) {
    viewRoot.append(panel("Common themes in this year's findings", el("div", { class: "chips" },
      ...a.themes.map((t) => el("span", { class: "chip static" }, t.word, el("span", { class: "chip-count" }, String(t.count)))))));
  }
}

// ==================================================================== Quality (QAIP)

async function renderQaipPage(fy = new Date().getFullYear()) {
  clear(viewRoot);
  const msg = el("div");
  viewRoot.append(viewHeader("Quality (QAIP)", el("div", { class: "actions" }, fySelect(fy, (y) => renderQaipPage(y)),
    el("a", { class: "btn small", href: `/api/qaip/report.docx?fiscal_year=${fy}` }, el("i", { class: "bi bi-file-earmark-word" }), " Internal assessment report")),
    { sub: "Engagement quality reviews and auditee satisfaction (IIA GIAS Principle 8)" }), msg);
  let q;
  try { q = await API.get(`/api/qaip/summary?fiscal_year=${fy}`); } catch (err) { notify(msg, err.message, "error"); return; }
  viewRoot.append(el("div", { class: "stats" },
    stat(q.reviews_completed, "Quality reviews completed", `${q.review_coverage_pct}% of ${q.closed_audits} closed audit(s)`, q.closed_audits && q.review_coverage_pct < 100 ? "warn" : ""),
    stat(q.average_score === null ? "-" : `${q.average_score}%`, "Average conformance", "across completed reviews", q.average_score !== null && q.average_score < 80 ? "warn" : ""),
    stat(q.survey_responses, "Survey responses", `${q.survey_invited} auditee(s) invited`),
    stat(q.survey_average === null ? "-" : q.survey_average.toFixed(2), "Satisfaction (out of 5)", null, q.survey_average !== null && q.survey_average < 3.5 ? "warn" : "")));
  const grid = el("div", { class: "dash-grid" });
  viewRoot.append(grid);
  grid.append(panel("Weakest checklist areas", q.weakest_items.length ? el("div", { class: "bars" }, ...q.weakest_items.map((w) =>
    el("div", { class: "bar-row" }, el("span", { class: "bar-label" }, el("span", { class: "chip-mini" }, w.standard), ` ${w.question}`),
      el("span", { class: "bar-track", role: "img", "aria-label": `${w.conformance_pct}% conformance` },
        el("span", { class: `bar-fill ${w.conformance_pct < 60 ? "danger" : w.conformance_pct < 85 ? "warn" : ""}`, style: `width:${w.conformance_pct}%` })),
      el("strong", { class: "bar-val" }, `${w.conformance_pct}%`))))
    : el("div", { class: "empty" }, "No completed quality reviews this year.")));
  grid.append(panel("Satisfaction by question", q.survey_by_question.length ? el("div", { class: "bars" }, ...q.survey_by_question.map((s) =>
    el("div", { class: "bar-row" }, el("span", { class: "bar-label" }, s.question),
      el("span", { class: "bar-track", role: "img", "aria-label": `${s.average} out of 5` },
        el("span", { class: `bar-fill ${s.average < 3 ? "danger" : s.average < 4 ? "warn" : ""}`, style: `width:${(s.average / 5) * 100}%` })),
      el("strong", { class: "bar-val" }, s.average.toFixed(1)))))
    : el("div", { class: "empty" }, "No survey responses this year.")));
  if (q.recent_comments.length) grid.append(panel("What auditees said", el("ul", { class: "plain-list quotes" }, ...q.recent_comments.map((c) => el("li", null, `"${c}"`)))));
  grid.append(panel("Completed reviews", dataTable(q.reviews, [
    { key: "title", label: "Audit" },
    { key: "score", label: "Conformance", num: true, render: (r) => (r.score === null ? "-" : `${r.score}%`) },
    { key: "completed_at", label: "Completed", render: (r) => fmtDate(r.completed_at).split(",")[0] },
  ], { onRow: (r) => openAudit(r.audit_id, "quality"), emptyText: "None yet.", pageSize: 10 })));
}

// ==================================================================== Capacity & time sheets

async function renderCapacity(tab = "team", fy = new Date().getFullYear()) {
  clear(viewRoot);
  const msg = el("div");
  viewRoot.append(viewHeader("Timesheets & capacity", el("div", { class: "actions" }, fySelect(fy, (y) => renderCapacity(tab, y)),
    el("button", { class: "btn", onclick: () => timeEntryForm({}, () => renderCapacity("mine", fy)) }, el("i", { class: "bi bi-plus-lg" }), " Log time")),
  { sub: "Auditor skills, available hours, planned load, time charged and budget versus actual" }), msg);
  viewRoot.append(tabBar([{ key: "team", label: "Team capacity" }, { key: "skills", label: "Skills matrix" }, { key: "budgets", label: "Budget vs actual" }, { key: "mine", label: "My time sheet" }],
    tab, (k) => renderCapacity(k, fy)));
  const body = el("div");
  viewRoot.append(body);
  try {
    if (tab === "mine") return renderMyTime(body, fy);
    const s = await API.get(`/api/capacity/summary?fiscal_year=${fy}`);
    const t = s.totals;
    body.append(el("div", { class: "stats" },
      stat(t.available_hours.toLocaleString(), "Available hours", `${s.auditors.length} auditor(s)`),
      stat(t.planned_hours.toLocaleString(), "Planned on the Assurance Plan", t.available_hours ? `${Math.round((100 * t.planned_hours) / t.available_hours)}% of available` : "", t.planned_hours > t.available_hours ? "danger" : ""),
      stat(t.logged_hours.toLocaleString(), "Hours logged", `FY${fy}`),
      stat(`${t.utilisation_pct}%`, "Charged to audit work", "audit + follow-up time")));
    if (tab === "team") {
      const filter = el("input", { placeholder: "Filter by skill or certification…", "aria-label": "Filter by skill" });
      const holder = el("div");
      const paint = () => {
        const n = filter.value.trim().toLowerCase();
        const rows = n ? s.auditors.filter((a) => a.skills.some((x) => x.toLowerCase().includes(n)) || a.name.toLowerCase().includes(n)) : s.auditors;
        holder.replaceChildren(dataTable(rows, [
          { key: "name", label: "Auditor" },
          { key: "grade", label: "Grade", render: (a) => a.grade || el("span", { class: "muted" }, "-") },
          { key: "skills", label: "Skills", render: (a) => (a.skills.length ? el("div", { class: "chips" }, ...a.skills.map((x) => el("span", { class: "chip static" }, x))) : el("span", { class: "muted" }, "-")), sortValue: (a) => a.skills.join(",") },
          { key: "available_hours", label: "Available", num: true },
          { key: "planned_hours", label: "Planned", num: true },
          { key: "load_pct", label: "Load", num: true, render: (a) => el("span", { class: a.load_pct > 100 ? "txt-danger" : a.load_pct > 85 ? "txt-warn" : "" }, `${a.load_pct}%`) },
          { key: "logged_hours", label: "Logged", num: true },
          { key: "utilisation_pct", label: "Audit time", num: true, render: (a) => `${a.utilisation_pct}%` },
        ], { onRow: (a) => profileForm(a, () => renderCapacity("team", fy)), exportName: `capacity-FY${fy}.csv` }));
      };
      filter.addEventListener("input", paint);
      body.append(el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, "Team"), filter),
        el("p", { class: "muted small" }, "Load = hours planned for the auditor as engagement lead ÷ available hours. Select a row to edit skills."), holder));
      paint();
    } else if (tab === "skills") {
      body.append(skillsMatrix(s.auditors));
    } else {
      body.append(el("div", { class: "card" }, el("h3", null, "Budget versus actual hours"), dataTable(s.audits, [
        { key: "title", label: "Audit" },
        { key: "status", label: "Status", render: (b) => badge(b.status) },
        { key: "budget_hours", label: "Budget", num: true, render: (b) => (b.budget_hours || el("span", { class: "muted" }, "-")) },
        { key: "actual_hours", label: "Actual", num: true },
        { key: "variance_hours", label: "Variance", num: true, render: (b) => (b.budget_hours ? el("span", { class: b.variance_hours < 0 ? "txt-danger" : "" }, `${b.variance_hours > 0 ? "+" : ""}${b.variance_hours}`) : "-") },
      ], { onRow: (b) => openAudit(b.audit_id, "time"), exportName: `budget-vs-actual-FY${fy}.csv`, emptyText: "No audits for this year." })));
    }
  } catch (err) { notify(msg, err.message, "error"); }
  return null;
}

async function renderMyTime(body, fy) {
  const start = `${fy}-01-01`;
  const end = `${fy}-12-31`;
  const entries = await API.get(`/api/capacity/time?start=${start}&end=${end}`);
  const byCat = {};
  entries.forEach((e) => { byCat[e.category] = (byCat[e.category] || 0) + e.hours; });
  const week = (() => { const d = new Date(); d.setDate(d.getDate() - 6); d.setHours(0, 0, 0, 0); return d; })();
  const thisWeek = entries.filter((e) => new Date(e.entry_date) >= week).reduce((s, e) => s + e.hours, 0);
  body.append(el("div", { class: "stats" },
    stat(thisWeek, "Hours in the last 7 days"),
    stat(entries.reduce((s, e) => s + e.hours, 0), `Hours in FY${fy}`),
    ...Object.entries(byCat).slice(0, 3).map(([c, h]) => stat(h, c))));
  const refresh = () => renderCapacity("mine", fy);
  body.append(el("div", { class: "card" }, el("h3", null, "My entries"), dataTable(entries, [
    { key: "entry_date", label: "Date", render: (e) => fmtDate(e.entry_date).split(",")[0], sortValue: (e) => e.entry_date },
    { key: "category", label: "Category" },
    { key: "audit_title", label: "Audit", render: (e) => e.audit_title || el("span", { class: "muted" }, "-") },
    { key: "hours", label: "Hours", num: true },
    { key: "description", label: "Work done", render: (e) => e.description || el("span", { class: "muted" }, "-") },
    { key: "id", label: "", render: (e) => (e.can_delete ? el("button", { class: "btn small secondary icon", title: "Delete entry", "aria-label": "Delete entry",
      onclick: async (ev) => { ev.stopPropagation(); try { await API.del(`/api/capacity/time/${e.id}`); toast("Entry deleted"); refresh(); } catch (err) { toast(err.message, "error"); } } },
    el("i", { class: "bi bi-trash" })) : "") },
  ], { exportName: `my-time-FY${fy}.csv`, emptyText: "No time logged this year. Use Log time to add an entry." })));
}

function profileForm(a, onDone) {
  const own = a.user_id === state.user.id;
  const supervisor = isAdmin() || hasPerm("oversight.resources");
  if (!own && !supervisor) { toast("You can only edit your own profile", "error"); return; }
  openForm({
    key: `profile:${a.user_id}`, title: `Skills & capacity · ${a.name}`, width: 640, draftable: false,
    fields: [
      { name: "grade", label: "Grade / position", maxLength: 100 },
      { name: "annual_hours", label: "Available hours per year", type: "number", min: 0, max: 3000, disabled: !supervisor, help: supervisor ? "After leave, training and public holidays" : "Set by the Audit Manager / CAE" },
      { name: "skills", label: "Skills", type: "textarea", rows: 2, help: "Comma separated, e.g. IT audit, Data analytics, Procurement", full: true },
      { name: "certifications", label: "Certifications", type: "textarea", rows: 2, help: "Comma separated, e.g. CIA, CISA, ACCA", full: true },
    ],
    initial: { grade: a.grade, annual_hours: a.available_hours, skills: (a.skills || []).join(", "), certifications: (a.certifications || []).join(", ") },
    submitLabel: "Save profile",
    onSubmit: (v) => API.put(`/api/capacity/profiles/${a.user_id}`, {
      grade: v.grade || "", annual_hours: v.annual_hours ?? a.available_hours,
      skills: (v.skills || "").split(",").map((x) => x.trim()).filter(Boolean),
      certifications: (v.certifications || "").split(",").map((x) => x.trim()).filter(Boolean) }),
    onDone: () => { toast("Profile saved"); onDone(); },
  });
}

// ==================================================================== Excel export + saved views

async function downloadXlsx(title, columns, rows) {
  const cols = columns.filter((c) => c.label);
  const data = rows.map((it) => cols.map((c) => {
    const v = c.csv ? c.csv(it) : it[c.key];
    if (v === null || v === undefined) return "";
    return typeof v === "number" ? v : Array.isArray(v) ? v.join(", ") : String(v);
  }));
  try {
    const token = API.csrf || readCookie("gpha_csrf");
    const res = await fetch("/api/export.xlsx", { method: "POST", credentials: "include",
      headers: { "Content-Type": "application/json", ...(token ? { "X-CSRF-Token": token } : {}) },
      body: JSON.stringify({ title, columns: cols.map((c) => c.label), rows: data }) });
    if (!res.ok) throw new Error(`Export failed (${res.status})`);
    const blob = await res.blob();
    const a = el("a", { href: URL.createObjectURL(blob), download: /\d{4}-\d{2}-\d{2}$/.test(title) ? `${title}.xlsx` : `${title}-${new Date().toISOString().slice(0, 10)}.xlsx` });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  } catch (err) { toast(err.message, "error"); }
}

// Saved views dropdown for a list: getParams() -> {param: value}; apply(params) sets the filters and reloads.
function savedViewsControl(module, getParams, apply) {
  const sel = el("select", { class: "compact", "aria-label": "Saved views" });
  const wrap = el("div", { class: "field" }, el("label", null, "Saved views"), el("div", { class: "inline-actions" }, sel,
    el("button", { class: "btn secondary icon", type: "button", title: "Save current filters as a view", "aria-label": "Save current filters as a view", onclick: save },
      el("i", { class: "bi bi-bookmark-plus" })),
    el("button", { class: "btn secondary icon", type: "button", title: "Delete selected view", "aria-label": "Delete selected view", onclick: remove },
      el("i", { class: "bi bi-bookmark-x" }))));
  let views = [];
  async function load(selectId = null) {
    try { views = await API.get(`/api/views?module=${encodeURIComponent(module)}`); } catch { views = []; }
    sel.replaceChildren(el("option", { value: "" }, views.length ? "- choose a view -" : "- none saved -"),
      ...views.map((v) => el("option", { value: v.id, selected: v.id === selectId ? "1" : null }, v.name)));
  }
  sel.addEventListener("change", () => { const v = views.find((x) => String(x.id) === sel.value); if (v) apply(v.params); });
  function save() {
    const params = getParams();
    openForm({
      key: `view:${module}`, title: "Save view", width: 460, draftable: false,
      intro: Object.keys(params).length ? `Filters: ${Object.entries(params).map(([k, v]) => `${k} = ${v}`).join(", ")}` : "No filters set - the view will show everything.",
      fields: [{ name: "name", label: "View name", required: true, maxLength: 100, singleLine: true, full: true }],
      submitLabel: "Save view",
      onSubmit: (v) => API.post("/api/views", { module, name: v.name, params }),
      onDone: (saved) => { toast("View saved"); load(saved && saved.id); },
    });
  }
  async function remove() {
    if (!sel.value) { toast("Choose a saved view first", "error"); return; }
    try { await API.del(`/api/views/${sel.value}`); toast("View deleted"); load(); } catch (err) { toast(err.message, "error"); }
  }
  load();
  return wrap;
}

// ==================================================================== Excel import dialog

function importDialog({ title, templateKind, path, intro, onDone }) {
  const file = el("input", { type: "file", accept: ".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", id: "imp-file" });
  const out = el("div", { class: "import-out", "aria-live": "polite" });
  const commitBtn = el("button", { class: "btn", disabled: "1", style: "margin-left:auto" }, "Import");
  let instance;
  async function send(commit) {
    if (!file.files[0]) { toast("Choose an Excel file first", "error"); return null; }
    const fd = new FormData();
    fd.append("file", file.files[0]);
    try { return await API.upload(`${path}?commit=${commit}`, fd); } catch (err) { out.replaceChildren(el("div", { class: "form-banner error" }, err.message)); return null; }
  }
  async function check() {
    commitBtn.disabled = true;
    out.replaceChildren(el("div", { class: "muted" }, "Checking the file…"));
    const r = await send(false);
    if (!r) return;
    const nodes = [el("p", null, `${r.total_rows} row(s): ${r.to_create} to create`, r.to_update ? `, ${r.to_update} to update` : "", ".")];
    if (r.errors.length) {
      nodes.push(el("div", { class: "form-banner error" }, `${r.errors.length} problem(s) - fix them in Excel and choose the file again. Nothing has been imported.`),
        el("div", { class: "table-wrap" }, el("table", null, el("thead", null, el("tr", null, el("th", null, "Row"), el("th", null, "Column"), el("th", null, "Problem"))),
          el("tbody", null, ...r.errors.slice(0, 100).map((e) => el("tr", { class: "no-click" }, el("td", null, String(e.row)), el("td", null, e.field), el("td", null, e.message)))))));
    } else {
      nodes.push(el("div", { class: "form-banner ok" }, "No problems found. Review the preview, then choose Import."),
        el("div", { class: "table-wrap" }, el("table", null, el("thead", null, el("tr", null, ...Object.keys(r.preview[0] || {}).map((k) => el("th", null, k)))),
          el("tbody", null, ...r.preview.slice(0, 15).map((p) => el("tr", { class: "no-click" }, ...Object.values(p).map((v) => el("td", null, v === null ? "" : String(v)))))))));
      commitBtn.disabled = false;
    }
    out.replaceChildren(...nodes);
  }
  file.addEventListener("change", check);
  commitBtn.addEventListener("click", async () => {
    commitBtn.disabled = true;
    const r = await send(true);
    if (r && r.committed) { instance.close(true); toast(`Imported ${r.total_rows} row(s)`); if (onDone) onDone(r); }
  });
  instance = modal({
    title, width: 720,
    body: el("div", null,
      el("p", { class: "muted" }, intro),
      el("p", null, el("a", { href: `/api/import/${templateKind}/template.xlsx`, class: "btn small secondary" }, el("i", { class: "bi bi-download" }), " Download the template")),
      el("div", { class: "form-field" }, el("label", { for: "imp-file" }, "Excel file (.xlsx, up to 5 MB)"), file), out),
    footer: el("div", { class: "form-foot-wrap" }, el("button", { class: "btn secondary", onclick: () => instance.close() }, "Cancel"), commitBtn),
  });
}

// ==================================================================== global search (top bar)

function initGlobalSearch() {
  const input = qs("#globalSearch");
  const box = qs("#searchResults");
  if (!input || input.dataset.ready) return;
  input.dataset.ready = "1";
  let timer = null;
  let hits = [];
  let cursor = -1;
  const close = () => { box.classList.add("hidden"); input.setAttribute("aria-expanded", "false"); cursor = -1; };
  const open = (h) => {
    close(); input.value = "";
    if (h.type === "audit") return openAudit(h.id);
    if (h.type === "finding") return openLink("finding", h.id);
    if (h.type === "audit_report") return openLink("audit_report", h.id);
    if (h.type === "capa") return openRecord("capa", h.id);
    if (h.type === "nonconformance") return openRecord("nonconformances", h.id);
    if (h.type === "service_feedback") return openRecord("service-feedback", h.id);
    if (h.type === "organization") return openRecord("organizations", h.id);
    if (h.type === "stakeholder") return openRecord("stakeholders", h.id);
    if (h.type === "assurance_plan") return openPlan(h.id);
    if (h.type === "entity_unit") return navigate("universe");
    return null;
  };
  function paint() {
    clear(box);
    if (!hits.length) { box.append(el("div", { class: "sr-empty" }, "No matches.")); }
    hits.forEach((h, i) => box.append(el("button", { class: `sr-item ${i === cursor ? "active" : ""}`, type: "button", role: "option",
      id: `sr-${i}`, "aria-selected": i === cursor ? "true" : "false", onclick: () => open(h) },
    el("span", { class: "sr-type" }, h.type_label),
    el("span", { class: "sr-main" }, h.ref ? el("span", { class: "ref" }, `${h.ref} `) : null, h.title,
      h.subtitle ? el("span", { class: "muted small" }, ` · ${h.subtitle}`) : null),
    h.status ? badge(h.status) : null)));
    box.classList.remove("hidden");
    input.setAttribute("aria-expanded", "true");
    input.setAttribute("aria-activedescendant", cursor >= 0 ? `sr-${cursor}` : "");
  }
  input.addEventListener("input", () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 2) { close(); return; }
    timer = setTimeout(async () => {
      try { hits = await API.get(`/api/search?q=${encodeURIComponent(q)}`); cursor = -1; paint(); } catch { /* ignore */ }
    }, 250);
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { close(); input.blur(); return; }
    if (box.classList.contains("hidden") || !hits.length) return;
    if (e.key === "ArrowDown") { cursor = Math.min(hits.length - 1, cursor + 1); paint(); e.preventDefault(); }
    if (e.key === "ArrowUp") { cursor = Math.max(0, cursor - 1); paint(); e.preventDefault(); }
    if (e.key === "Enter") { open(hits[Math.max(cursor, 0)]); e.preventDefault(); }
  });
  document.addEventListener("click", (e) => { if (!box.contains(e.target) && e.target !== input) close(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) { e.preventDefault(); input.focus(); }
  });
}

// ==================================================================== in-app help

const HELP = {
  _default: { title: "Using the workspace", items: [
    "Use the search box at the top (press / ) to find any audit, finding, remediation, report or register entry by name or reference.",
    "Every form saves a draft as you type. If something goes wrong, reopen the form or go to My Drafts.",
    "Lists can be sorted by clicking a column, filtered, saved as a view, and exported to Excel or CSV.",
    "The bell shows what needs your attention: assignments, approvals, overdue items.",
  ] },
  dashboard: { title: "Dashboard", items: ["Your headline numbers and recent work. Select a row to open it.", "GPHA Workspace (in the sidebar) lists every module."] },
  apps: { title: "Apps & customization", items: [
    "Super Administrators only. Switch an app off to hide it from everyone; its data is kept and returns when you switch it back on.",
    "Rename an app to use GPHA's own terms, and set the workspace name shown in the sidebar and browser tab.",
    "Core apps (Dashboard, Audits, Assurance Plan, Audit Universe, Remediation, Evidence, Organizations) are always on.",
  ] },
  roles: { title: "Roles & permissions", items: [
    "There are five roles: Super Administrator (full control), Administrator, Manager, Auditor and Audit Client.",
    "Managers cover Unit Heads, Audit Managers, PIAs and the GM Audit: give each Manager its approval level. Working papers and reports are signed off Unit Head, then Audit Manager, then PIA; only the GM Audit (CAE) approves and distributes the plan and approves reports.",
    "The levels each document passes through are set under Configuration > Audit workflow (review chains).",
    "Only a Super Administrator changes the matrix (tick, untick, Save; Reset returns a role to the standard permissions) and appoints administrators.",
    "Change someone's role on the 'People by role' tab or under Profile & Users.",
  ] },
  programs: { title: "Project Library", items: [
    "Reusable work programmes maintained by the Audit Administrator: objectives, risks, controls and test steps.",
    "On an audit's Risk & Control Matrix tab, use 'Apply audit programme' to copy the steps into the engagement.",
  ] },
  evidence: { title: "Requests", items: [
    "Auditors request documents from the auditees assigned to an audit, with a due date.",
    "Auditees upload files and submit; the auditor accepts (optionally filing them as working papers) or returns them with a comment.",
  ] },
  governance: { title: "Governance portal", items: [
    "Read-only view for the Audit Committee and executive reviewers: approved plans, issued reports (Word / print) and headline KPIs.",
  ] },
  portfolio: { title: "Port portfolio", items: [
    "Audits, open findings and remediation by port. A PIA sees their own port (set 'Where I work' on the profile); the GM Audit sees every port.",
  ] },
  workspace: { title: "All apps", items: ["Every app in one place, grouped by solution like the sidebar (Audit, Resource, Risk and Compliance management; Analytics & reporting; Platform settings), with live counts. Quick actions start the most common work."] },
  plans: { title: "Assurance Plans", items: [
    "The annual risk-based plan (IIA GIAS 9.4). Add engagements from the Audit Universe, then submit for CAE approval.",
    "Follow the annual planning cycle card: preparation, universe review, managers' meeting, draft, internal review (e-sign), submission, Audit Committee decision, approved version, GM distribution, execution.",
    "Once the approved version has been distributed, PIAs and Audit Managers start engagements to create their audit projects.",
  ] },
  universe: { title: "Audit Universe", items: [
    "Auditable units with an inherent risk rating (likelihood × impact, 1-5 each). The rating drives the plan and the heat map.",
    "Admins can import or update the whole universe from Excel: Import from Excel → download the template → fill → upload. The file is checked first; nothing is saved if any row has a problem.",
  ] },
  audits: { title: "Audits", items: [
    "Order of work: Planning memo (approved) → Risk & Control Matrix → tests and review → findings → report → remediation.",
    "Fieldwork can only start once the planning memo is approved (configurable by the Admin).",
    "Log your hours under Time entries so budget versus actual stays current.",
    "Reviewers raise review notes on the audit, working papers, tests or findings; the preparer answers and the reviewer clears them. Open notes block closure.",
    "Give working papers an index reference (A.1, B.2) and link them to the test or finding they support; a reviewer signs each one off.",
    "Record the exit meeting on the Results tab before the report goes for approval.",
    "After closure another auditor completes the Reviews tab (quality review); auditees receive the satisfaction survey.",
  ] },
  capa: { title: "Remediation & Follow-up", items: [
    "Register: every agreed action. Follow-up: overdue actions, escalation and those awaiting validation.",
    "The owner records implementation evidence; an auditor validates it. Only an Effective validation allows closure.",
  ] },
  analytics: { title: "Analytics", items: [
    "KPIs compare actual performance with the targets set on the Configuration screen.",
    "Repeat findings flag issues found again in later audits - a sign remediation did not hold.",
  ] },
  qaip: { title: "Quality (QAIP)", items: ["Results of engagement quality reviews and auditee surveys for the year, and the weakest checklist areas to improve."] },
  capacity: { title: "Timesheets & capacity", items: [
    "Team capacity compares hours planned on the Assurance Plan with each auditor's available hours.",
    "Log time daily in quarter hours. Audit and Follow-up time must name the audit.",
  ] },
  criteria: { title: "Criteria library", items: [
    "Laws, regulations, GPHA policies and standards that findings are measured against (the 'what should be').",
    "Pick a criterion in a finding's form to fill its Criteria box; the library counts where each one is used. Retire criteria that no longer apply.",
  ] },
  committee: { title: "Committee pack", items: ["Summary for the Audit Committee; download the Word pack for the meeting."] },
  configuration: { title: "Configuration", items: ["Business rules, SLAs, escalation, KPI targets and security settings. Every change is logged."] },
};

function openHelp() {
  const h = HELP[state.view] || HELP._default;
  const body = el("div", { class: "help-body" },
    el("ul", { class: "help-list" }, ...h.items.map((t) => el("li", null, t))),
    h !== HELP._default ? el("div", null, el("h4", null, HELP._default.title), el("ul", { class: "help-list" }, ...HELP._default.items.map((t) => el("li", null, t)))) : null,
    el("h4", null, "Keyboard"),
    el("ul", { class: "help-list" }, el("li", null, el("kbd", null, "/"), " search · ", el("kbd", null, "Esc"), " close a dialog · ", el("kbd", null, "Tab"), " move between controls · ", el("kbd", null, "Enter"), " open the selected row")));
  modal({ title: `Help · ${h.title}`, body, width: 620 });
}

// Skills matrix (GIAS 10.2): auditors down, skills and certifications across.
function skillsMatrix(auditors) {
  const card = el("div", { class: "card" }, el("h3", null, "Skills matrix"),
    el("p", { class: "muted small" }, "Who holds which skill or certification. Gaps show where training, co-sourcing or guest auditors are needed. Select a name to update a profile."));
  const skills = [...new Set(auditors.flatMap((a) => a.skills))].sort((x, y) => x.localeCompare(y));
  const certs = [...new Set(auditors.flatMap((a) => a.certifications || []))].sort((x, y) => x.localeCompare(y));
  const cols = [...skills.map((k) => ({ k, cert: false })), ...certs.map((k) => ({ k, cert: true }))];
  if (!cols.length) { card.append(el("div", { class: "empty" }, "No skills recorded yet. Open Team capacity and select an auditor to add skills.")); return card; }
  const has = (a, c) => (c.cert ? (a.certifications || []) : a.skills).some((x) => x.toLowerCase() === c.k.toLowerCase());
  card.append(el("div", { class: "table-wrap" }, el("table", { class: "matrix" },
    el("thead", null, el("tr", null, el("th", null, "Auditor"),
      ...cols.map((c) => el("th", { class: "mx-col", title: c.cert ? "Certification" : "Skill" }, el("span", null, c.k, c.cert ? " (cert.)" : ""))))),
    el("tbody", null,
      ...auditors.map((a) => el("tr", { tabindex: "0", onclick: () => profileForm(a, () => renderCapacity("skills")),
        onkeydown: (e) => { if (e.key === "Enter") profileForm(a, () => renderCapacity("skills")); } },
      el("td", null, a.name, a.grade ? el("div", { class: "muted small" }, a.grade) : null),
      ...cols.map((c) => el("td", { class: "mx-cell" }, has(a, c) ? el("i", { class: "bi bi-check-circle-fill mx-yes", "aria-label": "Yes" }) : el("span", { class: "mx-no", "aria-label": "No" }, "·"))))),
      el("tr", { class: "no-click mx-total" }, el("td", null, el("strong", null, "Holders")),
        ...cols.map((c) => { const n = auditors.filter((a) => has(a, c)).length; return el("td", { class: `mx-cell ${n <= 1 ? "txt-warn" : ""}` }, String(n)); }))))));
  return card;
}
