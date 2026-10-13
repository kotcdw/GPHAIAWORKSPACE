// GPHA Audit Workspace - single-page front end.

const state = {
  user: null,
  csrf: null,
  view: "dashboard",
};

const AUDIT_STATUSES = ["Planned", "In Progress", "Review", "Closed"];
const RISK_RATINGS = ["Low", "Medium", "High"];
const FINDING_STATUSES = ["Open", "Remediating", "Closed"];
const SEVERITIES = ["Low", "Medium", "High"];
const TASK_STATUSES = ["Open", "In Progress", "Closed"];
const ROLES = ["Admin", "Auditor", "Auditee"];

const WRITE_ROLES = ["Admin", "Auditor"];

const authView = qs("#authView");
const appView = qs("#appView");
const viewRoot = qs("#viewRoot");
const whoami = qs("#whoami");
const authMsg = qs("#authMsg");
const regMsg = qs("#regMsg");

function notify(container, text, kind = "ok") {
  if (!container) return;
  clear(container);
  if (text) container.append(el("div", { class: `msg ${kind}` }, text));
}

function isAdmin() {
  return state.user && state.user.role === "Admin";
}

// ==================================================================== shared UI

function toast(text, kind = "ok") {
  const host = qs("#toastHost");
  if (!host) return;
  const node = el("div", { class: `toast ${kind}` }, text);
  host.append(node);
  setTimeout(() => node.remove(), 4000);
}

// Generic modal. `body` is a node; `footer` optional node (buttons).
function modal({ title, body, footer, width, onClose }) {
  const root = qs("#modalRoot");
  const backdrop = el("div", { class: "modal-backdrop" });
  let closed = false;
  const close = (submitted = false) => {
    if (closed) return;
    closed = true;
    backdrop.remove();
    document.removeEventListener("keydown", onKey);
    if (onClose) onClose(submitted === true);
  };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", onKey);
  backdrop.addEventListener("click", (e) => { if (e.target === backdrop) close(); });
  backdrop.append(
    el("div", { class: "modal", style: width ? `width:${width}px` : null },
      el("div", { class: "modal-head" }, el("h3", null, title),
        el("button", { class: "modal-close", onclick: () => close(), title: "Close" }, "\u00d7")),
      el("div", { class: "modal-body" }, body),
      footer ? el("div", { class: "modal-foot" }, footer) : null,
    ),
  );
  root.replaceChildren(backdrop);
  return { close, root: backdrop };
}

function field(labelText, input) {
  return el("div", null, el("label", null, labelText), input);
}

function inputFor(fieldDef, value) {
  const attrs = { id: `fld-${fieldDef.key}` };
  if (fieldDef.type === "textarea") {
    const t = el("textarea", attrs);
    t.value = value ?? "";
    return t;
  }
  let node;
  if (fieldDef.type === "select") {
    node = el("select", attrs, ...(fieldDef.options || []).map((o) =>
      el("option", { value: o, selected: o === value ? "1" : null }, o)));
  } else {
    node = el("input", { ...attrs, type: fieldDef.type || "text" });
    if (value !== undefined && value !== null) node.value = value;
  }
  return node;
}

function readForm(fields) {
  const out = {};
  fields.forEach((f) => {
    const node = qs(`#fld-${f.key}`);
    if (!node) return;
    let v = node.value;
    if (typeof v === "string") v = v.trim();
    if (v === "") v = null;
    if (f.type === "number" && v !== null) v = Number(v);
    out[f.key] = v;
  });
  return out;
}

// Electronic-signature modal. Signs via a module endpoint (pathOverride) or the
// generic /api/approvals/sign endpoint.
function eSignModal({ title, recordType, recordId, pathOverride, actionLabel = "Sign & Approve", onDone, allowReject = false }) {
  const pass = el("input", { type: "password", placeholder: "Your password", required: "1" });
  const decision = el("select", null, el("option", { value: "Approve" }, "Approve"), el("option", { value: "Reject" }, "Reject (return for rework)"));
  const comment = el("textarea", { placeholder: "Comment (optional)" });
  const msg = el("div");
  let instance;
  const submit = el("button", { class: "btn" }, actionLabel);
  instance = modal({
    title: title || "Electronic signature",
    body: el("div", null,
      el("p", { class: "muted" },
        "By signing you certify this action. Your password is verified and never stored."),
      allowReject ? field("Decision", decision) : null,
      field("Password", pass),
      field("Comment", comment),
      msg),
    footer: el("div", { class: "actions" },
      el("button", { class: "btn secondary", onclick: () => instance.close() }, "Cancel"),
      submit),
  });
  submit.addEventListener("click", async () => {
    try {
      if (pathOverride) {
        await API.post(pathOverride, { password: pass.value, comment: comment.value, decision: decision.value });
      } else {
        await API.post("/api/approvals/sign", {
          record_type: recordType, record_id: recordId, decision: "Approve",
          comment: comment.value, password: pass.value,
        });
      }
      instance.close();
      toast("Signature recorded");
      if (onDone) onDone();
    } catch (err) { notify(msg, err.message, "error"); }
  });
}

function tabBar(tabs, activeKey, onSelect) {
  const bar = el("div", { class: "tabs" });
  tabs.forEach((t) => bar.append(
    el("button", { class: `tab ${t.key === activeKey ? "active" : ""}`, onclick: () => onSelect(t.key) }, t.label),
  ));
  return bar;
}

function fmtDate(value) {
  if (!value) return "-";
  try { return new Date(value).toLocaleString(); } catch { return value; }
}

// ==================================================================== module registry

