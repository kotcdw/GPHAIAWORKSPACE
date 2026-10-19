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

// Date and time in the workspace's regional settings, e.g. "18/10/2026, 14:30". Plain dates show the date only.
// (Callers that need only the date may take the part before the comma.)
function fmtDate(value) {
  if (!value) return "-";
  const w = parseWhen(value);
  if (w.day) return formatDay(w.day);
  if (Number.isNaN(w.date.getTime())) return String(value);
  const p = zonedParts(w.date);
  return `${formatDay(p)}, ${formatClock(p)}`;
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
      { key: "status", label: "Status", badge: true, render: (r) => badge(r.is_active === false ? "Deactivated" : r.status) },
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
    prepare: (m) => prepareCapa(m),
    customFields: true,
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
      { key: "close", label: "Close (e-sign)", kind: "esign", perm: "followup.manage", path: (id) => `/api/capa/${id}/close` },
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
  if (isReadOnly()) return false;
  return isAdmin() || WRITE_ROLES.includes(state.user.role);
}

// Read-only User: may view everything in scope; the server refuses every change.
function isReadOnly() { return !!(state.user && state.user.job_role === "read_only"); }

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
    state.idleMinutes = me.idle_timeout_minutes || 0;
    setRegional(me.regional);
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

qs("#draftsBtn").addEventListener("click", () => navigate("drafts"));
whoami.addEventListener("click", () => navigate("profile"));
qs("#signOut").addEventListener("click", () => {
  setRoute(`#/${state.view || "dashboard"}`);
  signOut("You signed out.");
});

async function boot() {
  try {
    const me = await API.get("/api/auth/me");
    state.user = me.user;
    state.perms = me.permissions || [];
    state.csrf = me.csrf_token;
    API.csrf = me.csrf_token;
    state.mfaSetupRequired = me.mfa_setup_required;
    state.idleMinutes = me.idle_timeout_minutes || 0;
    setRegional(me.regional);
    showApp();
  } catch {
    authView.classList.remove("hidden");
  }
}

function renderMfaGate() {
  clear(viewRoot);
  viewRoot.append(viewHeader("Set up two-step verification", null,
    { sub: "Your role must use two-step verification. The workspace opens as soon as it is set up." }));
  const steps = el("div", { class: "card" },
    el("h3", null, "What you need"),
    el("ol", { class: "steps-list" },
      el("li", null, "An authenticator app on your phone (Microsoft Authenticator, Google Authenticator or similar)."),
      el("li", null, "Press ", el("strong", null, "Set up two-step verification"), ", add the key to the app, then type the 6-digit code it shows.")),
    el("p", { class: "muted small" }, "No authenticator app available? Ask a Super Administrator, who can switch off enforcement or change the roles under Configuration > Security (or on the server with ",
      el("code", null, "uv run python -m scripts.mfa_policy --off"), ")."));
  const holder = el("div", { class: "two-cols" });
  viewRoot.append(holder);
  renderMfaCard(holder);
  holder.append(steps);
}

function showApp() {
  authView.classList.add("hidden");
  appView.classList.remove("hidden");
  whoami.replaceChildren(el("span", { class: "who-name" }, state.user.full_name || state.user.username),
    el("span", { class: `badge badge-role-${state.user.job_role || "x"}`, title: `${state.user.role} access` }, state.user.job_role_name || state.user.role));
  document.querySelectorAll("#sidebarNav button[data-admin]").forEach((b) => {
    b.classList.toggle("hidden", !isAdmin());
  });
  // Auditees have no access to internal master data.
  ["organizations", "stakeholders", "plans", "universe"].forEach((v) => {
    const b = document.querySelector(`#sidebarNav button[data-view="${v}"]`);
    if (b) b.classList.toggle("hidden", state.user.role === "Auditee");
  });
  document.querySelectorAll("#sidebarNav [data-staff]").forEach((n) => n.classList.toggle("hidden", state.user.role === "Auditee"));
  initNavGroups();
  applyNavPermissions();
  applyAppCustomization().then(applyNavPermissions);
  initScopeChip();
  // Two-step verification is mandatory for this role and not set up yet: only the set-up screen is
  // available (every other request would be refused), so show it alone instead of a page of errors.
  document.body.classList.toggle("mfa-gate", !!state.mfaSetupRequired);
  if (state.mfaSetupRequired) { renderMfaGate(); return; }
  if (window.location.hash === "#mfa-setup") history.replaceState(null, "", window.location.pathname);
  checkHealth();
  refreshDraftCount();
  refreshPortalCount();
  refreshMyWorkCount();
  initBell();
  initGlobalSearch();
  const helpBtn = qs("#helpBtn");
  if (helpBtn && !helpBtn.dataset.ready) { helpBtn.dataset.ready = "1"; helpBtn.addEventListener("click", openHelp); }
  if (typeof Idle !== "undefined") Idle.start(state.idleMinutes);
  // Deep link from an e-mail: #open/<type>/<id>
  const link = /^#open\/([a-z_]+)\/(\d+)$/.exec(window.location.hash);
  if (link) { history.replaceState(null, "", window.location.pathname); openLink(link[1], Number(link[2])); return; }
  // A refresh (or signing in again after an idle sign-out) reopens the page in the address bar.
  if (typeof restoreRoute === "function" && restoreRoute()) return;
  const home = isCommittee() ? "governance" : state.user.role === "Auditee" ? "portal" : "dashboard";
  navigate(state.view && viewAllowed(state.view) && !(isCommittee() && state.view === "dashboard") ? state.view : home);
}

// ------------------------------------------------------------------ nav
document.querySelectorAll("#sidebarNav button[data-view]").forEach((btn) => {
  btn.addEventListener("click", () => { navigate(btn.dataset.view); viewRoot.focus({ preventScroll: true }); });
});
const brandHome = qs("#brandHome");
if (brandHome) brandHome.addEventListener("click", (e) => { e.preventDefault(); navigate(isCommittee() ? "governance" : state.user && state.user.role === "Auditee" ? "portal" : "dashboard"); });

function setActiveNav(view) {
  const g = hostGroup(view);
  const target = g ? g.host : view;
  document.querySelectorAll("#sidebarNav button[data-view]").forEach((b) => {
    b.classList.toggle("active", b.dataset.view === target);
    if (b.dataset.view === target) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
  });
  document.body.classList.remove("nav-open");
  window.scrollTo(0, 0);
}

function navigate(view) {
  // A page with unsaved changes (e.g. the auditable entity form) asks before it is left.
  if (state.dirtyGuard) { const g = state.dirtyGuard; g(() => { state.dirtyGuard = null; navigate(view); }); return; }
  if (view !== "portal") state.fromPortal = false;
  const merged = hostGroup(view);
  if (state.user && merged && view === merged.host && !viewAllowed(view)) {
    const first = hostTabsAllowed(merged)[0];
    if (first) view = first[0];
  }
  if (state.user && !viewAllowed(view)) view = isCommittee() ? "governance" : "dashboard";
  state.view = view;
  if (typeof setRoute === "function") setRoute(`#/${view}`);
  setActiveNav(view);
  navCrumbs(view);
  if (view === "capa") return renderRemediation(state.remTab);
  if (MODULES[view]) return renderList(view);
  if (view === "dashboard") return renderWorkspace();
  if (view === "roles") return renderRolesPage();
  if (view === "imports") return renderImports();
  if (view === "programs") return renderProgramsPage();
  if (view === "evidence") return renderEvidencePage();
  if (view === "governance") return renderGovernance();
  if (view === "portfolio") return renderPortfolio();
  if (view === "analytics") return renderAnalytics();
  if (view === "qaip") return renderQaipPage();
  if (view === "capacity") return renderCapacity();
  if (view === "mywork") return renderMyWork();
  if (view === "admin") return renderAdministration();
  if (view === "users") return renderUsersAdmin();
  if (view === "tasks") return renderTasks();
  if (view === "audits") return renderAudits();
  if (view === "issues") return renderIssueTracker();
  if (view === "statustracker") return renderStatusTracker();
  if (view === "results") return renderResults();
  if (view === "storyboards") return renderStoryboards();
  if (view === "robots") return renderRobots();
  if (view === "audittypes") return renderAuditTypes();
  if (view === "orgstructure") return renderOrgStructure();
  if (view === "processes") return renderProcessLibrary();
  if (view === "riskassess") return renderRiskAssessments();
  if (view === "committee") return renderCommittee();
  if (view === "configuration") return renderConfiguration();
  if (view === "plans") return renderPlans();
  if (view === "drafts") return renderDrafts();
  if (view === "universe") return renderUniverse();
  if (view === "universe_units") return renderUniverseUnits();
  if (view === "universe_processes") return renderUniverseProcesses();
  if (view === "universe_entities") return renderUniverseEntities();
  if (view === "universe_assurance") return renderAssuranceMap();
  if (view === "profile") return renderProfile();
  if (view === "logs") return renderLogs();
  if (view === "backups") return renderBackups();
  if (view === "practice") return renderPractice();
  if (view === "library") return renderLibrary();
  if (view === "scheduler") return renderScheduler();
  if (view === "automations") return renderAutomations();
  if (view === "portal") return renderPortal();
  if (view === "apps") return renderAppsPage();
  if (view === "risk") return renderRiskManager();
  if (view === "compliance") return renderComplianceMaps();
  if (view === "policies") return renderPolicies();
  if (view === "assets") return renderAssets();
  // Unknown or retired page: open the Workspace instead of a blank screen.
  state.view = "dashboard"; setActiveNav("dashboard"); navCrumbs("dashboard");
  return renderWorkspace();
}

