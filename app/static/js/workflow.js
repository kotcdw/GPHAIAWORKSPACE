// GPHA Internal Audit Workspace - reporting, follow-up, notifications and two-step verification.
//
// Loaded after planning.js and before app.js; uses helpers from api.js, forms.js
// and app.js (el, badge, modal, toast, openForm, eSignModal, viewHeader ...) at call time.

const REPORT_STAGES = ["Draft", "Management Review", "Manager Review", "CAE Approval", "Issued"];
const REPORT_RATINGS = ["Satisfactory", "Needs Improvement", "Unsatisfactory"];

function isStaff() { return state.user && ["Admin", "Auditor"].includes(state.user.role); }

function longBlock(label, text, empty = "Not written yet") {
  return el("div", { class: "long-field" }, el("div", { class: "lf-label" }, label),
    el("div", { class: `lf-value ${text ? "" : "muted"}`.trim() }, text || empty));
}

function stepper(stages, current) {
  const at = stages.indexOf(current);
  return el("ol", { class: "stepper", "aria-label": "Progress" },
    ...stages.map((s, i) => el("li", { class: i < at ? "done" : (i === at ? "current" : ""), "aria-current": i === at ? "step" : null },
      el("span", { class: "dot" }, i < at ? el("i", { class: "bi bi-check" }) : String(i + 1)), el("span", { class: "lbl" }, s))));
}

// ==================================================================== audit report tab