const MODULES = {
  organizations: {
    title: "Organizations",
    endpoint: "/api/organizations",
    wrapped: true,
    recordType: "organization",
    refKey: "org_ref",
    nameKey: "name",
    search: true,
    filters: [{ param: "status", label: "Status", options: ["Pending", "Approved"] }],
    columns: [
      { key: "org_ref", label: "Ref", ref: true },
      { key: "name", label: "Name" },
      { key: "category", label: "Category" },
      { key: "status", label: "Status", badge: true },
    ],
    fields: [
      { key: "name", label: "Name", required: true },
      { key: "category", label: "Category" },
      { key: "contact_name", label: "Contact name" },
      { key: "contact_email", label: "Contact email", type: "email" },
      { key: "contact_phone", label: "Contact phone" },
      { key: "notes", label: "Notes", type: "textarea" },
    ],
    actions: [
      { key: "copy", label: "Copy", kind: "post", path: (id) => `/api/organizations/${id}/copy` },
      { key: "approve", label: "Approve", kind: "esign", adminOnly: true, path: (id) => `/api/organizations/${id}/approve` },
      { key: "set-pending", label: "Set pending", kind: "post", adminOnly: true, path: (id) => `/api/organizations/${id}/set-pending` },
    ],
  },
  stakeholders: {
    title: "Stakeholders",
    endpoint: "/api/stakeholders",
    wrapped: true,
    recordType: "stakeholder",
    refKey: "sh_ref",
    nameKey: "name",
    search: true,
    filters: [{ param: "status", label: "Status", options: ["Active", "Inactive"] }],
    columns: [
      { key: "sh_ref", label: "Ref", ref: true },
      { key: "name", label: "Name" },
      { key: "stakeholder_type", label: "Type" },
      { key: "status", label: "Status", badge: true },
    ],
    fields: [
      { key: "name", label: "Name", required: true },
      { key: "stakeholder_type", label: "Type" },
      { key: "contact_name", label: "Contact name" },
      { key: "contact_email", label: "Contact email", type: "email" },
      { key: "contact_phone", label: "Contact phone" },
      { key: "status", label: "Status", type: "select", options: ["Active", "Inactive"] },
      { key: "notes", label: "Notes", type: "textarea" },
    ],
    actions: [],
  },
  nonconformances: {
    title: "Nonconformance",
    endpoint: "/api/nonconformances",
    wrapped: true,
    recordType: "nonconformance",
    refKey: "nc_ref",
    nameKey: "title",
    search: true,
    filters: [
      { param: "status", label: "Status", options: ["Open", "Remediating", "Closed"] },
      { param: "severity", label: "Severity", options: SEVERITIES },
    ],
    columns: [
      { key: "nc_ref", label: "Ref", ref: true },
      { key: "title", label: "Title" },
      { key: "severity", label: "Severity", badge: true },
      { key: "status", label: "Status", badge: true },
      { key: "owner_email", label: "Owner" },
    ],
    fields: [
      { key: "title", label: "Title", required: true },
      { key: "description", label: "Description", type: "textarea" },
      { key: "severity", label: "Severity", type: "select", options: SEVERITIES },
      { key: "disposition", label: "Disposition" },
      { key: "owner_email", label: "Owner email", type: "email" },
    ],
    actions: [
      { key: "copy", label: "Copy", kind: "post", path: (id) => `/api/nonconformances/${id}/copy` },
      { key: "link", label: "Link CAPA", kind: "link-capa" },
    ],
  },
  capa: {
    title: "CAPA",
    endpoint: "/api/capa",
    wrapped: true,
    recordType: "capa",
    refKey: "capa_ref",
    nameKey: "title",
    search: true,
    filters: [
      { param: "status", label: "Status", options: ["Open", "In Progress", "Review", "Closed"] },
      { param: "severity", label: "Severity", options: SEVERITIES },
    ],
    columns: [
      { key: "capa_ref", label: "Ref", ref: true },
      { key: "title", label: "Title" },
      { key: "severity", label: "Severity", badge: true },
      { key: "status", label: "Status", badge: true },
      { key: "due_date", label: "Due", date: true },
    ],
    fields: [
      { key: "title", label: "Title", required: true },
      { key: "description", label: "Description", type: "textarea" },
      { key: "root_cause", label: "Root cause", type: "textarea" },
      { key: "corrective_action", label: "Corrective action", type: "textarea" },
      { key: "preventive_action", label: "Preventive action", type: "textarea" },
      { key: "effectiveness_check", label: "Effectiveness check", type: "textarea" },
      { key: "severity", label: "Severity", type: "select", options: SEVERITIES },
      { key: "owner_email", label: "Owner email", type: "email" },
      { key: "due_date", label: "Due date", type: "date", notPast: true },
    ],
    actions: [
      { key: "copy", label: "Copy", kind: "post", path: (id) => `/api/capa/${id}/copy` },
      { key: "close", label: "Close (e-sign)", kind: "esign", adminOnly: true, path: (id) => `/api/capa/${id}/close` },
    ],
  },
  "service-feedback": {
    title: "Service Feedback",
    endpoint: "/api/service-feedback",
    wrapped: true,
    recordType: "service_feedback",
    refKey: "sf_ref",
    nameKey: "subject",
    search: true,
    filters: [{ param: "status", label: "Status", options: ["Open", "In Progress", "Closed"] }],
    columns: [
      { key: "sf_ref", label: "Ref", ref: true },
      { key: "subject", label: "Subject" },
      { key: "source", label: "Source" },
      { key: "status", label: "Status", badge: true },
    ],
    fields: [
      { key: "subject", label: "Subject", required: true },
      { key: "description", label: "Description", type: "textarea" },
      { key: "source", label: "Source" },
      { key: "owner_email", label: "Owner email", type: "email" },
    ],
    actions: [
      { key: "copy", label: "Copy", kind: "post", path: (id) => `/api/service-feedback/${id}/copy` },
    ],
  },
};

function canWriteModule(key) {
  return isAdmin() || WRITE_ROLES.includes(state.user.role);
}

// ------------------------------------------------------------------ auth
function showLogin() {
  qs("#registerForm").classList.add("hidden");
  qs("#loginForm").classList.remove("hidden");
  notify(authMsg, "");
  notify(regMsg, "");
}

function showRegister() {
  qs("#loginForm").classList.add("hidden");
  qs("#registerForm").classList.remove("hidden");
  notify(authMsg, "");
  notify(regMsg, "");
}

if (qs("#btnVerifyAccount")) qs("#btnVerifyAccount").addEventListener("click", showRegister);
if (qs("#backToLogin")) qs("#backToLogin").addEventListener("click", showLogin);
if (qs("#btnResetPassword")) {
  qs("#btnResetPassword").addEventListener("click", () => {
    notify(authMsg, "Please contact your administrator to reset your password.", "ok");
  });
}

qs("#loginForm").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  notify(authMsg, "");
  try {
    const me = await API.post("/api/auth/login", {
      username: qs("#loginUser").value.trim(),
      password: qs("#loginPass").value,
    });
    state.user = me.user;
    state.csrf = me.csrf_token;
    API.csrf = me.csrf_token;
    qs("#loginForm").reset();
    showApp();
  } catch (err) {
    const text = authError(err, "sign in");
    if (text) notify(authMsg, text, "error");
  }
});

qs("#registerForm").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  notify(regMsg, "");
  const pass = qs("#regPass").value;
  const confirm = qs("#regConfirm").value;
  if (pass !== confirm) {
    notify(regMsg, "Passwords do not match.", "error");
    return;
  }
  if (pass.length < 8) {
    notify(regMsg, "Password must be at least 8 characters.", "error");
    return;
  }
  const first = qs("#regFirst").value.trim();
  const last = qs("#regLast").value.trim();
  try {
    const res = await API.post("/api/auth/register", {
      username: qs("#regUser").value.trim(),
      email: qs("#regEmail").value.trim(),
      first_name: first,
      last_name: last,
      company: qs("#regCompany").value.trim(),
      full_name: `${first} ${last}`.trim(),
      password: pass,
    });
    qs("#registerForm").reset();
    showLogin();
    notify(authMsg, res.message, "ok");
  } catch (err) {
    notify(regMsg, authError(err, "create your account"), "error");
  }
});

// Sign-in/registration never keep drafts (passwords are never stored), so say plainly what failed.
function authError(err, action) {
  if (err && (err.status === 503 || err.status === 0)) {
    const warn = qs("#authHealth");
    if (action === "sign in" && warn && !warn.classList.contains("hidden")) return "";  // already explained above
    checkAuthHealth();
    return `You can't ${action} right now because the database server is not running. `
      + "Nothing you typed was stored. Ask the administrator to start it, then try again.";
  }
  return err.message;
}

// Warn on the sign-in page before anyone types, and clear the warning once the database is back.
async function checkAuthHealth() {
  if (!authView || authView.classList.contains("hidden")) return;
  try {
    const h = await fetch("/health", { cache: "no-store" }).then((r) => r.json());
    let box = qs("#authHealth");
    if (!box) {
      box = el("div", { id: "authHealth", class: "auth-health hidden", role: "alert" });
      authMsg.parentNode.insertBefore(box, authMsg);
    }
    box.classList.toggle("hidden", !!h.can_save);
    const needsUpdate = h.database && h.database.ok && !h.database.up_to_date;
    box.textContent = h.can_save ? "" : (needsUpdate
      ? "The database is running but needs updating. Ask the administrator to restart the app with .\\run.ps1. "
      : "Sign-in is unavailable: the database server is not running. Ask the administrator to start it (run .\\run.ps1). ")
      + "This page will update automatically.";
  } catch { /* server itself unreachable - the browser shows its own error */ }
}
checkAuthHealth();
setInterval(checkAuthHealth, 10000);

qs("#signOut").addEventListener("click", async () => {
  try { await API.post("/api/auth/logout"); } catch { /* ignore */ }
  state.user = null;
  state.csrf = null;
  API.csrf = null;
  appView.classList.add("hidden");
  authView.classList.remove("hidden");
});

async function boot() {
  try {
    const me = await API.get("/api/auth/me");
    state.user = me.user;
    state.csrf = me.csrf_token;
    API.csrf = me.csrf_token;
    showApp();
  } catch {
    authView.classList.remove("hidden");
  }
}

