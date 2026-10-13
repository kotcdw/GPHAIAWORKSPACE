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
function modal({ title, body, footer, width }) {
  const root = qs("#modalRoot");
  const backdrop = el("div", { class: "modal-backdrop" });
  const close = () => {
    backdrop.remove();
    document.removeEventListener("keydown", onKey);
  };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", onKey);
  backdrop.addEventListener("click", (e) => { if (e.target === backdrop) close(); });
  backdrop.append(
    el("div", { class: "modal", style: width ? `width:${width}px` : null },
      el("div", { class: "modal-head" }, el("h3", null, title),
        el("button", { class: "modal-close", onclick: close, title: "Close" }, "\u00d7")),
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
function eSignModal({ title, recordType, recordId, pathOverride, actionLabel = "Sign & Approve", onDone }) {
  const pass = el("input", { type: "password", placeholder: "Your password", required: "1" });
  const comment = el("textarea", { placeholder: "Comment (optional)" });
  const msg = el("div");
  let instance;
  const submit = el("button", { class: "btn" }, actionLabel);
  instance = modal({
    title: title || "Electronic signature",
    body: el("div", null,
      el("p", { class: "muted" },
        "By signing you certify this action. Your password is verified and never stored."),
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
        await API.post(pathOverride, { password: pass.value, comment: comment.value });
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
    notify(authMsg, err.message, "error");
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
    notify(regMsg, err.message, "error");
  }
});

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
  whoami.textContent = `${state.user.full_name || state.user.username} (${state.user.role})`;
  document.querySelectorAll("#sidebarNav button[data-admin]").forEach((b) => {
    b.classList.toggle("hidden", !isAdmin());
  });
  // Auditees have no access to internal master data.
  ["organizations", "stakeholders"].forEach((v) => {
    const b = document.querySelector(`#sidebarNav button[data-view="${v}"]`);
    if (b) b.classList.toggle("hidden", state.user.role === "Auditee");
  });
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
}

function navigate(view) {
  state.view = view;
  setActiveNav(view);
  if (MODULES[view]) return renderList(view);
  if (view === "dashboard") return renderDashboard();
  if (view === "tasks") return renderTasks();
  if (view === "audits") return renderAudits();
  if (view === "profile") return renderProfile();
  if (view === "logs") return renderLogs();
  if (view === "backups") return renderBackups();
}

function viewHeader(title, actions = null) {
  return el("div", { class: "view-head" }, el("h2", null, title),
    actions ? el("div", { class: "view-actions" }, actions) : null);
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

function createModal(key) {
  const m = MODULES[key];
  const form = el("form", { class: "form-grid" },
    ...m.fields.map((f) => field(f.label + (f.required ? " *" : ""), inputFor(f, f.default))),
    el("div", { class: "msg" }),
  );
  const instance = modal({
    title: `New ${m.title.replace(/s$/, "")}`,
    body: form,
    footer: el("div", { class: "actions" },
      el("button", { class: "btn secondary", type: "button", onclick: () => instance.close() }, "Cancel"),
      el("button", { class: "btn", type: "button", onclick: submit }, "Create")),
  });
  const msgBox = form.querySelector(".msg");
  async function submit() {
    const payload = readForm(m.fields);
    const missing = m.fields.filter((f) => f.required && !payload[f.key]);
    if (missing.length) { notify(msgBox, `Required: ${missing.map((f) => f.label).join(", ")}`, "error"); return; }
    try {
      await API.post(m.endpoint, payload);
      instance.close();
      toast(`${m.title} record created`);
      renderList(key);
    } catch (err) { notify(msgBox, err.message, "error"); }
  }
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

async function openRecord(key, id) {
  const m = MODULES[key];
  clear(viewRoot);
  const msg = el("div");
  viewRoot.append(msg);
  let record;
  try {
    record = await API.get(`${m.endpoint}/${id}`);
  } catch (err) { notify(msg, err.message, "error"); return; }

  const title = record[m.nameKey] || m.title;
  const canWrite = canWriteModule(key);

  const head = viewHeader(String(title),
    el("div", { class: "view-actions" },
      el("span", { class: "ref" }, record[m.refKey] || ""),
      el("button", { class: "btn secondary small", onclick: () => window.print() }, "Print"),
      el("button", { class: "btn secondary small", onclick: () => navigate(key) }, "Back")));
  viewRoot.append(head);

  // Action bar (module workflow actions).
  const allowedActions = m.actions.filter((act) => !act.adminOnly || isAdmin());
  if (allowedActions.length && canWrite) {
    const bar = el("div", { class: "view-actions", style: "margin-bottom:14px" });
    allowedActions.forEach((act) => {
      bar.append(el("button", { class: "btn small", onclick: () => runAction(key, id, act, openRecord) }, act.label));
    });
    viewRoot.append(bar);
  }

  const detail = el("div");
  viewRoot.append(detail);
  const tabs = [
    { key: "info", label: "Information" },
    { key: "tasks", label: "Tasks" },
    { key: "history", label: "History" },
    { key: "approvals", label: "Approval Cycles" },
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

function renderInfoTab(panel, key, record, canWrite) {
  const m = MODULES[key];
  const card = el("div", { class: "card" });
  const dl = el("dl", { class: "kv" });
  const rows = [
    ["Reference", el("span", { class: "ref" }, record[m.refKey] || "-")],
    ["Status", record.status ? badge(record.status) : "-"],
    ...m.fields.map((f) => [f.label, String(record[f.key] ?? "-")]),
    ["Created", fmtDate(record.created_at)],
    ["Updated", fmtDate(record.updated_at)],
  ];
  rows.forEach(([k, v]) => { dl.append(el("dt", null, k), el("dd", null, v)); });
  card.append(el("h3", null, "Details"), dl);

  if (canWrite && record.status !== undefined) {
    const statusField = m.filters.find((f) => f.param === "status");
    // CAPA is closed only through the e-signed "Close" action.
    const options = ((statusField && statusField.options) || ["Open", "In Progress", "Closed"])
      .filter((o) => !(key === "capa" && o === "Closed" && record.status !== "Closed"));
    const sel = el("select", null, ...options.map((o) =>
      el("option", { value: o, selected: o === record.status ? "1" : null }, o)));
    const upd = el("button", { class: "btn small" }, "Update status");
    upd.addEventListener("click", async () => {
      try {
        await API.patch(`${m.endpoint}/${record.id}`, { status: sel.value });
        toast("Status updated");
        openRecord(key, record.id);
      } catch (err) { toast(err.message, "error"); }
    });
    card.append(el("div", { class: "row", style: "margin-top:12px" },
      el("div", null, el("label", null, "Status"), sel), el("div", { style: "flex:0" }, upd)));
  }
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

function stat(number, label) {
  return el("div", { class: "stat" }, el("div", { class: "n" }, number), el("div", { class: "l" }, label));
}

async function safeGet(path, fallback) {
  try { return await API.get(path); } catch { return fallback; }
}

async function renderDashboard() {
  clear(viewRoot);
  const msg = el("div");
  viewRoot.append(viewHeader("Dashboard"), msg);
  try {
    const [audits, ncs, capa, feedback, tasks] = await Promise.all([
      safeGet("/api/audits", []),
      safeGet("/api/nonconformances", { items: [] }),
      safeGet("/api/capa", { items: [] }),
      safeGet("/api/service-feedback", { items: [] }),
      safeGet("/api/tasks?assigned_to_me=true", { items: [] }),
    ]);
    const ncItems = ncs.items || ncs;
    const capaItems = capa.items || capa;
    const fbItems = feedback.items || feedback;
    const taskItems = tasks.items || tasks;

    const openAudits = audits.filter((a) => a.status !== "Closed").length;
    const openNc = ncItems.filter((n) => n.status !== "Closed").length;
    const openCapa = capaItems.filter((c) => c.status !== "Closed").length;
    const openFb = fbItems.filter((f) => f.status !== "Closed").length;

    viewRoot.append(el("div", { class: "grid cols-3" },
      stat(openAudits, "Audits open"),
      stat(openNc, "NC open"),
      stat(openCapa, "CAPA open"),
      stat(openFb, "Feedback open"),
      stat(taskItems.length, "My tasks"),
      stat(audits.length, "Audits total"),
    ));

    const recent = el("div", { class: "card" }, el("h3", null, "Recent audits"));
    if (!audits.length) recent.append(el("div", { class: "empty" }, "No audits yet."));
    else recent.append(el("table", null,
      el("thead", null, el("tr", null, el("th", null, "Title"), el("th", null, "Status"), el("th", null, "Created"))),
      el("tbody", null, ...audits.slice(0, 5).map((a) => el("tr", { onclick: () => openAudit(a.id) },
        el("td", null, a.title), el("td", null, badge(a.status)),
        el("td", { class: "muted" }, fmtDate(a.created_at)))))));
    viewRoot.append(recent);

    if (taskItems.length) {
      const t = el("div", { class: "card" }, el("h3", null, "My open tasks"));
      t.append(el("table", null,
        el("thead", null, el("tr", null, el("th", null, "Title"), el("th", null, "Status"), el("th", null, "Due"))),
        el("tbody", null, ...taskItems.filter((x) => x.status !== "Closed").slice(0, 5).map((x) =>
          el("tr", { class: "no-click" }, el("td", null, x.title), el("td", null, badge(x.status)),
            el("td", { class: "muted" }, fmtDate(x.due_date)))))));
      viewRoot.append(t);
    }
  } catch (err) { notify(msg, err.message, "error"); }
}

// ==================================================================== task center

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
  const title = el("input", { placeholder: "Task title" });
  const desc = el("textarea", { placeholder: "Description" });
  const assignee = el("input", { type: "number", placeholder: "Assignee user id (optional)" });
  const due = el("input", { type: "date" });
  const msg = el("div");
  let instance;
  instance = modal({
    title: "New task",
    body: el("div", null, field("Title", title), field("Description", desc),
      field("Assignee id", assignee), field("Due date", due), msg),
    footer: el("div", { class: "actions" },
      el("button", { class: "btn secondary", onclick: () => instance.close() }, "Cancel"),
      el("button", { class: "btn", onclick: async () => {
        if (!title.value.trim()) { notify(msg, "Title required", "error"); return; }
        try {
          await API.post("/api/tasks", {
            title: title.value.trim(),
            description: desc.value,
            assignee_id: assignee.value ? Number(assignee.value) : null,
            due_date: due.value ? new Date(due.value).toISOString() : null,
          });
          instance.close(); toast("Task created"); renderTasks();
        } catch (err) { notify(msg, err.message, "error"); }
      } }, "Create")),
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
      el("thead", null, el("tr", null, el("th", null, "Title"), el("th", null, "Scope"), el("th", null, "Status"), el("th", null, "Approval"))),
      el("tbody", null, ...audits.map((a) => el("tr", { onclick: () => openAudit(a.id) },
        el("td", null, a.title), el("td", { class: "muted" }, a.scope || "-"),
        el("td", null, badge(a.status)),
        el("td", null, a.approval_status ? badge(a.approval_status) : "-"))))));
    viewRoot.append(card);
  } catch (err) { notify(msg, err.message, "error"); }
}

function newAuditModal() {
  const title = el("input", { placeholder: "Title" });
  const desc = el("textarea", { placeholder: "Description" });
  const scope = el("textarea", { placeholder: "Scope" });
  const msg = el("div");
  let instance;
  instance = modal({
    title: "New audit",
    body: el("div", null, field("Title", title), field("Description", desc), field("Scope", scope), msg),
    footer: el("div", { class: "actions" },
      el("button", { class: "btn secondary", onclick: () => instance.close() }, "Cancel"),
      el("button", { class: "btn", onclick: async () => {
        if (!title.value.trim()) { notify(msg, "Title required", "error"); return; }
        try {
          await API.post("/api/audits", { title: title.value.trim(), description: desc.value, scope: scope.value });
          instance.close(); toast("Audit created"); renderAudits();
        } catch (err) { notify(msg, err.message, "error"); }
      } }, "Create")),
  });
}

async function openAudit(id) {
  clear(viewRoot);
  const msg = el("div");
  viewRoot.append(msg);
  let audit;
  try { audit = await API.get(`/api/audits/${id}`); }
  catch (err) { notify(msg, err.message, "error"); return; }
  const canWrite = canWriteModule("audits");

  viewRoot.append(viewHeader(audit.title,
    el("div", { class: "view-actions" },
      el("span", { class: "ref" }, `#${id}`),
      el("button", { class: "btn secondary small", onclick: () => window.print() }, "Print"),
      canWrite && audit.status === "Review" && audit.approval_status !== "In Approval"
        ? el("button", { class: "btn small secondary", onclick: async () => {
          try { await API.post(`/api/audits/${id}/in-approval`); toast("Submitted for approval"); openAudit(id); }
          catch (err) { toast(err.message, "error"); }
        } }, "Submit for approval") : null,
      isAdmin() && audit.status === "Review" ? el("button", { class: "btn small", onclick: () => eSignModal({
        title: "Close audit (e-sign)", recordType: "audit", recordId: id,
        pathOverride: `/api/audits/${id}/close`, actionLabel: "Sign & Close",
        onDone: () => openAudit(id) }) }, "Close (e-sign)") : null,
      el("button", { class: "btn secondary small", onclick: () => navigate("audits") }, "Back"))));

  const info = el("div", { class: "card" },
    el("h3", null, "Details"),
    el("dl", { class: "kv" },
      el("dt", null, "Status"), el("dd", null, badge(audit.status)),
      el("dt", null, "Approval"), el("dd", null, audit.approval_status ? badge(audit.approval_status) : "-"),
      el("dt", null, "Description"), el("dd", null, audit.description || "-"),
      el("dt", null, "Scope"), el("dd", null, audit.scope || "-"),
      el("dt", null, "Created"), el("dd", null, fmtDate(audit.created_at))));
  if (canWrite && audit.status !== "Closed") {
    // "Closed" is reached only through the e-signed sign-off.
    const sel = el("select", null, ...AUDIT_STATUSES.filter((s) => s !== "Closed").map((s) =>
      el("option", { value: s, selected: s === audit.status ? "1" : null }, s)));
    const upd = el("button", { class: "btn small" }, "Update status");
    upd.addEventListener("click", async () => {
      try { await API.patch(`/api/audits/${id}`, { status: sel.value }); toast("Status updated"); openAudit(id); }
      catch (err) { toast(err.message, "error"); }
    });
    info.append(el("div", { class: "row", style: "margin-top:12px" },
      el("div", null, el("label", null, "Status"), sel), el("div", { style: "flex:0" }, upd)));
  }
  viewRoot.append(info);
  if (canWrite) renderAuditees(viewRoot, id);

  const tabs = [
    { key: "findings", label: "Findings" },
    { key: "papers", label: "Working Papers" },
    { key: "tasks", label: "Tasks" },
    { key: "history", label: "History" },
    { key: "approvals", label: "Approval Cycles" },
  ];
  let active = "findings";
  const detail = el("div");
  viewRoot.append(detail);

  function paint() {
    clear(detail);
    detail.append(tabBar(tabs, active, (k) => { active = k; paint(); }));
    const panel = el("div");
    detail.append(panel);
    if (active === "findings") renderFindings(panel, id, canWrite);
    if (active === "papers") renderPapers(panel, id, canWrite);
    if (active === "tasks") renderTasksTab(panel, "audit", id);
    if (active === "history") renderHistoryTab(panel, "audit", id);
    if (active === "approvals") renderApprovalsTab(panel, "audit", id);
  }
  paint();
}

async function renderAuditees(container, auditId) {
  const card = el("div", { class: "card" }, el("h3", null, "Auditees with access"));
  container.append(card);
  const body = el("div");
  card.append(body);
  async function paint() {
    clear(body);
    try {
      const [assigned, candidates] = await Promise.all([
        API.get(`/api/audits/${auditId}/auditees`), API.get("/api/audits/auditee-candidates")]);
      if (!assigned.length) body.append(el("div", { class: "empty" }, "No auditee has access to this audit yet."));
      else body.append(el("table", null,
        el("thead", null, el("tr", null, el("th", null, "User"), el("th", null, "Email"), el("th", null, ""))),
        el("tbody", null, ...assigned.map((a) => el("tr", { class: "no-click" },
          el("td", null, a.full_name ? `${a.full_name} (${a.username})` : a.username),
          el("td", { class: "muted" }, a.email || "-"),
          el("td", null, el("button", { class: "btn small secondary", onclick: async () => {
            try { await API.del(`/api/audits/${auditId}/auditees/${a.user_id}`); toast("Access removed"); paint(); }
            catch (err) { toast(err.message, "error"); }
          } }, "Remove")))))));
      const free = candidates.filter((c) => !assigned.some((a) => a.user_id === c.user_id));
      if (free.length) {
        const sel = el("select", null, ...free.map((c) => el("option", { value: c.user_id }, `${c.username}${c.email ? ` - ${c.email}` : ""}`)));
        body.append(el("div", { class: "row", style: "margin-top:12px" },
          el("div", null, el("label", null, "Give access to"), sel),
          el("div", { style: "flex:0" }, el("button", { class: "btn small", onclick: async () => {
            try { await API.post(`/api/audits/${auditId}/auditees`, { user_id: Number(sel.value) }); toast("Access granted"); paint(); }
            catch (err) { toast(err.message, "error"); }
          } }, "Add"))));
      }
    } catch (err) { body.append(el("div", { class: "empty" }, err.message)); }
  }
  paint();
}

async function renderFindings(panel, id, canWrite) {
  const card = el("div", { class: "card" }, el("h3", null, "Findings"));
  panel.append(card);
  const findings = await API.get(`/api/audits/${id}/findings`);
  if (!findings.length) card.append(el("div", { class: "empty" }, "No findings recorded."));
  else card.append(el("table", null,
    el("thead", null, el("tr", null, el("th", null, "Title"), el("th", null, "Risk"), el("th", null, "Status"), el("th", null, "Owner"))),
    el("tbody", null, ...findings.map((f) => el("tr", { class: "no-click" },
      el("td", null, f.title), el("td", null, badge(f.risk_rating)),
      el("td", null, badge(f.status)), el("td", { class: "muted" }, f.assigned_owner_email || "-"))))));
  if (canWrite) {
    const t = el("input", { placeholder: "Title" });
    const o = el("input", { placeholder: "Owner email", type: "email" });
    const r = el("select", null, ...RISK_RATINGS.map((x) => el("option", { value: x }, x)));
    const s = el("select", null, ...FINDING_STATUSES.map((x) => el("option", { value: x }, x)));
    const d = el("textarea", { placeholder: "Description" });
    const msg = el("div");
    card.append(el("hr"),
      el("div", { class: "grid cols-2" }, field("Title", t), field("Owner email", o), field("Risk", r), field("Status", s)),
      field("Description", d), msg,
      el("div", { style: "margin-top:12px" }, el("button", { class: "btn", onclick: async () => {
        if (!t.value.trim()) { notify(msg, "Title required", "error"); return; }
        try {
          await API.post(`/api/audits/${id}/findings`, {
            title: t.value.trim(), description: d.value, risk_rating: r.value, status: s.value,
            assigned_owner_email: o.value.trim() || null,
          });
          toast("Finding added"); openAudit(id);
        } catch (err) { notify(msg, err.message, "error"); }
      } }, "Add finding")));
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
        isAdmin() ? el("button", { class: "btn small secondary", onclick: async () => {
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
  viewRoot.append(viewHeader("User Management"), msg);
  const u = state.user;

  viewRoot.append(el("div", { class: "card" },
    el("h3", null, "My Account"),
    el("dl", { class: "kv" },
      el("dt", null, "Username"), el("dd", null, u.username),
      el("dt", null, "Role"), el("dd", null, badge(u.role)),
      el("dt", null, "Status"), el("dd", null, u.is_active ? badge("Active") : badge("Pending")))));

  const full = el("input", { value: u.full_name || "" });
  const email = el("input", { type: "email", value: u.email });
  const edit = el("div", { class: "card" }, el("h3", null, "Edit My Profile"),
    field("Full name", full), field("Email", email),
    el("div", { style: "margin-top:12px" }, el("button", { class: "btn" }, "Save changes")));
  edit.querySelector("button").addEventListener("click", async () => {
    notify(msg, "");
    try {
      const res = await API.patch("/api/auth/me", { full_name: full.value.trim(), email: email.value.trim() });
      state.user = res.user; API.csrf = res.csrf_token; state.csrf = res.csrf_token;
      whoami.textContent = `${state.user.full_name || state.user.username} (${state.user.role})`;
      toast("Profile updated");
    } catch (err) { notify(msg, err.message, "error"); }
  });
  viewRoot.append(edit);

  const cur = el("input", { type: "password" });
  const nw = el("input", { type: "password" });
  const pw = el("div", { class: "card" }, el("h3", null, "Change My Password"),
    field("Current password", cur), field("New password (min 8 characters)", nw),
    el("div", { style: "margin-top:12px" }, el("button", { class: "btn" }, "Change password")));
  pw.querySelector("button").addEventListener("click", async () => {
    notify(msg, "");
    try {
      await API.post("/api/auth/me/password", { current_password: cur.value, new_password: nw.value });
      cur.value = ""; nw.value = "";
      toast("Password changed");
    } catch (err) { notify(msg, err.message, "error"); }
  });
  viewRoot.append(pw);

  if (isAdmin()) {
    viewRoot.append(el("hr"));
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

async function renderUserManagement(container, msg) {
  const uUser = el("input", { placeholder: "Username" });
  const uEmail = el("input", { type: "email", placeholder: "Email" });
  const uFull = el("input", { placeholder: "Full name" });
  const uRole = el("select", null, ...ROLES.map((r) => el("option", { value: r, selected: r === "Auditor" ? "1" : null }, r)));
  const uPass = el("input", { type: "password", placeholder: "Password" });
  const form = el("div", { class: "card" }, el("h3", null, "Create user"),
    el("div", { class: "grid cols-2" }, field("Username", uUser), field("Email", uEmail),
      field("Full name", uFull), field("Role", uRole), field("Password", uPass)),
    el("div", { style: "margin-top:12px" }, el("button", { class: "btn" }, "Create user")));
  form.querySelector("button").addEventListener("click", async () => {
    try {
      await API.post("/api/users", {
        username: uUser.value.trim(), email: uEmail.value.trim(), full_name: uFull.value.trim(),
        role: uRole.value, password: uPass.value,
      });
      toast("User created"); renderUsers();
    } catch (err) { notify(msg, err.message, "error"); }
  });
  container.append(form);

  try {
    const users = await API.get("/api/users");
    const card = el("div", { class: "card" }, el("h3", null, "All users"));
    card.append(el("table", null,
      el("thead", null, el("tr", null, el("th", null, "Username"), el("th", null, "Role"), el("th", null, "Status"), el("th", null, "Actions"))),
      el("tbody", null, ...users.map((u) => {
        const roleSelect = el("select", null, ...ROLES.map((r) => el("option", { value: r, selected: r === u.role ? "1" : null }, r)));
        const toggle = el("button", { class: "btn small", onclick: async () => {
          try { await API.patch(`/api/users/${u.id}`, { is_active: !u.is_active }); renderUsers(); }
          catch (err) { notify(msg, err.message, "error"); }
        } }, u.is_active ? "Deactivate" : "Approve");
        const saveRole = el("button", { class: "btn small secondary", onclick: async () => {
          try { await API.patch(`/api/users/${u.id}`, { role: roleSelect.value }); renderUsers(); }
          catch (err) { notify(msg, err.message, "error"); }
        } }, "Save role");
        const locked = u.locked_until && new Date(`${u.locked_until}Z`) > new Date();
        const unlock = locked ? el("button", { class: "btn small secondary", onclick: async () => {
          try { await API.post(`/api/users/${u.id}/unlock`); toast("Account unlocked"); renderUsers(); }
          catch (err) { notify(msg, err.message, "error"); }
        } }, "Unlock") : null;
        return el("tr", { class: "no-click" },
          el("td", null, u.username), el("td", null, roleSelect),
          el("td", null, u.is_active ? badge("Active") : badge("Pending"), locked ? " " : null, locked ? badge("Locked") : null),
          el("td", null, el("div", { class: "actions" }, toggle, saveRole, unlock)));
      }))));
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
        el("td", null, el("button", { class: "btn small danger", onclick: async () => {
          try { await API.del(`/api/admin/backups/${encodeURIComponent(b.filename)}`); toast("Deleted"); renderBackups(); }
          catch (err) { notify(msg, err.message, "error"); }
        } }, "Delete")))))));
    viewRoot.append(card);
  } catch (err) { notify(msg, err.message, "error"); }
}

boot();
