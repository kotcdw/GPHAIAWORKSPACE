// Reports app (Reports and Dashboards & Presentations walkthroughs): Browse (By Folder, Recent), the Report
// Builder (Report / Data / Charts / Design / Publish), the Dashboard and Present builders (widgets on a canvas,
// preview, publish) and AI Reporting (New report / Reports / Workstreams).
// Every run uses the viewer's own access, so sharing never shows anyone data they could not see themselves.

const REP = { views: null, groups: null, staff: null, folders: null, audits: null };
const REP_KINDS = { report: "Report", dashboard: "Dashboard", presentation: "Presentation" };
const REP_THEMES = ["Default", "Harbour", "Slate", "High contrast"];

async function repViews() { if (!REP.views) REP.views = await safeGet("/api/reporting/views", []); return REP.views; }
async function repGroups() { if (!REP.groups) REP.groups = await safeGet("/api/groups", []); return REP.groups; }
async function repStaff() { if (!REP.staff) REP.staff = await safeGet("/api/users/directory", []); return REP.staff; }
async function repFolders() { if (!REP.folders) REP.folders = await safeGet("/api/reporting/folders", ["My Reports"]); return REP.folders; }
async function repAudits() { if (!REP.audits) REP.audits = await safeGet("/api/audits", []); return REP.audits; }

// ------------------------------------------------------------------ the Reports frame

const REP_SIDE = [{ key: "browse", label: "Browse" }, { key: "report", label: "Reports" }, { key: "dashboard", label: "Dashboards" },
  { key: "presentation", label: "Presentations" }, { key: "ai", label: "AI Reporting" }];

function repCreateMenu() {
  return wsMenu("Create", [["Report", () => reportBuilder(null)], ["Dashboard", () => createBoardPage("dashboard")],
    ["Present", () => createBoardPage("presentation")]]);
}

function repFrame(active, { crumb = [], title = null, actions = [] } = {}) {
  return wsPage({ app: "Reports", side: REP_SIDE, active, sideLabel: "Reports pages",
    onSide: (k) => (k === "ai" ? renderAiReporting("new") : renderReportsApp(k)),
    util: [{ label: "Storyboards", icon: "easel", onClick: () => navigate("storyboards") }],
    crumb: [{ label: "Reports", onClick: () => renderReportsApp("browse") }, ...crumb], title, actions });
}

async function renderReportsApp(page = state.reportsPage || "browse", sub = null) {
  if (page === "ai") { renderAiReporting("new"); return; }
  state.reportsPage = page;
  if (page === "browse") { renderBrowse(sub); return; }
  const f = repFrame(page, { crumb: [REP_KINDS[page] ? `${REP_KINDS[page]}s` : page], title: `${REP_KINDS[page]}s`,
    actions: [wsAction(`Create ${page === "presentation" ? "Present" : REP_KINDS[page]}`, () => (page === "report" ? reportBuilder(null) : createBoardPage(page)), { primary: true, icon: "plus-lg" })] });
  f.body.append(loadingState());
  const items = await safeGet(`/api/reporting/items?kind=${page}`, []);
  clear(f.body);
  f.body.append(itemTable(items));
}

function itemTable(items, { empty = "Nothing here yet" } = {}) {
  if (!items.length) return emptyState({ icon: "file-earmark-bar-graph", title: empty });
  return dataTable(items, [
    { key: "name", label: "Name" },
    { key: "kind", label: "Type", render: (i) => REP_KINDS[i.kind] },
    { key: "folder", label: "Folder" },
    { key: "status", label: "Status", render: (i) => wsTag(i.status, i.status === "Active" ? "ok" : "") },
    { key: "access", label: "Access" }, { key: "owner", label: "Owner" },
    { key: "updated_at", label: "Updated", render: (i) => fmtDay(String(i.updated_at).slice(0, 10)) },
  ], { onRow: (i) => openReportItem(i.id), pageSize: 25 });
}

// Browse › By Folder / Recent. A folder is Templates, My Reports, Shared Reports or a configured folder.
async function renderBrowse(folder = null, mode = "folder") {
  const f = repFrame("browse", { crumb: ["Browse", folder ? folder.label : null], title: folder ? folder.label : "Browse content",
    actions: [repCreateMenu()] });
  if (!folder) {
    f.body.append(el("div", { class: "ws-flow", role: "tablist" },
      ...[["folder", "By Folder"], ["recent", "Recent"]].map(([k, l]) => el("button", { type: "button", role: "tab", class: k === mode ? "on" : "",
        "aria-selected": k === mode ? "true" : "false", onclick: () => renderBrowse(null, k) }, l))));
    if (mode === "recent") {
      const items = await safeGet("/api/reporting/items", []);
      f.body.append(itemTable(items.sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at))).slice(0, 25)));
      return;
    }
    const folders = await repFolders();
    const rows = [{ key: "templates", label: "Templates" }, { key: "mine", label: "My Reports" }, { key: "shared", label: "Shared Reports" },
      ...folders.filter((x) => x !== "My Reports").map((x) => ({ key: `folder:${x}`, label: x }))];
    f.body.append(el("div", { class: "ws-card" }, ...rows.map((r) => wsRow(r.label, "›", { class: "ws-row clickable", role: "button", tabindex: "0",
      onclick: () => renderBrowse(r), onkeydown: (e) => { if (e.key === "Enter") renderBrowse(r); } }))));
    return;
  }
  f.setCrumb([{ label: "Reports", onClick: () => renderReportsApp("browse") }, { label: "Browse", onClick: () => renderBrowse() }, folder.label]);
  if (folder.key === "templates") {
    const ts = await safeGet("/api/reporting/templates", []);
    const copy = async (t) => {
      try { const it = await API.post(`/api/reporting/templates/${t.key}/copy`); toast(`${it.name} saved as a draft in My Reports`); reportBuilder(it); }
      catch (err) { toast(err.message, "error"); }
    };
    if (!ts.length) { f.body.append(emptyState({ icon: "files", title: "No templates for the data you can see" })); return; }
    f.body.append(el("div", { class: "ws-card" }, ...ts.map((t) => {
      const row = wsRow(el("span", null, el("strong", null, t.name), el("span", { class: "ws-caption" }, t.description)),
        wsMenu("Actions", [["Make a copy", () => copy(t)]]));
      row.addEventListener("contextmenu", (e) => { e.preventDefault(); row.querySelector(".ws-menu .ws-action").click(); });
      return row;
    })));
    return;
  }
  const q = folder.key === "mine" ? "scope=mine" : folder.key === "shared" ? "scope=shared" : `folder=${encodeURIComponent(folder.key.slice(7))}`;
  const items = await safeGet(`/api/reporting/items?${q}`, []);
  f.body.append(itemTable(items, { empty: "This folder is empty" }));
}

// ------------------------------------------------------------------ result rendering (reports, widgets, AI facts)

function resultMeta(res) {
  return el("div", { class: "ws-caption rep-meta" },
    el("span", null, el("strong", null, "Source: "), res.source), " · ",
    el("span", null, el("strong", null, "Filters: "), res.filters_text), " · ",
    el("span", null, el("strong", null, "Period: "), res.period_text), " · ",
    el("span", null, el("strong", null, "Access: "), res.scope_text), " · ",
    el("span", null, `Run ${fmtDate(res.generated_at)}`));
}

