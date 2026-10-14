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
const ROLES = ["Admin", "Auditor", "Auditee", "Committee"];

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
  const node = el("div", { class: `toast ${kind}`, role: kind === "error" ? "alert" : "status" }, text);
  host.append(node);
  setTimeout(() => node.remove(), 4000);
}

// Generic modal. `body` is a node; `footer` optional node (buttons).
function modal({ title, body, footer, width, onClose }) {
  const root = qs("#modalRoot");
  const backdrop = el("div", { class: "modal-backdrop" });
  let closed = false;
  // Accessible dialog (WCAG 2.2): labelled, focus moves in, Tab is trapped, Esc closes, focus returns.
  const opener = document.activeElement;
  const titleId = `mdl-${Math.random().toString(36).slice(2, 8)}`;
  const close = (submitted = false) => {
    if (closed) return;
    closed = true;
    backdrop.remove();
    document.removeEventListener("keydown", onKey, true);
    if (opener && opener.focus && document.contains(opener)) opener.focus({ preventScroll: true });
    if (onClose) onClose(submitted === true);
  };
  const focusables = () => [...backdrop.querySelectorAll(
    'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')]
    .filter((n) => n.offsetParent !== null);
  const onKey = (e) => {
    if (!document.contains(backdrop)) return;
    if (e.key === "Escape") { e.stopPropagation(); close(); return; }
    if (e.key !== "Tab") return;
    const items = focusables();
    if (!items.length) return;
    const first = items[0]; const last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) { last.focus(); e.preventDefault(); }
    else if (!e.shiftKey && document.activeElement === last) { first.focus(); e.preventDefault(); }
    else if (!backdrop.contains(document.activeElement)) { first.focus(); e.preventDefault(); }
  };
  document.addEventListener("keydown", onKey, true);
  backdrop.addEventListener("click", (e) => { if (e.target === backdrop) close(); });
  const dialog = el("div", { class: "modal", role: "dialog", "aria-modal": "true", "aria-labelledby": titleId, style: width ? `width:${width}px` : null },
    el("div", { class: "modal-head" }, el("h3", { id: titleId }, title),
      el("button", { class: "modal-close", type: "button", onclick: () => close(), title: "Close", "aria-label": "Close dialog" }, "\u00d7")),
    el("div", { class: "modal-body" }, body),
    footer ? el("div", { class: "modal-foot" }, footer) : null);
  backdrop.append(dialog);
  root.replaceChildren(backdrop);
  setTimeout(() => {
    const target = dialog.querySelector(".modal-body input:not([disabled]), .modal-body select:not([disabled]), .modal-body textarea:not([disabled])")
      || dialog.querySelector(".modal-close");
    if (target) target.focus({ preventScroll: true });
  }, 0);
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
    // Entity types, ports, parents and custom fields are loaded at run time (prepareOrganizations).
    prepare: (m, fresh) => prepareOrganizations(m, fresh),
    customFields: true,
    filters: [{ param: "status", label: "Status", options: ["Pending", "Approved"] }],
    columns: [
      { key: "org_ref", label: "Ref", ref: true },
      { key: "name", label: "Name" },
      { key: "category", label: "Type" },
      { key: "port_name", label: "Port / site" },
      { key: "parent_name", label: "Part of" },
      { key: "status", label: "Status", badge: true },
    ],
    fields: [
      { key: "name", label: "Name", required: true },
      { key: "category", label: "Type" },
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
      { key: "link", label: "Link remediation", kind: "link-capa" },
    ],
  },
  capa: {
    title: "Remediation",
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
  criteria: {
    title: "Criteria library",
    endpoint: "/api/criteria",
    wrapped: true,
    recordType: "criterion",
    refKey: "crit_ref",
    nameKey: "title",
    search: true,
    filters: [
      { param: "source_type", label: "Source", options: ["Law / Regulation", "GPHA Policy", "Procedure / SOP", "Standard", "Contract / Agreement", "Board resolution", "Leading practice", "Other"] },
      { param: "status", label: "Status", options: ["Active", "Retired"] },
    ],
    columns: [
      { key: "crit_ref", label: "Ref", ref: true },
      { key: "title", label: "Criterion" },
      { key: "source_type", label: "Source" },
      { key: "reference", label: "Reference / clause" },
      { key: "used_in", label: "Used in findings" },
      { key: "status", label: "Status", badge: true },
    ],
    fields: [
      { key: "title", label: "Title", required: true },
      { key: "source_type", label: "Source", type: "select", required: true, options: ["Law / Regulation", "GPHA Policy", "Procedure / SOP", "Standard", "Contract / Agreement", "Board resolution", "Leading practice", "Other"] },
      { key: "reference", label: "Reference / clause", help: "e.g. Public Procurement Act 663, s.21; GPHA Finance Manual 4.2" },
      { key: "body", label: "Criterion text (what should be)", type: "textarea", required: true },
    ],
    actions: [],
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
    const otpInput = qs("#loginOtp");
    const me = await API.post("/api/auth/login", {
      username: qs("#loginUser").value.trim(),
      password: qs("#loginPass").value,
      otp: otpInput ? otpInput.value.trim() : null,
    });
    state.user = me.user;
    state.perms = me.permissions || [];
    state.csrf = me.csrf_token;
    API.csrf = me.csrf_token;
    state.mfaSetupRequired = me.mfa_setup_required;
    qs("#loginForm").reset();
    if (otpInput) otpInput.closest(".otp-row").remove();
    showApp();
  } catch (err) {
    if (err.status === 401 && String(err.message).startsWith("MFA_REQUIRED")) {
      if (!qs("#loginOtp")) {
        const row = el("div", { class: "row otp-row" }, el("div", { class: "col-lg-12 col-sm-12 col-md-12" },
          el("div", { class: "ant-form-item" }, el("div", { class: "ant-form-item-control" },
            el("span", { class: "ant-input-affix-wrapper ant-input-affix-wrapper-lg" },
              el("input", { id: "loginOtp", class: "ant-input ant-input-lg", inputmode: "numeric", autocomplete: "one-time-code",
                maxlength: "6", placeholder: "6-digit code from your authenticator app", "aria-label": "Authentication code" }))))));
        qs("#loginPass").closest(".row").after(row);
      }
      notify(authMsg, "Enter the 6-digit code from your authenticator app, then sign in.", "ok");
      qs("#loginOtp").focus();
      return;
    }
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
  if (err && err.code === "database_updating") { checkAuthHealth(); return err.message; }
  if (err && err.status >= 500 && err.status !== 503) {
    return `Something went wrong on the server, so you could not ${action}. Please try again; if it keeps happening, tell the administrator.`;
  }
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
    state.perms = me.permissions || [];
    state.csrf = me.csrf_token;
    API.csrf = me.csrf_token;
    state.mfaSetupRequired = me.mfa_setup_required;
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
  applyNavPermissions();
  checkHealth();
  refreshDraftCount();
  initBell();
  initGlobalSearch();
  const helpBtn = qs("#helpBtn");
  if (helpBtn && !helpBtn.dataset.ready) { helpBtn.dataset.ready = "1"; helpBtn.addEventListener("click", openHelp); }
  if (state.mfaSetupRequired) { navigate("profile"); toast("Set up two-step verification to continue", "error"); return; }
  // Deep link from an e-mail: #open/<type>/<id>
  const link = /^#open\/([a-z_]+)\/(\d+)$/.exec(window.location.hash);
  if (link) { history.replaceState(null, "", window.location.pathname); openLink(link[1], Number(link[2])); return; }
  const home = isCommittee() ? "governance" : "dashboard";
  navigate(state.view && viewAllowed(state.view) && !(isCommittee() && state.view === "dashboard") ? state.view : home);
}

// ------------------------------------------------------------------ nav
document.querySelectorAll("#sidebarNav button").forEach((btn) => {
  btn.addEventListener("click", () => { navigate(btn.dataset.view); viewRoot.focus({ preventScroll: true }); });
});

function setActiveNav(view) {
  document.querySelectorAll("#sidebarNav button").forEach((b) => {
    b.classList.toggle("active", b.dataset.view === view);
    if (b.dataset.view === view) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
  });
  document.body.classList.remove("nav-open");
  window.scrollTo(0, 0);
}

function navigate(view) {
  if (state.user && !viewAllowed(view)) view = isCommittee() ? "governance" : "dashboard";
  state.view = view;
  setActiveNav(view);
  if (view === "followup") { state.remTab = "followup"; return navigate("capa"); }
  if (view === "capa") return renderRemediation(state.remTab);
  if (MODULES[view]) return renderList(view);
  if (view === "dashboard") return renderDashboard();
  if (view === "roles") return renderRolesPage();
  if (view === "programs") return renderProgramsPage();
  if (view === "evidence") return renderEvidencePage();
  if (view === "governance") return renderGovernance();
  if (view === "portfolio") return renderPortfolio();
  if (view === "workspace") return renderWorkspace();
  if (view === "analytics") return renderAnalytics();
  if (view === "qaip") return renderQaipPage();
  if (view === "capacity") return renderCapacity();
  if (view === "tasks") return renderTasks();
  if (view === "audits") return renderAudits();
  if (view === "committee") return renderCommittee();
  if (view === "configuration") return renderConfiguration();
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
    help: f.help,
    step: f.step,
    maxLength: f.maxLength || (f.type === "textarea" ? 20000 : 255),
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

async function prepareModule(key, fresh = false) {
  const m = MODULES[key];
  if (m && m.prepare) {
    try { await m.prepare(m, fresh); } catch (err) { toast(err.message, "error"); }
  }
  return m;
}

// Custom field values travel as cf_<key> form fields and are sent as one custom_fields object.
function packCustomFields(m, values) {
  if (!m.customFields) return values;
  const out = {};
  const custom = {};
  Object.entries(values).forEach(([k, v]) => { if (k.startsWith("cf_")) custom[k.slice(3)] = v === "" ? null : v; else out[k] = v; });
  if (Object.keys(custom).length) out.custom_fields = custom;
  return out;
}

async function createModal(key, initial = {}) {
  const m = await prepareModule(key, true);
  const noun = m.title.replace(/s$/, "");
  openForm({
    title: `New ${noun}`,
    key: `${key}:new`,
    meta: { title: `New ${noun}` },
    fields: moduleFormFields(m),
    initial,
    submitLabel: "Create",
    onSubmit: (values) => {
      const body = packCustomFields(m, formPayload(values, m.fields));
      if (body.due_date) body.due_date = `${body.due_date}T00:00:00`;
      Object.keys(body).forEach((k) => { if (body[k] === null && m.fields.find((f) => f.key === k && f.type === "select")) delete body[k]; });
      return API.post(m.endpoint, body);
    },
    onDone: (rec) => { toast(`${noun} ${rec[m.refKey] || ""} created`); openRecord(key, rec.id); refreshDraftCount(); },
  });
}

async function editRecordModal(key, record) {
  const m = await prepareModule(key, true);
  const initial = Object.fromEntries(m.fields.map((f) => [f.key, f.key.startsWith("cf_")
    ? (record.custom_fields || {})[f.key.slice(3)] : record[f.key]]));
  // Keep a record's current choice selectable even if it was retired from the list; never offer itself as parent.
  const formFields = moduleFormFields(m).map((f) => {
    if (f.type !== "select" || !f.options) return f;
    let options = f.name === "parent_id" ? f.options.filter((o) => (o.value ?? o) !== record.id) : f.options;
    const cur = initial[f.name];
    if (cur !== null && cur !== undefined && cur !== "" && !options.some((o) => String(o.value ?? o) === String(cur))) {
      options = [...options, typeof options[0] === "object" ? { value: cur, label: String(cur) } : cur];
    }
    return { ...f, options };
  });
  openForm({
    title: `Edit ${record[m.refKey] || m.title}`,
    key: `${key}:edit:${record.id}`,
    meta: { title: `Edit ${record[m.refKey] || ""} ${record[m.nameKey] || ""}`.trim(), record_type: m.recordType, record_id: record.id },
    fields: formFields,
    initial,
    submitLabel: "Save changes",
    onSubmit: (values) => {
      const body = packCustomFields(m, formPayload(values, m.fields));
      if (body.due_date) body.due_date = `${body.due_date}T00:00:00`;
      return API.patch(`${m.endpoint}/${record.id}`, body);
    },
    onDone: () => { toast("Changes saved"); openRecord(key, record.id); refreshDraftCount(); },
  });
}

async function renderList(key, opts = {}) {
  const m = await prepareModule(key);
  const root = opts.root || viewRoot;
  const msg = el("div");
  if (opts.root) root.append(msg);
  else {
    clear(root);
    root.append(
      viewHeader(m.title, canWriteModule(key) ? el("button", { class: "btn", onclick: () => createModal(key) }, "New") : null),
      msg,
    );
  }

  const search = el("input", { placeholder: "Search\u2026" });
  const filterEls = {};
  const toolbar = el("div", { class: "toolbar" },
    el("div", { class: "field grow" }, el("label", null, "Search"), search));
  (m.filters || []).forEach((f) => {
    const sel = el("select", null, el("option", { value: "" }, "All"),
      ...f.options.map((o) => (typeof o === "object" ? el("option", { value: o.value }, o.label) : el("option", { value: o }, o))));
    sel.setAttribute("aria-label", f.label);
    filterEls[f.param] = sel;
    toolbar.append(el("div", { class: "field" }, el("label", null, f.label), sel));
  });
  const apply = el("button", { class: "btn secondary" }, "Apply");
  toolbar.append(apply);
  apply.addEventListener("click", load);
  search.addEventListener("keydown", (e) => { if (e.key === "Enter") load(); });
  search.setAttribute("aria-label", `Search ${m.title}`);
  toolbar.append(savedViewsControl(key,
    () => Object.fromEntries([["q", search.value.trim()], ...Object.entries(filterEls).map(([p, sel]) => [p, sel.value])].filter(([, v]) => v)),
    (params) => {
      search.value = params.q || "";
      Object.entries(filterEls).forEach(([p, sel]) => { sel.value = params[p] || ""; });
      load();
    }));
  root.append(toolbar);

  const card = el("div", { class: "card" });
  root.append(card);

  async function load() {
    const params = new URLSearchParams();
    if (m.search && search.value.trim()) params.set("q", search.value.trim());
    Object.entries(filterEls).forEach(([p, sel]) => {
      if (!sel.value) return;
      const f = (m.filters || []).find((x) => x.param === p);
      if (f && f.apply) f.apply(params, sel.value); else params.set(p, sel.value);
    });
    clear(card);
    try {
      const data = await API.get(`${m.endpoint}${params.toString() ? `?${params}` : ""}`);
      const items = m.wrapped ? data.items : data;
      const total = m.wrapped ? data.total : data.length;
      card.append(dataTable(items, m.columns.map((c) => ({
        key: c.key, label: c.label, render: (it) => renderCell(it, c),
        // Rank severities/statuses in their business order, not alphabetically.
        sortValue: (it) => {
          const v = it[c.key];
          const rank = { Low: 1, Medium: 2, High: 3 }[v];
          if (rank) return rank;
          const statusOpts = ((m.filters || []).find((f) => f.param === c.key) || {}).options;
          return statusOpts && statusOpts.includes(v) ? statusOpts.indexOf(v) : v;
        },
        csv: (it) => (c.date && it[c.key] ? String(it[c.key]).slice(0, 10) : it[c.key]),
      })), { onRow: (it) => openRecord(key, it.id), exportName: `${key}-${new Date().toISOString().slice(0, 10)}.csv` }));
      if (total > items.length) card.append(el("p", { class: "muted small" }, `Showing ${items.length} of ${total}`));
    } catch (err) { notify(msg, err.message, "error"); }
  }
  load();
}

// Remediation register and follow-up live on one page: the register of agreed
// actions, and (for audit staff) the follow-up view of overdue / unvalidated ones.
function renderRemediation(tab = state.remTab || "register") {
  const staff = state.user.role !== "Auditee";
  if (!staff) tab = "register";
  state.remTab = tab;
  clear(viewRoot);
  const actions = [];
  if (tab === "followup" && isAdmin()) {
    actions.push(el("button", { class: "btn small secondary", onclick: async () => {
      try { const r = await API.post("/api/followup/run-escalations"); toast(`${r.escalated} action(s) escalated`); renderRemediation("followup"); }
      catch (err) { toast(err.message, "error"); }
    } }, el("i", { class: "bi bi-arrow-repeat" }), " Run escalation check"));
  }
  if (canWriteModule("capa")) actions.push(el("button", { class: "btn", onclick: () => createModal("capa") }, "New remediation"));
  viewRoot.append(viewHeader("Remediation & Follow-up", actions.length ? actions : null, {
    sub: tab === "followup"
      ? "Agreed actions that are overdue or waiting for an auditor to validate them"
      : "Agreed actions raised from audit findings and nonconformances, tracked to validated closure",
  }));
  const tabs = [{ key: "register", label: "Register" }];
  if (staff) tabs.push({ key: "followup", label: "Follow-up" });
  if (tabs.length > 1) viewRoot.append(tabBar(tabs, tab, (k) => renderRemediation(k)));
  const body = el("div");
  viewRoot.append(body);
  if (tab === "followup") renderFollowup(body);
  else renderList("capa", { root: body });
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
  const m = await prepareModule(key);
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
  const allowedActions = (canWrite ? m.actions.filter((act) => !act.adminOnly || isAdmin()) : [])
    .filter((act) => !(key === "capa" && act.key === "close" && !(record.status === "Review" && record.validation_result === "Effective")));

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

function fieldValue(f, record) {
  return f.key.startsWith("cf_") ? (record.custom_fields || {})[f.key.slice(3)] : record[f.key];
}

function displayValue(f, value) {
  if (value === true) return "Yes";
  if (value === false) return "No";
  if (value === null || value === undefined || value === "") return el("span", { class: "muted" }, "-");
  if (f.type === "date") return fmtDate(value).split(",")[0];
  if (f.type === "select") return badge(value);
  if (f.type === "email") return el("a", { href: `mailto:${value}` }, value);
  return String(value);
}

function renderInfoTab(panel, key, record, canWrite) {
  const m = MODULES[key];
  const statusField = m.filters.find((f) => f.param === "status");
  // Remediation is closed only through the e-signed "Close" action.
  const options = ((statusField && statusField.options) || ["Open", "In Progress", "Closed"])
    .filter((o) => !(key === "capa" && ["Closed", "Review"].includes(o) && record.status !== o));
  const control = canWrite && record.status !== undefined && record.status !== "Closed"
    && !(key === "capa" && record.status === "Review")
    ? statusControl(record.status, options, async (v) => {
      await API.patch(`${m.endpoint}/${record.id}`, { status: v });
      toast("Status updated"); openRecord(key, record.id);
    }) : null;

  const short = m.fields.filter((f) => f.type !== "textarea");
  const long = m.fields.filter((f) => f.type === "textarea");
  const dl = el("dl", { class: "kv two-col" },
    ...short.flatMap((f) => [el("dt", null, f.label), el("dd", null, f.display ? f.display(record) : displayValue(f, fieldValue(f, record)))]),
    el("dt", null, "Created"), el("dd", null, fmtDate(record.created_at)),
    el("dt", null, "Updated"), el("dd", null, fmtDate(record.updated_at)));
  const card = el("div", { class: "card" },
    el("div", { class: "card-head" }, el("h3", null, "Details"), control), dl,
    ...long.map((f) => el("div", { class: "long-field" }, el("div", { class: "lf-label" }, f.label),
      el("div", { class: `lf-value ${fieldValue(f, record) ? "" : "muted"}`.trim() }, fieldValue(f, record) || "Not recorded"))));
  panel.append(card);
  if (key === "organizations") renderEntityExtras(panel, record, canWrite);
  if (key === "capa") renderCapaFollowup(panel, record, () => openRecord("capa", record.id));
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
    return linkPicker("Link remediation", "/api/capa", (selectedId) =>
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

// ==================================================================== GPHA Workspace hub
// One launch page for every module, grouped the way the audit work flows,
// with live counts and quick actions. Tiles follow the user's role.

async function renderWorkspace() {
  clear(viewRoot);
  const staff = isStaff();
  const admin = isAdmin();
  const quick = [];
  if (staff && hasPerm("audit.create")) quick.push(el("button", { class: "btn secondary", onclick: () => navigate("audits") }, el("i", { class: "bi bi-clipboard-plus" }), " Start an audit"));
  if (canWriteModule("capa")) quick.push(el("button", { class: "btn secondary", onclick: () => createModal("capa") }, el("i", { class: "bi bi-tools" }), " New remediation"));
  if (canWriteModule("nonconformances")) quick.push(el("button", { class: "btn secondary", onclick: () => createModal("nonconformances") }, el("i", { class: "bi bi-exclamation-triangle" }), " New nonconformance"));
  viewRoot.append(viewHeader("GPHA Workspace", null, { sub: "Every Internal Audit module in one place" }));
  if (quick.length) viewRoot.append(el("div", { class: "ws-quick" }, ...quick));

  const groupsEl = el("div", { class: "ws-groups" });
  viewRoot.append(groupsEl);

  const groups = [
    { title: "Overview", tiles: [
      { view: "dashboard", icon: "grid-1x2", name: "Dashboard", desc: "Your headline numbers and recent work" },
      { view: "tasks", icon: "check2-square", name: "Task Center", desc: "Tasks assigned to you and your team", count: "tasks" },
      { view: "drafts", icon: "pencil-square", name: "My Drafts", desc: "Forms you started and can finish later", count: "drafts" },
      { view: "governance", icon: "bank", name: "Governance portal", desc: "Approved plans, issued reports and headline KPIs" },
      { view: "portfolio", icon: "geo-alt", name: "Port portfolio", desc: "Audits, findings and remediation by port" },
      { view: "committee", icon: "bar-chart-line", name: "Committee pack", desc: "Audit Committee summary and Word pack", staff: true },
      { view: "analytics", icon: "graph-up-arrow", name: "Analytics", desc: "Heat map, trends, repeat findings and KPIs", staff: true },
      { view: "qaip", icon: "patch-check", name: "Quality (QAIP)", desc: "Quality reviews and auditee satisfaction", staff: true },
    ] },
    { title: "Planning", staff: true, tiles: [
      { view: "plans", icon: "calendar3", name: "Assurance Plan", desc: "Annual risk-based audit plan by fiscal year", count: "plans" },
      { view: "universe", icon: "diagram-3", name: "Audit Universe", desc: "Auditable units and their risk ratings" },
      { view: "capacity", icon: "people-fill", name: "Capacity & time", desc: "Skills, available hours, time sheets, budgets" },
    ] },
    { title: "Audit work", tiles: [
      { view: "audits", icon: "clipboard-check", name: "Audits", desc: "Engagements: RCM, testing, findings, reports", count: "audits" },
      { view: "capa", icon: "tools", name: "Remediation & Follow-up", desc: "Agreed actions tracked to validated closure", count: "capa" },
      { view: "evidence", icon: "inbox", name: "Evidence requests", desc: "Documents requested from and submitted by auditees" },
      { view: "nonconformances", icon: "exclamation-triangle", name: "Nonconformance", desc: "Nonconformities and their disposition", count: "ncs" },
    ] },
    { title: "Registers", tiles: [
      { view: "organizations", icon: "building", name: "Organizations", desc: "Departments, units and external bodies", staff: true },
      { view: "stakeholders", icon: "people", name: "Stakeholders", desc: "Key contacts for each organization", staff: true },
      { view: "criteria", icon: "journal-bookmark", name: "Criteria library", desc: "Laws, policies and standards findings are measured against", staff: true },
      { view: "programs", icon: "list-check", name: "Audit programmes", desc: "Reusable work programmes applied to an audit's RCM", staff: true },
      { view: "service-feedback", icon: "chat-left-text", name: "Service Feedback", desc: "Auditee feedback on audit services", count: "feedback" },
    ] },
    { title: "Account & administration", tiles: [
      { view: "profile", icon: "person-gear", name: "Profile & Users", desc: "Your profile, password and two-step sign-in" },
      { view: "roles", icon: "shield-lock", name: "Roles & permissions", desc: "Job roles and what each one can do" },
      { view: "configuration", icon: "sliders", name: "Configuration", desc: "Business rules, audit types, plan settings, SLAs" },
      { view: "logs", icon: "journal-text", name: "Audit Log", desc: "Who did what, and when", admin: true },
      { view: "backups", icon: "hdd-stack", name: "Backups", desc: "Database backups and restore", admin: true },
    ] },
  ];

  const countEls = {};
  groups.filter((g) => !g.staff || staff || isCommittee()).forEach((g) => {
    const tiles = g.tiles.filter((t) => (!t.staff || staff || isCommittee()) && (!t.admin || admin) && viewAllowed(t.view));
    if (!tiles.length) return;
    groupsEl.append(el("section", { class: "ws-group" },
      el("h3", { class: "ws-group-title" }, g.title),
      el("div", { class: "ws-grid" }, ...tiles.map((t) => {
        const badgeEl = el("span", { class: "ws-count hidden" });
        if (t.count) countEls[t.count] = badgeEl;
        return el("button", { class: "ws-tile", type: "button", onclick: () => navigate(t.view) },
          el("span", { class: "ws-icon" }, el("i", { class: `bi bi-${t.icon}` })),
          el("span", { class: "ws-text" }, el("span", { class: "ws-name" }, t.name), el("span", { class: "ws-desc" }, t.desc), badgeEl));
      }))));
  });

  // Live counts (best effort: a tile without a count still works).
  const open = (rows) => (rows.items || rows).filter((x) => x.status !== "Closed").length;
  const jobs = {
    tasks: () => safeGet("/api/tasks?assigned_to_me=true", { items: [] }).then((r) => [open(r), "open"]),
    drafts: () => safeGet("/api/drafts", []).then((r) => [r.length, "unfinished"]),
    plans: () => (staff ? safeGet("/api/assurance-plans", []).then((r) => [open(r), "active"]) : null),
    audits: () => safeGet("/api/audits", []).then((r) => [open(r), "open"]),
    capa: () => safeGet("/api/capa", { items: [] }).then((r) => {
      const rows = r.items || r;
      const overdue = rows.filter((c) => c.status !== "Closed" && c.due_date && new Date(c.due_date) < new Date()).length;
      return overdue ? [overdue, "overdue", "danger"] : [open(rows), "open"];
    }),
    ncs: () => safeGet("/api/nonconformances", { items: [] }).then((r) => [open(r), "open"]),
    feedback: () => safeGet("/api/service-feedback", { items: [] }).then((r) => [open(r), "open"]),
  };
  Object.entries(countEls).forEach(([k, node]) => {
    const job = jobs[k] && jobs[k]();
    if (!job) return;
    job.then(([n, label, tone]) => {
      if (!n) return;
      node.textContent = `${n} ${label}`;
      node.classList.remove("hidden");
      if (tone) node.classList.add(tone);
    }).catch(() => {});
  });
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
      stat(capaItems.filter((c) => c.status !== "Closed").length, "Open remediation", overdueCapa ? `${overdueCapa} overdue` : "None overdue", overdueCapa ? "danger" : ""),
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
    canWriteModule("audits") && hasPerm("audit.create") ? el("button", { class: "btn", onclick: newAuditModal }, "New audit") : null), msg);
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

// Audit type and port pickers (types come from Configuration > Audit methodology; ports from Organizations).
async function auditFields() {
  let types = []; let ports = [];
  try { const c = await loadEntityConfig(); types = c.types.audit_types || []; ports = c.entities.filter((e) => e.is_port); } catch { /* optional */ }
  return [
    ...AUDIT_FIELDS.slice(0, 1),
    { name: "audit_type", label: "Audit type", type: "select", options: types, emptyLabel: "Select..." },
    { name: "port_entity_id", label: "Port", type: "select", options: ports.map((p) => ({ value: String(p.id), label: p.name })),
      emptyLabel: "Select...", help: "Defaults to the port where you work" },
    ...AUDIT_FIELDS.slice(1),
  ];
}

function auditPayload(v) {
  return { title: v.title, description: v.description || "", scope: v.scope || "", audit_type: v.audit_type || null,
    port_entity_id: v.port_entity_id ? Number(v.port_entity_id) : null };
}

async function newAuditModal() {
  const fields = await auditFields();
  openForm({
    title: "New audit",
    key: "audit:new",
    meta: { title: "New audit" },
    intro: "Tip: audits for the year are normally started from the Assurance Plan so they stay linked to it.",
    fields,
    submitLabel: "Create",
    onSubmit: (v) => { const body = auditPayload(v); if (!body.port_entity_id) delete body.port_entity_id; return API.post("/api/audits", body); },
    onDone: (a) => { toast("Audit created"); openAudit(a.id); refreshDraftCount(); },
  });
}

async function editAuditModal(audit) {
  const fields = await auditFields();
  openForm({
    title: `Edit audit #${audit.id}`,
    key: `audit:edit:${audit.id}`,
    meta: { title: `Edit audit: ${audit.title}`, record_type: "audit", record_id: audit.id },
    fields,
    initial: { ...audit, audit_type: audit.audit_type || "", port_entity_id: audit.port_entity_id ? String(audit.port_entity_id) : "" },
    submitLabel: "Save changes",
    onSubmit: (v) => API.patch(`/api/audits/${audit.id}`, auditPayload(v)),
    onDone: () => { toast("Audit saved"); openAudit(audit.id); refreshDraftCount(); },
  });
}

async function openAudit(id, startTab = null) {
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
      canWrite ? el("a", { class: "btn secondary small", href: `/api/audits/${id}/engagement-letter.docx`, title: "Engagement letter to the auditee (Word)" },
        el("i", { class: "bi bi-envelope-paper" }), " Engagement letter") : null,
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
      el("dt", null, "Audit type"), el("dd", null, audit.audit_type || el("span", { class: "muted" }, "Not set")),
      el("dt", null, "Port"), el("dd", null, (() => {
        if (!audit.port_entity_id) return el("span", { class: "muted" }, "Not set");
        const s = el("span", null, `#${audit.port_entity_id}`);
        loadEntityConfig().then((c) => { const p = c.entities.find((e) => e.id === audit.port_entity_id); if (p) s.textContent = p.name; }).catch(() => {});
        return s;
      })()),
      el("dt", null, "Created"), el("dd", null, fmtDate(audit.created_at)),
      el("dt", null, "Last updated"), el("dd", null, fmtDate(audit.updated_at))),
    el("div", { class: "long-field" }, el("div", { class: "lf-label" }, "Scope"),
      el("div", { class: `lf-value ${audit.scope ? "" : "muted"}`.trim() }, audit.scope || "Not recorded")),
    audit.description ? el("div", { class: "long-field" }, el("div", { class: "lf-label" }, "Description"),
      el("div", { class: "lf-value" }, audit.description)) : null);
  if (canWrite) info.append(el("div", { class: "auditee-strip" }));
  viewRoot.append(info);
  if (canWrite) renderAuditees(info.querySelector(".auditee-strip"), id);
  if (canWrite && ["In Progress", "Review"].includes(audit.status)) {
    const slot = el("div");
    viewRoot.append(slot);
    renderClosureCard(slot, audit, isAdmin());
  }

  const tabs = [
    ...(canWrite ? [{ key: "memo", label: "Planning Memo" }, { key: "rcm", label: "Risk & Control Matrix" }] : []),
    { key: "findings", label: "Findings / Issues" },
    { key: "report", label: "Audit Report" },
    { key: "papers", label: "Working Papers" },
    { key: "evidence", label: "Evidence Requests" },
    ...(canWrite ? [{ key: "notes", label: "Review Notes" }, { key: "time", label: "Time" }, { key: "quality", label: "Quality Review" }] : []),
    { key: "survey", label: "Survey" },
    { key: "tasks", label: "Tasks" },
    { key: "history", label: "History" },
    { key: "approvals", label: "Approval Cycles" },
  ];
  let active = startTab || (canWrite ? (audit.status === "Planned" ? "memo" : "rcm") : "findings");
  const detail = el("div");
  viewRoot.append(detail);

  function paint() {
    clear(detail);
    detail.append(tabBar(tabs, active, (k) => { active = k; paint(); }));
    const panel = el("div");
    detail.append(panel);
    if (active === "memo") renderMemoTab(panel, audit, canWrite);
    if (active === "rcm") {
      if (canWrite && audit.status !== "Closed" && hasPerm("audit.plan", "audit.fieldwork")) {
        panel.append(el("div", { class: "actions end", style: "margin-bottom:8px" }, el("button", { class: "btn small secondary",
          onclick: () => applyProgramDialog(audit, () => paint()) }, el("i", { class: "bi bi-list-check" }), " Apply audit programme")));
      }
      const rcmPanel = el("div");
      panel.append(rcmPanel);
      renderRcm(rcmPanel, id);
    }
    if (active === "evidence") renderEvidenceTab(panel, audit, canWrite);
    if (active === "time") renderAuditTimeTab(panel, audit);
    if (active === "notes") renderReviewNotesTab(panel, audit);
    if (active === "quality") renderQualityTab(panel, audit);
    if (active === "survey") renderSurveyTab(panel, audit);
    if (active === "findings") renderFindings(panel, id, canWrite);
    if (active === "report") renderReportTab(panel, id, canWrite);
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
  const card = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, "Findings"),
    canWrite ? el("button", { class: "btn small secondary", onclick: () => importDialog({
      title: "Import findings from Excel", templateKind: "findings", path: `/api/audits/${id}/import/findings`,
      intro: "Add many findings at once. Required columns: Title and Risk rating (High, Medium or Low). The file is checked first; nothing is added if any row has a problem.",
      onDone: () => openAudit(id, "findings") }) }, el("i", { class: "bi bi-file-earmark-arrow-up" }), " Import from Excel") : null));
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
  else card.append(el("div", { class: "table-wrap" }, el("table", null,
    el("thead", null, el("tr", null, el("th", null, "Ref"), el("th", null, "Title"), el("th", null, "Version"), el("th", null, "Supports"),
      el("th", null, "Uploaded"), el("th", null, "Review"), el("th", { class: "hide-sm" }, "SHA-256"), el("th", null, ""))),
    el("tbody", null, ...papers.map((p) => el("tr", { class: "no-click" },
      el("td", { class: "ref" }, p.wp_ref || "-"), el("td", null, p.title), el("td", null, `v${p.version_number}`),
      el("td", { class: "muted small" }, [p.test_id ? `Test #${p.test_id}` : null, p.finding_id ? `Finding #${p.finding_id}` : null].filter(Boolean).join(" · ") || "-"),
      el("td", { class: "muted" }, fmtDate(p.uploaded_at)),
      el("td", null, p.reviewed_at ? el("span", { title: fmtDate(p.reviewed_at) }, badge("Reviewed"))
        : (canWrite && p.uploaded_by !== state.user.id ? el("button", { class: "btn small", onclick: async () => {
          try { await API.post(`/api/working-papers/${p.id}/review`); toast("Working paper signed off"); openAudit(id, "papers"); }
          catch (err) { toast(err.message, "error"); }
        } }, "Sign off") : badge("Not reviewed"))),
      el("td", { class: "muted hide-sm", title: p.sha256 || "" }, p.sha256 ? `${p.sha256.slice(0, 12)}\u2026` : "-"),
      el("td", null, el("div", { class: "actions" },
        el("a", { href: `/api/working-papers/${p.id}/download` }, "Download"),
        canWrite ? el("button", { class: "btn small secondary", onclick: () => workPaperXrefForm(p, id, () => openAudit(id, "papers")) }, "Cross-ref") : null,
        isAdmin() ? el("button", { class: "btn small danger-ghost", onclick: async () => {
          try { await API.del(`/api/working-papers/${p.id}`); toast("Withdrawn (file retained)"); openAudit(id); }
          catch (err) { toast(err.message, "error"); }
        } }, "Withdraw") : null))))))));
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
      state.user = res.user; state.perms = res.permissions || state.perms; API.csrf = res.csrf_token; state.csrf = res.csrf_token;
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

  const sec = el("div", { class: "two-cols" });
  viewRoot.append(sec);
  renderWorkplaceCard(sec);
  renderMfaCard(sec);

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
      { name: "job_role", label: "Job role", type: "select", required: true,
        options: (JOB_ROLE_OPTIONS || []).map((r) => ({ value: r.code, label: r.name })),
        help: "Sets the access tier and review level; fine-tune permissions under Roles & permissions." },
      { name: "password", label: "Initial password", type: "password", required: true, minLength: 8, maxLength: 128,
        help: "The user should change it after first sign-in." },
    ],
    initial: { job_role: "auditor" },
    submitLabel: "Create user",
    onSubmit: (v) => API.post("/api/users", { ...v, role: ((JOB_ROLE_OPTIONS || []).find((r) => r.code === v.job_role) || {}).tier || "Auditor" }),
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
      el("thead", null, el("tr", null, el("th", null, "User"), el("th", null, "Job role"), el("th", null, "Access tier"), el("th", null, "Review level"),
        el("th", null, "Status"), el("th", { class: "num" }, ""))),
      el("tbody", null, ...(await Promise.all(users.sort((a, b) => Number(a.is_active) - Number(b.is_active)).map(async (u) => {
        const self = u.id === state.user.id;
        const jobSelect = await jobRoleSelect(u, () => renderProfile());
        const roleSelect = el("select", { class: "compact", disabled: self ? "1" : null, "aria-label": `Role of ${u.username}` },
          ...ROLES.map((r) => el("option", { value: r, selected: r === u.role ? "1" : null }, r)));
        roleSelect.addEventListener("change", async () => {
          try { await API.patch(`/api/users/${u.id}`, { role: roleSelect.value }); toast(`${u.username} is now ${roleSelect.value}`); renderProfile(); }
          catch (err) { toast(err.message, "error"); roleSelect.value = u.role; }
        });
        const staffRole = ["Admin", "Auditor"].includes(u.role);
        const levelSelect = el("select", { class: "compact", disabled: staffRole ? null : "1", "aria-label": `Review level of ${u.username}`,
          title: staffRole ? "Audit Managers review reports; the CAE approves and issues them" : "Only Admin or Auditor accounts" },
        ...[["", "-"], ["Manager", "Audit Manager"], ["CAE", "CAE"]].map(([v, t]) =>
          el("option", { value: v, selected: (u.review_level || "") === v ? "1" : null }, t)));
        levelSelect.addEventListener("change", async () => {
          try { await API.patch(`/api/users/${u.id}`, { review_level: levelSelect.value }); toast("Review level saved"); }
          catch (err) { toast(err.message, "error"); levelSelect.value = u.review_level || ""; }
        });
        const locked = u.locked_until && new Date(`${u.locked_until}Z`) > new Date();
        const actions = el("div", { class: "actions end" },
          u.mfa_enabled && !self ? el("button", { class: "btn small secondary", title: "Use when the user lost their phone",
            onclick: async () => {
              try { await API.patch(`/api/users/${u.id}`, { reset_mfa: true }); toast("Two-step verification reset"); renderProfile(); }
              catch (err) { toast(err.message, "error"); }
            } }, "Reset 2-step") : null,
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
          el("td", null, jobSelect),
          el("td", null, roleSelect),
          el("td", null, levelSelect),
          el("td", null, u.is_active ? badge("Active") : badge("Pending"), locked ? " " : null, locked ? badge("Locked") : null,
            u.mfa_enabled ? " " : null, u.mfa_enabled ? el("span", { class: "chip-mini", title: "Two-step verification on" }, el("i", { class: "bi bi-shield-check" }), " 2-step") : null),
          el("td", { class: "num" }, actions));
      })))))));
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
  registerFormOpener("report:", async (formKey) => {
    const r = await API.get(`/api/reports/${formKey.split(":")[1]}`);
    await openAudit(r.audit_id, "report");
    if (formKey.endsWith(":comments")) commentsForm(r, () => openAudit(r.audit_id, "report"));
    else reportForm(r, () => openAudit(r.audit_id, "report"));
  });
  registerFormOpener("capa:", async (formKey) => {
    const [, id, kind] = formKey.split(":");
    if (!["implement", "validate"].includes(kind)) return;
    const c = await API.get(`/api/capa/${id}`);
    await openRecord("capa", Number(id));
    (kind === "implement" ? implementForm : validateForm)(c, () => openRecord("capa", Number(id)));
  });
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