async function renderReportTab(panel, auditId, canWrite) {
  clear(panel);
  let report = null;
  try { report = await API.get(`/api/audits/${auditId}/report`); }
  catch (err) {
    if (err.status !== 404) { panel.append(el("div", { class: "msg error" }, err.message)); return; }
  }
  if (!report) {
    panel.append(el("div", { class: "card empty-state" },
      el("i", { class: "bi bi-file-earmark-text big-icon" }),
      el("h3", null, "No audit report yet"),
      el("p", { class: "muted" }, isStaff()
        ? "Create the draft report when fieldwork is complete. Findings and management responses are pulled in automatically."
        : "The audit team has not shared a report for this audit yet."),
      canWrite ? el("button", { class: "btn", onclick: async () => {
        try { await API.post(`/api/audits/${auditId}/report`); toast("Draft report created"); renderReportTab(panel, auditId, canWrite); }
        catch (err) { toast(err.message, "error"); }
      } }, el("i", { class: "bi bi-plus-lg" }), " Create draft report") : null));
    return;
  }
  const reload = () => renderReportTab(panel, auditId, canWrite);
  const r = report;
  const post = (path, okText) => async () => {
    try { await API.post(path); toast(okText); reload(); } catch (err) { toast(err.message, "error"); }
  };

  const actions = el("div", { class: "actions" },
    r.can_edit ? el("button", { class: "btn small secondary", onclick: () => reportForm(r, reload) },
      el("i", { class: "bi bi-pencil" }), " Edit report") : null,
    r.can_edit ? el("button", { class: "btn small secondary", onclick: post(`/api/reports/${r.id}/send-to-management`, "Sent to management for comments") },
      el("i", { class: "bi bi-send" }), " Send to management") : null,
    isStaff() && ["Draft", "Management Review"].includes(r.status) ? el("button", {
      class: "btn small", disabled: r.blockers.length ? "1" : null, title: r.blockers.join(" ") || "Send to the Audit Manager",
      onclick: post(`/api/reports/${r.id}/submit-for-review`, "Submitted for Audit Manager review") },
    el("i", { class: "bi bi-check2-circle" }), " Submit for review") : null,
    r.can_comment ? el("button", { class: "btn small", onclick: () => commentsForm(r, reload) },
      el("i", { class: "bi bi-chat-left-text" }), " Management comments") : null,
    r.can_manager_review ? el("button", { class: "btn small", onclick: () => eSignModal({
      title: "Audit Manager review", pathOverride: `/api/reports/${r.id}/manager-review`, actionLabel: "Sign review",
      allowReject: true, onDone: reload }) }, el("i", { class: "bi bi-pen" }), " Review (e-sign)") : null,
    r.can_cae_approve ? el("button", { class: "btn small", onclick: () => eSignModal({
      title: "CAE approval - issue report", pathOverride: `/api/reports/${r.id}/cae-approve`, actionLabel: "Approve & issue",
      allowReject: true, onDone: reload }) }, el("i", { class: "bi bi-patch-check" }), " Approve & issue (e-sign)") : null,
    el("a", { class: "btn small secondary", href: `/api/reports/${r.id}/export.docx` }, el("i", { class: "bi bi-file-earmark-word" }), " Word"),
    el("a", { class: "btn small secondary", href: `/api/reports/${r.id}/print`, target: "_blank", rel: "noopener" },
      el("i", { class: "bi bi-printer" }), " Print / PDF"));

  const head = el("div", { class: "card" },
    el("div", { class: "card-head" },
      el("div", null, el("h3", null, r.title),
        el("div", { class: "view-meta" }, el("span", { class: "ref" }, r.report_ref), badge(r.status),
          r.overall_rating ? el("span", { class: `rating rating-${r.overall_rating.toLowerCase().replace(/\s+/g, "-")}` }, r.overall_rating)
            : el("span", { class: "muted" }, "Not rated"))),
      actions),
    stepper(REPORT_STAGES, r.status));
  panel.append(head);

  if (r.blockers.length) {
    panel.append(el("div", { class: "callout warn" }, el("i", { class: "bi bi-exclamation-triangle" }),
      el("div", null, el("strong", null, "Before it can go to review"),
        el("ul", null, ...r.blockers.map((b) => el("li", null, b))))));
  }
  if (r.status === "Management Review" && !isStaff()) {
    panel.append(el("div", { class: "callout" }, el("i", { class: "bi bi-info-circle" }),
      el("div", null, "Please read the draft, add your management comments and respond to each finding on the Findings tab.")));
  }

  panel.append(el("div", { class: "card" },
    longBlock("Executive summary", r.executive_summary),
    longBlock("Overall opinion", r.overall_opinion),
    longBlock("Background", r.background),
    longBlock("Scope and objectives", r.scope_objectives),
    longBlock("Methodology", r.methodology),
    longBlock("Management comments", r.management_comments, "None received yet"),
    longBlock("Distribution", r.distribution_list, "Not specified")));

  panel.append(el("div", { class: "card" }, el("h3", null, "Sign-off"),
    el("div", { class: "table-wrap" }, el("table", null,
      el("thead", null, el("tr", null, el("th", null, "Role"), el("th", null, "Name"), el("th", null, "Date"))),
      el("tbody", null, ...r.signoffs.map((s) => el("tr", { class: "no-click" },
        el("td", null, s.role), el("td", null, s.name || el("span", { class: "muted" }, "Pending")),
        el("td", null, s.name && s.at ? fmtDate(s.at).split(",")[0] : "-"))))))));
}

function reportForm(r, reload) {
  openForm({
    title: `Edit ${r.report_ref}`,
    key: `report:${r.id}:edit`,
    meta: { title: `Edit report ${r.report_ref}`, record_type: "audit_report", record_id: r.id },
    width: 860,
    fields: [
      { name: "title", label: "Report title", required: true, maxLength: 255, singleLine: true },
      { name: "overall_rating", label: "Overall rating", type: "select", options: REPORT_RATINGS, emptyLabel: "- choose -" },
      { name: "executive_summary", label: "Executive summary", type: "textarea", rows: 5, maxLength: 50000,
        help: "What the reader must know: the overall conclusion and the most significant issues." },
      { name: "overall_opinion", label: "Overall opinion", type: "textarea", rows: 3, maxLength: 50000 },
      { name: "background", label: "Background", type: "textarea", rows: 3, maxLength: 50000 },
      { name: "scope_objectives", label: "Scope and objectives", type: "textarea", rows: 3, maxLength: 50000 },
      { name: "methodology", label: "Methodology", type: "textarea", rows: 3, maxLength: 50000 },
      { name: "distribution_list", label: "Distribution list", type: "textarea", rows: 2, maxLength: 5000,
        placeholder: "e.g. Director-General; Deputy Director-General (Finance); Audit Committee" },
    ],
    initial: r,
    submitLabel: "Save report",
    onSubmit: (v) => API.patch(`/api/reports/${r.id}`, { ...v, overall_rating: v.overall_rating || null }),
    onDone: () => { toast("Report saved"); reload(); },
  });
}