function showApp() {
  authView.classList.add("hidden");
  appView.classList.remove("hidden");
  whoami.replaceChildren(el("span", { class: "who-name" }, state.user.full_name || state.user.username), badge(state.user.role));
  document.querySelectorAll("#sidebarNav button[data-admin]").forEach((b) => {
    b.classList.toggle("hidden", !isAdmin());
  });
  // Auditees have no access to internal master data.
  ["organizations", "stakeholders", "plans", "universe"].forEach((v) => {
    const b = document.querySelector(`#sidebarNav button[data-view="${v}"]`);
    if (b) b.classList.toggle("hidden", state.user.role === "Auditee");
  });
  document.querySelectorAll("#sidebarNav [data-staff]").forEach((n) => n.classList.toggle("hidden", state.user.role === "Auditee"));
  checkHealth();
  refreshDraftCount();
  const adminOnly = ["logs", "backups"];
  const requested = isAdmin() ? state.view : (adminOnly.includes(state.view) ? "dashboard" : state.view);
  navigate(requested);
}

// ------------------------------------------------------------------ nav
document.querySelectorAll("#sidebarNav button").forEach((btn) => {
  btn.addEventListener("click", () => navigate(btn.dataset.view));
});

function setActiveNav(view) {
  document.querySelectorAll("#sidebarNav button").forEach((b) => {
    b.classList.toggle("active", b.dataset.view === view);
  });
  document.body.classList.remove("nav-open");
  window.scrollTo(0, 0);
}

function navigate(view) {
  state.view = view;
  setActiveNav(view);
  if (MODULES[view]) return renderList(view);
  if (view === "dashboard") return renderDashboard();
  if (view === "tasks") return renderTasks();
  if (view === "audits") return renderAudits();
  if (view === "plans") return renderPlans();
  if (view === "drafts") return renderDrafts();
  if (view === "universe") return renderUniverse();
  if (view === "profile") return renderProfile();
  if (view === "logs") return renderLogs();
  if (view === "backups") return renderBackups();
}

// Page header: title, optional subtitle / meta chips, and actions on the right.
function viewHeader(title, actions = null, opts = {}) {
  const left = el("div", { class: "view-title" },
    opts.back ? el("button", { class: "back-link", onclick: opts.back, title: "Back" }, el("i", { class: "bi bi-arrow-left" })) : null,
    el("div", null,
      el("h2", null, title),
      opts.sub || opts.meta ? el("div", { class: "view-meta" }, opts.meta || null, opts.sub ? el("span", { class: "muted" }, opts.sub) : null) : null));
  return el("div", { class: "view-head" }, left, actions ? el("div", { class: "view-actions" }, actions) : null);
}

// ==================================================================== generic list

function renderCell(item, col) {
  const value = item[col.key];
  if (value === null || value === undefined || value === "") return "-";
  if (col.badge) return badge(value);
  if (col.ref) return el("span", { class: "ref" }, value);
  if (col.date) return fmtDate(value);
  return String(value);
}

// Map a module's field definitions onto the data-entry framework.
function moduleFormFields(m) {
  return m.fields.map((f) => ({
    name: f.key,
    label: f.label,
    type: f.type || "text",
    required: !!f.required,
    options: f.options,
    notPast: f.notPast,
    maxLength: f.type === "textarea" ? 20000 : 255,
    singleLine: !f.type || f.type === "text",
    emptyLabel: f.type === "select" && !f.required ? "Select..." : undefined,
    ...(f.key === "contact_phone" ? { pattern: "^[0-9+()\\-\\s]{6,25}$", patternMessage: "Phone must be 6-25 digits, spaces, +, - or ()" } : {}),
  }));
}

function formPayload(values, fields = []) {
  // Optional single-value blanks are sent as null ("not set"); free text stays "".
  const textareas = new Set(fields.filter((f) => f.type === "textarea").map((f) => f.key || f.name));
  return Object.fromEntries(Object.entries(values).map(([k, v]) => [k, v === "" && !textareas.has(k) ? null : v]));
}

function createModal(key) {
  const m = MODULES[key];
  const noun = m.title.replace(/s$/, "");
  openForm({
    title: `New ${noun}`,
    key: `${key}:new`,
    meta: { title: `New ${noun}` },
    fields: moduleFormFields(m),
    submitLabel: "Create",
    onSubmit: (values) => {
      const body = formPayload(values, m.fields);
      if (body.due_date) body.due_date = `${body.due_date}T00:00:00`;
      Object.keys(body).forEach((k) => { if (body[k] === null && m.fields.find((f) => f.key === k && f.type === "select")) delete body[k]; });
      return API.post(m.endpoint, body);
    },
    onDone: (rec) => { toast(`${noun} ${rec[m.refKey] || ""} created`); openRecord(key, rec.id); refreshDraftCount(); },
  });
}

function editRecordModal(key, record) {
  const m = MODULES[key];
  const initial = Object.fromEntries(m.fields.map((f) => [f.key, record[f.key]]));
  openForm({
    title: `Edit ${record[m.refKey] || m.title}`,
    key: `${key}:edit:${record.id}`,
    meta: { title: `Edit ${record[m.refKey] || ""} ${record[m.nameKey] || ""}`.trim(), record_type: m.recordType, record_id: record.id },
    fields: moduleFormFields(m),
    initial,
    submitLabel: "Save changes",
    onSubmit: (values) => {
      const body = formPayload(values, m.fields);
      if (body.due_date) body.due_date = `${body.due_date}T00:00:00`;
      return API.patch(`${m.endpoint}/${record.id}`, body);
    },
    onDone: () => { toast("Changes saved"); openRecord(key, record.id); refreshDraftCount(); },
  });
}

async function renderList(key) {
  const m = MODULES[key];
  clear(viewRoot);
  const msg = el("div");
  viewRoot.append(
    viewHeader(m.title, canWriteModule(key) ? el("button", { class: "btn", onclick: () => createModal(key) }, "New") : null),
    msg,
  );

  const search = el("input", { placeholder: "Search\u2026" });
  const filterEls = {};
  const toolbar = el("div", { class: "toolbar" },
    el("div", { class: "field grow" }, el("label", null, "Search"), search));
  (m.filters || []).forEach((f) => {
    const sel = el("select", null, el("option", { value: "" }, "All"),
      ...f.options.map((o) => el("option", { value: o }, o)));
    filterEls[f.param] = sel;
    toolbar.append(el("div", { class: "field" }, el("label", null, f.label), sel));
  });
  const apply = el("button", { class: "btn secondary" }, "Apply");
  toolbar.append(apply);
  apply.addEventListener("click", load);
  search.addEventListener("keydown", (e) => { if (e.key === "Enter") load(); });
  viewRoot.append(toolbar);

  const card = el("div", { class: "card" });
  viewRoot.append(card);

  async function load() {
    const params = new URLSearchParams();
    if (m.search && search.value.trim()) params.set("q", search.value.trim());
    Object.entries(filterEls).forEach(([p, sel]) => { if (sel.value) params.set(p, sel.value); });
    clear(card);
    try {
      const data = await API.get(`${m.endpoint}${params.toString() ? `?${params}` : ""}`);
      const items = m.wrapped ? data.items : data;
      const total = m.wrapped ? data.total : data.length;
      if (!items.length) { card.append(el("div", { class: "empty" }, "No records.")); return; }
      card.append(el("table", null,
        el("thead", null, el("tr", null, ...m.columns.map((c) => el("th", null, c.label)))),
        el("tbody", null, ...items.map((it) => el("tr", { onclick: () => openRecord(key, it.id) },
          ...m.columns.map((c) => el("td", null, renderCell(it, c))))))));
      card.append(el("p", { class: "muted small" }, `Showing ${items.length} of ${total}`));
    } catch (err) { notify(msg, err.message, "error"); }
  }
  load();
}

// ==================================================================== generic detail

// Compact "Move to <status>" control used in detail-card headers.
function statusControl(current, options, onSave) {
  const sel = el("select", { class: "compact", "aria-label": "New status" },
    ...options.map((o) => el("option", { value: o, selected: o === current ? "1" : null }, o)));
  const apply = el("button", { class: "btn small", disabled: "1" }, "Apply");
  sel.addEventListener("change", () => { apply.disabled = sel.value === current; });
  apply.addEventListener("click", async () => {
    apply.disabled = true;
    try { await onSave(sel.value); } catch (err) { toast(err.message, "error"); apply.disabled = false; }
  });
  return el("div", { class: "status-control" }, el("span", { class: "muted" }, "Move to"), sel, apply);
}

