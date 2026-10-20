// GPHA Audit Workspace - shared UI components (design system).
//
// Loaded after api.js (el, qs, clear) and before every screen script. Screens build pages from these parts so
// that headers, tables, states and dialogs look and behave the same everywhere:
//   setCrumbs        breadcrumb trail above the page
//   statusBadge      status label (text + colour; never colour alone)
//   emptyState / loadingState / errorState / deniedState
//   confirmDialog    promise-based confirmation, optional reason
//   detailPanel      right-hand side panel for record details
//   activityTimeline history list
//   saveState        "Saving / Saved / Not saved" indicator
//   formSection      titled group of form fields
//   filterBar        search box + filter dropdowns + Clear + result count
//   serverTable      register backed by a server-paged endpoint (paging, sorting, search, filters, columns, export)
//   recordLayout     record page: breadcrumb, title row, utility links, tabs straight under the title, side panel

// ------------------------------------------------------------------ preferences (per viewer, best effort)
const Prefs = {
  get(key, fallback) {
    try { const v = localStorage.getItem(`gpha.pref.${key}`); return v === null ? fallback : JSON.parse(v); } catch { return fallback; }
  },
  set(key, value) { try { localStorage.setItem(`gpha.pref.${key}`, JSON.stringify(value)); } catch { /* storage unavailable */ } },
};

// ------------------------------------------------------------------ breadcrumbs
// items: [{ label, onClick? }]; the last item is the current page.
function setCrumbs(items) {
  const nav = qs("#crumbs");
  if (!nav) return;
  clear(nav);
  const list = (items || []).filter((i) => i && i.label);
  nav.classList.toggle("hidden", list.length === 0);
  const ol = el("ol");
  list.forEach((it, i) => {
    const last = i === list.length - 1;
    ol.append(el("li", null, last || !it.onClick
      ? el("span", last ? { "aria-current": "page" } : null, it.label)
      : el("a", { href: "#", onclick: (e) => { e.preventDefault(); it.onClick(); } }, it.label)));
  });
  nav.append(ol);
}

// ------------------------------------------------------------------ status
function statusBadge(value) {
  return typeof badge === "function" ? badge(value) : el("span", { class: "badge" }, value);
}

// ------------------------------------------------------------------ states
function emptyState({ icon = "inbox", title = "Nothing here yet", text = "", action = null } = {}) {
  return el("div", { class: "state state-empty", role: "status" },
    el("i", { class: `bi bi-${icon}`, "aria-hidden": "true" }), el("div", { class: "state-title" }, title),
    text ? el("div", { class: "state-text" }, text) : null, action ? el("div", { class: "state-action" }, action) : null);
}

function loadingState(text = "Loading…") {
  return el("div", { class: "state state-loading", role: "status", "aria-live": "polite" },
    el("span", { class: "spinner", "aria-hidden": "true" }), el("div", { class: "state-text" }, text));
}

function errorState(err, retry = null) {
  const status = err && err.status;
  if (status === 403) return deniedState(err.message);
  return el("div", { class: "state state-error", role: "alert" },
    el("i", { class: "bi bi-exclamation-octagon", "aria-hidden": "true" }),
    el("div", { class: "state-title" }, "This could not be loaded"),
    el("div", { class: "state-text" }, (err && err.message) || "Something went wrong."),
    retry ? el("div", { class: "state-action" }, el("button", { class: "btn small secondary", onclick: retry }, el("i", { class: "bi bi-arrow-clockwise" }), " Try again")) : null);
}

function deniedState(text = "") {
  return el("div", { class: "state state-denied", role: "alert" },
    el("i", { class: "bi bi-shield-lock", "aria-hidden": "true" }), el("div", { class: "state-title" }, "You do not have access"),
    el("div", { class: "state-text" }, text || "Your role or scope does not include this. Ask a Super Administrator if you need it."));
}