function commentsForm(r, reload) {
  openForm({
    title: "Management comments",
    key: `report:${r.id}:comments`,
    meta: { title: `Comments on ${r.report_ref}`, record_type: "audit_report", record_id: r.id },
    fields: [{ name: "management_comments", label: "Management comments on the draft report", type: "textarea", rows: 8,
      required: true, maxLength: 50000 }],
    initial: { management_comments: r.management_comments },
    submitLabel: "Save comments",
    onSubmit: (v) => API.put(`/api/reports/${r.id}/management-comments`, v),
    onDone: () => { toast("Comments saved - the audit team has been notified"); reload(); },
  });
}

// ==================================================================== CAPA follow-up panel

function renderCapaFollowup(panel, c, refresh) {
  const mine = state.user.email && c.owner_email && state.user.email.toLowerCase() === c.owner_email.toLowerCase();
  const canImplement = ["Open", "In Progress"].includes(c.status) && (isStaff() || mine);
  const canValidate = isStaff() && c.status === "Review" && c.implemented_at && !c.validation_result && c.implemented_by !== state.user.id;
  const overdue = c.due_date && c.status !== "Closed" && new Date(`${c.due_date}Z`) < new Date();

  const card = el("div", { class: "card" },
    el("div", { class: "card-head" }, el("h3", null, "Follow-up"),
      el("div", { class: "actions" },
        canImplement ? el("button", { class: "btn small", onclick: () => implementForm(c, refresh) },
          el("i", { class: "bi bi-clipboard-check" }), c.reopen_count ? " Record new evidence" : " Record implementation") : null,
        canValidate ? el("button", { class: "btn small", onclick: () => validateForm(c, refresh) },
          el("i", { class: "bi bi-shield-check" }), " Validate") : null)),
    stepper(["Open", "Implemented", "Validated", "Closed"],
      c.status === "Closed" ? "Closed" : (c.validation_result === "Effective" ? "Validated" : (c.implemented_at ? "Implemented" : "Open"))));
  if (overdue) {
    card.append(el("div", { class: "callout danger" }, el("i", { class: "bi bi-alarm" }),
      el("div", null, el("strong", null, "Overdue. "), c.escalation_level >= 3 ? "Escalated to the CAE."
        : (c.escalation_level === 2 ? "Escalated to Audit Managers." : "The owner has been reminded."))));
  }
  if (c.reopen_count) card.append(el("p", { class: "muted small" }, `Reopened ${c.reopen_count} time(s) after validation.`));
  card.append(longBlock("Implementation evidence", c.implementation_evidence, "Not recorded yet"));
  if (c.implemented_at) card.append(el("p", { class: "muted small" }, `Recorded ${fmtDate(c.implemented_at)}`));
  if (c.validation_result) {
    card.append(el("div", { class: "long-field" }, el("div", { class: "lf-label" }, "Auditor validation"),
      el("div", { class: "lf-value" }, badge(c.validation_result), c.validation_comment ? ` ${c.validation_comment}` : "",
        el("div", { class: "muted small" }, `Validated ${fmtDate(c.validated_at)}`))));
  }
  if (c.status === "Review" && c.validation_result === "Effective") {
    card.append(el("p", { class: "muted small" }, "Validated as effective - an administrator can now close it with an e-signature."));
  }
  panel.append(card);
}