function iconBtn(icon, title, onclick) {
  return el("button", { class: "btn secondary small icon", title, "aria-label": title, onclick }, el("i", { class: `bi bi-${icon}` }));
}

async function openRecord(key, id) {
  const m = MODULES[key];
  setActiveNav(key);
  clear(viewRoot);
  const msg = el("div");
  viewRoot.append(msg);
  let record;
  try {
    record = await API.get(`${m.endpoint}/${id}`);
  } catch (err) { notify(msg, err.message, "error"); return; }

  const title = record[m.nameKey] || m.title;
  const canWrite = canWriteModule(key);
  const allowedActions = canWrite ? m.actions.filter((act) => !act.adminOnly || isAdmin()) : [];

  viewRoot.append(viewHeader(String(title),
    [
      ...allowedActions.map((act) => el("button", {
        class: `btn small ${act.kind === "esign" ? "" : "secondary"}`.trim(),
        onclick: () => runAction(key, id, act, openRecord) }, act.label)),
      canWrite && record.status !== "Closed" ? el("button", { class: "btn small secondary", onclick: () => editRecordModal(key, record) },
        el("i", { class: "bi bi-pencil" }), " Edit") : null,
      iconBtn("printer", "Print", () => window.print()),
    ],
    { back: () => navigate(key), meta: [el("span", { class: "ref" }, record[m.refKey] || ""), record.status ? badge(record.status) : null] }));

  const detail = el("div");
  viewRoot.append(detail);
  const tabs = [
    { key: "info", label: "Information" },
    { key: "tasks", label: "Tasks" },
    { key: "history", label: "History" },
    { key: "approvals", label: "Approval cycles" },
  ];
  let active = "info";

  function paint() {
    clear(detail);
    detail.append(tabBar(tabs, active, (k) => { active = k; paint(); }));
    const panel = el("div");
    detail.append(panel);
    if (active === "info") renderInfoTab(panel, key, record, canWrite);
    if (active === "tasks") renderTasksTab(panel, m.recordType, id);
    if (active === "history") renderHistoryTab(panel, m.recordType, id);
    if (active === "approvals") renderApprovalsTab(panel, m.recordType, id);
  }
  paint();
}

function displayValue(f, value) {
  if (value === null || value === undefined || value === "") return el("span", { class: "muted" }, "-");
  if (f.type === "date") return fmtDate(value).split(",")[0];
  if (f.type === "select") return badge(value);
  if (f.type === "email") return el("a", { href: `mailto:${value}` }, value);
  return String(value);
}

function renderInfoTab(panel, key, record, canWrite) {
  const m = MODULES[key];
  const statusField = m.filters.find((f) => f.param === "status");
  // CAPA is closed only through the e-signed "Close" action.
  const options = ((statusField && statusField.options) || ["Open", "In Progress", "Closed"])
    .filter((o) => !(key === "capa" && o === "Closed" && record.status !== "Closed"));
  const control = canWrite && record.status !== undefined && record.status !== "Closed"
    ? statusControl(record.status, options, async (v) => {
      await API.patch(`${m.endpoint}/${record.id}`, { status: v });
      toast("Status updated"); openRecord(key, record.id);
    }) : null;

  const short = m.fields.filter((f) => f.type !== "textarea");
  const long = m.fields.filter((f) => f.type === "textarea");
  const dl = el("dl", { class: "kv two-col" },
    ...short.flatMap((f) => [el("dt", null, f.label), el("dd", null, displayValue(f, record[f.key]))]),
    el("dt", null, "Created"), el("dd", null, fmtDate(record.created_at)),
    el("dt", null, "Updated"), el("dd", null, fmtDate(record.updated_at)));
  const card = el("div", { class: "card" },
    el("div", { class: "card-head" }, el("h3", null, "Details"), control), dl,
    ...long.map((f) => el("div", { class: "long-field" }, el("div", { class: "lf-label" }, f.label),
      el("div", { class: `lf-value ${record[f.key] ? "" : "muted"}`.trim() }, record[f.key] || "Not recorded"))));
  panel.append(card);
}

async function renderTasksTab(panel, recordType, id) {
  const card = el("div", { class: "card" }, el("h3", null, "Linked tasks"));
  panel.append(card);
  try {
    const data = await API.get("/api/tasks");
    const items = (data.items || data).filter((t) => t.source_type === recordType && t.source_id === id);
    if (!items.length) { card.append(el("div", { class: "empty" }, "No tasks linked to this record.")); return; }
    card.append(el("table", null,
      el("thead", null, el("tr", null, el("th", null, "Title"), el("th", null, "Assignee"), el("th", null, "Status"))),
      el("tbody", null, ...items.map((t) => el("tr", { class: "no-click" },
        el("td", null, t.system_generated ? el("span", null, el("i", { class: "bi bi-robot sys-task" }), " ", t.title) : t.title),
        el("td", null, t.assignee_id ?? "-"),
        el("td", null, badge(t.status)))))));
  } catch (err) { card.append(el("div", { class: "empty" }, err.message)); }
}

async function renderHistoryTab(panel, recordType, id) {
  const card = el("div", { class: "card" }, el("h3", null, "History"));
  panel.append(card);
  try {
    const items = await API.get(`/api/records/${recordType}/${id}/history`);
    if (!items.length) { card.append(el("div", { class: "empty" }, "No history yet.")); return; }
    card.append(el("div", null, ...items.map((h) => el("div", { class: "comment-row" },
      el("div", { class: "who" }, `${fmtDate(h.timestamp)} \u00b7 user ${h.user_id ?? "-"}${h.cycle_no ? ` \u00b7 cycle ${h.cycle_no}` : ""}`),
      el("div", null, h.action)))));
  } catch (err) { card.append(el("div", { class: "empty" }, err.message)); }
}

async function renderApprovalsTab(panel, recordType, id) {
  const card = el("div", { class: "card" }, el("h3", null, "Approval cycles"));
  panel.append(card);
  try {
    const items = await API.get(`/api/records/${recordType}/${id}/approval-cycles`);
    if (!items.length) { card.append(el("div", { class: "empty" }, "No approval signatures yet.")); return; }
    card.append(el("table", null,
      el("thead", null, el("tr", null, el("th", null, "Cycle"), el("th", null, "Decision"), el("th", null, "Approver"), el("th", null, "When"), el("th", null, "Comment"))),
      el("tbody", null, ...items.map((c) => el("tr", { class: "no-click" },
        el("td", null, c.cycle_no),
        el("td", null, badge(c.decision)),
        el("td", null, c.approver_id ?? "-"),
        el("td", { class: "muted" }, fmtDate(c.timestamp)),
        el("td", { class: "muted" }, c.comment || "-"))))));
  } catch (err) { card.append(el("div", { class: "empty" }, err.message)); }
}

function runAction(key, id, act, refresh) {
  const m = MODULES[key];
  if (act.kind === "esign") {
    return eSignModal({ title: act.label, recordType: m.recordType, recordId: id, pathOverride: act.path(id), onDone: () => refresh(key, id) });
  }
  if (act.kind === "link-capa") {
    return linkPicker("Link CAPA", "/api/capa", (selectedId) =>
      API.post(`/api/nonconformances/${id}/link-capa`, { capa_id: selectedId }), () => refresh(key, id));
  }
  if (act.kind === "post") {
    return (async () => {
      try {
        await API.post(act.path(id));
        toast(`${act.label} done`);
        refresh(key, id);
      } catch (err) { toast(err.message, "error"); }
    })();
  }
}