// ------------------------------------------------------------------ confirm dialog
// Resolves { ok: true, reason } or { ok: false }. With reason: true a reason of at least 10 characters is required.
function confirmDialog({ title = "Are you sure?", text = "", confirmLabel = "Confirm", danger = false, reason = false, reasonLabel = "Reason", maxLength = 2000 } = {}) {
  return new Promise((resolve) => {
    let done = false;
    const box = reason ? el("textarea", { "aria-label": reasonLabel, maxlength: String(maxLength), rows: "3" }) : null;
    const err = el("div", { class: "field-error", role: "alert" });
    const finish = (result) => { if (done) return; done = true; instance.close(true); resolve(result); };
    const ok = el("button", { class: `btn ${danger ? "danger" : ""}`, type: "button", onclick: () => {
      const r = box ? box.value.trim() : "";
      if (box && r.length < 10) { err.textContent = `${reasonLabel}: at least 10 characters`; box.focus(); return; }
      finish({ ok: true, reason: r });
    } }, confirmLabel);
    const body = el("div", { class: "confirm-body" }, text ? el("p", null, text) : null,
      box ? el("div", { class: "form-field" }, el("label", null, reasonLabel, el("span", { class: "req" }, " *")), box, err) : null);
    const instance = modal({ title, body, width: 460,
      footer: el("div", { class: "actions end" }, el("button", { class: "btn secondary", type: "button", onclick: () => finish({ ok: false }) }, "Cancel"), ok),
      onClose: () => { if (!done) { done = true; resolve({ ok: false }); } } });
    setTimeout(() => (box || ok).focus(), 30);
  });
}

// ------------------------------------------------------------------ side panel
function detailPanel({ title, body, footer = null, width = 520, onClose = null }) {
  const prev = document.activeElement;
  const close = () => { wrap.remove(); document.removeEventListener("keydown", onKey); if (onClose) onClose(); if (prev && prev.focus) prev.focus(); };
  // Once something has been typed in the panel, only its x closes it (not Esc or a click outside).
  let edited = false;
  const onKey = (e) => { if (e.key === "Escape" && !edited && !(e.target.closest && e.target.closest(".form-panel, .modal-backdrop"))) close(); };
  const aside = el("aside", { class: "side-panel", role: "dialog", "aria-modal": "true", "aria-label": title, style: `width:${width}px` },
    el("div", { class: "side-panel-head" }, el("h3", null, title),
      el("button", { class: "modal-close", type: "button", "aria-label": "Close", onclick: close }, "×")),
    el("div", { class: "side-panel-body" }, body), footer ? el("div", { class: "side-panel-foot" }, footer) : null);
  // Typing counts; ticking a box or picking from a list (e.g. the column chooser) does not.
  aside.addEventListener("input", (e) => { if (e.target.matches("textarea, input:not([type=checkbox]):not([type=radio])")) edited = true; });
  const wrap = el("div", { class: "side-panel-wrap" }, el("div", { class: "side-panel-scrim", onclick: () => { if (!edited) close(); } }), aside);
  document.body.append(wrap);
  document.addEventListener("keydown", onKey);
  setTimeout(() => { const f = aside.querySelector("button, a, input, select, textarea"); if (f) f.focus(); }, 30);
  return { close, root: aside };
}

// ------------------------------------------------------------------ activity timeline
// items: [{ at, who, text, icon? }]
function activityTimeline(items, { emptyText = "No activity yet." } = {}) {
  if (!items || !items.length) return emptyState({ icon: "clock-history", title: emptyText });
  return el("ol", { class: "timeline" }, ...items.map((it) => el("li", null,
    el("span", { class: "tl-dot", "aria-hidden": "true" }, el("i", { class: `bi bi-${it.icon || "dot"}` })),
    el("div", { class: "tl-body" }, el("div", { class: "tl-text" }, it.text),
      el("div", { class: "tl-meta muted" }, [it.who, it.at ? fmtDate(it.at) : null].filter(Boolean).join(" · "))))));
}

// ------------------------------------------------------------------ save state
function saveState() {
  const node = el("span", { class: "save-state", role: "status", "aria-live": "polite" });
  const labels = { dirty: ["dot", "Unsaved changes"], saving: ["arrow-repeat", "Saving…"], saved: ["check2", "Saved"], error: ["exclamation-triangle", "Not saved"] };
  return {
    node,
    set(s) {
      node.className = `save-state ${s || ""}`;
      clear(node);
      if (labels[s]) node.append(el("i", { class: `bi bi-${labels[s][0]}`, "aria-hidden": "true" }), ` ${labels[s][1]}`);
    },
  };
}