function implementForm(c, refresh) {
  openForm({
    title: `Record implementation - ${c.capa_ref}`,
    key: `capa:${c.id}:implement`,
    meta: { title: `Implementation of ${c.capa_ref}`, record_type: "capa", record_id: c.id },
    fields: [{ name: "evidence", label: "What was done, when, and where the evidence is", type: "textarea", rows: 6,
      required: true, minLength: 10, maxLength: 20000,
      help: "Be specific: dates, documents, system changes. Upload supporting files to the audit's working papers." }],
    initial: {},
    submitLabel: "Submit for validation",
    onSubmit: (v) => API.post(`/api/capa/${c.id}/implement`, v),
    onDone: () => { toast("Sent to the auditor for validation"); refresh(); },
  });
}

function validateForm(c, refresh) {
  openForm({
    title: `Validate ${c.capa_ref}`,
    key: `capa:${c.id}:validate`,
    meta: { title: `Validation of ${c.capa_ref}`, record_type: "capa", record_id: c.id },
    fields: [
      { name: "result", label: "Is the action effective?", type: "select", required: true, options: ["Effective", "Not Effective"] },
      { name: "comment", label: "Validation notes", type: "textarea", rows: 4, maxLength: 20000,
        help: "Required when not effective: say what is still missing." },
    ],
    validate: (v) => (v.result === "Not Effective" && (v.comment || "").trim().length < 5 ? { comment: "Explain why it is not effective" } : {}),
    initial: { result: "Effective" },
    submitLabel: "Save validation",
    onSubmit: (v) => API.post(`/api/capa/${c.id}/validate`, { result: v.result, comment: v.comment || "" }),
    onDone: () => { toast("Validation saved"); refresh(); },
  });
}

// ==================================================================== follow-up page

async function renderFollowup() {
  clear(viewRoot);
  const msg = el("div");
  viewRoot.append(viewHeader("Follow-up", isAdmin() ? [el("button", { class: "btn small secondary", onclick: async () => {
    try { const r = await API.post("/api/followup/run-escalations"); toast(`${r.escalated} action(s) escalated`); renderFollowup(); }
    catch (err) { toast(err.message, "error"); }
  } }, el("i", { class: "bi bi-arrow-repeat" }), " Run escalation check")] : null,
  { sub: "Agreed actions that are overdue or waiting for an auditor to validate them" }), msg);
  let overdue = [];
  let review = [];
  try {
    [overdue, review] = await Promise.all([
      API.get("/api/followup/overdue"),
      API.get("/api/capa?status=Review&limit=200").then((r) => (r.items || r).filter((c) => c.implemented_at && !c.validation_result)),
    ]);
  } catch (err) { notify(msg, err.message, "error"); return; }

  const lvl = (n) => overdue.filter((o) => o.escalation_level === n).length;
  viewRoot.append(el("div", { class: "stats" },
    stat(overdue.length, "Overdue actions", overdue.length ? "past their due date" : "none", overdue.length ? "danger" : "ok"),
    stat(lvl(2), "With Audit Managers", "14+ days overdue", lvl(2) ? "warn" : ""),
    stat(lvl(3), "With the CAE", "30+ days overdue", lvl(3) ? "danger" : ""),
    stat(review.length, "Awaiting validation", "evidence submitted", review.length ? "warn" : "")));

  const table = (rows, cols) => (rows.length ? el("div", { class: "table-wrap" }, el("table", null,
    el("thead", null, el("tr", null, ...cols.map((c) => el("th", { class: c.num ? "num" : null }, c.label)))),
    el("tbody", null, ...rows.map((r) => el("tr", { onclick: () => openRecord("capa", r.id) },
      ...cols.map((c) => el("td", { class: c.num ? "num" : null }, c.render(r)))))))) : el("div", { class: "empty" }, "Nothing here."));

  viewRoot.append(panel("Overdue actions", table(overdue, [
    { label: "Ref", render: (r) => el("span", { class: "ref" }, r.capa_ref) },
    { label: "Action", render: (r) => r.title },
    { label: "Owner", render: (r) => r.owner_email || el("span", { class: "muted" }, "Unassigned") },
    { label: "Due", render: (r) => fmtDate(r.due_date).split(",")[0] },
    { label: "Days overdue", num: true, render: (r) => el("strong", null, String(r.days_overdue)) },
    { label: "Escalated to", render: (r) => badge(r.escalation_name) },
  ])));
  viewRoot.append(panel("Awaiting auditor validation", table(review, [
    { label: "Ref", render: (r) => el("span", { class: "ref" }, r.capa_ref) },
    { label: "Action", render: (r) => r.title },
    { label: "Owner", render: (r) => r.owner_email || "-" },
    { label: "Evidence recorded", render: (r) => fmtDate(r.implemented_at) },
  ])));
}

