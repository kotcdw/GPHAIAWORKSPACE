// Application frame used across the workspace (interface walkthroughs): a dark title bar with the app name and
// utility links, a left navigation of the app's pages, and the work area with breadcrumb, a right-aligned
// toolbar, a page heading and the content. Also small building blocks used on those pages: actions, cards,
// rows, tags, field rows, bars, two-column grids and notes.
// Loaded after api.js and ui.js; everything here is called at run time.

function wsAction(label, onclick, { primary = false, icon = null, disabled = false, title = null, focus = false } = {}) {
  return el("button", { class: `ws-action${primary ? " primary" : ""}${focus ? " focus" : ""}`, type: "button", onclick,
    disabled: disabled ? "1" : null, title },
  icon ? el("i", { class: `bi bi-${icon}`, "aria-hidden": "true" }) : null, icon ? ` ${label}` : label);
}

function wsToolbar(...items) {
  const kids = items.flat().filter(Boolean);
  return kids.length ? el("div", { class: "ws-toolbar" }, ...kids) : document.createDocumentFragment();
}

function wsCard(title, ...children) {
  return el("div", { class: "ws-card" }, title ? el("b", { class: "ws-card-t" }, title) : null, ...children.flat());
}

function wsRow(left, right = null, attrs = {}) {
  return el("div", { class: "ws-row", ...attrs }, el("span", { class: "ws-row-l" }, left), right === null ? null : el("span", { class: "ws-row-r" }, right));
}

function wsTag(text, tone = "") {
  return el("span", { class: `ws-tag ${tone}` }, text);
}

function wsField(label, control, help = null) {
  const id = control && control.id ? control.id : `wsf-${Math.random().toString(36).slice(2, 8)}`;
  if (control && control.tagName && ["INPUT", "SELECT", "TEXTAREA"].includes(control.tagName) && !control.id) control.id = id;
  return el("div", { class: "ws-field" }, el("label", { for: id }, label),
    el("div", { class: "ws-field-c" }, control, help ? el("div", { class: "ws-help" }, help) : null));
}

function wsBar(pct, tone = "") {
  const v = Math.max(0, Math.min(100, Math.round(pct || 0)));
  return el("span", { class: `ws-bar ${tone}`, role: "progressbar", "aria-valuenow": String(v), "aria-valuemin": "0", "aria-valuemax": "100", title: `${v}%` },
    el("i", { style: `width:${v}%` }));
}

// Two-part resource meter: used (green) and overage (red) against what is available.
function wsMeter(used, available) {
  const total = Math.max(used, available, 1);
  const ok = Math.min(used, available || used);
  const over = available ? Math.max(0, used - available) : 0;
  return el("div", { class: "ws-meter", role: "img", "aria-label": `${used} of ${available} used${over ? `, ${over} over` : ""}` },
    el("span", { class: "ok", style: `width:${(100 * ok) / total}%` }), el("span", { class: "over", style: `width:${(100 * over) / total}%` }));
}

function wsGrid(...children) {
  return el("div", { class: "ws-grid" }, ...children.flat().filter(Boolean));
}

function wsNote(...children) {
  return el("div", { class: "ws-note" }, ...children);
}

function wsChoice(title, text, onclick, { disabled = false, why = null } = {}) {
  return el("button", { class: "ws-choice", type: "button", onclick, disabled: disabled ? "1" : null, title: disabled ? why : null },
    el("strong", null, title), el("span", { class: "ws-caption" }, disabled && why ? why : text));
}

function wsInput(value = "", attrs = {}) {
  return el("input", { class: "ws-input", value: value ?? "", ...attrs });
}
function wsText(value = "", attrs = {}) {
  return el("textarea", { class: "ws-input", rows: attrs.rows || "3", ...attrs }, value ?? "");
}
function wsSelect(options, value = "", attrs = {}) {
  const opts = options.map((o) => (typeof o === "object" ? o : { value: o, label: String(o) }));
  return el("select", { class: "ws-input", ...attrs }, ...opts.map((o) => el("option", { value: String(o.value), selected: String(o.value) === String(value ?? "") ? "1" : null }, o.label)));
}