function formSection(title, ...children) {
  return el("fieldset", { class: "form-section" }, el("legend", null, title), ...children);
}

// ------------------------------------------------------------------ filter bar
// filters: [{ key, label, options: [value | {value,label}] }]
function filterBar({ search = true, placeholder = "Search list…", filters = [], values = {}, onChange }) {
  const state_ = { q: values.q || "", ...values };
  const bar = el("div", { class: "filter-bar", role: "search" });
  let timer = null;
  const emit = () => onChange({ ...state_ });
  if (search) {
    const input = el("input", { type: "search", class: "fb-search", placeholder, value: state_.q, "aria-label": placeholder });
    input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => { state_.q = input.value.trim(); emit(); }, 300); });
    bar.append(el("span", { class: "fb-search-wrap" }, el("i", { class: "bi bi-search", "aria-hidden": "true" }), input));
  }
  const selects = filters.map((f) => {
    const sel = el("select", { class: "fb-select", "aria-label": f.label },
      el("option", { value: "" }, `${f.label}: All`),
      ...(f.options || []).map((o) => { const v = typeof o === "object" ? o.value : o; const l = typeof o === "object" ? o.label : o; return el("option", { value: v }, `${f.label}: ${l}`); }));
    sel.value = state_[f.key] ?? "";
    sel.addEventListener("change", () => { state_[f.key] = sel.value; emit(); });
    bar.append(sel);
    return [f.key, sel];
  });
  const clearBtn = el("button", { class: "link-btn", type: "button", onclick: () => {
    state_.q = ""; const s = bar.querySelector(".fb-search"); if (s) s.value = "";
    selects.forEach(([k, sel]) => { state_[k] = ""; sel.value = ""; });
    emit();
  } }, "Clear");
  const count = el("span", { class: "fb-count muted", "aria-live": "polite" });
  bar.append(clearBtn, count);
  return { root: bar, setCount: (text) => { count.textContent = text; }, values: () => ({ ...state_ }) };
}