// A modal that picks a related record by reference then runs `onPick`.
async function linkPicker(title, endpoint, onPick, onDone) {
  const body = el("div");
  const msg = el("div");
  const select = el("select");
  let instance;
  body.append(field("Related record", select), msg);
  instance = modal({
    title, body,
    footer: el("div", { class: "actions" },
      el("button", { class: "btn secondary", onclick: () => instance.close() }, "Cancel"),
      el("button", { class: "btn", onclick: async () => {
        if (!select.value) { notify(msg, "Pick a record", "error"); return; }
        try { await onPick(Number(select.value)); instance.close(); toast("Linked"); if (onDone) onDone(); }
        catch (err) { notify(msg, err.message, "error"); }
      } }, "Link")),
  });
  try {
    const data = await API.get(endpoint);
    const items = data.items || data;
    items.forEach((it) => select.append(el("option", { value: it.id },
      `${it.capa_ref || it.nc_ref || it.org_ref || it.sh_ref || it.sf_ref || it.id} \u2014 ${it.title || it.name || it.subject || ""}`)));
  } catch (err) { notify(msg, err.message, "error"); }
}

// ==================================================================== dashboard

function stat(number, label, sub = null, tone = "") {
  return el("div", { class: `stat ${tone}`.trim() }, el("div", { class: "l" }, label), el("div", { class: "n" }, number),
    sub ? el("div", { class: "s" }, sub) : null);
}

async function safeGet(path, fallback) {
  try { return await API.get(path); } catch { return fallback; }
}

function u_name() { return state.user.full_name || state.user.username; }

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

function panel(title, body, action = null) {
  return el("div", { class: "card panel" }, el("div", { class: "card-head" }, el("h3", null, title), action), body);
}