// The application frame. `side` = [{ key, label, count? }]; `util` = [{ label, icon?, onClick }].
function wsFrame({ app, context = null, util = [], side = [], active = null, onSide = null, crumb = [], title = null, actions = [], sideLabel = null }) {
  const nav = el("nav", { class: "ws-side", "aria-label": sideLabel || `${app} pages` });
  const crumbs = el("div", { class: "ws-crumb" });
  const head = el("div", { class: "ws-head" });
  const work = el("main", { class: "ws-work" }, crumbs, head);
  const body = el("div", { class: "ws-body" });
  work.append(body);
  const top = el("div", { class: "ws-top" },
    el("div", { class: "ws-top-l" }, el("span", { class: "ws-app" }, app), context ? el("span", { class: "ws-ctx" }, context) : null),
    el("div", { class: "ws-top-r" }, ...util.filter(Boolean).map((u) => el("button", { class: "ws-util", type: "button", onclick: u.onClick },
      u.icon ? el("i", { class: `bi bi-${u.icon}`, "aria-hidden": "true" }) : null, ` ${u.label}`, u.count ? el("span", { class: "count-pill" }, String(u.count)) : null))));
  const root = el("section", { class: "ws" }, top, el("div", { class: `ws-shell${side.length ? "" : " no-side"}` }, side.length ? nav : null, work));
  let current = active;
  function paintNav() {
    clear(nav);
    side.forEach((s) => nav.append(el("button", { type: "button", class: `ws-nav${s.key === current ? " on" : ""}`, "aria-current": s.key === current ? "page" : null,
      onclick: () => { if (onSide) onSide(s.key); } }, s.label, s.count ? el("span", { class: "count-pill" }, String(s.count)) : null)));
  }
  function setCrumb(parts) {
    clear(crumbs);
    parts.filter(Boolean).forEach((p, i) => {
      if (i) crumbs.append(el("span", { class: "ws-crumb-sep", "aria-hidden": "true" }, " / "));
      crumbs.append(typeof p === "object" && p.onClick ? el("button", { class: "ws-crumb-link", type: "button", onclick: p.onClick }, p.label) : el("span", null, typeof p === "object" ? p.label : p));
    });
  }
  function setHead(text, acts = []) {
    clear(head);
    head.append(wsToolbar(...acts));
    if (text) head.append(el("h2", { class: "ws-h" }, text));
  }
  paintNav();
  setCrumb(crumb);
  setHead(title, actions);
  return { root, work, body, nav, setActive: (k) => { current = k; paintNav(); }, setCrumb, setHead };
}

// A full page in the frame. The app's pages come from the host group (merged apps) when there is one.
function wsPage(opts) {
  clear(viewRoot);
  const g = typeof hostGroup === "function" ? hostGroup(state.view) : null;
  let side = opts.side;
  let onSide = opts.onSide;
  let active = opts.active;
  if (!side && g) {
    side = hostTabsAllowed(g).map(([v, label]) => ({ key: v, label }));
    onSide = (k) => navigate(k);
    active = state.view;
  }
  const f = wsFrame({ ...opts, side: side || [], onSide, active });
  viewRoot.append(f.root);
  if (typeof navCrumbs === "function") navCrumbs(state.view);
  return f;
}

// Inline form in field rows (label left, control right). fields: [{ name, label, control, help, value() }].
function wsFieldRows(rows) {
  return el("div", { class: "ws-fields" }, ...rows.filter(Boolean).map((r) => wsField(r.label, r.control, r.help)));
}

// Show an API error on a form: field messages under the matching controls, the summary as a toast.
function wsShowErrors(container, err) {
  container.querySelectorAll(".ws-err").forEach((n) => n.remove());
  (err.errors || []).forEach((e) => {
    const ctl = container.querySelector(`[name="${e.field}"]`);
    if (ctl) ctl.closest(".ws-field-c").append(el("div", { class: "ws-err" }, e.message));
  });
  toast(err.message, "error");
}

// A drop-down menu of actions ("Go To ▾").
function wsMenu(label, items) {
  const wrap = el("span", { class: "ws-menu" });
  const list = el("div", { class: "ws-menu-list", role: "menu", hidden: "1" });
  const btnEl = el("button", { class: "ws-action", type: "button", "aria-haspopup": "menu", "aria-expanded": "false",
    onclick: (e) => {
      e.stopPropagation();
      const open = list.hidden;
      document.querySelectorAll(".ws-menu-list").forEach((l) => { l.hidden = true; });
      list.hidden = !open;
      btnEl.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) {
        // Fixed position so table and frame overflow never clip the menu.
        const r = btnEl.getBoundingClientRect();
        list.style.top = `${Math.round(r.bottom + 4)}px`;
        list.style.left = `${Math.round(Math.max(8, Math.min(window.innerWidth - 220, r.right - 200)))}px`;
        const close = () => { list.hidden = true; btnEl.setAttribute("aria-expanded", "false"); document.removeEventListener("click", close); };
        setTimeout(() => document.addEventListener("click", close), 0);
      }
    } }, `${label} ▾`);
  items.filter(Boolean).forEach(([text, fn]) => list.append(el("button", { type: "button", role: "menuitem", class: "ws-menu-item",
    onclick: () => { list.hidden = true; fn(); } }, text)));
  wrap.append(btnEl, list);
  return wrap;
}