// ------------------------------------------------------------------ server-paged register
// opts: {
//   url: "/api/audits/register", columns: [{ key, label, render?(row), sort?: true|"key", num?, hidden?, csv?(row) }],
//   filters: [...filterBar filters], defaultSort: "-updated_at", pageSize: 25, onRow(row), exportName,
//   storageKey: "audits", emptyTitle, emptyText, emptyAction, params: {fixed query params},
//   values: {initial filter values}, onFilter(values) (e.g. to refresh charts that follow the list filters)
// }
function serverTable(opts) {
  const { url, columns, filters = [], defaultSort = null, onRow = null, exportName = null, storageKey = url,
    emptyTitle = "No records", emptyText = "", emptyAction = null, params = {} } = opts;
  const wrap = el("div", { class: "register" });
  const hiddenCols = new Set(Prefs.get(`cols.${storageKey}`, columns.filter((c) => c.hidden).map((c) => c.key)));
  const q = { page: 1, pageSize: Prefs.get(`size.${storageKey}`, opts.pageSize || 25), sort: defaultSort, values: {} };
  let last = null;
  let seq = 0;

  const fb = filterBar({ filters, values: opts.values || {}, onChange: (v) => { q.values = v; q.page = 1; load(); if (opts.onFilter) opts.onFilter(v); } });
  if (opts.values) q.values = { ...opts.values };
  const colsBtn = el("button", { class: "btn small secondary", type: "button", "aria-haspopup": "true", title: "Choose columns",
    onclick: () => openColumnChooser() }, el("i", { class: "bi bi-layout-three-columns" }), " Columns");
  const exportBtns = exportName && hasPerm("data.export") ? [
    el("button", { class: "btn small secondary", type: "button", onclick: () => exportAll("xlsx") }, el("i", { class: "bi bi-file-earmark-excel" }), " Excel"),
    el("button", { class: "btn small secondary", type: "button", onclick: () => exportAll("csv") }, el("i", { class: "bi bi-filetype-csv" }), " CSV")] : [];
  fb.root.append(el("span", { class: "fb-tools" }, colsBtn, ...exportBtns));
  const body = el("div", { class: "register-body" });
  wrap.append(fb.root, body);

  function query(page, size) {
    const sp = new URLSearchParams({ ...params, page: String(page), page_size: String(size) });
    if (q.sort) sp.set("sort", q.sort);
    Object.entries(q.values).forEach(([k, v]) => { if (v !== "" && v !== null && v !== undefined) sp.set(k, v); });
    return `${url}?${sp.toString()}`;
  }

  async function load() {
    const my = ++seq;
    if (!last) { clear(body); body.append(loadingState()); } else body.classList.add("is-loading");
    try {
      const data = await API.get(query(q.page, q.pageSize));
      if (my !== seq) return;
      last = data;
      paint();
    } catch (err) {
      if (my !== seq) return;
      clear(body); body.classList.remove("is-loading"); body.append(errorState(err, load)); fb.setCount("");
    }
  }

  function visibleCols() { return columns.filter((c) => !hiddenCols.has(c.key)); }

  function paint() {
    body.classList.remove("is-loading");
    clear(body);
    const { items, total, page, page_size: size } = last;
    const pages = Math.max(1, Math.ceil(total / size));
    fb.setCount(`${total} ${total === 1 ? "record" : "records"}`);
    if (!items.length) {
      const filtered = Object.values(q.values).some((v) => v);
      body.append(emptyState(filtered ? { icon: "funnel", title: "No records match", text: "Change or clear the filters." }
        : { title: emptyTitle, text: emptyText, action: emptyAction }));
      return;
    }
    const cols = visibleCols();
    const head = el("tr", null, ...cols.map((c) => {
      const key = c.sort === true ? c.key : c.sort;
      const active = key && q.sort && q.sort.replace(/^-/, "") === key;
      const desc = active && q.sort.startsWith("-");
      return el("th", { class: [c.num ? "num" : "", c.wide ? "col-wide" : ""].join(" ").trim() || null, scope: "col", "aria-sort": active ? (desc ? "descending" : "ascending") : (key ? "none" : null) },
        key ? el("button", { class: "th-sort", type: "button", title: `Sort by ${c.label}`, onclick: () => {
          q.sort = active && !desc ? `-${key}` : key; q.page = 1; load();
        } }, c.label, el("i", { class: `bi ${active ? (desc ? "bi-caret-down-fill" : "bi-caret-up-fill") : "bi-chevron-expand"} sort-ico`, "aria-hidden": "true" })) : c.label);
    }));
    const rows = items.map((it) => el("tr", onRow ? { tabindex: "0", onclick: () => onRow(it), onkeydown: (e) => { if (e.key === "Enter") onRow(it); } } : { class: "no-click" },
      ...cols.map((c) => el("td", { class: [c.num ? "num" : "", c.wide ? "col-wide" : ""].join(" ").trim() || null, "data-label": c.label }, c.render ? c.render(it) : cellText(it[c.key])))));
    body.append(el("div", { class: "table-wrap" }, el("table", { class: "dense" }, el("thead", null, head), el("tbody", null, ...rows))));
    const sizeSel = el("select", { class: "compact", "aria-label": "Rows per page" }, ...[10, 25, 50, 100].map((n) => el("option", { value: n, selected: n === size ? "1" : null }, `${n} / page`)));
    sizeSel.addEventListener("change", () => { q.pageSize = Number(sizeSel.value); Prefs.set(`size.${storageKey}`, q.pageSize); q.page = 1; load(); });
    body.append(el("div", { class: "table-foot" },
      el("span", { class: "muted small" }, `${(page - 1) * size + 1}–${Math.min(page * size, total)} of ${total}`),
      el("div", { class: "actions" }, sizeSel,
        el("button", { class: "btn small secondary", type: "button", disabled: page <= 1 ? "1" : null, "aria-label": "Previous page", onclick: () => { q.page -= 1; load(); } }, el("i", { class: "bi bi-chevron-left" })),
        el("span", { class: "small" }, `Page ${page} of ${pages}`),
        el("button", { class: "btn small secondary", type: "button", disabled: page >= pages ? "1" : null, "aria-label": "Next page", onclick: () => { q.page += 1; load(); } }, el("i", { class: "bi bi-chevron-right" })))));
  }

  function openColumnChooser() {
    const list = el("div", { class: "checklist" }, ...columns.map((c) => {
      const cb = el("input", { type: "checkbox", checked: hiddenCols.has(c.key) ? null : "1" });
      cb.addEventListener("change", () => {
        if (cb.checked) hiddenCols.delete(c.key); else hiddenCols.add(c.key);
        if (visibleCols().length === 0) { hiddenCols.delete(c.key); cb.checked = true; }
        Prefs.set(`cols.${storageKey}`, [...hiddenCols]);
        if (last) paint();
      });
      return el("label", { class: "check" }, cb, c.label);
    }));
    detailPanel({ title: "Columns", width: 320, body: list });
  }

  // Export runs the same server query page by page, so it carries the same permissions and filters as the screen.
  async function exportAll(kind) {
    try {
      const rowsOut = [];
      let page = 1;
      for (;;) {
        const data = await API.get(query(page, 100));
        rowsOut.push(...data.items);
        if (page * 100 >= data.total || page >= 100) break;
        page += 1;
      }
      const cols = visibleCols().map((c) => ({ ...c, csv: c.csv || ((it) => plainText(c.render ? c.render(it) : it[c.key])) }));
      if (kind === "xlsx" && typeof downloadXlsx === "function") await downloadXlsx(exportName, cols, rowsOut);
      else if (typeof downloadCsv === "function") downloadCsv(`${exportName}.csv`, cols, rowsOut);
    } catch (err) { toast(err.message, "error"); }
  }

  load();
  return { root: wrap, reload: load };
}