// Page header: title, optional subtitle / meta chips, and actions on the right.
function viewHeader(title, actions = null, opts = {}) {
  const left = el("div", { class: "view-title" },
    opts.back ? el("button", { class: "back-link", onclick: opts.back, title: "Back" }, el("i", { class: "bi bi-arrow-left" })) : null,
    el("div", null,
      el("h2", null, title),
      opts.sub || opts.meta ? el("div", { class: "view-meta" }, opts.meta || null, opts.sub ? el("span", { class: "muted" }, opts.sub) : null) : null));
  const head = el("div", { class: "view-head" }, left, actions ? el("div", { class: "view-actions" }, actions) : null);
  // Merged apps: the sibling pages show as tabs under the first header of the page.
  const bar = !opts.back && !viewRoot.querySelector(".host-tabs") ? hostBar(state.view) : null;
  return bar ? el("div", { class: "view-head-wrap" }, head, bar) : head;
}

// ==================================================================== generic list

function renderCell(item, col) {
  if (col.render) return col.render(item);
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
  // An agreed remediation target date is revised from the Follow-up panel (with a reason), not by editing.
  const formFields = moduleFormFields(m).filter((f) => !(key === "capa" && f.name === "due_date" && record.due_date)).map((f) => {
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
  if (tab === "followup" && hasPerm("followup.manage")) {
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
  if (hasPerm("followup.report", "governance.view")) tabs.push({ key: "reports", label: "Statutory reports" });
  if (tabs.length > 1) viewRoot.append(tabBar(tabs, tab, (k) => renderRemediation(k)));
  const body = el("div");
  viewRoot.append(body);
  if (tab === "followup") renderFollowup(body);
  else if (tab === "reports") renderFollowupReports(body);
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
  const allowedActions = (canWrite ? m.actions.filter((act) => (!act.adminOnly || isAdmin()) && (!act.perm || hasPerm(act.perm))) : [])
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
      el("div", { class: "who" }, `${fmtDate(h.timestamp)} \u00b7 ${h.user || (h.user_id ? `user ${h.user_id}` : "System")}${h.cycle_no ? ` \u00b7 cycle ${h.cycle_no}` : ""}`),
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

// The apps the Workspace hosts, grouped and ordered like the sidebar (Diligent One style solution groups).
function workspaceGroups() {
  return [
    { title: "Audit management", tiles: [
      { view: "mywork", icon: "inbox", name: "My work", desc: "Everything waiting for you: prepare, review, respond, validate", count: "mywork" },
      { view: "universe", icon: "bullseye", name: "Audit universe", desc: "Units, processes and auditable entities" },
      { view: "riskassess", icon: "clipboard-data", name: "Audit risk assessment", desc: "Score entities on assessment factors and prioritise them for the plan", staff: true },
      { view: "plans", icon: "calendar3", name: "Assurance Plans", desc: "Annual risk-based audit plan by fiscal year", count: "plans", staff: true },
      { view: "audits", icon: "clipboard-check", name: "Audits", desc: "Engagements: planning, fieldwork, issues, results, requests", count: "audits" },
      { view: "statustracker", icon: "speedometer2", name: "Status Tracker", desc: "Time expired, work completed, budget and time spent per audit", staff: true },
      { view: "programs", icon: "list-check", name: "Project Library", desc: "Reusable audit programmes (project templates)", staff: true },
      { view: "portal", icon: "check2-square", name: "Task Tracker", desc: "Priorities, to-dos and requests assigned to you or by you", count: "tasks" },
      { view: "issues", icon: "flag", name: "Issue Tracker", desc: "Every issue and its remediation actions, with KPIs", count: "capa" },
    ] },
    { title: "Resource management", staff: true, tiles: [
      { view: "scheduler", icon: "calendar-week", name: "Scheduler", desc: "Engagement timeline, team bookings, double-booking warnings" },
      { view: "capacity", icon: "people-fill", name: "Timesheets & capacity", desc: "Time sheets, available hours, skills, budget versus actual" },
    ] },
    { title: "Risk management", tiles: [
      { view: "risk", icon: "shield-exclamation", name: "Risk Manager", desc: "Enterprise risk register, heat maps and indicators" },
      { view: "processes", icon: "gear-wide-connected", name: "Process library", desc: "Business processes linked to org units, risks and controls", staff: true },
      { view: "assets", icon: "hdd-network", name: "Asset Inventory", desc: "Systems, vendors and other assets with their criticality" },
    ] },
    { title: "Compliance management", tiles: [
      { view: "library", icon: "diagram-3-fill", name: "Frameworks", desc: "COSO, ISO, PFM and GPHA frameworks with standard controls", staff: true },
      { view: "compliance", icon: "diagram-2", name: "Compliance Maps", desc: "Obligations mapped to common controls, with gaps" },
      { view: "policies", icon: "file-earmark-ruled", name: "Policy Manager", desc: "Policies, versions, reviews and attestation" },
    ] },
    { title: "Analytics & reporting", tiles: [
      { view: "analytics", icon: "graph-up-arrow", name: "Analytics", desc: "Headline indicators, heat map, trends and repeat findings", staff: true },
      { view: "results", icon: "table", name: "Results", desc: "Analytic tables with priority, status, assignee and triggers", staff: true },
      { view: "storyboards", icon: "easel", name: "Storyboards", desc: "Charts, metrics and text from Results, shared read-only", staff: true },
      { view: "robots", icon: "robot", name: "Robots", desc: "Scheduled analytic tasks and automation rules", staff: true },
      { view: "committee", icon: "bar-chart-line", name: "Audit Committee", desc: "Committee pack, governance portal and port portfolio" },
      { view: "qaip", icon: "patch-check", name: "Quality (QAIP)", desc: "Quality reviews, professional practice and service feedback", staff: true },
    ] },
    { title: "Platform settings", tiles: [
      { view: "admin", icon: "gear-wide-connected", name: "Administration", desc: "Users, settings, audit trail, imports, data policies and backups at a glance" },
      { view: "orgstructure", icon: "diagram-3", name: "Org Structure", desc: "Ports, departments, units, organizations and contacts", staff: true },
      { view: "users", icon: "people", name: "Users & access", desc: "Accounts, approvals, roles, sessions and access history" },
      { view: "profile", icon: "person-gear", name: "My profile", desc: "Your details, password and two-step sign-in" },
      { view: "roles", icon: "shield-lock", name: "Roles & permissions", desc: "Job roles and what each one can do" },
      { view: "configuration", icon: "sliders", name: "Configuration", desc: "Business rules, audit types, apps and activity logs" },
      { view: "backups", icon: "hdd-stack", name: "Backups", desc: "Database backups and restore", admin: true },
    ] },
  ];
}

// ==================================================================== GPHA Workspace hub
// One launch page for every module, grouped the way the audit work flows,
// with live counts and quick actions. Tiles follow the user's role.

async function renderWorkspace() {
  clear(viewRoot);
  const staff = isStaff();
  const admin = isAdmin();
  viewRoot.append(viewHeader("Workspace Apps"));

  const groupsEl = el("div", { class: "ws-groups" });
  viewRoot.append(groupsEl);

  const groups = workspaceGroups();

  const countEls = {};
  groups.filter((g) => !g.staff || staff || isCommittee()).forEach((g) => {
    const tiles = g.tiles.filter((t) => (!t.staff || staff || isCommittee()) && (!t.admin || admin) && viewAllowed(t.view)
      && (typeof appEnabledForView !== "function" || appEnabledForView(t.view)));
    if (!tiles.length) return;
    groupsEl.append(el("section", { class: "ws-group" },
      el("h3", { class: "ws-group-title" }, g.title),
      el("div", { class: "ws-grid" }, ...tiles.map((t) => {
        const badgeEl = el("span", { class: "ws-count hidden" });
        if (t.count) countEls[t.count] = badgeEl;
        return el("div", { class: "ws-cell", "data-app": `${t.name} ${t.desc} ${g.title}`.toLowerCase() },
          el("button", { class: "ws-tile", type: "button", onclick: () => navigate(t.view) },
            el("span", { class: "ws-icon" }, el("i", { class: `bi bi-${t.icon}` })),
            el("span", { class: "ws-text" }, el("span", { class: "ws-name" }, t.name), el("span", { class: "ws-desc" }, t.desc), badgeEl)),
          null);
      }))));
  });

  // Live counts (best effort: a tile without a count still works).
  const open = (rows) => (rows.items || rows).filter((x) => x.status !== "Closed").length;
  const jobs = {
    tasks: () => safeGet("/api/tasks?assigned_to_me=true", { items: [] }).then((r) => [open(r), "open"]),
    mywork: () => safeGet("/api/my-work/counts", { total: 0, overdue: 0 }).then((c) => (c.overdue ? [c.overdue, "overdue", "danger"] : [c.total, "open"])),
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

async function renderTasks() {
  clear(viewRoot);
  const msg = el("div");
  viewRoot.append(viewHeader("Task Tracker", el("button", { class: "btn", onclick: newTaskModal }, el("i", { class: "bi bi-plus-lg" }), " New to-do")), msg);
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
      if (!items.length) { card.append(el("div", { class: "empty" }, "No to-dos.")); return; }
      card.append(el("table", null,
        el("thead", null, el("tr", null, el("th", null, "Title"), el("th", null, "Assignee"), el("th", null, "Status"), el("th", null, "Due"), el("th", null, ""))),
        el("tbody", null, ...items.map((t) => {
          const sel = el("select", { "aria-label": `Status of ${t.title}` }, ...TASK_STATUSES.map((s) =>
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
    title: "New to-do",
    key: "task:new",
    meta: { title: "New to-do" },
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
    onDone: () => { toast("To-do created"); renderTasks(); refreshDraftCount(); },
  });
}

// ==================================================================== audits

async function renderAudits() {
  clear(viewRoot);
  viewRoot.append(viewHeader("Audits",
    canWriteModule("audits") && hasPerm("audit.create") ? el("button", { class: "btn", onclick: newAuditModal }, el("i", { class: "bi bi-plus-lg" }), " New audit") : null,
    { sub: "Engagements you can see, with plan, lead, location and progress. Search, filter, sort and export work on the server." }));
  let types = []; let ports = [];
  try { const c = await loadEntityConfig(); types = c.types.audit_types || []; ports = c.entities.filter((e) => e.is_port); } catch { /* filters are optional */ }
  const card = el("div", { class: "card" });
  viewRoot.append(card);
  const t = serverTable({
    url: "/api/audits/register",
    storageKey: "audits",
    defaultSort: "-updated_at",
    exportName: "Audits register",
    onRow: (a) => openAudit(a.id),
    filters: [
      { key: "status", label: "Status", options: ["Planned", "In Progress", "Review", "Closed"] },
      ...(types.length ? [{ key: "audit_type", label: "Stream", options: types }] : []),
      ...(ports.length ? [{ key: "port_id", label: "Port", options: ports.map((p) => ({ value: p.id, label: p.name })) }] : []),
      ...(state.user.work_entity_id ? [{ key: "mine", label: "Scope", options: [{ value: "true", label: "My port" }] }] : []),
      { key: "fav_first", label: "Order", options: [{ value: "true", label: "Show favorites first" }] },
    ],
    emptyTitle: "No audits yet",
    emptyText: "Audits are started from an approved plan engagement or created here.",
    columns: [
      { key: "favorite", label: "Favorite", render: (a) => favoriteStar(a, () => t.reload()), csv: (a) => (a.favorite ? "Yes" : "") },
      { key: "ref", label: "Ref", sort: true, render: (a) => el("span", { class: "ref" }, a.ref) },
      { key: "title", label: "Audit", sort: true, render: (a) => el("a", { href: "#", onclick: (e) => { e.preventDefault(); e.stopPropagation(); openAudit(a.id); } }, a.title) },
      { key: "audit_type", label: "Stream", sort: true },
      { key: "port", label: "Port", sort: true },
      { key: "plan", label: "Plan", sort: true, hidden: true },
      { key: "lead", label: "Lead", sort: true },
      { key: "planned_start", label: "Planned", sort: true, render: (a) => a.planned_start ? `${fmtDay(a.planned_start)} – ${a.planned_end ? fmtDay(a.planned_end) : "?"}` : (a.planned_quarter || "-"), csv: (a) => a.planned_start || a.planned_quarter || "" },
      { key: "status", label: "Status", sort: true, render: (a) => statusBadge(a.status), csv: (a) => a.status },
      { key: "open_findings", label: "Open findings", sort: true, num: true, render: (a) => a.findings ? `${a.open_findings} / ${a.findings}` : "0", csv: (a) => a.open_findings },
      { key: "working_papers", label: "Working papers", num: true, hidden: true },
      { key: "progress", label: "Progress", sort: true, num: true, render: (a) => progressBar(a.progress), csv: (a) => a.progress },
      { key: "report_status", label: "Report", render: (a) => a.report_status ? statusBadge(a.report_status) : "-", csv: (a) => a.report_status || "" },
      { key: "updated_at", label: "Updated", sort: true, render: (a) => fmtDay(a.updated_at), csv: (a) => a.updated_at },
    ],
  });
  card.append(t.root);
}

const AUDIT_FIELDS = [
  { name: "title", label: "Title", required: true, maxLength: 255, singleLine: true },
  { name: "scope", label: "Scope", type: "textarea", maxLength: 20000 },
  { name: "description", label: "Description / background", type: "textarea", maxLength: 20000 },
];

// Audit type and port pickers (types come from Configuration > Audit methodology; ports from Organizations).
async function auditFields(keepPortId = null) {
  let types = []; let ports = [];
  // Deactivated ports are not offered for new audits; an audit that already names one keeps it.
  try { const c = await loadEntityConfig(); types = c.types.audit_types || []; ports = c.entities.filter((e) => e.is_port && (e.is_active !== false || e.id === keepPortId)); } catch { /* optional */ }
  const defs = await safeGet("/api/custom-fields?module=audits", []);
  return [
    ...AUDIT_FIELDS.slice(0, 1),
    { name: "audit_type", label: "Audit type", type: "select", options: types, emptyLabel: "Select..." },
    { name: "port_entity_id", label: "Port", type: "select", options: ports.map((p) => ({ value: String(p.id), label: p.name })),
      emptyLabel: "Select...", help: "Defaults to the port where you work" },
    ...AUDIT_FIELDS.slice(1),
    ...customFieldDefs(defs).map((f) => ({ ...f, name: f.key })),
  ];
}

function auditPayload(v) {
  const custom = {};
  Object.entries(v).forEach(([k, x]) => { if (k.startsWith("cf_")) custom[k.slice(3)] = x === "" ? null : x; });
  return { title: v.title, description: v.description || "", scope: v.scope || "", audit_type: v.audit_type || null,
    port_entity_id: v.port_entity_id ? Number(v.port_entity_id) : null, custom_fields: custom };
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
  const fields = await auditFields(audit.port_entity_id);
  openForm({
    title: `Edit audit #${audit.id}`,
    key: `audit:edit:${audit.id}`,
    meta: { title: `Edit audit: ${audit.title}`, record_type: "audit", record_id: audit.id },
    fields,
    initial: { ...audit, audit_type: audit.audit_type || "", port_entity_id: audit.port_entity_id ? String(audit.port_entity_id) : "",
      ...Object.fromEntries(Object.entries(audit.custom_fields || {}).map(([k, x]) => [`cf_${k}`, x])) },
    submitLabel: "Save changes",
    onSubmit: (v) => API.patch(`/api/audits/${audit.id}`, auditPayload(v)),
    onDone: () => { toast("Audit saved"); openAudit(audit.id); refreshDraftCount(); },
  });
}

async function openAudit(id, startTab = null) {
  setActiveNav("audits");
  clear(viewRoot);
  viewRoot.append(loadingState("Opening the audit…"));
  let audit;
  try { audit = await API.get(`/api/audits/${id}`); }
  catch (err) { clear(viewRoot); viewRoot.append(errorState(err, () => openAudit(id, startTab))); return; }
  clear(viewRoot);
  const canWrite = canWriteModule("audits");
  const terms = canWrite || isStaff() ? await auditTerms(id) : {};
  const ref = `AUD-${String(id).padStart(4, "0")}`;

  const actions = [
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
  ].filter(Boolean);

  // Phase tabs straight under the title; supporting views open from the utility links on the right.
  const tabs = [
    { key: "dashboard", label: "Dashboard" },
    ...(canWrite ? [{ key: "memo", label: termOf(terms, "planning", "Planning") }, { key: "fieldwork", label: termOf(terms, "fieldwork", "Fieldwork") }] : []),
    ...(canWrite ? [{ key: "quality", label: termOf(terms, "reviews", "Reviews") }] : []),
    { key: "report", label: termOf(terms, "results", "Results") },
    { key: "findings", label: `${termOf(terms, "issue", "Issue")}s` },
    ...(canWrite ? [{ key: "progress", label: "Progress" }] : []),
    { key: "evidence", label: `${termOf(terms, "request", "Request")}s` },
  ];
  const utility = [
    ...(canWrite ? [{ label: "Review notes", icon: "chat-square-text", key: "notes" }, { label: "Time entries", icon: "clock", key: "time" }] : []),
    { label: "To-dos", icon: "check2-square", key: "tasks" },
    { label: "History", icon: "clock-history", key: "history" },
    { label: "Approvals", icon: "pen", key: "approvals" },
  ];
  const side = el("div");
  const layout = recordLayout({
    crumbs: recordCrumbs("audits", ref),
    back: () => navigate("audits"),
    title: audit.title, ref, status: audit.status,
    meta: audit.approval_status ? [statusBadge(audit.approval_status)] : [],
    actions,
    utility: utility.map((u) => ({ ...u, onClick: () => layout.select(u.key) })),
    tabs,
    side,
    onTab: (key, pane) => {
      state.lastAuditTab = { id, key };
      if (typeof setRoute === "function") setRoute(`#/audit/${id}/${key}`);
      // Work screens (HighBond execution views) use the full width; the summary panel shows on the others.
      layout.root.querySelector(".rec-grid").classList.toggle("no-side", ["fieldwork", "findings", "evidence", "progress"].includes(key));
      paintTab(key, pane);
    },
  });
  viewRoot.append(layout.root);
  renderAuditSide(side, audit, canWrite);

  function paintTab(key, pane) {
    if (key === "dashboard") renderAuditDashboard(pane, audit, canWrite, (k) => layout.select(k));
    if (key === "memo") renderMemoTab(pane, audit, canWrite);
    if (key === "fieldwork") renderFieldworkTab(pane, audit, canWrite);
    if (key === "evidence") renderEvidenceTab(pane, audit, canWrite);
    if (key === "time") renderAuditTimeTab(pane, audit);
    if (key === "notes") renderReviewNotesTab(pane, audit);
    if (key === "quality") renderQualityTab(pane, audit);
    if (key === "progress") renderProgressTab(pane, audit);
    if (key === "findings") renderAuditIssues(pane, audit, canWrite);
    if (key === "report") {
      // Results: the report, then the supporting workpapers (Diligent: Results > Supporting Workpapers).
      const rep = el("div"); const wp = el("div", { class: "supporting-wp" });
      pane.append(rep, wp);
      renderReportTab(rep, id, canWrite);
      renderPapers(wp, id, canWrite);
    }
    if (key === "tasks") renderTasksTab(pane, "audit", id);
    if (key === "history") renderHistoryTab(pane, "audit", id);
    if (key === "approvals") renderApprovalsTab(pane, "audit", id);
  }
  const legacy = { rcm: "fieldwork", papers: "report", survey: "dashboard" };
  // Reloading the same audit (after a save) keeps the tab the user was on.
  const remembered = state.lastAuditTab && state.lastAuditTab.id === id ? state.lastAuditTab.key : null;
  layout.select(startTab ? (legacy[startTab] || startTab) : (remembered || "dashboard"));
}

// Right-hand summary of an audit: key facts, status control and close-out readiness.
function renderAuditSide(side, audit, canWrite) {
  const control = canWrite && audit.status !== "Closed"
    ? statusControl(audit.status, AUDIT_STATUSES.filter((x) => x !== "Closed"), async (v) => {
      await API.patch(`/api/audits/${audit.id}`, { status: v });
      toast("Status updated"); openAudit(audit.id);
    }) : null;
  const plan = audit.plan_id ? (() => {
    const a = el("a", { href: "#", onclick: (e) => { e.preventDefault(); openPlan(audit.plan_id); } }, `Plan #${audit.plan_id}`);
    API.get(`/api/assurance-plans/${audit.plan_id}`).then((p) => { a.textContent = `FY${p.fiscal_year} · ${p.plan_ref}`; }).catch(() => {});
    return a;
  })() : el("span", { class: "muted" }, "Not linked");
  const port = (() => {
    if (!audit.port_entity_id) return el("span", { class: "muted" }, "Not set");
    const s = el("span", null, `#${audit.port_entity_id}`);
    loadEntityConfig().then((c) => { const p = c.entities.find((e) => e.id === audit.port_entity_id); if (p) s.textContent = p.name; }).catch(() => {});
    return s;
  })();
  side.append(el("div", { class: "card" }, el("h3", null, "Engagement"),
    el("dl", { class: "kv" },
      el("dt", null, "Plan"), el("dd", null, plan),
      el("dt", null, "Stream"), el("dd", null, audit.audit_type || el("span", { class: "muted" }, "Not set")),
      el("dt", null, "Nature"), el("dd", null, audit.nature || "Assurance"),
      el("dt", null, "Port"), el("dd", null, port),
      el("dt", null, "Created"), el("dd", null, fmtDay(audit.created_at)),
      el("dt", null, "Updated"), el("dd", null, fmtDay(audit.updated_at))),
    control ? el("div", { style: "margin-top:10px" }, control) : null));
  const teamSlot = el("div");
  side.append(teamSlot);
  renderAuditTeam(teamSlot, audit, canWrite && hasPerm("audit.create") && audit.status !== "Closed");
  if (canWrite && ["In Progress", "Review"].includes(audit.status)) renderClosureCard(side, audit, isAdmin());
}

// Engagement team: members work on the audit even when it belongs to another port.
async function renderAuditTeam(slot, audit, canEdit) {
  const LEVEL = { "Unit Head": "Unit Head", Manager: "Audit Manager", PIA: "PIA", CAE: "GM Audit" };
  const card = el("div", { class: "card" });
  slot.replaceChildren(card);
  card.append(el("div", { class: "card-head" }, el("h3", null, "Engagement team")));
  let team;
  try { team = await API.get(`/api/audits/${audit.id}/team`); } catch (err) { card.append(errorState(err)); return; }
  if (!team.length) card.append(el("p", { class: "muted small" }, "No team assigned yet."));
  else card.append(el("ul", { class: "plain-list team-list" }, ...team.map((m) => el("li", null,
    el("div", null, el("strong", null, m.name), el("div", { class: "muted small" },
      [m.team_role, m.approval_level ? LEVEL[m.approval_level] || m.approval_level : null].filter(Boolean).join(" · ")),
      m.independence ? el("div", null, el("span", { class: `u-chip ${m.independence === "Declared" || m.independence === "Cleared" ? "ok" : "warn"}` }, m.independence)) : null,
      ...(m.objectivity || []).map((t) => el("div", { class: "small text-danger" }, el("i", { class: "bi bi-exclamation-triangle" }), ` ${t}`))),
    canEdit && m.team_role !== "Lead auditor" ? el("button", { class: "chip-x", type: "button", title: `Remove ${m.name}`, "aria-label": `Remove ${m.name}`,
      onclick: async () => {
        const ok = await confirmDialog({ title: "Remove from team", text: `${m.name} will lose access to this audit unless it belongs to their port.`, confirmLabel: "Remove", danger: true });
        if (!ok.ok) return;
        try { await API.del(`/api/audits/${audit.id}/team/${m.user_id}`); toast("Removed from the team"); renderAuditTeam(slot, audit, canEdit); }
        catch (err) { toast(err.message, "error"); }
      } }, "\u00d7") : null))));
  if (!canEdit) return;
  const who = el("select", { "aria-label": "Team member" }, el("option", { value: "" }, "Add a person…"));
  const role = el("select", { "aria-label": "Team role" }, ...["Auditor", "Reviewer", "Lead auditor"].map((r) => el("option", { value: r }, r)));
  safeGet(`/api/audits/${audit.id}/team-candidates`, []).then((list) => {
    const on = new Set(team.map((t) => t.user_id));
    list.filter((u) => !on.has(u.id)).forEach((u) => who.append(el("option", { value: u.id }, u.approval_level ? `${u.name} (${LEVEL[u.approval_level] || u.approval_level})` : u.name)));
  });
  card.append(el("div", { class: "team-add" }, who, role, el("button", { class: "btn small", type: "button", onclick: async () => {
    if (!who.value) { toast("Choose a person", "error"); return; }
    try {
      const t = await API.post(`/api/audits/${audit.id}/team`, { user_id: Number(who.value), team_role: role.value });
      const added = t.find((m) => m.user_id === Number(who.value));
      if (added && added.objectivity && added.objectivity.length) toast(`Objectivity: ${added.objectivity.join("; ")}`, "error");
      else toast("Team updated");
      renderAuditTeam(slot, audit, canEdit);
    }
    catch (err) { toast(err.message, "error"); }
  } }, "Add")));
}

// Audit Dashboard tab: scope, auditees, independence, review status of working papers and the findings summary.
async function renderAuditDashboard(pane, audit, canWrite, goTo) {
  const id = audit.id;
  const info = el("div", { class: "card" },
    el("div", { class: "card-head" }, el("h3", null, "Scope")),
    el("div", { class: `lf-value ${audit.scope ? "" : "muted"}`.trim() }, audit.scope || "Not recorded"),
    audit.description ? el("div", { class: "long-field" }, el("div", { class: "lf-label" }, "Description"), el("div", { class: "lf-value" }, audit.description)) : null);
  if (canWrite) info.append(el("div", { class: "auditee-strip" }));
  pane.append(info);
  if (canWrite) renderAuditees(info.querySelector(".auditee-strip"), id);

  const review = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, "Working paper review status"),
    el("button", { class: "link-btn", type: "button", onclick: () => goTo("report") }, "Open supporting workpapers")));
  const fsum = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, "Findings"),
    el("button", { class: "link-btn", type: "button", onclick: () => goTo("findings") }, "Open findings")));
  pane.append(review, fsum);
  if (isStaff()) { const dslot = el("div"); pane.append(dslot); renderDeclarationCard(dslot, audit); }

  const [papers, findings] = await Promise.all([
    safeGet(`/api/audits/${id}/working-papers`, []), safeGet(`/api/audits/${id}/findings`, [])]);
  // Latest version of each paper; columns follow the GPHA chain levels seen on this audit's papers.
  const latest = Object.values(papers.reduce((acc, p) => { if (!acc[p.title] || acc[p.title].version_number < p.version_number) acc[p.title] = p; return acc; }, {}));
  if (!latest.length) review.append(emptyState({ icon: "file-earmark-text", title: "No working papers yet", text: "Create one on the Working papers tab." }));
  else {
    const order = ["Unit Head", "Audit Manager", "PIA", "GM Audit (CAE)"];
    const seen = new Set();
    latest.forEach((p) => { (p.review_trail || []).forEach((t) => seen.add(t.level)); if (p.review_stage) seen.add(p.review_stage); });
    const levels = order.filter((l) => seen.has(l));
    const cols = levels.length ? levels : ["Reviewed"];
    const signedAt = (p, level) => (level === "Reviewed" ? !!p.reviewed_at : (p.review_trail || []).some((t) => t.level === level));
    const chip = (n, total) => el("span", { class: `count-chip ${n === total ? "done" : n ? "part" : "none"}` }, n === total ? "✓" : `${n}/${total}`);
    const total = latest.length;
    review.append(el("div", { class: "table-wrap" }, el("table", { class: "dense" },
      el("thead", null, el("tr", null, el("th", null, "Working paper"), el("th", null, "Prepared"), ...cols.map((c) => el("th", null, c)), el("th", null, "Sign-offs"))),
      el("tbody", null,
        el("tr", { class: "no-click" }, el("td", null, el("strong", null, `All papers (${total})`)), el("td", null, chip(total, total)),
          ...cols.map((c) => el("td", null, chip(latest.filter((p) => signedAt(p, c)).length, total))), el("td", null, "")),
        ...latest.slice(0, 10).map((p) => el("tr", { class: "no-click" },
          el("td", null, el("a", { href: "#", onclick: (e) => { e.preventDefault(); wpTemplateView(p.id, () => goTo("dashboard")); } }, p.wp_ref ? `${p.wp_ref} ${p.title}` : p.title)),
          el("td", null, chip(1, 1)), ...cols.map((c) => el("td", null, chip(signedAt(p, c) ? 1 : 0, 1))),
          el("td", null, el("span", { class: "signoff-dots", title: p.reviewed_at ? "Reviewed" : (p.review_stage ? `Awaiting ${p.review_stage}` : "Not reviewed") },
            el("i", { class: "on" }), ...cols.map((c) => el("i", { class: signedAt(p, c) ? "on" : "" }))))))))));
    if (latest.length > 10) review.append(el("p", { class: "muted small" }, `Showing 10 of ${latest.length}.`));
  }
  if (!findings.length) fsum.append(emptyState({ icon: "flag", title: "No findings recorded" }));
  else {
    const by = (r) => findings.filter((f) => f.risk_rating === r).length;
    const resp = findings.filter((f) => f.management_response).length;
    const client = findings.filter((f) => f.client_response).length;
    const open = findings.filter((f) => f.status !== "Closed").length;
    fsum.append(el("div", { class: "stats" },
      ...[["Open", open, open ? "warn" : "ok"], ["High", by("High"), by("High") ? "danger" : ""], ["Medium", by("Medium"), ""], ["Low", by("Low"), ""],
        ["Client responses", `${client}/${findings.length}`, client === findings.length ? "ok" : "warn"],
        ["Management responses", `${resp}/${findings.length}`, resp === findings.length ? "ok" : "warn"]]
        .map(([l, n, k]) => el("div", { class: `stat ${k}` }, el("div", { class: "l" }, l), el("div", { class: "n" }, String(n))))));
  }
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

// Review progress of a working paper along the review chain, with the next sign-off.
function wpReviewCell(p, canWrite, reload) {
  const trail = p.review_trail || [];
  const steps = trail.map((t) => el("span", { class: "chip-mini ok", title: `${t.name} · ${fmtDate(t.at)}${t.acting_as ? ` (acting ${t.acting_as})` : ""}` }, el("i", { class: "bi bi-check2" }), ` ${t.level}`));
  if (p.reviewed_at) return el("span", { class: "chips" }, ...steps, el("span", { title: fmtDate(p.reviewed_at) }, badge("Reviewed")));
  const label = p.review_stage ? `Sign off as ${p.review_stage}` : "Sign off";
  const btn = canWrite && p.uploaded_by !== state.user.id ? el("button", { class: "btn small", onclick: async () => {
    try {
      const r = await API.post(`/api/working-papers/${p.id}/review`);
      toast(r.reviewed_at ? "Working paper reviewed" : `Signed off; next: ${r.review_stage}`); reload();
    } catch (err) { toast(err.message, "error"); }
  } }, label) : null;
  return el("span", { class: "chips" }, ...steps, btn || badge(p.review_stage ? `Awaiting ${p.review_stage}` : "Not reviewed"));
}

// Print just one element (e.g. a working paper form) using the print stylesheet.
function printNode(node, title) {
  const area = el("div", { id: "printArea" }, el("h2", null, title), node.cloneNode(true));
  document.body.append(area);
  document.body.classList.add("printing-area");
  const done = () => { document.body.classList.remove("printing-area"); area.remove(); window.removeEventListener("afterprint", done); };
  window.addEventListener("afterprint", done);
  window.print();
  setTimeout(done, 1000);
}

// ---- GPHA Working Paper Template: read-only (printable) view and edit form
const WP_FORM_TOTAL = 17;

async function wpTemplateView(paperId, reload) {
  let t;
  try { t = await API.get(`/api/working-papers/${paperId}/template`); } catch (err) { toast(err.message, "error"); return; }
  const a = t.admin;
  const val = (k) => t.values[k] || "";
  const row = (label, value) => el("tr", null, el("th", null, label), el("td", null, value || el("span", { class: "muted" }, "-")));
  const reviewed = a.reviewed_by.length
    ? a.reviewed_by.map((r) => `${r.name} (${r.level}${r.acting_as ? `, acting ${r.acting_as}` : ""}) ${fmtDate(r.at)}`).join("; ")
    : (a.review_stage ? `Awaiting ${a.review_stage}` : "Not yet reviewed");
  const body = el("div", { class: "wp-doc" },
    el("div", { class: "wp-doc-head" }, el("strong", null, "GHANA PORTS AND HARBOURS AUTHORITY"), el("div", null, "Internal Audit Department - Working Paper")),
    el("h4", null, "Administrative details"),
    el("table", { class: "wp-admin" }, el("tbody", null,
      row("Audit title", a.audit_title), row("Working paper", `${a.title} (v${a.version})`),
      row("Audit period", val("audit_period")), row("Location", val("location")), row("Audited unit", val("audited_unit")),
      row("Audit reference number", a.audit_reference), row("Prepared by", a.prepared_by), row("Date prepared", fmtDate(a.date_prepared)),
      row("Reviewed by", reviewed), row("Date reviewed", a.date_reviewed ? fmtDate(a.date_reviewed) : ""),
      a.linked_finding ? row("Supports finding", `#${a.linked_finding.id} ${a.linked_finding.title}`) : null)),
    ...t.fields.filter((f) => f.section === "body").map((f) => el("section", { class: "wp-sec" },
      el("h5", null, f.label), el("div", { class: "wp-val" }, f.kind === "date" && val(f.key) ? fmtDate(val(f.key)) : (val(f.key) || el("span", { class: "muted" }, "Not completed"))))),
    el("h4", null, "Sign-off"),
    el("table", { class: "wp-admin" }, el("tbody", null,
      row("Prepared by", `${a.prepared_by || "-"} · ${fmtDate(a.date_prepared)}`),
      ...a.reviewed_by.map((r) => row(`Reviewed by (${r.level})`, `${r.name}${r.acting_as ? ` (acting ${r.acting_as})` : ""} · ${fmtDate(r.at)}`)))));
  let instance;
  const footer = el("div", { class: "actions" },
    el("span", { class: "muted small" }, `${t.complete}/${t.total} fields completed`),
    el("button", { class: "btn secondary", onclick: () => printNode(body, `${a.title} v${a.version}`) }, el("i", { class: "bi bi-printer" }), " Print"),
    t.can_edit ? el("button", { class: "btn", onclick: () => { instance.close(); wpTemplateForm(t, reload); } }, el("i", { class: "bi bi-pencil" }), " Fill in / edit") : null);
  instance = modal({ title: `Working paper: ${a.title} v${a.version}`, body, footer, width: 900 });
}

function wpTemplateForm(t, reload) {
  const fields = [{ type: "heading", label: "Administrative details" }];
  t.fields.forEach((f) => {
    if (f.key === "objective") fields.push({ type: "heading", label: "Working paper" });
    if (f.key === "client_response") fields.push({ type: "heading", label: "Responses" });
    const base = { name: f.key, label: f.label, help: f.help };
    if (f.kind === "text") fields.push({ ...base, type: "textarea", maxLength: 20000, full: true });
    else if (f.kind === "date") fields.push({ ...base, type: "date" });
    else if (f.kind === "location" && t.locations.length) fields.push({ ...base, type: "select", options: t.locations, emptyLabel: "- choose -" });
    else fields.push({ ...base, maxLength: 255, singleLine: true });
  });
  openForm({
    title: `GPHA working paper form: ${t.admin.title} v${t.admin.version}`,
    key: `wp-template:${t.id}`,
    meta: { title: `Working paper form ${t.admin.title}` },
    intro: el("div", null,
      el("p", { class: "muted small" }, `${t.admin.audit_title} · prepared by ${t.admin.prepared_by || "-"} on ${fmtDate(t.admin.date_prepared)}`),
      t.signed ? el("div", { class: "form-banner warn" }, "This paper has review sign-offs. Saving a change clears them and the review starts again.") : null),
    fields,
    initial: t.values,
    width: 900,
    submitLabel: "Save form",
    onSubmit: (v) => API.put(`/api/working-papers/${t.id}/template`, { values: Object.fromEntries(Object.entries(v).map(([k, x]) => [k, x ?? ""])) }),
    onDone: (r) => { toast(r && r.review_restarted ? "Form saved; the review restarts" : "Form saved"); if (reload) reload(); },
  });
}

async function renderPapers(panel, id, canWrite) {
  const card = el("div", { class: "card" }, el("h3", null, "Supporting workpapers"));
  panel.append(card);
  const papers = await API.get(`/api/audits/${id}/working-papers`);
  if (!papers.length) card.append(el("div", { class: "empty" }, "No working papers yet. Create one below: the GPHA template form, with or without a file."));
  else card.append(el("div", { class: "table-wrap" }, el("table", null,
    el("thead", null, el("tr", null, el("th", null, "Ref"), el("th", null, "Title"), el("th", null, "Version"), el("th", null, "Supports"),
      el("th", null, "Uploaded"), el("th", null, "Review"), el("th", { class: "hide-sm" }, "SHA-256"), el("th", null, ""))),
    el("tbody", null, ...papers.map((p) => el("tr", { class: "no-click" },
      el("td", { class: "ref" }, p.wp_ref || "-"),
      el("td", null, el("a", { href: "#", onclick: (e) => { e.preventDefault(); wpTemplateView(p.id, () => openAudit(id, "papers")); } }, p.title),
        el("div", { class: "muted small" }, `Form ${p.form_filled}/${WP_FORM_TOTAL} fields${p.has_file ? "" : " · no file"}`)),
      el("td", null, `v${p.version_number}`),
      el("td", { class: "muted small" }, [p.test_id ? `Test #${p.test_id}` : null, p.finding_id ? `Finding #${p.finding_id}` : null].filter(Boolean).join(" · ") || "-"),
      el("td", { class: "muted" }, fmtDate(p.uploaded_at)),
      el("td", null, wpReviewCell(p, canWrite, () => openAudit(id, "papers"))),
      el("td", { class: "muted hide-sm", title: p.sha256 || "" }, p.sha256 ? `${p.sha256.slice(0, 12)}\u2026` : "-"),
      el("td", null, el("div", { class: "actions" },
        el("button", { class: "btn small secondary", onclick: () => wpTemplateView(p.id, () => openAudit(id, "papers")) }, el("i", { class: "bi bi-file-earmark-text" }), " Form"),
        p.has_file ? el("a", { href: `/api/working-papers/${p.id}/download` }, "Download") : null,
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
      el("p", { class: "muted small" }, "Each working paper follows the GPHA Working Paper Template. Attaching a file is optional. Using an existing title creates a new version, which carries the form forward."),
      el("div", { class: "row" }, field("Title", t), el("div", null, el("label", null, "File (optional)"), file)), msg,
      el("div", { style: "margin-top:12px" }, el("button", { class: "btn", onclick: async () => {
        if (!t.value.trim()) { notify(msg, "Enter a title", "error"); return; }
        const form = new FormData();
        form.append("title", t.value.trim());
        if (file.files.length) form.append("file", file.files[0]);
        try {
          const p = await API.upload(`/api/audits/${id}/working-papers`, form);
          toast(p.version_number > 1 ? `Version ${p.version_number} created` : "Working paper created");
          openAudit(id, "papers");
          wpTemplateView(p.id, () => openAudit(id, "papers"));
        } catch (err) { notify(msg, err.message, "error"); }
      } }, "Create working paper")));
  }
}

// ==================================================================== profile

async function renderProfile() {
  clear(viewRoot);
  const msg = el("div");
  viewRoot.append(viewHeader("My profile", null,
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
      whoami.replaceChildren(el("span", { class: "who-name" }, state.user.full_name || state.user.username),
    el("span", { class: `badge badge-role-${state.user.job_role || "x"}`, title: `${state.user.role} access` }, state.user.job_role_name || state.user.role));
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
        help: "At least 8 characters; not your username or a common password." },
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

  // Recent activity on this account (sign-ins, failed attempts, changes by administrators).
  const act = el("div", { class: "card" }, el("h3", null, "Recent activity on your account"), loadingState());
  viewRoot.append(act);
  API.get("/api/auth/me/activity").then((d) => {
    act.lastChild.remove();
    if (!d.items.length) { act.append(el("p", { class: "muted" }, "No activity recorded yet.")); return; }
    act.append(el("div", { class: "table-wrap" }, el("table", { class: "compact-table" },
      el("thead", null, el("tr", null, el("th", null, "When"), el("th", null, "Event"), el("th", null, "From"))),
      el("tbody", null, ...d.items.slice(0, 10).map((r) => el("tr", { class: `no-click ${r.outcome === "failure" ? "row-failure" : ""}` },
        el("td", null, fmtDate(r.at)), el("td", null, r.event, r.by_someone_else ? el("span", { class: "muted small" }, " · by an administrator") : null),
        el("td", { title: r.browser || "" }, r.ip || "-")))))),
    el("p", { class: "muted small" }, "Don't recognise something? Change your password and tell an administrator."));
  }).catch(() => act.remove());
}

// ==================================================================== users (admin)

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
      { name: "job_role", label: "Role", type: "select", required: true,
        options: (JOB_ROLE_OPTIONS || []).filter((r) => r.assignable).map((r) => ({ value: r.code, label: r.name })) },
      { name: "password", label: "Initial password", type: "password", required: true, minLength: 8, maxLength: 128,
        help: "They change it after their first sign-in." },
    ],
    initial: { job_role: "auditor" },
    submitLabel: "Create user",
    onSubmit: (v) => API.post("/api/users", { ...v, role: ((JOB_ROLE_OPTIONS || []).find((r) => r.code === v.job_role) || {}).tier || "Auditor" }),
    onDone: () => { toast("User created"); refreshUsers(); },
  });
}

async function editUserForm(u) {
  // Workplace: active units only, plus the one already set (even if deactivated since) so the choice stays visible.
  let ents = [];
  try { ents = (await loadEntityConfig(true)).entities.filter((e) => e.is_active !== false || e.id === u.work_entity_id); } catch { /* optional */ }
  openForm({
    title: `Edit user: ${u.full_name || u.username}`,
    key: `user:edit:${u.id}`,
    meta: { title: `Edit user ${u.username}`, record_type: "user", record_id: u.id },
    width: 560,
    fields: [
      { name: "full_name", label: "Full name", required: true, maxLength: 255, singleLine: true },
      { name: "email", label: "Email", type: "email", required: true },
      { name: "company", label: "Department / unit (text)", maxLength: 255, singleLine: true },
      { name: "work_entity_id", label: "Workplace", type: "select", emptyLabel: "- not set -", full: true,
        options: ents.map((e) => ({ value: String(e.id), label: entityLabel(e) + (e.is_active === false ? " (deactivated)" : "") })),
        help: "The unit in the Org Structure where the person works. It decides which port's audits they see." },
    ],
    initial: { full_name: u.full_name || "", email: u.email || "", company: u.company || "", work_entity_id: u.work_entity_id ? String(u.work_entity_id) : "" },
    submitLabel: "Save changes",
    onSubmit: (v) => API.patch(`/api/users/${u.id}`, { full_name: v.full_name, email: v.email, company: v.company || "",
      work_entity_id: v.work_entity_id ? Number(v.work_entity_id) : null }),
    onDone: () => { toast("User updated"); refreshUsers(); },
  });
}

function resetPasswordForm(u) {
  openForm({
    title: `Reset password: ${u.full_name || u.username}`,
    key: `user:password:${u.id}`,
    draftable: false,
    width: 520,
    fields: [
      { name: "password", label: "New password", type: "password", required: true, minLength: 8, maxLength: 128,
        help: "At least 8 characters, not only numbers, and not containing the username. Give it to the user in person." },
      { name: "confirm", label: "Repeat new password", type: "password", required: true, minLength: 8, maxLength: 128 },
    ],
    validate: (v) => (v.password && v.confirm && v.password !== v.confirm ? { confirm: "The two passwords do not match" } : null),
    submitLabel: "Reset password",
    onSubmit: (v) => API.patch(`/api/users/${u.id}`, { password: v.password }),
    onDone: () => { toast("Password reset. The user was signed out everywhere and any lock was cleared."); refreshUsers(); },
  });
}

async function deleteUser(u) {
  const res = await confirmDialog({
    title: "Delete user account?",
    text: `${u.full_name || u.username} (${u.username}) will be removed permanently. Accounts with recorded audit work `
      + "cannot be deleted; deactivate them instead so the audit trail stays complete.",
    confirmLabel: "Delete account", danger: true,
  });
  if (!res.ok) return;
  try { await API.del(`/api/users/${u.id}`); toast("User deleted"); refreshUsers(); }
  catch (err) { toast(err.message, "error"); }
}

// ==================================================================== logs (admin)

const LOG_CATEGORIES = [
  { value: "authentication", label: "Sign-in & sessions" }, { value: "user_admin", label: "User administration" },
  { value: "security", label: "Security" }, { value: "export", label: "Exports & downloads" },
  { value: "system", label: "System" }, { value: "data", label: "Record changes" }];
const LOG_CATEGORY_LABEL = Object.fromEntries(LOG_CATEGORIES.map((c) => [c.value, c.label]));

async function renderLogs(preset = null) {
  clear(viewRoot);
  const shield = el("span", { class: "chip-mini", title: "Checking the database protection…" }, el("i", { class: "bi bi-shield" }), " Checking…");
  const exportLink = el("a", { class: "btn small secondary", title: "Download every matching entry (the download is logged)" },
    el("i", { class: "bi bi-download" }), " Export CSV");
  viewRoot.append(viewHeader("Audit trail", el("div", { class: "actions" }, shield, exportLink)));
  API.get("/api/audit-logs/integrity").then((g) => {
    clear(shield);
    shield.className = `chip-mini ${g.protected ? "ok" : "warn"}`;
    shield.title = g.tables.map((t) => `${t.label}: ${t.update_blocked && t.delete_blocked ? "changes refused by the database" : "NOT protected"}`).join("\n")
      + `\n${g.entries.toLocaleString()} entries${g.oldest ? ` since ${fmtDay(g.oldest)}` : ""}`;
    shield.append(el("i", { class: `bi bi-${g.protected ? "shield-check" : "shield-exclamation"}` }), g.protected ? " Tamper-protected" : " Protection missing");
  }).catch(() => shield.remove());
  const tiles = el("div", { class: "stats" }, loadingState());
  viewRoot.append(tiles);
  API.get("/api/audit-logs/summary?days=7").then((s) => {
    clear(tiles);
    tiles.append(
      stat(s.sign_ins, "Sign-ins", "last 7 days"),
      stat(s.failed_sign_ins, "Failed sign-ins", s.top_failures.length ? `most: ${s.top_failures[0].username}` : "last 7 days", s.failed_sign_ins ? "warn" : "ok"),
      stat(s.lockouts, "Lockouts", s.locked_now.length ? `locked now: ${s.locked_now.join(", ")}` : "none now", s.lockouts ? "danger" : "ok"),
      stat(s.exports, "Exports", "last 7 days"));
  }).catch(() => clear(tiles));
  const presets = [
    { key: "all", label: "All activity", values: {} },
    { key: "signins", label: "Sign-ins", values: { category: "authentication" } },
    { key: "failed", label: "Failed", values: { outcome: "failure" } },
    { key: "users", label: "User administration", values: { category: "user_admin" } },
    { key: "system", label: "Settings & system", values: { category: "system" } },
    { key: "exports", label: "Exports", values: { category: "export" } },
  ];
  const active = preset || "all";
  viewRoot.append(tabBar(presets.map((p) => ({ key: p.key, label: p.label })), active, (k) => renderLogs(k)));
  const card = el("div", { class: "card" });
  viewRoot.append(card);
  const today = new Date();
  const ago = (d) => { const x = new Date(today); x.setDate(x.getDate() - d); return x.toISOString().slice(0, 10); };
  let users = [];
  try { users = await API.get("/api/users"); } catch { users = []; }
  const initial = { ...(presets.find((p) => p.key === active) || presets[0]).values };
  const setExport = (v) => {
    const sp = new URLSearchParams();
    Object.entries(v).forEach(([k, val]) => { if (val) sp.set(k, val); });
    exportLink.href = `/api/audit-logs/export.csv?${sp.toString()}`;
  };
  setExport(initial);
  const t = serverTable({
    url: "/api/audit-logs/register",
    storageKey: "audit-log",
    defaultSort: "-timestamp",
    pageSize: 50,
    exportName: "Audit trail",
    values: initial,
    onFilter: (v) => setExport(v),
    onRow: (l) => openLogEntry(l),
    filters: [
      { key: "date_from", label: "Period", options: [{ value: ago(1), label: "Last 24 hours" }, { value: ago(7), label: "Last 7 days" }, { value: ago(30), label: "Last 30 days" }, { value: ago(90), label: "Last 90 days" }, { value: ago(365), label: "Last 12 months" }] },
      { key: "category", label: "Category", options: LOG_CATEGORIES },
      { key: "outcome", label: "Outcome", options: [{ value: "success", label: "Success" }, { value: "failure", label: "Failure" }] },
      { key: "user_id", label: "User", options: users.map((u) => ({ value: u.id, label: u.full_name || u.username })) },
    ],
    emptyTitle: "No activity recorded",
    columns: [
      { key: "timestamp", label: "When", sort: true, render: (l) => fmtDate(l.timestamp), csv: (l) => fmtDate(l.timestamp) },
      { key: "user", label: "User", sort: true, render: (l) => l.user || (l.user_id ? `#${l.user_id}` : "System"), csv: (l) => l.user || "" },
      { key: "event", label: "Event", render: (l) => el("div", null, el("div", null, l.event), l.details ? el("div", { class: "muted small log-details" }, clip(l.details, 90)) : null), csv: (l) => l.event },
      { key: "category", label: "Category", hidden: true, render: (l) => LOG_CATEGORY_LABEL[l.category] || l.category, csv: (l) => LOG_CATEGORY_LABEL[l.category] || l.category },
      { key: "outcome", label: "Outcome", render: (l) => (l.outcome === "failure" ? badge("Failed") : el("span", { class: "muted" }, "Success")), csv: (l) => l.outcome },
      { key: "ip_address", label: "IP address" },
      { key: "action_performed", label: "As recorded", hidden: true, render: (l) => el("span", { class: "log-action" }, l.action_performed) },
      { key: "user_agent", label: "Browser", hidden: true, render: (l) => el("span", { class: "muted small", title: l.user_agent || "" }, (l.user_agent || "-").slice(0, 60)), csv: (l) => l.user_agent || "" },
    ],
  });
  card.append(t.root);
}

// One audit trail entry in full.
function openLogEntry(l) {
  const row = (label, value) => (value === null || value === undefined || value === "" ? null
    : el("div", { class: "log-fact" }, el("dt", null, label), el("dd", null, value)));
  const body = el("dl", { class: "log-facts" },
    row("When", fmtDate(l.timestamp)),
    row("User", l.user || "System"), row("Username", l.username),
    row("Outcome", l.outcome === "failure" ? badge("Failed") : "Success"),
    row("Category", LOG_CATEGORY_LABEL[l.category] || l.category),
    row("Record", l.entity_type ? `${l.entity_type}${l.entity_id ? ` #${l.entity_id}` : ""}` : null),
    row("Details", l.details), row("IP address", l.ip_address), row("Browser", l.user_agent),
    row("As recorded", el("code", { class: "log-action" }, l.action_performed)), row("Entry", `#${l.id}`));
  detailPanel({ title: l.event || "Audit entry", body, width: 560 });
}

// ==================================================================== backups (admin)

async function renderBackups() {
  clear(viewRoot);
  const msg = el("div");
  const runBtn = el("button", { class: "btn", type: "button" }, el("i", { class: "bi bi-play-fill" }), " Run backup now");
  runBtn.addEventListener("click", async () => {
    runBtn.disabled = true; runBtn.textContent = "Backing up…";
    try {
      const b = await API.post("/api/admin/backup");
      toast(b.verified && b.verified.outcome === "passed" ? "Backup created and checked" : "Backup created; the check found a problem");
      renderBackups();
    } catch (err) { notify(msg, err.message, "error"); runBtn.disabled = false; runBtn.textContent = "Run backup now"; }
  });
  const actions = el("div", { class: "actions" },
    el("button", { class: "btn secondary", type: "button", onclick: openRestoreGuide }, el("i", { class: "bi bi-life-preserver" }), " Restore guide"),
    hasPerm("system.technical") ? el("button", { class: "btn secondary", type: "button", onclick: () => { state.configSection = "Backups"; navigate("configuration"); } }, el("i", { class: "bi bi-gear" }), " Settings") : null,
    runBtn);
  viewRoot.append(viewHeader("Backups", actions), msg);
  const tiles = el("div", { class: "stats" }, loadingState());
  const setsCard = el("div", { class: "card" });
  const checksCard = el("div", { class: "card" });
  viewRoot.append(tiles, setsCard, checksCard);
  let st, sets, checks;
  try {
    [st, sets, checks] = await Promise.all([API.get("/api/admin/backups/status"), API.get("/api/admin/backups"), API.get("/api/admin/backups/checks?limit=20")]);
  } catch (err) { clear(tiles); notify(msg, err.message, "error"); return; }

  const size = (n) => (n >= 1073741824 ? `${(n / 1073741824).toFixed(1)} GB` : n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
  const age = (h) => (h < 1 ? "Under 1 h" : h < 48 ? `${Math.round(h)} h ago` : `${Math.round(h / 24)} days ago`);
  const result = (c) => (!c ? el("span", { class: "chip-mini" }, "Not checked")
    : c.outcome === "passed" ? el("span", { class: "chip-mini ok" }, el("i", { class: "bi bi-check2" }), " Passed")
      : el("span", { class: "chip-mini danger" }, el("i", { class: "bi bi-x-lg" }), " Failed"));
  clear(tiles);
  tiles.append(
    st.latest ? stat(age(st.latest.age_hours), "Last backup", fmtDate(st.latest.created_at), st.overdue ? "danger" : "ok") : stat("None", "Last backup", null, "danger"),
    stat(!st.server_schedule ? "Off" : st.interval_hours ? `Every ${st.interval_hours} h` : "Paused", "Schedule",
      !st.server_schedule ? "switched off on the server" : st.next_due ? `next ${fmtDate(st.next_due)}` : null, st.interval_hours ? "" : "warn"),
    stat(`${st.count} / ${st.retention}`, "Kept", st.include_attachments ? "with attachments" : "database only"),
    stat(st.verified ? (st.verified.outcome === "passed" ? "Passed" : "Failed") : "-", "Last check", st.verified ? fmtDate(st.verified.at) : null,
      st.verified ? (st.verified.outcome === "passed" ? "ok" : "danger") : ""),
    stat(st.restore_test ? (st.restore_test.outcome === "passed" ? "Passed" : "Failed") : "Never", "Restore test",
      st.restore_test ? fmtDate(st.restore_test.at) : null, st.restore_test ? (st.restore_test.outcome === "passed" ? "ok" : "danger") : "warn"));

  setsCard.append(el("div", { class: "card-head" }, el("h3", null, "Backup sets")));
  if (!sets.length) setsCard.append(emptyState({ icon: "hdd-stack", title: "No backups yet" }));
  else {
    const verify = async (b, btn) => {
      btn.disabled = true;
      try { const r = await API.post(`/api/admin/backups/${encodeURIComponent(b.stamp)}/verify`); toast(r.ok ? "Check passed" : "Check failed"); renderBackups(); }
      catch (err) { notify(msg, err.message, "error"); btn.disabled = false; }
    };
    const remove = async (b) => {
      const ok = await confirmDialog({ title: "Delete backup?", text: `${fmtDate(b.created_at)}: the database snapshot${b.files_name ? " and attachments" : ""} will be removed.`, confirmLabel: "Delete", danger: true });
      if (!ok.ok) return;
      try { await API.del(`/api/admin/backups/${encodeURIComponent(b.stamp)}`); toast("Backup deleted"); renderBackups(); }
      catch (err) { notify(msg, err.message, "error"); }
    };
    setsCard.append(el("div", { class: "table-wrap" }, el("table", { class: "compact-table" },
      el("thead", null, el("tr", null, ...["Created", "Database", "Attachments", "Check", ""].map((h) => el("th", null, h)))),
      el("tbody", null, ...sets.map((b, i) => {
        const vbtn = el("button", { class: "btn small secondary", type: "button", title: "Check this backup" }, el("i", { class: "bi bi-shield-check" }), " Verify");
        vbtn.addEventListener("click", (e) => { e.stopPropagation(); verify(b, vbtn); });
        return el("tr", { tabindex: "0", onclick: () => openBackupSet(b), onkeydown: (e) => { if (e.key === "Enter") openBackupSet(b); } },
          el("td", null, fmtDate(b.created_at), i === 0 ? el("span", { class: "chip-mini", style: "margin-left:6px" }, "Latest") : null),
          el("td", null, size(b.size_bytes)),
          el("td", null, b.files_name ? `${b.file_count.toLocaleString()} file${b.file_count === 1 ? "" : "s"} · ${size(b.files_bytes)}` : el("span", { class: "muted" }, "Not included")),
          el("td", null, result(b.verified)),
          el("td", { class: "actions end" }, vbtn, sets.length > 1 ? el("button", { class: "btn small danger-ghost icon-only", type: "button", title: "Delete", "aria-label": "Delete backup",
            onclick: (e) => { e.stopPropagation(); remove(b); } }, el("i", { class: "bi bi-trash" })) : null));
      })))));
  }

  checksCard.append(el("div", { class: "card-head" }, el("h3", null, "Check history")));
  if (!checks.items.length) checksCard.append(el("p", { class: "muted" }, "No checks yet."));
  else checksCard.append(el("div", { class: "table-wrap" }, el("table", { class: "compact-table" },
    el("thead", null, el("tr", null, ...["When", "Type", "Result", "By"].map((h) => el("th", null, h)))),
    el("tbody", null, ...checks.items.map((c) => el("tr", { tabindex: "0", class: c.outcome === "failed" ? "row-failure" : "", onclick: () => openBackupCheck(c),
      onkeydown: (e) => { if (e.key === "Enter") openBackupCheck(c); } },
    el("td", null, fmtDate(c.at)), el("td", null, c.kind === "restore_test" ? "Restore test" : "Check"),
    el("td", null, result(c)), el("td", null, c.by)))))));
}

function backupCheckList(checks) {
  return el("ul", { class: "check-list" }, ...(checks || []).map((c) => el("li", { class: c.ok ? "ok" : "bad" },
    el("i", { class: `bi bi-${c.ok ? "check-circle-fill" : "x-circle-fill"}`, "aria-hidden": "true" }),
    el("span", null, c.name), c.detail ? el("span", { class: "muted small" }, ` · ${c.detail}`) : null)));
}

function openBackupSet(b) {
  const fact = (k, v) => el("div", { class: "log-fact" }, el("dt", null, k), el("dd", null, v));
  const body = el("div", null, el("dl", { class: "log-facts" },
    fact("Created", fmtDate(b.created_at)), fact("Database", b.filename), fact("Method", b.method === "mysqldump" ? "MySQL dump" : "Portable snapshot"),
    fact("Attachments", b.files_name ? `${b.file_count.toLocaleString()} file${b.file_count === 1 ? "" : "s"}` : "Not included")));
  if (b.verified) body.append(el("h4", null, `Last check · ${fmtDate(b.verified.at)}`), backupCheckList(b.verified.checks));
  else body.append(el("p", { class: "muted" }, "Not checked yet."));
  detailPanel({ title: "Backup", body, width: 560 });
}

function openBackupCheck(c) {
  detailPanel({ title: c.kind === "restore_test" ? "Restore test" : "Backup check", width: 560,
    body: el("div", null, el("p", { class: "muted" }, `${fmtDate(c.at)} · ${c.by}`), backupCheckList(c.checks)) });
}

function openRestoreGuide() {
  const step = (title, code) => el("li", null, el("div", null, title), code ? el("code", { class: "cmd" }, code) : null);
  modal({ title: "Restore guide", width: 620, body: el("div", { class: "restore-guide" },
    el("p", { class: "muted" }, "Restores are done on the server by the system administrator, never from the browser."),
    el("ol", null,
      step("Stop the application and create a new, empty database."),
      step("Restore the database snapshot (point GPHA_DATABASE_URL at the new database):", "uv run python -m scripts.restore_backup backups/backup_<date>.json.enc --yes"),
      step("For a MySQL dump, decrypt it and load it with the mysql client:", "uv run python -m scripts.restore_backup backups/backup_<date>.sql.enc --decrypt-only"),
      step("Restore the attachments of the same backup:", "uv run python -m scripts.restore_backup backups/backup_<date>.files.tar.gz --yes"),
      step("Start the application and sign in to check."),
      step("Every quarter, run a full restore test; the result appears here:", "uv run python -m scripts.verify_backup")),
    el("p", { class: "muted small" }, "The same encryption key must be in .env. Keep backups and the key off e-mail and chat.")) });
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
  registerFormOpener("user:new", () => { navigate(hasPerm("system.users") ? "users" : "profile"); newUserForm(); });
}

registerAppOpeners();
registerPlanningOpeners();
window.addEventListener("online", () => { checkHealth(); toast("Back online - drafts will sync as you type"); });
setInterval(() => { if (state.user) checkHealth(); }, 60000);
const navToggle = qs("#navToggle");
if (navToggle) navToggle.addEventListener("click", () => document.body.classList.toggle("nav-open"));
boot();