function lineChart(title, groups) {
  const max = Math.max(1, ...groups.map((g) => g.count));
  const w = 320; const hgt = 120; const step = groups.length > 1 ? w / (groups.length - 1) : 0;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${w} ${hgt + 10}`); svg.setAttribute("class", "rep-line"); svg.setAttribute("aria-hidden", "true");
  const line = document.createElementNS(svg.namespaceURI, "polyline");
  line.setAttribute("points", groups.map((g, i) => `${i * step},${hgt - (hgt * g.count) / max + 5}`).join(" "));
  line.setAttribute("fill", "none"); line.style.stroke = "var(--accent)"; line.setAttribute("stroke-width", "2");
  svg.append(line);
  return el("figure", { class: "chart-card", role: "group", "aria-label": `${title}: ${groups.map((g) => `${g.value} ${g.count}`).join(", ")}` },
    el("figcaption", null, title), svg, el("div", { class: "muted small" }, groups.map((g) => `${g.value}: ${g.count}`).join(" · ")));
}

function resultChart(res) {
  if (!res.groups || !res.groups.length || !res.chart) return null;
  const label = (res.columns.find((c) => c.key === res.group_by) || {}).label || res.group_by;
  const items = res.groups.map((g) => ({ label: g.value, count: g.count }));
  if (res.chart === "pie") return donutChart(`By ${label}`, items, SEVERITY_TONES, "records");
  if (res.chart === "line") return lineChart(`By ${label}`, res.groups);
  const max = Math.max(1, ...res.groups.map((g) => g.count));
  return el("figure", { class: "chart-card", role: "group", "aria-label": `By ${label}: ${items.map((i) => `${i.label} ${i.count}`).join(", ")}` },
    el("figcaption", null, `By ${label}`),
    el("div", { class: "hbars" }, ...res.groups.map((g) => el("div", { class: "hbar" },
      el("span", { class: "hbar-label", title: g.value }, g.value),
      el("span", { class: "hbar-track" }, el("span", { class: "hbar-fill", style: `width:${(100 * g.count) / max}%` })),
      el("span", { class: "num" }, String(g.count))))));
}

function resultTable(res, pageSize = 25) {
  return dataTable(res.rows, res.columns.map((c) => ({ key: c.key, label: c.label, num: c.type === "number",
    render: c.type === "date" ? (r) => (r[c.key] ? fmtDay(r[c.key]) : "-") : null })), { pageSize });
}

// visualization: "table", "chart" or "both" (dashboard and slide widgets); compact for widgets.
function resultView(res, { compact = false, visualization = "both", meta = true } = {}) {
  const box = el("div", { class: "rep-result" }, meta ? resultMeta(res) : null);
  box.append(el("p", null, el("strong", null, String(res.total)), ` record${res.total === 1 ? "" : "s"}`,
    res.truncated ? el("span", { class: "muted small" }, ` (first ${res.rows.length} shown)`) : null));
  const chart = visualization === "table" ? null : resultChart(res);
  if (chart) box.append(chart);
  if (visualization !== "chart" || !chart) box.append(resultTable(res, compact ? 5 : 25));
  return box;
}

// ------------------------------------------------------------------ audience (Public to folder users / Private)

async function audienceFields(item) {
  const [staff, groups] = await Promise.all([repStaff(), repGroups()]);
  const name = `acc-${Math.random().toString(36).slice(2, 7)}`;
  const radio = (v, label) => el("label", { class: "check" }, el("input", { type: "radio", name, value: v, checked: (item.access || "Private") === v ? "1" : null }), ` ${label}`);
  const pub = radio("Public", "Public to folder users");
  const priv = radio("Private", "Private users/groups");
  const users = new Set(item.user_ids || []);
  const gids = new Set(item.group_ids || []);
  const pick = (rows, chosen, label) => el("fieldset", { class: "ws-list-pick" }, el("legend", { class: "ws-caption" }, label),
    ...rows.map((r) => el("label", { class: "check" }, el("input", { type: "checkbox", value: String(r.id), checked: chosen.has(r.id) ? "1" : null }), ` ${r.name}`)));
  const userBox = pick(staff.filter((u) => u.id !== state.user.id), users, "Users");
  const groupBox = pick(groups, gids, "Groups");
  const who = el("div", { class: "ws-grid" }, userBox, groupBox);
  const access = () => (pub.querySelector("input").checked ? "Public" : "Private");
  const sync = () => { who.hidden = access() !== "Private"; };
  [pub, priv].forEach((r) => r.querySelector("input").addEventListener("change", sync));
  sync();
  const picked = (box) => [...box.querySelectorAll("input:checked")].map((b) => Number(b.value));
  return {
    node: el("div", { class: "ws-field-c" }, el("div", { class: "ws-inline" }, pub, priv), who),
    value: () => ({ access: access(), user_ids: access() === "Private" ? picked(userBox) : [], group_ids: access() === "Private" ? picked(groupBox) : [] }),
  };
}

// Publish page shared by reports, dashboards and presentations: details, folder, access, settings, Save.
async function publishFields(item, { settings = false } = {}) {
  const folders = await repFolders();
  const name = wsInput(item.name || "", { name: "name", maxlength: "200" });
  const desc = wsText(item.description || "", { name: "description", rows: "2", maxlength: "4000" });
  const folder = wsSelect(folders, item.folder || "My Reports", { name: "folder" });
  const aud = await audienceFields(item);
  const s = item.settings || { show_on_browse: true, allow_dashboards: true };
  const browse = el("input", { type: "checkbox", checked: s.show_on_browse ? "1" : null });
  const dash = el("input", { type: "checkbox", checked: s.allow_dashboards ? "1" : null });
  const rows = [
    { label: "Name", control: name }, { label: "Description", control: desc }, { label: "Folder", control: folder },
    { label: `${REP_KINDS[item.kind] || "Report"} access`, control: aud.node },
    settings ? { label: "Distribution / export", control: el("div", { class: "ws-inline" }, wsTag("Email"), wsTag("Export"), el("span", { class: "ws-caption" }, "on the active report")) } : null,
    settings ? { label: "Report settings", control: el("div", { class: "ws-inline" }, el("label", null, browse, " Show on Browse"), el("label", null, dash, " Add to dashboards")) } : null,
  ];
  return {
    node: wsFieldRows(rows),
    value: () => ({ name: name.value.trim(), description: desc.value, folder: folder.value, ...aud.value(),
      ...(settings ? { settings: { show_on_browse: browse.checked, allow_dashboards: dash.checked } } : {}) }),
  };
}

// Save → Draft / Save → Activate: create or update, then set the status. Returns the saved item or null.
async function saveItem(item, body, activate, container) {
  try {
    let saved = item.id ? await API.patch(`/api/reporting/items/${item.id}`, body) : await API.post("/api/reporting/items", { kind: item.kind, ...body });
    if (activate && saved.status !== "Active") saved = await API.patch(`/api/reporting/items/${saved.id}`, { status: "Active" });
    if (!activate && saved.status === "Active" && item.id) saved = await API.patch(`/api/reporting/items/${saved.id}`, { status: "Draft" });
    toast(activate ? `${saved.name} is active` : `${saved.name} saved as a draft`);
    return saved;
  } catch (err) {
    if (container) wsShowErrors(container, err); else toast(err.message, "error");
    return null;
  }
}

// ------------------------------------------------------------------ Report Builder

async function reportBuilder(item) {
  const vs = await repViews();
  if (!vs.length) { toast("No data views are available to you", "error"); return; }
  const it = item ? { ...item } : { kind: "report", name: "", description: "", folder: "My Reports", access: "Private", user_ids: [], group_ids: [] };
  const def = it.definition ? { ...it.definition } : { view: null, columns: [], filters: [], period: null, group_by: null, chart: null, sort: null };
  let page = def.view ? "data" : "report";
  const f = wsPage({ app: "Report Builder", context: it.name || "New report",
    side: [{ key: "report", label: "Report" }, { key: "data", label: "Data" }, { key: "charts", label: "Charts" }, { key: "design", label: "Design" }, { key: "publish", label: "Publish" }],
    active: page, onSide: (k) => go(k), sideLabel: "Report Builder pages",
    util: [{ label: it.status || "Draft" }, { label: "Close", icon: "x-lg", onClick: () => (it.id ? openReportItem(it.id) : renderReportsApp("browse")) }] });
  const view = () => vs.find((v) => v.key === def.view);
  const col = (k) => (view() ? view().columns.find((c) => c.key === k) : null);
  const spec = () => ({
    view: def.view, columns: def.columns.filter((k) => col(k)),
    filters: (def.filters || []).filter((x) => x.column && (["empty", "not_empty"].includes(x.op) || `${x.value ?? ""}`.trim())),
    period: def.period && (def.period.date_from || def.period.date_to) ? def.period : null,
    group_by: def.group_by || null, chart: def.group_by ? def.chart || null : null, sort: def.sort || null, sort_desc: !!def.sort_desc,
  });
  const preview = async (box, opts = {}) => {
    clear(box); box.append(loadingState("Running…"));
    try { const res = await API.post("/api/reporting/run", spec()); clear(box); box.append(resultView(res, opts)); }
    catch (err) { clear(box); box.append(errorState(err)); }
  };
  function go(k) {
    if (k !== "report" && !def.view) { toast("Select a View first", "error"); k = "report"; }
    page = k; f.setActive(k); clear(f.body);
    ({ report: pageReport, data: pageData, charts: pageCharts, design: pageDesign, publish: pagePublish })[k]();
  }
  function pageReport() {
    f.setCrumb([it.name || "New Report", "Data source"]);
    f.setHead("Select a View", [wsAction("Next", () => go("data"), { primary: true })]);
    const sel = wsSelect([{ value: "", label: "Choose a View" }, ...vs.map((v) => ({ value: v.key, label: v.label }))], def.view || "", { name: "view" });
    const fields = el("div");
    const paint = () => {
      clear(fields);
      const v = view();
      if (!v) return;
      const by = (t) => v.columns.filter((c) => (t === "number" ? c.type === "number" : t === "date" ? c.type === "date" : !["number", "date"].includes(c.type))).map((c) => c.label).join(" · ") || "-";
      fields.append(wsCard("Available fields", wsRow("Dimensions", by("text")), wsRow("Metrics", by("number")), wsRow("Dates", by("date"))));
    };
    sel.addEventListener("change", () => {
      if (sel.value !== def.view) Object.assign(def, { view: sel.value || null, columns: [], filters: [], period: null, group_by: null, chart: null, sort: null });
      paint();
    });
    f.body.append(wsFieldRows([{ label: "View", control: sel }]), fields);
    paint();
  }
  function pageData() {
    const v = view();
    f.setCrumb(["Report Builder", "Data"]);
    f.setHead("Build the report table", [wsAction("Preview", () => preview(out, { compact: true }), { icon: "play" })]);
    const kind = (c) => (c.type === "number" ? "Metric" : c.type === "date" ? "Date" : "Dimension");
    const cols = el("div", { class: "ws-thumbs rep-drop", "aria-label": "Columns" });
    const out = el("div");
    const paintCols = () => {
      clear(cols);
      if (!def.columns.length) cols.append(el("span", { class: "ws-caption" }, "Drag fields here, or select them in the field list"));
      def.columns.forEach((k, i) => {
        const c = col(k);
        if (!c) return;
        const chip = el("div", { class: "ws-thumb", draggable: "true" }, el("span", { class: "ws-drag", "aria-hidden": "true" }, "⋮⋮"), el("span", null, c.label),
          el("span", { style: "margin-left:auto" }, iconBtn("arrow-up", `Move ${c.label} left`, () => { if (i) { [def.columns[i - 1], def.columns[i]] = [def.columns[i], def.columns[i - 1]]; paintCols(); } }),
            iconBtn("x-lg", `Remove ${c.label}`, () => { def.columns.splice(i, 1); paintCols(); paintList(); })));
        chip.addEventListener("dragstart", (e) => e.dataTransfer.setData("text/col-index", String(i)));
        chip.addEventListener("dragover", (e) => { e.preventDefault(); chip.classList.add("over"); });
        chip.addEventListener("dragleave", () => chip.classList.remove("over"));
        chip.addEventListener("drop", (e) => {
          e.preventDefault(); e.stopPropagation();
          const from = e.dataTransfer.getData("text/col-index");
          const field = e.dataTransfer.getData("text/field");
          if (from !== "") { const [m] = def.columns.splice(Number(from), 1); def.columns.splice(i, 0, m); } else if (field && !def.columns.includes(field)) def.columns.splice(i, 0, field);
          paintCols(); paintList();
        });
        cols.append(chip);
      });
    };
    cols.addEventListener("dragover", (e) => { e.preventDefault(); cols.classList.add("drop"); });
    cols.addEventListener("dragleave", () => cols.classList.remove("drop"));
    cols.addEventListener("drop", (e) => {
      e.preventDefault(); cols.classList.remove("drop");
      const field = e.dataTransfer.getData("text/field");
      if (field && !def.columns.includes(field)) { def.columns.push(field); paintCols(); paintList(); }
    });
    const search = wsInput("", { type: "search", placeholder: "Search fields", "aria-label": "Search fields" });
    const list = el("div", { class: "ws-list-pick" });
    const paintList = () => {
      clear(list);
      const q = search.value.trim().toLowerCase();
      v.columns.filter((c) => !q || c.label.toLowerCase().includes(q)).forEach((c) => {
        const on = def.columns.includes(c.key);
        const b = el("input", { type: "checkbox", checked: on ? "1" : null, "aria-label": c.label });
        b.addEventListener("change", () => { if (b.checked) def.columns.push(c.key); else def.columns = def.columns.filter((k) => k !== c.key); paintCols(); });
        const row = el("label", { class: "ws-row", draggable: "true" }, el("span", { class: "ws-row-l" }, b, ` ${c.label}`), el("span", { class: "ws-caption" }, kind(c)));
        row.addEventListener("dragstart", (e) => e.dataTransfer.setData("text/field", c.key));
        list.append(row);
      });
    };
    search.addEventListener("input", paintList);
    const opLabels = { eq: "is", ne: "is not", contains: "contains", gte: "≥", lte: "≤", empty: "is empty", not_empty: "is not empty" };
    const filtersBox = el("div", { class: "rep-filters" });
    const paintFilters = () => {
      def.filters = def.filters || [];
      filtersBox.replaceChildren(...def.filters.map((x, i) => {
        const c = wsSelect(v.columns.map((cc) => ({ value: cc.key, label: cc.label })), x.column, { "aria-label": "Filter field" });
        const op = wsSelect(Object.entries(opLabels).map(([k, l]) => ({ value: k, label: l })), x.op, { "aria-label": "Operator" });
        const val = wsInput(x.value ?? "", { "aria-label": "Value" });
        c.addEventListener("change", () => { x.column = c.value; });
        op.addEventListener("change", () => { x.op = op.value; });
        val.addEventListener("input", () => { x.value = val.value; });
        return el("div", { class: "rep-filter" }, c, op, val, iconBtn("x-lg", "Remove filter", () => { def.filters.splice(i, 1); paintFilters(); }));
      }), el("div", null, wsAction("+ Filter", () => { def.filters.push({ column: v.columns[0].key, op: "eq", value: "" }); paintFilters(); })));
    };
    const dates = v.columns.filter((c) => c.type === "date");
    const pcol = wsSelect(dates.map((c) => ({ value: c.key, label: c.label })), (def.period && def.period.column) || v.date_column || "", { "aria-label": "Period field" });
    const pfrom = wsInput((def.period && def.period.date_from) || "", { type: "date", "aria-label": "From" });
    const pto = wsInput((def.period && def.period.date_to) || "", { type: "date", "aria-label": "To" });
    const syncPeriod = () => { def.period = pfrom.value || pto.value ? { column: pcol.value, date_from: pfrom.value || null, date_to: pto.value || null } : null; };
    [pcol, pfrom, pto].forEach((x) => x.addEventListener("change", syncPeriod));
    const sort = wsSelect([{ value: "", label: "Default order" }, ...v.columns.map((c) => ({ value: c.key, label: c.label }))], def.sort || "", { "aria-label": "Sort by" });
    const desc = el("input", { type: "checkbox", checked: def.sort_desc ? "1" : null });
    sort.addEventListener("change", () => { def.sort = sort.value || null; });
    desc.addEventListener("change", () => { def.sort_desc = desc.checked; });
    f.body.append(el("div", { class: "rep-builder" },
      wsCard("Field list", search, list),
      el("div", null,
        wsCard("Columns", cols),
        wsCard("Filters", filtersBox),
        wsCard("Period", dates.length ? el("div", { class: "ws-inline" }, pcol, pfrom, pto) : el("span", { class: "ws-caption" }, "This View has no dates")),
        wsCard("Sort", el("div", { class: "ws-inline" }, sort, el("label", null, desc, " Descending"))),
        wsCard("Report preview", out))));
    paintList(); paintCols(); paintFilters();
    preview(out, { compact: true, meta: false });
  }
  function pageCharts() {
    const v = view();
    f.setCrumb(["Report Builder", "Charts"]);
    f.setHead("Visualize the report data");
    const groupable = v.columns.filter((c) => c.type !== "number");
    const type = wsSelect([{ value: "auto", label: "Auto Chart" }, { value: "bar", label: "Bar" }, { value: "pie", label: "Pie" }, { value: "line", label: "Line" }, { value: "", label: "No chart" }],
      def.group_by ? def.chart || "auto" : "", { "aria-label": "Chart type" });
    const color = wsSelect([{ value: "", label: "Choose a field" }, ...groupable.map((c) => ({ value: c.key, label: c.label }))], def.group_by || "", { "aria-label": "Color (group by)" });
    const out = el("div");
    const apply = () => {
      def.group_by = type.value ? color.value || null : null;
      def.chart = def.group_by ? (type.value === "auto" ? "bar" : type.value) : null;
      preview(out, { visualization: "chart", meta: false });
    };
    type.addEventListener("change", apply);
    color.addEventListener("change", apply);
    f.body.append(wsFieldRows([{ label: "Chart type", control: type }, { label: "Color / group by", control: color }, { label: "Size / value", control: el("span", null, "Record count") }]),
      wsCard("Chart builder", out));
    preview(out, { visualization: "chart", meta: false });
  }
  function pageDesign() {
    f.setCrumb(["Report Builder", "Design"]);
    const out = el("div", { class: "rep-design" });
    f.setHead("Review and format", [
      wsAction("Fit to page", () => out.classList.toggle("fit"), { icon: "arrows-angle-contract" }),
      wsAction("Print", () => window.print(), { icon: "printer" })]);
    f.body.append(el("div", { class: "ws-slide rep-page" }, el("h3", null, it.name || "Untitled report"),
      it.description ? el("p", { class: "ws-caption" }, it.description) : null, out));
    preview(out);
  }
  async function pagePublish() {
    f.setCrumb(["Publish", "Save Report"]);
    f.setHead("Set report details and access");
    const pub = await publishFields(it, { settings: true });
    const box = el("div", null, pub.node);
    const save = async (activate) => {
      const body = { ...pub.value(), definition: spec() };
      if (body.name.length < 2) { wsShowErrors(box, { message: "Name the report", errors: [{ field: "name", message: "Enter a name" }] }); return; }
      const saved = await saveItem(it, body, activate, box);
      if (saved) openReportItem(saved.id);
    };
    box.append(wsToolbar(wsAction("Save → Draft", () => save(false)), wsAction("Save → Activate", () => save(true), { primary: true })));
    f.body.append(box);
  }
  go(page);
}

// ------------------------------------------------------------------ saved item: report view, dashboard view, presentation

async function openReportItem(id, ctx = {}) {
  const f0 = repFrame("browse", { crumb: ["…"] });
  f0.body.append(loadingState());
  const qs = new URLSearchParams(Object.entries(ctx).filter(([, v]) => v)).toString();
  let it;
  try { it = await API.get(`/api/reporting/items/${id}/run${qs ? `?${qs}` : ""}`); }
  catch (err) { clear(f0.body); f0.body.append(errorState(err, () => renderReportsApp("browse"))); return; }
  const path = `/api/reporting/items/${id}`;
  const reload = () => openReportItem(id, ctx);
  const more = it.can_edit ? wsMenu("More", [
    it.status === "Active" ? ["Back to draft", async () => { try { await API.patch(path, { status: "Draft" }); reload(); } catch (err) { toast(err.message, "error"); } }] : null,
    ["Archive", async () => {
      const ok = await confirmDialog({ title: `Archive ${it.name}`, text: "It is kept and can be restored.", confirmLabel: "Archive" });
      if (!ok.ok) return;
      try { await API.del(path); toast("Archived"); renderReportsApp(it.kind); } catch (err) { toast(err.message, "error"); }
    }]]) : null;
  const edit = it.can_edit ? wsAction("Edit", () => (it.kind === "report" ? reportBuilder(it) : boardBuilder(it))) : null;
  const email = it.status === "Active" ? wsAction("Email", () => emailDialog(it), { icon: "envelope" }) : null;
  const actions = it.kind === "report" ? [
    hasPerm("data.export") ? wsMenu("Export Download", [["Excel", () => { window.location.href = `${path}/export?format=xlsx`; }], ["CSV", () => { window.location.href = `${path}/export?format=csv`; }]]) : null,
    email, it.settings.allow_dashboards || it.can_edit ? wsAction("Add to dashboard", () => addToDashboard(it), { icon: "grid-1x2" }) : null, edit, more]
    : [it.kind === "presentation" ? wsAction("Present", () => presentSlides(it), { primary: true, icon: "play-fill" }) : null, email, edit, more];
  const f = repFrame(it.kind, { crumb: [{ label: `${REP_KINDS[it.kind]}s`, onClick: () => renderReportsApp(it.kind) }, it.name], title: it.name, actions });
  f.body.append(el("div", { class: "ws-inline rep-tags" }, wsTag(it.status, it.status === "Active" ? "ok" : ""), wsTag(it.access), wsTag(it.folder),
    it.owner ? el("span", { class: "ws-caption" }, `Owner: ${it.owner}`) : null));
  if (it.description) f.body.append(el("p", { class: "ws-caption" }, it.description));
  if (it.kind === "report") { f.body.append(resultView(it.result)); return; }
  if (it.kind === "dashboard") {
    f.body.append(boardView(it.definition.layout, it.tabs, { ctx, onFilter: (c) => openReportItem(id, c) }));
    return;
  }
  f.body.append(el("div", { class: "ws-thumbs" }, ...it.slides.map((s, i) => el("button", { class: "ws-thumb", type: "button", onclick: () => presentSlides(it, i) },
    el("strong", null, `${i + 1}.`), ` ${s.name}`, el("span", { class: "ws-caption", style: "margin-left:auto" }, `${s.widgets.length} item${s.widgets.length === 1 ? "" : "s"}`)))));
}

async function emailDialog(it) {
  const [staff, groups] = await Promise.all([repStaff(), repGroups()]);
  const pick = (rows, label) => el("fieldset", { class: "ws-list-pick" }, el("legend", { class: "ws-caption" }, label),
    ...rows.map((r) => el("label", { class: "check" }, el("input", { type: "checkbox", value: String(r.id) }), ` ${r.name}`)));
  const users = pick(staff.filter((u) => u.id !== state.user.id), "Users");
  const gs = pick(groups, "Groups");
  const msg = wsText("", { rows: "3", maxlength: "2000", "aria-label": "Message" });
  const ids = (box) => [...box.querySelectorAll("input:checked")].map((b) => Number(b.value));
  const dlg = modal({ title: `Email · ${it.name}`, width: 620,
    body: el("div", null, el("div", { class: "ws-grid" }, users, gs), wsField("Message", msg)),
    footer: wsToolbar(wsAction("Cancel", () => dlg.close()), wsAction("Send", async () => {
      try {
        const r = await API.post(`/api/reporting/items/${it.id}/email`, { user_ids: ids(users), group_ids: ids(gs), message: msg.value });
        toast(r.not_shared ? `Sent to ${r.sent}; ${r.not_shared} not shared with it` : `Sent to ${r.sent}`); dlg.close();
      } catch (err) { toast(err.message, "error"); }
    }, { primary: true })) });
}

async function addToDashboard(rep) {
  const boards = (await safeGet("/api/reporting/items?kind=dashboard&scope=mine", [])).filter((d) => d.can_edit);
  const sel = wsSelect([{ value: "", label: "New dashboard" }, ...boards.map((d) => ({ value: String(d.id), label: d.name }))], "", { "aria-label": "Dashboard" });
  const vis = wsSelect([{ value: "both", label: "Table and chart" }, { value: "chart", label: "Chart" }, { value: "table", label: "Table" }], "both", { "aria-label": "Visualization" });
  const dlg = modal({ title: "Add to dashboard", width: 520,
    body: wsFieldRows([{ label: "Dashboard", control: sel }, { label: "Visualization", control: vis }]),
    footer: wsToolbar(wsAction("Cancel", () => dlg.close()), wsAction("Add", async () => {
      const w = { type: "report", report_id: rep.id, visualization: vis.value, title: "", x: 0, y: 0, w: 6, h: 4 };
      try {
        let d;
        if (!sel.value) {
          d = await API.post("/api/reporting/items", { kind: "dashboard", name: `${rep.name} dashboard`.slice(0, 200), definition: { layout: "canvas", tabs: [{ name: "Tab 1", widgets: [w] }] } });
        } else {
          const cur = await API.get(`/api/reporting/items/${sel.value}`);
          const def = cur.definition;
          const tab = def.tabs[0];
          w.y = tab.widgets.reduce((m, x) => Math.max(m, x.y + x.h), 0);
          tab.widgets.push(w);
          d = await API.patch(`/api/reporting/items/${cur.id}`, { definition: def });
        }
        dlg.close(); toast(`Added to ${d.name}`); boardBuilder(d);
      } catch (err) { toast(err.message, "error"); }
    }, { primary: true })) });
}

// ------------------------------------------------------------------ widgets on a canvas (dashboards and slides)

function widgetBody(w) {
  if (w.type === "text") return el("div", { class: "pre" }, w.text || "");
  if (w.type === "image") return w.image ? el("img", { src: w.image, alt: w.title || "Image" }) : el("span", { class: "ws-caption" }, "No image");
  if (w.type === "filter") return el("span", { class: "ws-caption" }, w.filter === "period" ? "Period filter" : "Project filter");
  if (w.error) return el("p", { class: "ws-caption" }, w.error);
  if (w.result) return resultView(w.result, { compact: true, visualization: w.visualization, meta: false });
  return loadingState();
}

function placeWidget(node, w, layout) {
  if (layout === "static") node.style.gridColumn = `span ${w.w > 6 ? 2 : 1}`;
  else { node.style.gridColumn = `${w.x + 1} / span ${Math.min(w.w, 12 - w.x)}`; node.style.gridRow = `${w.y + 1} / span ${w.h}`; }
}

function sortedWidgets(ws) { return [...ws].sort((a, b) => a.y - b.y || a.x - b.x); }

// Filter widgets (Project, Period) apply to every report on the tab or slide.
function filterControl(w, ctx, audits, onFilter) {
  if (w.filter === "project") {
    const s = wsSelect([{ value: "", label: "All projects" }, ...audits.map((a) => ({ value: a.ref, label: `${a.ref} · ${a.title}` }))], ctx.audit || "", { "aria-label": "Project" });
    s.addEventListener("change", () => onFilter({ ...ctx, audit: s.value || null }));
    return wsField("Project", s);
  }
  const a = wsInput(ctx.date_from || "", { type: "date", "aria-label": "Period from" });
  const b = wsInput(ctx.date_to || "", { type: "date", "aria-label": "Period to" });
  const ch = () => onFilter({ ...ctx, date_from: a.value || null, date_to: b.value || null });
  a.addEventListener("change", ch); b.addEventListener("change", ch);
  return wsField("Period", el("div", { class: "ws-inline" }, a, b));
}

function canvasView(layout, widgets, { ctx = {}, audits = [], onFilter = null, theme = null } = {}) {
  const c = el("div", { class: `ws-canvas view${layout === "static" ? " static" : ""}` });
  sortedWidgets(widgets).forEach((w) => {
    const node = el("div", { class: "ws-widget" }, w.title && w.type !== "filter" ? el("b", { class: "ws-card-t" }, w.title) : null,
      w.type === "filter" && onFilter ? filterControl(w, ctx, audits, onFilter) : widgetBody(w));
    placeWidget(node, w, layout);
    c.append(node);
  });
  if (!widgets.length) c.append(el("span", { class: "ws-caption" }, "No content"));
  return theme ? el("div", { class: `ws-slide theme-${theme.toLowerCase().replace(/ /g, "-")}` }, c) : c;
}

function boardView(layout, tabs, { ctx = {}, onFilter = null } = {}) {
  const box = el("div");
  let cur = 0;
  const strip = el("div", { class: "ws-flow", role: "tablist" });
  const body = el("div");
  const paint = async () => {
    strip.replaceChildren(...tabs.map((t, i) => el("button", { type: "button", role: "tab", class: i === cur ? "on" : "", "aria-selected": i === cur ? "true" : "false",
      onclick: () => { cur = i; paint(); } }, t.name)));
    const audits = tabs[cur].widgets.some((w) => w.type === "filter" && w.filter === "project") ? await repAudits() : [];
    body.replaceChildren(canvasView(layout, tabs[cur].widgets, { ctx, audits, onFilter }));
  };
  if (tabs.length > 1) box.append(strip);
  box.append(body);
  paint();
  return box;
}

// Run the report widgets client-side (unsaved builder preview) with the viewer's access and the filters.
async function runWidgets(widgets, ctx = {}) {
  const qs = new URLSearchParams(Object.entries(ctx).filter(([, v]) => v)).toString();
  return Promise.all(widgets.map(async (w) => {
    if (w.type !== "report") return { ...w };
    try { const r = await API.get(`/api/reporting/items/${w.report_id}/run${qs ? `?${qs}` : ""}`); return { ...w, title: w.title || r.name, result: r.result }; }
    catch (err) { return { ...w, error: err.status === 404 ? "This report is not shared with you" : err.message }; }
  }));
}

function presentSlides(it, start = 0) {
  const slides = it.slides || [];
  if (!slides.length) { toast("This presentation has no slides", "error"); return; }
  const theme = (it.definition && it.definition.theme) || "Default";
  let i = start;
  const stage = el("div", { class: "rep-stage" });
  const count = el("span", { class: "ws-caption" });
  const paint = () => {
    const s = slides[i];
    stage.replaceChildren(el("h2", null, s.name), canvasView("canvas", s.widgets, { theme }));
    count.textContent = `${i + 1} / ${slides.length}`;
  };
  const key = (e) => { if (e.key === "ArrowRight") next(); if (e.key === "ArrowLeft") prev(); };
  const prev = () => { if (i) { i -= 1; paint(); } };
  const next = () => { if (i < slides.length - 1) { i += 1; paint(); } };
  document.addEventListener("keydown", key);
  const dlg = modal({ title: it.name, width: 1100, body: stage, onClose: () => document.removeEventListener("keydown", key),
    footer: wsToolbar(wsAction("Previous", prev), count, wsAction("Next", next, { primary: true })) });
  paint();
  return dlg;
}

// ------------------------------------------------------------------ Create → Dashboard / Create → Present

function createBoardPage(kind) {
  const dash = kind === "dashboard";
  const f = repFrame(dash ? "dashboard" : "presentation", { crumb: [dash ? "Create dashboard" : "Create"],
    title: dash ? "Name and choose a layout" : "Create a stakeholder presentation" });
  const name = wsInput("", { name: "name", maxlength: "200" });
  let layout = "canvas";
  const theme = wsSelect([{ value: "Default", label: "Select a theme (optional)" }, ...REP_THEMES.filter((t) => t !== "Default").map((t) => ({ value: t, label: t }))], "Default", { name: "theme" });
  const choices = el("div", { class: "ws-grid add-choices" });
  const paintChoices = () => choices.replaceChildren(
    wsChoiceSel("Dashboard Canvas", "Flexible placement of reports, filters, text and images.", layout === "canvas", () => { layout = "canvas"; paintChoices(); }),
    wsChoiceSel("Static layout", "Prearranged structure with simpler placement.", layout === "static", () => { layout = "static"; paintChoices(); }));
  if (dash) paintChoices();
  const box = el("div", null, wsFieldRows([{ label: dash ? "Dashboard name" : "Presentation name", control: name },
    dash ? { label: "Choose Layout", control: choices } : { label: "Theme", control: theme }]));
  box.append(wsToolbar(wsAction("Cancel", () => renderReportsApp(kind)), wsAction("Create", async () => {
    if (name.value.trim().length < 2) { wsShowErrors(box, { message: "Enter a name", errors: [{ field: "name", message: "Enter a name" }] }); return; }
    const definition = dash ? { layout, tabs: [{ name: "Tab 1", widgets: [] }] } : { theme: theme.value, slides: [{ name: "Slide 1", widgets: [] }] };
    try { const it = await API.post("/api/reporting/items", { kind, name: name.value.trim(), definition }); boardBuilder(it); }
    catch (err) { wsShowErrors(box, err); }
  }, { primary: true })));
  f.body.append(box);
}

function wsChoiceSel(title, text, on, onclick) {
  const b = wsChoice(title, text, onclick);
  b.classList.add("add-choice");
  if (on) { b.classList.add("on"); b.setAttribute("aria-pressed", "true"); } else b.setAttribute("aria-pressed", "false");
  return b;
}

// ------------------------------------------------------------------ Dashboard Builder / Present Builder

async function boardBuilder(item) {
  const dash = item.kind === "dashboard";
  const it = { ...item };
  const def = JSON.parse(JSON.stringify(it.definition));
  const pages = dash ? def.tabs : def.slides;
  if (!pages.length) pages.push({ name: dash ? "Tab 1" : "Slide 1", widgets: [] });
  const layout = dash ? def.layout : "canvas";
  let cur = 0;
  let sel = null;
  let panel = dash ? "reports" : "slides";
  const undo = []; const redo = [];
  const snap = () => { undo.push(JSON.stringify(pages)); if (undo.length > 50) undo.shift(); redo.length = 0; };
  const restore = (from, to) => {
    if (!from.length) return;
    to.push(JSON.stringify(pages));
    const p = JSON.parse(from.pop());
    pages.splice(0, pages.length, ...p);
    cur = Math.min(cur, pages.length - 1); sel = null; paint();
  };
  const reports = (await safeGet("/api/reporting/items?kind=report", [])).filter((r) => r.settings.allow_dashboards || r.can_edit);
  const results = {};
  const app = dash ? "Dashboard Builder" : "Present Builder";
  const side = [...(dash ? [] : [{ key: "slides", label: "Slides" }]), { key: "reports", label: "Reports" }, ...(dash ? [{ key: "filters", label: "Filters" }] : []),
    { key: "text", label: "Text" }, { key: "images", label: dash ? "Images" : "Images / Video" }, { key: "properties", label: "Properties" }];
  const f = wsPage({ app, context: it.name, side, active: panel, sideLabel: `${app} panels`,
    onSide: (k) => { panel = k; f.setActive(k); paintPanel(); },
    util: [{ label: "Close", icon: "x-lg", onClick: () => openReportItem(it.id) }] });
  const head = () => f.setHead(null, [
    wsAction("Undo", () => restore(undo, redo), { icon: "arrow-counterclockwise", disabled: !undo.length }),
    wsAction("Redo", () => restore(redo, undo), { icon: "arrow-clockwise", disabled: !redo.length }),
    wsAction("Save", () => persist(), { icon: "save" }),
    wsAction("Preview", () => previewMode(), { icon: "eye" }),
    wsAction("Publish", () => publishPage(), { primary: true })]);
  const pal = el("div", { class: "rep-palette" });
  const strip = el("div", { class: "ws-flow", role: "tablist" });
  const canvas = el("div", { class: `ws-canvas edit${layout === "static" ? " static" : ""}`, "aria-label": `${dash ? "Dashboard" : "Slide"} content area` });
  const stage = dash ? canvas : el("div", { class: `ws-slide theme-${(def.theme || "Default").toLowerCase().replace(/ /g, "-")}` }, canvas);
  f.body.append(el("div", { class: "rep-builder board" }, pal, el("div", null, dash ? strip : null, stage)));
  const page = () => pages[cur];
  const persist = async (quiet = false) => {
    try { const saved = await API.patch(`/api/reporting/items/${it.id}`, { definition: def }); Object.assign(it, saved); if (!quiet) toast("Saved"); return true; }
    catch (err) { toast(err.message, "error"); return false; }
  };
  const nextY = () => page().widgets.reduce((m, w) => Math.max(m, w.y + w.h), 0);
  const addWidget = (w, at = null) => {
    snap();
    const nw = { title: "", text: "", image: "", visualization: "both", x: 0, y: nextY(), w: 6, h: w.type === "filter" ? 2 : 4, ...w, ...(at || {}) };
    nw.x = Math.max(0, Math.min(nw.x, 12 - nw.w));
    page().widgets.push(nw);
    sel = page().widgets.length - 1;
    paint();
  };
  const dropAt = (e) => {
    const r = canvas.getBoundingClientRect();
    const x = Math.max(0, Math.min(11, Math.floor(((e.clientX - r.left) / r.width) * 12)));
    const y = Math.max(0, Math.floor((e.clientY - r.top - 13) / 50));
    return layout === "static" ? {} : { x, y };
  };
  canvas.addEventListener("dragover", (e) => { e.preventDefault(); canvas.classList.add("drop"); });
  canvas.addEventListener("dragleave", () => canvas.classList.remove("drop"));
  canvas.addEventListener("drop", (e) => {
    e.preventDefault(); canvas.classList.remove("drop");
    const move = e.dataTransfer.getData("text/widget");
    const add = e.dataTransfer.getData("text/new-widget");
    if (move !== "") {
      snap();
      const w = page().widgets[Number(move)];
      Object.assign(w, dropAt(e));
      w.x = Math.min(w.x, 12 - w.w);
      sel = Number(move); paint();
    } else if (add) addWidget(JSON.parse(add), dropAt(e));
  });
  const draggable = (node, w) => {
    node.setAttribute("draggable", "true");
    node.addEventListener("dragstart", (e) => e.dataTransfer.setData("text/new-widget", JSON.stringify(w)));
    return node;
  };
  async function ensureResult(w) {
    if (w.type !== "report" || !w.report_id) return;
    if (!results[w.report_id]) results[w.report_id] = (await runWidgets([w]))[0];
  }
  function paintCanvas() {
    clear(canvas);
    canvas.style.gridAutoRows = layout === "static" ? "" : "40px";
    page().widgets.forEach((w, i) => {
      const r = w.type === "report" ? results[w.report_id] : null;
      const node = el("div", { class: `ws-widget${i === sel ? " sel" : ""}`, tabindex: "0", draggable: "true", "aria-label": `${w.type} widget`,
        onclick: () => { sel = i; panel = "properties"; f.setActive("properties"); paint(); } },
      el("div", { class: "ws-widget-tools" }, iconBtn("x-lg", "Remove widget", (e) => { e.stopPropagation(); snap(); page().widgets.splice(i, 1); sel = null; paint(); })),
      el("b", { class: "ws-card-t" }, w.title || (r && r.title) || (w.type === "filter" ? (w.filter === "period" ? "Period" : "Project") : w.type === "report" ? "Report" : "")),
      r ? widgetBody({ ...w, result: r.result, error: r.error }) : widgetBody(w));
      node.addEventListener("dragstart", (e) => e.dataTransfer.setData("text/widget", String(i)));
      node.addEventListener("keydown", (e) => {
        if (e.target !== node) return;
        const moves = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
        if (moves[e.key]) { e.preventDefault(); snap(); w.x = Math.max(0, Math.min(12 - w.w, w.x + moves[e.key][0])); w.y = Math.max(0, w.y + moves[e.key][1]); sel = i; paint(); node.focus(); }
        if (e.key === "Delete") { snap(); page().widgets.splice(i, 1); sel = null; paint(); }
      });
      placeWidget(node, w, layout);
      canvas.append(node);
      if (w.type === "report" && !r) ensureResult(w).then(() => paintCanvas());
    });
    if (!page().widgets.length) canvas.append(el("span", { class: "ws-caption", style: "grid-column:1/-1" }, `Drag ${dash ? "reports, filters, text or images" : "a report, text or an image"} here`));
  }
  function paintStrip() {
    if (!dash) return;
    strip.replaceChildren(...pages.map((t, i) => el("button", { type: "button", role: "tab", class: i === cur ? "on" : "", "aria-selected": i === cur ? "true" : "false",
      onclick: () => { cur = i; sel = null; paint(); } }, t.name)),
    el("button", { type: "button", onclick: () => { snap(); pages.push({ name: `Tab ${pages.length + 1}`, widgets: [] }); cur = pages.length - 1; sel = null; paint(); } }, "+ Tab"));
  }
  function paintPanel() {
    clear(pal);
    const P = {
      slides: () => {
        const list = el("div", { class: "ws-thumbs" });
        pages.forEach((s, i) => {
          const t = el("button", { type: "button", class: `ws-thumb${i === cur ? " on" : ""}`, draggable: "true", onclick: () => { cur = i; sel = null; paint(); } },
            el("span", { class: "ws-drag", "aria-hidden": "true" }, "⋮⋮"), `${i + 1}. ${s.name}`);
          t.addEventListener("dragstart", (e) => e.dataTransfer.setData("text/slide", String(i)));
          t.addEventListener("dragover", (e) => { e.preventDefault(); t.classList.add("over"); });
          t.addEventListener("dragleave", () => t.classList.remove("over"));
          t.addEventListener("drop", (e) => {
            e.preventDefault();
            const from = e.dataTransfer.getData("text/slide");
            if (from === "") return;
            snap();
            const [m] = pages.splice(Number(from), 1); pages.splice(i, 0, m); cur = i; paint();
          });
          list.append(t);
        });
        const nm = wsInput("", { maxlength: "80", placeholder: "Slide name", "aria-label": "New slide name" });
        pal.append(wsCard("Slides", list, el("div", { class: "ws-inline" }, nm, wsAction("New", () => {
          snap(); pages.push({ name: nm.value.trim() || `Slide ${pages.length + 1}`, widgets: [] }); cur = pages.length - 1; sel = null; paint();
        }))));
      },
      reports: () => {
        const q = wsInput("", { type: "search", placeholder: "Search reports", "aria-label": "Search reports" });
        const list = el("div", { class: "ws-list-pick" });
        const vis = wsSelect([{ value: "both", label: "Table and chart" }, { value: "chart", label: "Chart" }, { value: "table", label: "Table" }], "both", { "aria-label": "Visualization" });
        const fill = () => {
          const t = q.value.trim().toLowerCase();
          list.replaceChildren(...reports.filter((r) => !t || r.name.toLowerCase().includes(t)).map((r) => draggable(
            wsRow(el("span", null, el("span", { class: "ws-drag", "aria-hidden": "true" }, "⋮⋮ "), r.name), wsAction("Add", () => addWidget({ type: "report", report_id: r.id, visualization: vis.value }))),
            { type: "report", report_id: r.id, visualization: vis.value })));
          if (!reports.length) list.append(el("span", { class: "ws-caption" }, "No reports yet"));
        };
        q.addEventListener("input", fill); vis.addEventListener("change", fill);
        fill();
        pal.append(wsCard("Report widgets", q, vis, list));
      },
      filters: () => pal.append(wsCard("Filter widget", ...[["project", "Project"], ["period", "Period"]].map(([k, l]) => draggable(
        wsRow(el("span", null, el("span", { class: "ws-drag", "aria-hidden": "true" }, "⋮⋮ "), l), wsAction("Add", () => addWidget({ type: "filter", filter: k, w: 4 }))),
        { type: "filter", filter: k, w: 4 })))),
      text: () => {
        const t = wsText("", { rows: "5", maxlength: "10000", "aria-label": "Text" });
        const drag = el("div", { class: "ws-thumb", draggable: "true" }, el("span", { class: "ws-drag", "aria-hidden": "true" }, "⋮⋮"), "Drag text to canvas");
        drag.addEventListener("dragstart", (e) => e.dataTransfer.setData("text/new-widget", JSON.stringify({ type: "text", text: t.value })));
        pal.append(wsCard("Text widget", t, drag, wsToolbar(wsAction("Add", () => { if (t.value.trim()) addWidget({ type: "text", text: t.value, h: 3 }); }))));
      },
      images: () => {
        const file = el("input", { type: "file", accept: "image/png,image/jpeg,image/gif,image/webp", "aria-label": "Image file" });
        file.addEventListener("change", () => {
          const fl = file.files[0];
          if (!fl) return;
          if (fl.size > 300_000) { toast("Choose an image under 300 KB", "error"); return; }
          const rd = new FileReader();
          rd.onload = () => addWidget({ type: "image", image: rd.result, title: fl.name.slice(0, 200) });
          rd.readAsDataURL(fl);
        });
        pal.append(wsCard("Image widget", file, el("span", { class: "ws-caption" }, "PNG, JPEG, GIF or WebP, up to 300 KB")));
      },
      properties: () => {
        const p = page();
        const nm = wsInput(p.name, { maxlength: "80", "aria-label": dash ? "Tab name" : "Slide name" });
        nm.addEventListener("change", () => { snap(); p.name = nm.value.trim() || p.name; paintStrip(); paintPanel(); });
        pal.append(wsCard(dash ? "Tab" : "Slide", wsField("Name", nm), pages.length > 1 ? wsToolbar(wsAction(`Delete ${dash ? "tab" : "slide"}`, () => {
          snap(); pages.splice(cur, 1); cur = Math.max(0, cur - 1); sel = null; paint();
        })) : null));
        if (!dash) {
          const th = wsSelect(REP_THEMES, def.theme || "Default", { "aria-label": "Theme" });
          th.addEventListener("change", () => { def.theme = th.value; stage.className = `ws-slide theme-${th.value.toLowerCase().replace(/ /g, "-")}`; });
          pal.append(wsCard("Theme", th));
        }
        const w = sel !== null ? p.widgets[sel] : null;
        if (!w) { pal.append(wsNote("Select a widget to set its properties")); return; }
        const num = (k, min, max) => {
          const n = wsInput(String(w[k]), { type: "number", min: String(min), max: String(max), "aria-label": k });
          n.addEventListener("change", () => { snap(); w[k] = Math.max(min, Math.min(max, Number(n.value) || min)); if (w.x + w.w > 12) w.x = 12 - w.w; paint(); });
          return n;
        };
        const title = wsInput(w.title || "", { maxlength: "200", "aria-label": "Title" });
        title.addEventListener("change", () => { snap(); w.title = title.value; paint(); });
        const rows = [{ label: "Title", control: title }];
        if (w.type === "report") {
          const vis = wsSelect([{ value: "both", label: "Table and chart" }, { value: "chart", label: "Chart" }, { value: "table", label: "Table" }], w.visualization, { "aria-label": "Visualization" });
          vis.addEventListener("change", () => { snap(); w.visualization = vis.value; paint(); });
          rows.push({ label: "Visualization", control: vis });
        }
        if (w.type === "text") {
          const t = wsText(w.text, { rows: "5", maxlength: "10000", "aria-label": "Text" });
          t.addEventListener("change", () => { snap(); w.text = t.value; paint(); });
          rows.push({ label: "Text", control: t });
        }
        if (layout !== "static") rows.push({ label: "Position (column, row)", control: el("div", { class: "ws-inline" }, num("x", 0, 11), num("y", 0, 200)) });
        rows.push({ label: "Size (width, height)", control: el("div", { class: "ws-inline" }, num("w", 1, 12), num("h", 1, 20)) });
        pal.append(wsCard("Widget", wsFieldRows(rows)));
      },
    };
    (P[panel] || P.reports)();
  }
  function paint() { head(); paintStrip(); paintCanvas(); paintPanel(); f.setCrumb([app, page().name]); }
  async function previewMode() {
    if (!dash) {
      const ran = await Promise.all(pages.map(async (p) => ({ ...p, widgets: await runWidgets(p.widgets) })));
      presentSlides({ ...it, definition: def, slides: ran }, cur);
      return;
    }
    let ctx = {};
    const m = el("div");
    const run = async () => {
      m.replaceChildren(loadingState());
      const ran = await Promise.all(pages.map(async (p) => ({ ...p, widgets: await runWidgets(p.widgets, ctx) })));
      m.replaceChildren(boardView(layout, ran, { ctx, onFilter: (c) => { ctx = c; run(); } }));
    };
    const dlg = modal({ title: `Preview Mode · ${it.name}`, width: 1150, body: m, footer: wsToolbar(wsAction("Exit", () => dlg.close(), { primary: true })) });
    run();
  }
  async function publishPage() {
    if (!(await persist(true))) return;
    const pf = await publishFields(it);
    const box = el("div", null, pf.node);
    const back = () => boardBuilder(it);
    const save = async (activate) => {
      const saved = await saveItem(it, { ...pf.value(), definition: def }, activate, box);
      if (saved) openReportItem(saved.id);
    };
    box.append(wsToolbar(wsAction("Back to builder", back), wsAction("Save → Draft", () => save(false)), wsAction("Save → Activate", () => save(true), { primary: true })));
    const pg = repFrame(dash ? "dashboard" : "presentation", { crumb: [dash ? "Dashboard" : "Present", "Publish"], title: dash ? "Save and set audience access" : "Preview, activate, and share" });
    pg.body.append(box);
  }
  paint();
}

// ------------------------------------------------------------------ AI Reporting

function aiFrame(active, { crumb = [], title = null, actions = [] } = {}) {
  return wsPage({ app: "AI Reporting", side: [{ key: "new", label: "New report" }, { key: "reports", label: "Reports" }, { key: "workstreams", label: "Workstreams" }],
    active, sideLabel: "AI Reporting pages", onSide: (k) => renderAiReporting(k),
    util: [{ label: "Reports", icon: "arrow-left", onClick: () => renderReportsApp("browse") }],
    crumb: [{ label: "AI Reporting", onClick: () => renderAiReporting("new") }, ...crumb], title, actions });
}

async function renderAiReporting(page = "new") {
  if (page === "new") { aiNewReport(); return; }
  const f = aiFrame(page, { crumb: [page === "reports" ? "Reports" : "Workstreams"], title: page === "reports" ? "Published reports" : "Workstreams",
    actions: [wsAction("New report", () => aiNewReport(), { primary: true, icon: "plus-lg" })] });
  const rows = (await safeGet("/api/ai-reporting", [])).filter((w) => (page === "reports" ? w.status === "Published" : true));
  if (!rows.length) { f.body.append(emptyState({ icon: "stars", title: page === "reports" ? "No published reports yet" : "No workstreams yet" })); return; }
  f.body.append(dataTable(rows, [
    { key: "title", label: "Report" }, { key: "status", label: "Status", render: (w) => wsTag(w.status, w.status === "Published" ? "ok" : w.status === "In review" ? "warn" : "") },
    { key: "owner", label: "Author" }, { key: "access", label: "Access" },
    { key: "updated_at", label: "Updated", render: (w) => fmtDay(String(w.updated_at).slice(0, 10)) },
  ], { onRow: (w) => openWorkstream(w.id) }));
}

async function aiNewReport() {
  const f = aiFrame("new", { crumb: ["Build with Templates & Customize"], title: "New report" });
  const ts = await safeGet("/api/ai-reporting/templates", []);
  const suggest = async (body, box) => {
    try { aiReviewSources(await API.post("/api/ai-reporting/suggest", body)); } catch (err) { if (box) wsShowErrors(box, err); else toast(err.message, "error"); }
  };
  f.body.append(wsCard("Start from a template", ...(ts.length ? ts.map((t) => wsRow(el("span", null, el("strong", null, t.name), el("span", { class: "ws-caption" }, t.purpose)),
    wsAction("Use template", () => suggest({ template: t.key })))) : [el("span", { class: "ws-caption" }, "No templates for the data you can see")])));
  const req = wsText("", { name: "request", rows: "3", maxlength: "2000", placeholder: "Summarize open audit findings by severity and owner…" });
  const box = el("div", null, wsField("Describe the report", req));
  box.append(wsToolbar(wsAction("Generate report", () => suggest({ request: req.value }, box), { primary: true, icon: "stars" })));
  f.body.append(wsCard("Or describe the report you need", box));
}

// Suggested data sources: review, then Confirm creates the workstream and generates the draft.
function aiReviewSources(s) {
  const f = aiFrame("new", { crumb: ["New report", "Suggested data sources"], title: "Review sources" });
  const title = wsInput(s.title, { name: "title", maxlength: "200" });
  const purpose = wsText(s.purpose, { name: "purpose", rows: "3", maxlength: "4000" });
  const checks = s.sources.map((src) => el("input", { type: "checkbox", checked: "1", "aria-label": src.label }));
  const box = el("div", null, wsFieldRows([{ label: "Title", control: title }, { label: "Purpose", control: purpose }]),
    wsCard("Suggested data sources", ...s.sources.map((src, i) => wsRow(el("label", null, checks[i], ` ${src.label}`), el("span", { class: "ws-caption" }, src.spec.view)))));
  box.append(wsToolbar(wsAction("Back", () => aiNewReport()), wsAction("Confirm", async () => {
    const sources = s.sources.filter((_, i) => checks[i].checked);
    if (!sources.length) { toast("Keep at least one source", "error"); return; }
    try {
      const w = await API.post("/api/ai-reporting", { title: title.value.trim(), purpose: purpose.value, sources });
      clear(f.body); f.body.append(loadingState("Generating…"));
      try {
        const g = await API.post(`/api/ai-reporting/${w.id}/generate`);
        toast(g.ai_used ? "Draft generated; review it before publishing" : g.ai_error ? `Facts stored; the narrative was not drafted: ${g.ai_error}` : "Facts stored; write the narrative");
      } catch (err) { toast(err.message, "error"); }
      openWorkstream(w.id);
    } catch (err) { wsShowErrors(box, err); }
  }, { primary: true })));
  f.body.append(box);
}

async function openWorkstream(id) {
  let w;
  try { w = await API.get(`/api/ai-reporting/${id}`); } catch (err) { const f0 = aiFrame("workstreams"); f0.body.append(errorState(err, () => renderAiReporting("workstreams"))); return; }
  const reload = () => openWorkstream(id);
  const call = (path, msg) => async () => {
    try { await API.post(`/api/ai-reporting/${id}${path}`); toast(msg); reload(); } catch (err) { toast(err.message, "error"); }
  };
  const actions = [
    w.can_edit ? wsAction("Generate again", call("/generate", "Regenerated from the sources"), { icon: "arrow-repeat" }) : null,
    w.can_edit && w.facts ? wsAction("Edit narrative", () => narrativeEditor(w)) : null,
    w.can_edit && w.status === "Draft" && w.facts ? wsAction("Submit for review", call("/submit", "Submitted for review")) : null,
    w.can_review ? wsAction("Review", () => reviewDialog(w, reload), { primary: true }) : null,
    w.owner_id === state.user.id && w.status === "Approved" ? wsAction("Publish", call("/publish", "Published"), { primary: true }) : null,
    w.facts ? wsAction("Download PDF", () => window.print(), { icon: "file-earmark-pdf" }) : null,
    w.can_edit ? wsMenu("More", [["Share", () => aiShareDialog(w, reload)],
      ["Archive", async () => { try { await API.del(`/api/ai-reporting/${id}`); renderAiReporting("workstreams"); } catch (err) { toast(err.message, "error"); } }]]) : null,
  ];
  const f = aiFrame(w.status === "Published" ? "reports" : "workstreams", { crumb: [{ label: w.status === "Published" ? "Reports" : "Workstreams", onClick: () => renderAiReporting(w.status === "Published" ? "reports" : "workstreams") }, w.title],
    title: w.title, actions });
  f.body.append(el("div", { class: "ws-inline rep-tags" }, wsTag(w.status, w.status === "Published" ? "ok" : w.status === "In review" ? "warn" : ""), wsTag(w.access),
    w.owner ? el("span", { class: "ws-caption" }, `Author: ${w.owner}`) : null));
  if (w.purpose) f.body.append(el("p", { class: "ws-caption" }, w.purpose));
  if (w.review_note || w.reviewed_by) f.body.append(wsNote(`Reviewed by ${w.reviewed_by || "-"}${w.reviewed_at ? ` on ${fmtDate(w.reviewed_at)}` : ""}. `, w.review_note || ""));
  f.body.append(wsCard("Narrative", el("span", { class: "ws-caption" }, w.narrative_label), w.narrative ? el("div", { class: "pre rep-narrative" }, w.narrative) : null));
  const facts = wsCard("Facts");
  if (w.facts_hidden) facts.append(el("span", { class: "ws-caption" }, "The stored facts include data outside your access."));
  else if (!w.facts) facts.append(el("span", { class: "ws-caption" }, "No facts yet"));
  else {
    facts.append(el("span", { class: "ws-caption" }, `Stored ${fmtDate(w.facts_generated_at)} from live data with the author's access.`));
    w.facts.sources.forEach((s) => facts.append(wsCard(s.label,
      resultView({ ...s, rows: s.sample_rows, truncated: s.total > s.sample_rows.length, chart: s.group_by ? "bar" : null }, { compact: true }))));
  }
  f.body.append(facts);
}