function cellText(v) {
  if (v === null || v === undefined || v === "") return "-";
  if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}T/.test(v)) return fmtDate(v);
  return String(v);
}

function plainText(v) {
  if (v === null || v === undefined) return "";
  if (v instanceof Node) return v.textContent;
  return String(v);
}

// ------------------------------------------------------------------ record page
// opts: { crumbs, title, ref, status, meta: [nodes], actions: [nodes], utility: [{label, icon, count, onClick}],
//         tabs: [{key, label, count?}], active, onTab(key, pane, side), side: node | null }
function recordLayout(opts) {
  const tabsNav = el("div", { class: "rec-tabs", role: "tablist", "aria-label": `${opts.title} sections` });
  const pane = el("div", { class: "rec-pane", role: "tabpanel" });
  const side = el("aside", { class: "rec-side", "aria-label": "Summary" });
  const grid = el("div", { class: `rec-grid ${opts.side === null ? "no-side" : ""}` }, pane, opts.side === null ? null : side);
  const head = el("div", { class: "rec-head" },
    el("div", { class: "rec-title-row" },
      opts.back ? el("button", { class: "back-link", type: "button", title: "Back", "aria-label": "Back", onclick: opts.back }, el("i", { class: "bi bi-arrow-left" })) : null,
      el("h1", { class: "rec-title" }, opts.title),
      opts.ref ? el("span", { class: "ref" }, opts.ref) : null,
      opts.status ? statusBadge(opts.status) : null,
      ...(opts.meta || []),
      el("span", { class: "rec-util" }, ...(opts.utility || []).map((u) => el("button", { class: "link-btn", type: "button", onclick: u.onClick },
        u.icon ? el("i", { class: `bi bi-${u.icon}`, "aria-hidden": "true" }) : null, ` ${u.label}`, u.count ? el("span", { class: "count-pill" }, String(u.count)) : null))),
      opts.actions && opts.actions.length ? el("span", { class: "rec-actions" }, ...opts.actions) : null),
    opts.band || null,
    tabsNav);
  const root = el("div", { class: "record" }, head, grid);
  let current = null;
  function select(key) {
    current = key;
    tabsNav.querySelectorAll("[role=tab]").forEach((b) => {
      const on = b.dataset.key === key;
      b.classList.toggle("active", on); b.setAttribute("aria-selected", on ? "true" : "false"); b.tabIndex = on ? 0 : -1;
    });
    clear(pane);
    opts.onTab(key, pane, side);
  }
  (opts.tabs || []).forEach((t) => {
    tabsNav.append(el("button", { class: "rec-tab", role: "tab", type: "button", "data-key": t.key, onclick: () => select(t.key),
      onkeydown: (e) => {
        if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
        const all = [...tabsNav.querySelectorAll("[role=tab]")]; const i = all.indexOf(e.currentTarget);
        const next = all[(i + (e.key === "ArrowRight" ? 1 : all.length - 1)) % all.length]; next.focus(); next.click();
      } }, t.label, t.count ? el("span", { class: "count-pill" }, String(t.count)) : null));
  });
  if (opts.side && opts.side !== null) side.append(opts.side);
  if (opts.crumbs) setCrumbs(opts.crumbs);
  return { root, pane, side, select, current: () => current };
}