// ==================================================================== notification bell

const Bell = { timer: null, open: false };

function initBell() {
  const btn = qs("#bellBtn");
  if (!btn || btn.dataset.ready) return;
  btn.dataset.ready = "1";
  btn.addEventListener("click", (e) => { e.stopPropagation(); toggleBellPanel(); });
  document.addEventListener("click", (e) => {
    const p = qs("#bellPanel");
    if (Bell.open && p && !p.contains(e.target)) toggleBellPanel(false);
  });
  refreshBell();
  Bell.timer = setInterval(refreshBell, 60000);
}

async function refreshBell() {
  if (!state.user) return;
  try {
    const data = await API.get("/api/notifications?unread_only=true&limit=1");
    const count = qs("#bellCount");
    count.textContent = data.unread > 99 ? "99+" : String(data.unread);
    count.classList.toggle("hidden", !data.unread);
    qs("#bellBtn").setAttribute("aria-label", `Notifications, ${data.unread} unread`);
  } catch { /* offline - try again next tick */ }
}

function timeAgo(iso) {
  const s = Math.max(1, (Date.now() - new Date(`${iso}Z`).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

async function toggleBellPanel(force) {
  const p = qs("#bellPanel");
  Bell.open = force === undefined ? !Bell.open : force;
  p.classList.toggle("hidden", !Bell.open);
  qs("#bellBtn").setAttribute("aria-expanded", Bell.open ? "true" : "false");
  if (!Bell.open) return;
  clear(p);
  p.append(el("div", { class: "bell-head" }, el("strong", null, "Notifications"),
    el("button", { class: "linkish", onclick: async () => {
      try { await API.post("/api/notifications/read-all"); refreshBell(); toggleBellPanel(true); } catch (err) { toast(err.message, "error"); }
    } }, "Mark all read")));
  try {
    const data = await API.get("/api/notifications?limit=25");
    if (!data.items.length) { p.append(el("div", { class: "empty" }, "You're all caught up.")); return; }
    p.append(el("ul", { class: "bell-list" }, ...data.items.map((n) => el("li", { class: n.is_read ? "" : "unread" },
      el("button", { onclick: async () => {
        toggleBellPanel(false);
        if (!n.is_read) { API.post(`/api/notifications/${n.id}/read`).then(refreshBell).catch(() => {}); }
        if (n.link_type && n.link_id) openLink(n.link_type, n.link_id);
      } },
      el("span", { class: "bell-title" }, n.title),
      n.body ? el("span", { class: "bell-body" }, n.body.split("\n")[0]) : null,
      el("span", { class: "bell-time" }, timeAgo(n.created_at)))))));
  } catch (err) { p.append(el("div", { class: "msg error" }, err.message)); }
}

// Open any record a notification (or an e-mail link #open/<type>/<id>) points at.
async function openLink(type, id) {
  try {
    if (type === "audit") return openAudit(id);
    if (type === "audit_report") { const r = await API.get(`/api/reports/${id}`); return openAudit(r.audit_id, "report"); }
    if (type === "finding") { const f = await API.get(`/api/findings/${id}`); return openAudit(f.audit_id, "findings"); }
    if (type === "capa") return openRecord("capa", id);
    if (type === "assurance_plan") return openPlan(id);
    if (type === "task") return navigate("tasks");
    return navigate("dashboard");
  } catch (err) { toast(err.message, "error"); return null; }
}

// ==================================================================== two-step verification (TOTP)

function renderMfaCard(container) {
  const card = el("div", { class: "card" });
  container.append(card);
  paintMfa(card);
}

function paintMfa(card) {
  clear(card);
  const on = state.user.mfa_enabled;
  card.append(el("div", { class: "card-head" }, el("h3", null, "Two-step verification"), badge(on ? "On" : "Off")));
  if (state.mfaSetupRequired && !on) {
    card.append(el("div", { class: "callout warn" }, el("i", { class: "bi bi-shield-lock" }),
      el("div", null, "Your role requires two-step verification. Set it up to continue using the workspace.")));
  }
  if (!on) {
    card.append(el("p", { class: "muted" }, "Protect your account with a 6-digit code from an authenticator app (Microsoft Authenticator, Google Authenticator) in addition to your password."),
      el("button", { class: "btn", onclick: async () => {
        try { const s = await API.post("/api/auth/mfa/setup"); mfaEnrol(card, s); } catch (err) { toast(err.message, "error"); }
      } }, el("i", { class: "bi bi-shield-lock" }), " Set up two-step verification"));
    return;
  }
  card.append(el("p", { class: "muted" }, "You will be asked for a code from your authenticator app each time you sign in."));
  const holder = el("div");
  card.append(holder);
  inlineForm(holder, {
    draftable: false,
    fields: [
      { name: "password", label: "Password", type: "password", required: true },
      { name: "code", label: "Current 6-digit code", required: true, pattern: "^\\d{6}$", patternMessage: "Enter the 6 digits" },
    ],
    submitLabel: "Turn off",
    onSubmit: (v) => API.post("/api/auth/mfa/disable", v),
    onDone: (me) => { state.user = me.user; toast("Two-step verification turned off"); paintMfa(card); },
  });
}

function mfaEnrol(card, setup) {
  clear(card);
  const grouped = setup.secret.replace(/(.{4})/g, "$1 ").trim();
  card.append(el("h3", null, "Set up two-step verification"),
    el("ol", { class: "steps-list" },
      el("li", null, "Open your authenticator app and choose ", el("strong", null, "Add account"), " then ", el("strong", null, "Enter a setup key"), "."),
      el("li", null, "Account name: ", el("strong", null, `GPHA Internal Audit (${state.user.username})`), ". Key:",
        el("div", { class: "secret-key", tabindex: "0" }, grouped), "Type: time-based."),
      el("li", null, "Enter the 6-digit code the app shows below.")),
    el("p", { class: "muted small" }, "On a phone with the app installed you can also ",
      el("a", { href: setup.otpauth_uri }, "open this link"), " to add it directly."));
  const holder = el("div");
  card.append(holder);
  inlineForm(holder, {
    draftable: false,
    fields: [{ name: "code", label: "6-digit code", required: true, pattern: "^\\d{6}$", patternMessage: "Enter the 6 digits" }],
    submitLabel: "Turn on",
    onSubmit: (v) => API.post("/api/auth/mfa/enable", v),
    onDone: (me) => {
      state.user = me.user; state.mfaSetupRequired = me.mfa_setup_required;
      toast("Two-step verification is on");
      paintMfa(card);
    },
  });
}