async function renderDashboard() {
  clear(viewRoot);
  const msg = el("div");
  const staff = state.user.role !== "Auditee";
  viewRoot.append(viewHeader(`${greeting()}, ${(state.user.full_name || state.user.username).split(" ")[0]}`, null,
    { sub: new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" }) }), msg);
  try {
    const [audits, ncs, capa, feedback, tasks, plans, drafts] = await Promise.all([
      safeGet("/api/audits", []),
      safeGet("/api/nonconformances", { items: [] }),
      safeGet("/api/capa", { items: [] }),
      safeGet("/api/service-feedback", { items: [] }),
      safeGet("/api/tasks?assigned_to_me=true", { items: [] }),
      staff ? safeGet("/api/assurance-plans", []) : Promise.resolve([]),
      safeGet("/api/drafts", []),
    ]);
    const ncItems = ncs.items || ncs;
    const capaItems = capa.items || capa;
    const fbItems = feedback.items || feedback;
    const myTasks = (tasks.items || tasks).filter((x) => x.status !== "Closed");
    const openAudits = audits.filter((x) => x.status !== "Closed");
    const inReview = audits.filter((x) => x.status === "Review").length;
    const overdueCapa = capaItems.filter((c) => c.status !== "Closed" && c.due_date && new Date(c.due_date) < new Date()).length;

    viewRoot.append(el("div", { class: "stats" },
      stat(openAudits.length, "Open audits", `${inReview} in review · ${audits.length} total`),
      stat(capaItems.filter((c) => c.status !== "Closed").length, "Open CAPA", overdueCapa ? `${overdueCapa} overdue` : "None overdue", overdueCapa ? "danger" : ""),
      stat(ncItems.filter((n) => n.status !== "Closed").length, "Open nonconformances"),
      stat(fbItems.filter((f) => f.status !== "Closed").length, "Open feedback"),
      stat(myTasks.length, "My open tasks", null, myTasks.length ? "warn" : ""),
      stat(drafts.length, "Unfinished drafts", drafts.length ? "Continue in My Drafts" : "All saved"),
    ));

    const grid = el("div", { class: "dash-grid" });
    viewRoot.append(grid);

    grid.append(panel("Recent audits", !audits.length ? el("div", { class: "empty" }, "No audits yet.")
      : el("table", null,
        el("thead", null, el("tr", null, el("th", null, "Audit"), el("th", null, "Status"), el("th", { class: "num" }, "Updated"))),
        el("tbody", null, ...audits.slice(0, 6).map((x) => el("tr", { onclick: () => openAudit(x.id) },
          el("td", null, x.title), el("td", null, badge(x.status)),
          el("td", { class: "muted num" }, fmtDate(x.updated_at).split(",")[0]))))),
    el("button", { class: "btn small secondary", onclick: () => navigate("audits") }, "View all")));

    grid.append(panel("My open tasks", !myTasks.length ? el("div", { class: "empty" }, "Nothing assigned to you.")
      : el("table", null,
        el("thead", null, el("tr", null, el("th", null, "Task"), el("th", null, "Status"), el("th", { class: "num" }, "Due"))),
        el("tbody", null, ...myTasks.slice(0, 6).map((x) => el("tr", { onclick: () => navigate("tasks") },
          el("td", null, x.title), el("td", null, badge(x.status)),
          el("td", { class: "muted num" }, x.due_date ? fmtDate(x.due_date).split(",")[0] : "-"))))),
    el("button", { class: "btn small secondary", onclick: () => navigate("tasks") }, "Task Center")));

    if (staff) {
      const plan = plans.find((x) => x.status !== "Closed") || plans[0];
      let body = el("div", { class: "empty" }, "No Assurance Plan yet.");
      if (plan) {
        const detail = await safeGet(`/api/assurance-plans/${plan.id}`, null);
        if (detail) {
          const sm = detail.summary;
          const live = sm.engagements - sm.cancelled;
          const pct = live ? Math.round((100 * sm.started) / live) : 0;
          body = el("div", { class: "plan-snap", onclick: () => openPlan(plan.id) },
            el("div", { class: "plan-snap-head" }, el("strong", null, plan.title), badge(plan.status)),
            el("div", { class: "progress" }, el("div", { class: "progress-fill", style: `width:${pct}%` })),
            el("div", { class: "muted small" }, `${sm.started} of ${live} engagements started (${pct}%) · ${sm.coverage_pct}% universe coverage · ${sm.planned_hours}h planned`));
        }
      }
      grid.append(panel("Assurance Plan", body, el("button", { class: "btn small secondary", onclick: () => navigate("plans") }, "Open plans")));
    }
    if (drafts.length) {
      grid.append(panel("Continue where you left off", el("ul", { class: "plain-list" },
        ...drafts.slice(0, 5).map((d) => el("li", null, el("i", { class: "bi bi-pencil-square muted" }), ` ${d.title || d.form_key}`,
          el("span", { class: "muted small" }, ` · ${fmtDate(`${d.updated_at}Z`)}`)))),
      el("button", { class: "btn small secondary", onclick: () => navigate("drafts") }, "My Drafts")));
    }
  } catch (err) { notify(msg, err.message, "error"); }
}

async function renderTasks() {
  clear(viewRoot);
  const msg = el("div");
  viewRoot.append(viewHeader("Task Center", el("button", { class: "btn", onclick: newTaskModal }, "New task")), msg);
  const tabs = [
    { key: "assigned_to_me", label: "Assigned to me" },
    { key: "by_me", label: "Assigned by me" },
    { key: "closed", label: "Closed" },
  ];
  let active = "assigned_to_me";
  const detail = el("div");
  viewRoot.append(detail);

  function paint() {
    clear(detail);
    detail.append(tabBar(tabs, active, (k) => { active = k; paint(); }));
    const card = el("div", { class: "card" });
    detail.append(card);
    let qs2;
    if (active === "assigned_to_me") qs2 = "?assigned_to_me=true";
    else if (active === "by_me") qs2 = "?by_me=true";
    else qs2 = "?status=Closed";
    API.get(`/api/tasks${qs2}`).then((data) => {
      const items = data.items || data;
      if (!items.length) { card.append(el("div", { class: "empty" }, "No tasks.")); return; }
      card.append(el("table", null,
        el("thead", null, el("tr", null, el("th", null, "Title"), el("th", null, "Assignee"), el("th", null, "Status"), el("th", null, "Due"), el("th", null, ""))),
        el("tbody", null, ...items.map((t) => {
          const sel = el("select", null, ...TASK_STATUSES.map((s) =>
            el("option", { value: s, selected: s === t.status ? "1" : null }, s)));
          const save = el("button", { class: "btn small secondary", onclick: async () => {
            try { await API.patch(`/api/tasks/${t.id}`, { status: sel.value }); toast("Task updated"); paint(); }
            catch (err) { toast(err.message, "error"); }
          } }, "Save");
          return el("tr", { class: "no-click" },
            el("td", null, t.system_generated ? el("span", null, el("i", { class: "bi bi-robot sys-task" }), " ", t.title) : t.title),
            el("td", null, t.assignee_id ?? "-"),
            el("td", null, badge(t.status)),
            el("td", { class: "muted" }, fmtDate(t.due_date)),
            el("td", null, el("div", { class: "actions" }, sel, save)));
        }))));
    }).catch((err) => notify(msg, err.message, "error"));
  }
  paint();
}

function newTaskModal() {
  openForm({
    title: "New task",
    key: "task:new",
    meta: { title: "New task" },
    fields: [
      { name: "title", label: "Title", required: true, maxLength: 255, singleLine: true },
      { name: "assignee_id", label: "Assignee user id", type: "number", min: 1, help: "Leave blank to keep it unassigned" },
      { name: "due_date", label: "Due date", type: "date", notPast: true },
      { name: "description", label: "Description", type: "textarea", maxLength: 20000 },
    ],
    submitLabel: "Create",
    onSubmit: (v) => API.post("/api/tasks", {
      title: v.title, description: v.description || "", assignee_id: v.assignee_id,
      due_date: v.due_date ? `${v.due_date}T00:00:00` : null,
    }),
    onDone: () => { toast("Task created"); renderTasks(); refreshDraftCount(); },
  });
}

// ==================================================================== audits

async function renderAudits() {
  clear(viewRoot);
  const msg = el("div");
  viewRoot.append(viewHeader("Audits",
    canWriteModule("audits") ? el("button", { class: "btn", onclick: newAuditModal }, "New audit") : null), msg);
  try {
    const audits = await API.get("/api/audits");
    const card = el("div", { class: "card" });
    if (!audits.length) card.append(el("div", { class: "empty" }, "No audits yet."));
    else card.append(el("table", null,
      el("thead", null, el("tr", null, el("th", null, "Ref"), el("th", null, "Title"), el("th", { class: "hide-sm" }, "Scope"), el("th", null, "Status"), el("th", { class: "hide-sm" }, "Approval"))),
      el("tbody", null, ...audits.map((a) => el("tr", { onclick: () => openAudit(a.id) },
        el("td", { class: "ref" }, `AUD-${String(a.id).padStart(4, "0")}`),
        el("td", null, a.title), el("td", { class: "muted hide-sm" }, (a.scope || "-").replace(/\s+/g, " ")),
        el("td", null, badge(a.status)),
        el("td", { class: "hide-sm" }, a.approval_status ? badge(a.approval_status) : "-"))))));
    viewRoot.append(card);
  } catch (err) { notify(msg, err.message, "error"); }
}

const AUDIT_FIELDS = [
  { name: "title", label: "Title", required: true, maxLength: 255, singleLine: true },
  { name: "scope", label: "Scope", type: "textarea", maxLength: 20000 },
  { name: "description", label: "Description / background", type: "textarea", maxLength: 20000 },
];

function newAuditModal() {
  openForm({
    title: "New audit",
    key: "audit:new",
    meta: { title: "New audit" },
    intro: "Tip: audits for the year are normally started from the Assurance Plan so they stay linked to it.",
    fields: AUDIT_FIELDS,
    submitLabel: "Create",
    onSubmit: (v) => API.post("/api/audits", { title: v.title, description: v.description || "", scope: v.scope || "" }),
    onDone: (a) => { toast("Audit created"); openAudit(a.id); refreshDraftCount(); },
  });
}

function editAuditModal(audit) {
  openForm({
    title: `Edit audit #${audit.id}`,
    key: `audit:edit:${audit.id}`,
    meta: { title: `Edit audit: ${audit.title}`, record_type: "audit", record_id: audit.id },
    fields: AUDIT_FIELDS,
    initial: audit,
    submitLabel: "Save changes",
    onSubmit: (v) => API.patch(`/api/audits/${audit.id}`, { title: v.title, description: v.description || "", scope: v.scope || "" }),
    onDone: () => { toast("Audit saved"); openAudit(audit.id); refreshDraftCount(); },
  });
}

async function openAudit(id) {
  setActiveNav("audits");
  clear(viewRoot);
  const msg = el("div");
  viewRoot.append(msg);
  let audit;
  try { audit = await API.get(`/api/audits/${id}`); }
  catch (err) { notify(msg, err.message, "error"); return; }
  const canWrite = canWriteModule("audits");

  viewRoot.append(viewHeader(audit.title,
    [
      canWrite && audit.status === "Review" && audit.approval_status !== "In Approval"
        ? el("button", { class: "btn small secondary", onclick: async () => {
          try { await API.post(`/api/audits/${id}/in-approval`); toast("Submitted for approval"); openAudit(id); }
          catch (err) { toast(err.message, "error"); }
        } }, "Submit for approval") : null,
      isAdmin() && audit.status === "Review" ? el("button", { class: "btn small", onclick: () => eSignModal({
        title: "Close audit (e-sign)", recordType: "audit", recordId: id,
        pathOverride: `/api/audits/${id}/close`, actionLabel: "Sign & Close",
        onDone: () => openAudit(id) }) }, el("i", { class: "bi bi-pen" }), " Close (e-sign)") : null,
      canWrite && audit.status !== "Closed" ? el("button", { class: "btn secondary small", onclick: () => editAuditModal(audit) },
        el("i", { class: "bi bi-pencil" }), " Edit") : null,
      iconBtn("printer", "Print", () => window.print()),
    ],
    {
      back: () => navigate("audits"),
      meta: [el("span", { class: "ref" }, `AUD-${String(id).padStart(4, "0")}`), badge(audit.status),
        audit.approval_status ? badge(audit.approval_status) : null],
    }));

  const control = canWrite && audit.status !== "Closed"
    ? statusControl(audit.status, AUDIT_STATUSES.filter((x) => x !== "Closed"), async (v) => {
      await API.patch(`/api/audits/${id}`, { status: v });
      toast("Status updated"); openAudit(id);
    }) : null;
  const info = el("div", { class: "card" },
    el("div", { class: "card-head" }, el("h3", null, "Overview"), control),
    el("dl", { class: "kv two-col" },
      el("dt", null, "Assurance Plan"), el("dd", null, audit.plan_id
        ? (() => {
          const a = el("a", { href: "#", onclick: (e) => { e.preventDefault(); openPlan(audit.plan_id); } }, `Plan #${audit.plan_id}`);
          API.get(`/api/assurance-plans/${audit.plan_id}`).then((p) => { a.textContent = `FY${p.fiscal_year} · ${p.title}`; }).catch(() => {});
          return a;
        })()
        : el("span", { class: "muted" }, "Not linked")),
      el("dt", null, "Created"), el("dd", null, fmtDate(audit.created_at)),
      el("dt", null, "Last updated"), el("dd", null, fmtDate(audit.updated_at))),
    el("div", { class: "long-field" }, el("div", { class: "lf-label" }, "Scope"),
      el("div", { class: `lf-value ${audit.scope ? "" : "muted"}`.trim() }, audit.scope || "Not recorded")),
    audit.description ? el("div", { class: "long-field" }, el("div", { class: "lf-label" }, "Description"),
      el("div", { class: "lf-value" }, audit.description)) : null);
  if (canWrite) info.append(el("div", { class: "auditee-strip" }));
  viewRoot.append(info);
  if (canWrite) renderAuditees(info.querySelector(".auditee-strip"), id);

  const tabs = [
    ...(canWrite ? [{ key: "rcm", label: "Risk & Control Matrix" }] : []),
    { key: "findings", label: "Findings / Issues" },
    { key: "papers", label: "Working Papers" },
    { key: "tasks", label: "Tasks" },
    { key: "history", label: "History" },
    { key: "approvals", label: "Approval Cycles" },
  ];
  let active = canWrite ? "rcm" : "findings";
  const detail = el("div");
  viewRoot.append(detail);

  function paint() {
    clear(detail);
    detail.append(tabBar(tabs, active, (k) => { active = k; paint(); }));
    const panel = el("div");
    detail.append(panel);
    if (active === "rcm") renderRcm(panel, id);
    if (active === "findings") renderFindings(panel, id, canWrite);
    if (active === "papers") renderPapers(panel, id, canWrite);
    if (active === "tasks") renderTasksTab(panel, "audit", id);
    if (active === "history") renderHistoryTab(panel, "audit", id);
    if (active === "approvals") renderApprovalsTab(panel, "audit", id);
  }
  paint();
}

// Auditee access, shown as removable chips inside the audit overview card.
async function renderAuditees(container, auditId) {
  async function paint() {
    clear(container);
    container.append(el("div", { class: "lf-label" }, "Auditees with access"));
    try {
      const [assigned, candidates] = await Promise.all([
        API.get(`/api/audits/${auditId}/auditees`), API.get("/api/audits/auditee-candidates")]);
      const chips = el("div", { class: "chips" });
      if (!assigned.length) chips.append(el("span", { class: "muted" }, "No auditee has access yet."));
      assigned.forEach((a) => chips.append(el("span", { class: "chip", title: a.email || "" },
        el("i", { class: "bi bi-person" }), ` ${a.full_name || a.username}`,
        el("button", { class: "chip-x", title: "Remove access", "aria-label": `Remove ${a.username}`, onclick: async () => {
          try { await API.del(`/api/audits/${auditId}/auditees/${a.user_id}`); toast("Access removed"); paint(); }
          catch (err) { toast(err.message, "error"); }
        } }, "×"))));
      const free = candidates.filter((c) => !assigned.some((x) => x.user_id === c.user_id));
      if (free.length) {
        const sel = el("select", { class: "compact", "aria-label": "Auditee to add" },
          el("option", { value: "" }, "Add auditee..."),
          ...free.map((c) => el("option", { value: c.user_id }, c.full_name ? `${c.full_name} (${c.username})` : c.username)));
        sel.addEventListener("change", async () => {
          if (!sel.value) return;
          try { await API.post(`/api/audits/${auditId}/auditees`, { user_id: Number(sel.value) }); toast("Access granted"); paint(); }
          catch (err) { toast(err.message, "error"); }
        });
        chips.append(sel);
      }
      container.append(chips);
    } catch (err) { container.append(el("span", { class: "muted" }, err.message)); }
  }
  paint();
}

async function renderFindings(panel, id, canWrite) {
  const card = el("div", { class: "card" }, el("h3", null, "Findings"));
  panel.append(card);
  const findings = await API.get(`/api/audits/${id}/findings`);
  if (!findings.length) card.append(el("div", { class: "empty" }, "No findings recorded."));
  else card.append(el("table", null,
    el("thead", null, el("tr", null, el("th", null, "#"), el("th", null, "Issue"), el("th", null, "Risk"), el("th", null, "Status"),
      el("th", null, "Owner"), el("th", null, "Mgmt response"))),
    el("tbody", null, ...findings.map((f) => el("tr", { onclick: () => issueForm(f, id, canWrite, () => openAudit(id)), title: "Open issue" },
      el("td", { class: "ref" }, `#${f.id}`),
      el("td", null, f.title, f.control_id ? el("span", { class: "muted" }, " (from control test)") : null),
      el("td", null, badge(f.risk_rating)),
      el("td", null, badge(f.status)), el("td", { class: "muted" }, f.assigned_owner_email || "-"),
      el("td", null, f.management_response ? badge("Received") : badge("Awaited")))))));
  if (canWrite) {
    card.append(el("div", { style: "margin-top:12px" }, el("button", { class: "btn", onclick: () => issueForm(null, id, true, () => openAudit(id)) }, "Add finding / issue")));
  }
}

async function renderPapers(panel, id, canWrite) {
  const card = el("div", { class: "card" }, el("h3", null, "Working papers"));
  panel.append(card);
  const papers = await API.get(`/api/audits/${id}/working-papers`);
  if (!papers.length) card.append(el("div", { class: "empty" }, "No working papers uploaded."));
  else card.append(el("table", null,
    el("thead", null, el("tr", null, el("th", null, "Title"), el("th", null, "Version"), el("th", null, "Uploaded"), el("th", null, "SHA-256"), el("th", null, ""))),
    el("tbody", null, ...papers.map((p) => el("tr", { class: "no-click" },
      el("td", null, p.title), el("td", null, `v${p.version_number}`),
      el("td", { class: "muted" }, fmtDate(p.uploaded_at)),
      el("td", { class: "muted", title: p.sha256 || "" }, p.sha256 ? `${p.sha256.slice(0, 12)}\u2026` : "-"),
      el("td", null, el("div", { class: "actions" },
        el("a", { href: `/api/working-papers/${p.id}/download` }, "Download"),
        isAdmin() ? el("button", { class: "btn small danger-ghost", onclick: async () => {
          try { await API.del(`/api/working-papers/${p.id}`); toast("Withdrawn (file retained)"); openAudit(id); }
          catch (err) { toast(err.message, "error"); }
        } }, "Withdraw") : null)))))));
  if (canWrite) {
    const t = el("input", { placeholder: "Title" });
    const file = el("input", { type: "file" });
    const msg = el("div");
    card.append(el("hr"),
      el("div", { class: "row" }, field("Title", t), el("div", null, el("label", null, "File"), file)), msg,
      el("div", { style: "margin-top:12px" }, el("button", { class: "btn", onclick: async () => {
        if (!t.value.trim() || !file.files.length) { notify(msg, "Title and file required", "error"); return; }
        const form = new FormData();
        form.append("title", t.value.trim());
        form.append("file", file.files[0]);
        try { await API.upload(`/api/audits/${id}/working-papers`, form); toast("Uploaded"); openAudit(id); }
        catch (err) { notify(msg, err.message, "error"); }
      } }, "Upload")));
  }
}

// ==================================================================== profile

async function renderProfile() {
  clear(viewRoot);
  const msg = el("div");
  viewRoot.append(viewHeader(isAdmin() ? "Profile & users" : "My profile", null,
    { meta: [el("span", { class: "muted" }, `Signed in as ${u_name()}`), badge(state.user.role)] }), msg);
  const u = state.user;
  const cols = el("div", { class: "two-cols" });
  viewRoot.append(cols);

  const edit = el("div", { class: "card" }, el("h3", null, "My details"));
  cols.append(edit);
  inlineForm(edit, {
    key: "profile:me",
    meta: { title: "My profile" },
    fields: [
      { name: "full_name", label: "Full name", required: true, maxLength: 255, singleLine: true },
      { name: "email", label: "Email", type: "email", required: true },
    ],
    initial: { full_name: u.full_name || "", email: u.email },
    submitLabel: "Save changes",
    onSubmit: (v) => API.patch("/api/auth/me", v),
    onDone: (res) => {
      state.user = res.user; API.csrf = res.csrf_token; state.csrf = res.csrf_token;
      whoami.replaceChildren(el("span", { class: "who-name" }, state.user.full_name || state.user.username), badge(state.user.role));
      toast("Profile updated");
    },
  });

  const pw = el("div", { class: "card" }, el("h3", null, "Change password"));
  cols.append(pw);
  const pwForm = inlineForm(pw, {
    draftable: false,
    fields: [
      { name: "current_password", label: "Current password", type: "password", required: true },
      { name: "new_password", label: "New password", type: "password", required: true, minLength: 8, maxLength: 128,
        help: "At least 8 characters, not all numbers, not a common password, and not containing your username." },
      { name: "confirm_password", label: "Confirm new password", type: "password", required: true },
    ],
    validate: (v) => (v.new_password && v.confirm_password !== v.new_password ? { confirm_password: "Passwords do not match" } : {}),
    submitLabel: "Change password",
    onSubmit: (v) => API.post("/api/auth/me/password", { current_password: v.current_password, new_password: v.new_password }),
    onDone: () => { Object.values(pwForm.nodes).forEach((n) => { n.value = ""; }); toast("Password changed - other sessions were signed out"); },
  });

  if (isAdmin()) {
    viewRoot.append(el("h2", { class: "section-title" }, "User accounts"));
    await renderUserManagement(viewRoot, msg);
  }
}

// ==================================================================== users (admin)

async function renderUsers() {
  clear(viewRoot);
  const msg = el("div");
  viewRoot.append(viewHeader("Users"), msg);
  await renderUserManagement(viewRoot, msg);
}

function newUserForm() {
  openForm({
    title: "New user account",
    key: "user:new",
    meta: { title: "New user account" },
    fields: [
      { name: "full_name", label: "Full name", maxLength: 255, singleLine: true },
      { name: "username", label: "Username", required: true, minLength: 3, maxLength: 64, pattern: "^[A-Za-z0-9._-]+$",
        patternMessage: "Username may contain letters, digits, '.', '_' and '-' only" },
      { name: "email", label: "Email", type: "email", required: true },
      { name: "role", label: "Role", type: "select", required: true, options: ROLES },
      { name: "password", label: "Initial password", type: "password", required: true, minLength: 8, maxLength: 128,
        help: "The user should change it after first sign-in." },
    ],
    initial: { role: "Auditor" },
    submitLabel: "Create user",
    onSubmit: (v) => API.post("/api/users", v),
    onDone: () => { toast("User created"); renderProfile(); },
  });
}

async function renderUserManagement(container, msg) {
  try {
    const users = await API.get("/api/users");
    const pending = users.filter((u) => !u.is_active).length;
    const card = el("div", { class: "card" },
      el("div", { class: "card-head" },
        el("h3", null, `${users.length} accounts`, pending ? el("span", { class: "muted" }, ` · ${pending} awaiting approval`) : null),
        el("button", { class: "btn small", onclick: newUserForm }, el("i", { class: "bi bi-person-plus" }), " Add user")));
    card.append(el("div", { class: "table-wrap" }, el("table", null,
      el("thead", null, el("tr", null, el("th", null, "User"), el("th", null, "Role"), el("th", null, "Status"), el("th", { class: "num" }, ""))),
      el("tbody", null, ...users.sort((a, b) => Number(a.is_active) - Number(b.is_active)).map((u) => {
        const self = u.id === state.user.id;
        const roleSelect = el("select", { class: "compact", disabled: self ? "1" : null, "aria-label": `Role of ${u.username}` },
          ...ROLES.map((r) => el("option", { value: r, selected: r === u.role ? "1" : null }, r)));
        roleSelect.addEventListener("change", async () => {
          try { await API.patch(`/api/users/${u.id}`, { role: roleSelect.value }); toast(`${u.username} is now ${roleSelect.value}`); renderProfile(); }
          catch (err) { toast(err.message, "error"); roleSelect.value = u.role; }
        });
        const locked = u.locked_until && new Date(`${u.locked_until}Z`) > new Date();
        const actions = el("div", { class: "actions end" },
          locked ? el("button", { class: "btn small secondary", onclick: async () => {
            try { await API.post(`/api/users/${u.id}/unlock`); toast("Account unlocked"); renderProfile(); }
            catch (err) { toast(err.message, "error"); }
          } }, "Unlock") : null,
          self ? null : el("button", { class: `btn small ${u.is_active ? "danger-ghost" : ""}`.trim(), onclick: async () => {
            try { await API.patch(`/api/users/${u.id}`, { is_active: !u.is_active }); toast(u.is_active ? "Account deactivated" : "Account approved"); renderProfile(); }
            catch (err) { toast(err.message, "error"); }
          } }, u.is_active ? "Deactivate" : "Approve"));
        return el("tr", { class: "no-click" },
          el("td", null, el("div", { class: "cell-title" }, u.full_name || u.username),
            el("div", { class: "muted small" }, `${u.username} · ${u.email}`)),
          el("td", null, roleSelect),
          el("td", null, u.is_active ? badge("Active") : badge("Pending"), locked ? " " : null, locked ? badge("Locked") : null),
          el("td", { class: "num" }, actions));
      })))));
    container.append(card);
  } catch (err) { notify(msg, err.message, "error"); }
}

// ==================================================================== logs (admin)

async function renderLogs() {
  clear(viewRoot);
  const msg = el("div");
  viewRoot.append(viewHeader("Audit log"), msg);
  try {
    const logs = await API.get("/api/audit-logs?limit=200");
    const card = el("div", { class: "card" }, el("h3", null, "Immutable activity trail"));
    if (!logs.length) card.append(el("div", { class: "empty" }, "No activity recorded."));
    else card.append(el("table", null,
      el("thead", null, el("tr", null, el("th", null, "When"), el("th", null, "User"), el("th", null, "IP"), el("th", null, "Action"))),
      el("tbody", null, ...logs.map((l) => el("tr", { class: "no-click" },
        el("td", { class: "muted" }, fmtDate(l.timestamp)), el("td", null, l.user_id ?? "-"),
        el("td", { class: "muted" }, l.ip_address || "-"), el("td", null, l.action_performed))))));
    viewRoot.append(card);
  } catch (err) { notify(msg, err.message, "error"); }
}

// ==================================================================== backups (admin)

async function renderBackups() {
  clear(viewRoot);
  const msg = el("div");
  viewRoot.append(viewHeader("Backups",
    el("button", { class: "btn", onclick: async () => {
      try { const b = await API.post("/api/admin/backup"); toast(`Backup ${b.filename} created`); renderBackups(); }
      catch (err) { notify(msg, err.message, "error"); }
    } }, "Run backup now")), msg);
  try {
    const backups = await API.get("/api/admin/backups");
    const card = el("div", { class: "card" }, el("h3", null, "Snapshots"));
    if (!backups.length) card.append(el("div", { class: "empty" }, "No backups yet."));
    else card.append(el("table", null,
      el("thead", null, el("tr", null, el("th", null, "File"), el("th", null, "Size"), el("th", null, "Created"), el("th", null, ""))),
      el("tbody", null, ...backups.map((b) => el("tr", { class: "no-click" },
        el("td", { class: "ref" }, b.filename),
        el("td", null, `${(b.size_bytes / 1024).toFixed(1)} KB`),
        el("td", { class: "muted" }, fmtDate(b.created_at)),
        el("td", null, el("button", { class: "btn small danger-ghost", onclick: async () => {
          try { await API.del(`/api/admin/backups/${encodeURIComponent(b.filename)}`); toast("Deleted"); renderBackups(); }
          catch (err) { notify(msg, err.message, "error"); }
        } }, "Delete")))))));
    viewRoot.append(card);
  } catch (err) { notify(msg, err.message, "error"); }
}

function registerAppOpeners() {
  Object.keys(MODULES).forEach((key) => {
    registerFormOpener(`${key}:new`, () => { navigate(key); createModal(key); });
    registerFormOpener(`${key}:edit:`, async (formKey) => {
      const id = formKey.split(":")[2];
      await openRecord(key, Number(id));
      editRecordModal(key, await API.get(`${MODULES[key].endpoint}/${id}`));
    });
  });
  registerFormOpener("audit:new", () => { navigate("audits"); newAuditModal(); });
  registerFormOpener("audit:edit:", async (formKey) => {
    const id = formKey.split(":")[2];
    await openAudit(id);
    editAuditModal(await API.get(`/api/audits/${id}`));
  });
  registerFormOpener("task:new", () => { navigate("tasks"); newTaskModal(); });
  registerFormOpener("profile:me", () => navigate("profile"));
  registerFormOpener("user:new", () => { navigate("profile"); newUserForm(); });
}

registerAppOpeners();
registerPlanningOpeners();
window.addEventListener("online", () => { checkHealth(); toast("Back online - drafts will sync as you type"); });
setInterval(() => { if (state.user) checkHealth(); }, 60000);
const navToggle = qs("#navToggle");
if (navToggle) navToggle.addEventListener("click", () => document.body.classList.toggle("nav-open"));
boot();