// ------------------------------------------------------------------ application shell
// Sidebar groups (the blueprint's modules) collapse and expand; the group holding the current page stays open.
function initNavGroups() {
  const collapsed = new Set(Prefs.get("nav.collapsed", ["settings"]));
  document.querySelectorAll("#sidebarNav .nav-group").forEach((g) => {
    const head = g.querySelector(".nav-group-head");
    const set = (open) => { g.classList.toggle("collapsed", !open); head.setAttribute("aria-expanded", open ? "true" : "false"); };
    set(!collapsed.has(g.dataset.group));
    if (head.dataset.ready) return;
    head.dataset.ready = "1";
    head.addEventListener("click", () => {
      const open = g.classList.contains("collapsed");
      set(open);
      if (open) collapsed.delete(g.dataset.group); else collapsed.add(g.dataset.group);
      Prefs.set("nav.collapsed", [...collapsed]);
    });
  });
}

function navGroupOf(view) {
  const hg = typeof hostGroup === "function" ? hostGroup(view) : null;
  const b = document.querySelector(`#sidebarNav button[data-view="${view}"]`)
    || (hg ? document.querySelector(`#sidebarNav button[data-view="${hg.host}"]`) : null);
  const g = b && b.closest(".nav-group");
  return g ? { key: g.dataset.group, label: g.querySelector(".nav-group-head span").textContent, button: b, group: g } : null;
}

// Breadcrumb for a top-level page: "Module / Page".
function navCrumbs(view) {
  const info = navGroupOf(view);
  if (!info) { setCrumbs([]); return; }
  info.group.classList.remove("collapsed");
  info.group.querySelector(".nav-group-head").setAttribute("aria-expanded", "true");
  const label = info.button.querySelector("span:not(.count)").textContent;
  const g = hostGroup(view);
  const tab = g && view !== g.host ? (g.tabs.find((t) => t[0] === view) || [])[1] : null;
  const host = tab ? [{ label, onClick: () => navigate(g.host) }, { label: tab }] : [{ label }];
  setCrumbs(info.key === "home" ? host : [{ label: info.label }, ...host]);
}

// Crumbs for a record opened from a top-level page: "Module / Page / Record".
function recordCrumbs(view, record) {
  const info = navGroupOf(view);
  const label = info ? info.button.querySelector("span:not(.count)").textContent : view;
  return [...(info && info.key !== "home" ? [{ label: info.label }] : []), { label, onClick: () => navigate(view) }, { label: record }];
}