function narrativeEditor(w) {
  const f = aiFrame("workstreams", { crumb: [{ label: w.title, onClick: () => openWorkstream(w.id) }, "Narrative"], title: "Narrative" });
  const t = wsText(w.narrative || "", { name: "narrative", rows: "16", maxlength: "50000" });
  const box = el("div", null, t, wsToolbar(wsAction("Cancel", () => openWorkstream(w.id)), wsAction("Save", async () => {
    try { await API.patch(`/api/ai-reporting/${w.id}`, { narrative: t.value }); toast("Narrative saved"); openWorkstream(w.id); } catch (err) { wsShowErrors(box, err); }
  }, { primary: true })));
  f.body.append(box);
}

async function aiShareDialog(w, after) {
  const aud = await audienceFields(w);
  const dlg = modal({ title: `Share · ${w.title}`, width: 620, body: wsFieldRows([{ label: "Access", control: aud.node }]),
    footer: wsToolbar(wsAction("Cancel", () => dlg.close()), wsAction("Save", async () => {
      try { await API.patch(`/api/ai-reporting/${w.id}`, aud.value()); toast("Access saved"); dlg.close(); after(); } catch (err) { toast(err.message, "error"); }
    }, { primary: true })) });
}

function reviewDialog(w, after) {
  const decision = wsSelect([{ value: "approve", label: "Approve for publishing" }, { value: "return", label: "Return to the author" }], "approve", { "aria-label": "Decision" });
  const checked = el("input", { type: "checkbox" });
  const note = wsText("", { rows: "3", maxlength: "4000", "aria-label": "Review note" });
  const dlg = modal({ title: `Review · ${w.title}`, width: 560,
    body: wsFieldRows([{ label: "Decision", control: decision },
      { label: "Facts checked", control: el("label", null, checked, " Facts match their sources; the narrative matches the facts") },
      { label: "Note", control: note }]),
    footer: wsToolbar(wsAction("Cancel", () => dlg.close()), wsAction("Record review", async () => {
      try { await API.post(`/api/ai-reporting/${w.id}/review`, { decision: decision.value, facts_checked: checked.checked, note: note.value }); toast("Review recorded"); dlg.close(); after(); }
      catch (err) { toast(err.message, "error"); }
    }, { primary: true })) });
}