// Scope indicator: the user's working context (home port / office). It explains, it does not grant access:
// the server decides what each person may read.
async function initScopeChip() {
  const chip = qs("#scopeChip"); const label = qs("#scopeLabel"); const pop = qs("#scopePanel");
  if (!chip) return;
  let where = null;
  if (state.user.work_entity_id) {
    try { where = await API.get(`/api/organizations/${state.user.work_entity_id}`); } catch { where = null; }
  }
  const wide = isAdmin();
  const place = where ? (where.port_name && where.port_name !== where.name ? `${where.port_name} · ${where.name}` : where.name) : null;
  label.textContent = place || (wide ? "All ports" : "Workplace not set");
  chip.title = `Working context: ${label.textContent}`;
  const close = () => { pop.classList.add("hidden"); chip.setAttribute("aria-expanded", "false"); };
  if (!chip.dataset.ready) {
    chip.dataset.ready = "1";
    chip.addEventListener("click", (e) => {
      e.stopPropagation();
      const open = pop.classList.contains("hidden");
      if (!open) { close(); return; }
      clear(pop);
      pop.append(el("div", { class: "pop-title" }, "Working context"),
        el("dl", { class: "kv compact" },
          el("dt", null, "Workplace"), el("dd", null, place || "Not set"),
          el("dt", null, "Role"), el("dd", null, state.user.job_role_name || state.user.role),
          state.user.review_level ? el("dt", null, "Approval level") : null,
          state.user.review_level ? el("dd", null, state.user.review_level === "Manager" ? "Audit Manager" : state.user.review_level === "CAE" ? "GM Audit (CAE)" : state.user.review_level) : null),
        el("button", { class: "btn small secondary", type: "button", onclick: () => { close(); navigate("profile"); } }, "Change workplace"));
      pop.classList.remove("hidden"); chip.setAttribute("aria-expanded", "true");
    });
    document.addEventListener("click", (e) => { if (!pop.contains(e.target) && e.target !== chip) close(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
  }
}

// Date only, in the workspace's date format. Plain dates ("2026-10-15") are shown as written, never shifted.
function fmtDay(value) {
  if (!value) return "-";
  const w = parseWhen(value);
  if (w.day) return formatDay(w.day);
  if (Number.isNaN(w.date.getTime())) return String(value);
  return formatDay(zonedParts(w.date));
}

// ------------------------------------------------------------------ merged apps (one sidebar entry, tabs on top)
// Pages that live inside another app: the sidebar shows the host only; the others open as its tabs.
const HOST_GROUPS = [
  { host: "portal", tabs: [["portal", "Priorities"], ["tasks", "To-dos"], ["evidence", "Requests"]] },
  { host: "universe", tabs: [["universe", "Overview"], ["universe_units", "Units"], ["universe_processes", "Processes"], ["universe_entities", "Entities"], ["universe_assurance", "Assurance map"]] },
  { host: "issues", tabs: [["issues", "Issues"], ["capa", "Actions"]] },
  { host: "committee", tabs: [["committee", "Committee pack"], ["governance", "Governance portal"], ["portfolio", "Port portfolio"]] },
  { host: "qaip", tabs: [["qaip", "Quality reviews"], ["practice", "Professional practice"], ["service-feedback", "Service feedback"]] },
  { host: "orgstructure", tabs: [["orgstructure", "Org Structure"], ["organizations", "Organizations"], ["stakeholders", "Contacts"]] },
  { host: "configuration", tabs: [["configuration", "Business rules"], ["audittypes", "Audit types"], ["apps", "Apps & customization"], ["imports", "Data import"], ["logs", "Audit trail"]] },
  { host: "robots", tabs: [["robots", "Robots"], ["automations", "Automations"]] },
];

function hostGroup(view) {
  return HOST_GROUPS.find((g) => g.tabs.some((t) => t[0] === view)) || null;
}

function hostTabsAllowed(g) {
  return g.tabs.filter(([v]) => (typeof viewAllowed !== "function" || viewAllowed(v)));
}

// The tab strip shown under the page header of a merged app.
function hostBar(view) {
  const g = hostGroup(view);
  if (!g) return null;
  const tabs = hostTabsAllowed(g);
  if (tabs.length < 2) return null;
  return el("nav", { class: "tabs host-tabs", "aria-label": "Sections" }, ...tabs.map(([v, label]) =>
    el("button", { class: `tab ${v === view ? "active" : ""}`, type: "button", "aria-current": v === view ? "page" : null,
      onclick: () => { if (v !== view) navigate(v); } }, label)));
}

// ------------------------------------------------------------------ "more actions" menu
// items: [label, onClick, danger?]; falsy items are skipped. Closes on choice, Esc or a click elsewhere.
function moreMenu(items, label = "More actions") {
  const list = items.filter(Boolean);
  if (!list.length) return null;
  const menu = el("details", { class: "more-menu" },
    el("summary", { class: "btn small secondary icon", title: label, "aria-label": label }, el("i", { class: "bi bi-three-dots" })),
    el("div", { class: "more-menu-list", role: "menu" }, ...list.map(([text, fn, danger]) => el("button", {
      type: "button", role: "menuitem", class: danger ? "danger" : null,
      onclick: () => { menu.open = false; fn(); } }, text))));
  const away = (e) => { if (!menu.contains(e.target)) menu.open = false; };
  const esc = (e) => { if (e.key === "Escape" && menu.open) { menu.open = false; menu.querySelector("summary").focus(); } };
  menu.addEventListener("toggle", () => {
    if (menu.open) { document.addEventListener("click", away, true); document.addEventListener("keydown", esc); }
    else { document.removeEventListener("click", away, true); document.removeEventListener("keydown", esc); }
  });
  return menu;
}
