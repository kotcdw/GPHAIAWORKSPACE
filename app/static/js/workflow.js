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

// ==================================================================== Remediation follow-up panel

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

async function renderFollowup(root = viewRoot) {
  const msg = el("div");
  root.append(msg);
  let overdue = [];
  let review = [];
  try {
    [overdue, review] = await Promise.all([
      API.get("/api/followup/overdue"),
      API.get("/api/capa?status=Review&limit=200").then((r) => (r.items || r).filter((c) => c.implemented_at && !c.validation_result)),
    ]);
  } catch (err) { notify(msg, err.message, "error"); return; }

  const lvl = (n) => overdue.filter((o) => o.escalation_level === n).length;
  root.append(el("div", { class: "stats" },
    stat(overdue.length, "Overdue actions", overdue.length ? "past their due date" : "none", overdue.length ? "danger" : "ok"),
    stat(lvl(2), "With Audit Managers", "escalated after the manager threshold", lvl(2) ? "warn" : ""),
    stat(lvl(3), "With the CAE", "escalated after the CAE threshold", lvl(3) ? "danger" : ""),
    stat(review.length, "Awaiting validation", "evidence submitted", review.length ? "warn" : "")));

  const table = (rows, cols) => (rows.length ? el("div", { class: "table-wrap" }, el("table", null,
    el("thead", null, el("tr", null, ...cols.map((c) => el("th", { class: c.num ? "num" : null }, c.label)))),
    el("tbody", null, ...rows.map((r) => el("tr", { onclick: () => openRecord("capa", r.id) },
      ...cols.map((c) => el("td", { class: c.num ? "num" : null }, c.render(r)))))))) : el("div", { class: "empty" }, "Nothing here."));

  root.append(panel("Overdue actions", table(overdue, [
    { label: "Ref", render: (r) => el("span", { class: "ref" }, r.capa_ref) },
    { label: "Action", render: (r) => r.title },
    { label: "Owner", render: (r) => r.owner_email || el("span", { class: "muted" }, "Unassigned") },
    { label: "Due", render: (r) => fmtDate(r.due_date).split(",")[0] },
    { label: "Days overdue", num: true, render: (r) => el("strong", null, String(r.days_overdue)) },
    { label: "Escalated to", render: (r) => badge(r.escalation_name) },
  ])));
  root.append(panel("Awaiting auditor validation", table(review, [
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

// ==================================================================== data table: sort, page, export, keyboard

function csvCell(v) {
  const s = v === null || v === undefined ? "" : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function downloadCsv(filename, columns, items) {
  const raw = (it, c) => (c.csv ? c.csv(it) : it[c.key]);
  const lines = [columns.map((c) => csvCell(c.label)).join(","), ...items.map((it) => columns.map((c) => csvCell(raw(it, c))).join(","))];
  const blob = new Blob([`﻿${lines.join("\r\n")}`], { type: "text/csv;charset=utf-8" });
  const a = el("a", { href: URL.createObjectURL(blob), download: filename });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

// Sortable, paged, keyboard-accessible table with CSV export.
// columns: [{ key, label, render(item) -> node|string, sortValue(item)?, csv(item)?, num? }]
function dataTable(items, columns, { onRow = null, pageSize = 25, exportName = null, emptyText = "No records." } = {}) {
  const wrap = el("div", { class: "data-table" });
  let sortKey = null;
  let dir = 1;
  let page = 0;
  const value = (it, c) => (c.sortValue ? c.sortValue(it) : it[c.key]);

  function sorted() {
    if (!sortKey) return items;
    const c = columns.find((x) => x.key === sortKey);
    return [...items].sort((a, b) => {
      const va = value(a, c); const vb = value(b, c);
      if (va === vb) return 0;
      if (va === null || va === undefined || va === "") return 1;
      if (vb === null || vb === undefined || vb === "") return -1;
      return (typeof va === "number" && typeof vb === "number" ? va - vb : String(va).localeCompare(String(vb), undefined, { numeric: true })) * dir;
    });
  }

  function paint() {
    clear(wrap);
    if (!items.length) { wrap.append(el("div", { class: "empty" }, emptyText)); return; }
    const rows = sorted();
    const pages = Math.max(1, Math.ceil(rows.length / pageSize));
    page = Math.min(page, pages - 1);
    const slice = rows.slice(page * pageSize, page * pageSize + pageSize);
    const head = el("tr", null, ...columns.map((c) => {
      const active = sortKey === c.key;
      const th = el("th", { class: c.num ? "num" : null, "aria-sort": active ? (dir > 0 ? "ascending" : "descending") : "none" },
        el("button", { class: "th-sort", type: "button", title: `Sort by ${c.label}`, onclick: () => {
          if (sortKey === c.key) dir = -dir; else { sortKey = c.key; dir = 1; }
          paint();
        } }, c.label, el("i", { class: `bi ${active ? (dir > 0 ? "bi-caret-up-fill" : "bi-caret-down-fill") : "bi-chevron-expand"} sort-ico` })));
      return th;
    }));
    const body = el("tbody", null, ...slice.map((it) => {
      const tr = el("tr", onRow ? { tabindex: "0", onclick: () => onRow(it), onkeydown: (e) => { if (e.key === "Enter") onRow(it); } } : { class: "no-click" },
        ...columns.map((c) => el("td", { class: c.num ? "num" : null }, c.render ? c.render(it) : (it[c.key] ?? "-"))));
      return tr;
    }));
    wrap.append(el("div", { class: "table-wrap" }, el("table", null, el("thead", null, head), body)));
    wrap.append(el("div", { class: "table-foot" },
      el("span", { class: "muted small" }, `${rows.length} record${rows.length === 1 ? "" : "s"}${pages > 1 ? ` · page ${page + 1} of ${pages}` : ""}`),
      el("div", { class: "actions" },
        pages > 1 ? el("button", { class: "btn small secondary", disabled: page === 0 ? "1" : null, onclick: () => { page -= 1; paint(); } }, el("i", { class: "bi bi-chevron-left" }), " Previous") : null,
        pages > 1 ? el("button", { class: "btn small secondary", disabled: page >= pages - 1 ? "1" : null, onclick: () => { page += 1; paint(); } }, "Next ", el("i", { class: "bi bi-chevron-right" })) : null,
        exportName ? el("button", { class: "btn small secondary", onclick: () => downloadCsv(exportName, columns, rows) },
          el("i", { class: "bi bi-filetype-csv" }), " Export CSV") : null)));
  }
  paint();
  return wrap;
}

// ==================================================================== System Configuration (Admin)

const CONFIG_GROUP_ICONS = { "Audit workflow": "diagram-3", "Action plans": "alarm", Security: "shield-lock", Reports: "file-earmark-text" };

async function renderConfiguration() {
  clear(viewRoot);
  const msg = el("div");
  viewRoot.append(viewHeader("Configuration", null,
    { sub: "Business rules that drive the audit workflow. Changes apply immediately and are recorded in the audit log." }), msg);
  let rules;
  try { rules = await API.get("/api/config"); } catch (err) { notify(msg, err.message, "error"); return; }
  const groups = [...new Set(rules.map((r) => r.group))];
  const grid = el("div", { class: "config-grid" });
  viewRoot.append(grid);
  groups.forEach((g) => {
    const items = rules.filter((r) => r.group === g);
    const card = el("div", { class: "card" },
      el("div", { class: "card-head" }, el("h3", null, el("i", { class: `bi bi-${CONFIG_GROUP_ICONS[g] || "gear"}` }), ` ${g}`),
        items.some((r) => !r.is_default) ? el("span", { class: "chip-mini" }, "customised") : null));
    grid.append(card);
    const fields = items.map((r) => {
      const f = { name: r.key, label: r.label, help: r.help || `Default: ${Array.isArray(r.default) ? (r.default.join(", ") || "none") : String(r.default)}` };
      if (r.kind === "bool") return { ...f, type: "checkbox" };
      if (r.kind === "int") return { ...f, type: "number", required: true, min: r.min ?? undefined, max: r.max ?? undefined };
      if (r.kind === "roles") return { ...f, type: "checklist", options: r.options };
      if (r.kind === "longtext") return { ...f, type: "textarea", rows: 4, maxLength: 5000 };
      return { ...f, required: true, maxLength: 200, singleLine: true };
    });
    const initial = Object.fromEntries(items.map((r) => [r.key, r.value]));
    const holder = el("div");
    card.append(holder);
    inlineForm(holder, {
      draftable: false,
      fields,
      initial,
      submitLabel: "Save",
      onSubmit: (v) => API.put("/api/config", { values: Object.fromEntries(items.map((r) => [r.key, r.kind === "int" ? Number(v[r.key]) : v[r.key]])) }),
      onDone: () => { toast(`${g} saved`); renderConfiguration(); },
    });
    const changed = items.filter((r) => !r.is_default);
    if (changed.length) {
      card.append(el("div", { class: "reset-list" }, el("span", { class: "muted small" }, "Changed from default: "),
        ...changed.map((r) => el("button", { class: "linkish", title: `Reset "${r.label}" to its default`, onclick: async () => {
          try { await API.post(`/api/config/${r.key}/reset`); toast("Reset to default"); renderConfiguration(); }
          catch (err) { toast(err.message, "error"); }
        } }, `reset ${r.label.split(" ").slice(0, 4).join(" ")}…`))));
    }
  });
}

// ==================================================================== audit closure readiness

async function renderClosureCard(container, audit, canClose) {
  const card = el("div", { class: "card closure-card" });
  container.append(card);
  let res;
  try { res = await API.get(`/api/audits/${audit.id}/closure-check`); } catch { card.remove(); return; }
  card.append(el("div", { class: "card-head" },
    el("h3", null, "Closure readiness"),
    res.ready ? el("span", { class: "rating rating-satisfactory" }, "Ready to close") : el("span", { class: "rating rating-needs-improvement" }, "Not ready")),
  el("ul", { class: "checklist-view" }, ...res.checks.map((c) => el("li", { class: c.ok ? "ok" : (c.required ? "bad" : "warn") },
    el("i", { class: `bi ${c.ok ? "bi-check-circle-fill" : (c.required ? "bi-x-circle-fill" : "bi-dash-circle")}`, "aria-hidden": "true" }),
    el("div", null, el("span", null, c.label), !c.required && !c.ok ? el("span", { class: "muted small" }, " (not required by configuration)") : null,
      c.detail ? el("div", { class: "muted small" }, c.detail) : null)))));
  if (!res.ready && canClose) card.append(el("p", { class: "muted small" }, "The audit can be closed with an e-signature once every required item is ticked."));
}

// ==================================================================== Audit Committee pack

async function renderCommittee(year = null) {
  clear(viewRoot);
  const msg = el("div");
  let s;
  try { s = await API.get(`/api/committee/summary${year ? `?fiscal_year=${year}` : ""}`); }
  catch (err) { viewRoot.append(viewHeader("Audit Committee pack"), msg); notify(msg, err.message, "error"); return; }
  const yearSel = el("select", { class: "compact", "aria-label": "Fiscal year" },
    ...(s.fiscal_years.length ? s.fiscal_years : [s.plan.fiscal_year]).map((y) => el("option", { value: y, selected: y === s.plan.fiscal_year ? "1" : null }, `FY${y}`)));
  yearSel.addEventListener("change", () => renderCommittee(Number(yearSel.value)));
  viewRoot.append(viewHeader("Audit Committee pack", [yearSel,
    el("a", { class: "btn small", href: `/api/committee/pack.docx?fiscal_year=${s.plan.fiscal_year}` }, el("i", { class: "bi bi-file-earmark-word" }), " Download Word pack")],
  { sub: `Status of the Internal Audit Plan, reports and agreed actions · prepared ${fmtDate(s.generated_at)}` }), msg);

  const p = s.plan;
  const a = s.actions;
  const openTotal = Object.values(s.open_findings_by_rating).reduce((x, y) => x + y, 0);
  viewRoot.append(el("div", { class: "stats" },
    stat(`${p.completed_pct}%`, "Plan completed", p.plan_ref ? `${p.engagements} engagements in ${p.plan_ref}` : "no plan this year", p.completed_pct >= 75 ? "ok" : ""),
    stat(s.reports_issued.length, "Reports issued", Object.entries(s.ratings).map(([k, v]) => `${v} ${k}`).join(" · ") || "none yet"),
    stat(openTotal, "Open findings", `${s.open_findings_by_rating.High || 0} high risk`, (s.open_findings_by_rating.High || 0) ? "danger" : ""),
    stat(a.overdue, "Overdue actions", `${a.with_cae} with the CAE`, a.overdue ? "danger" : "ok")));

  const bars = (obj, tone = () => "") => {
    const max = Math.max(1, ...Object.values(obj));
    return el("div", { class: "hbars" }, ...Object.entries(obj).map(([k, v]) => el("div", { class: "hbar" },
      el("span", { class: "hbar-label" }, k),
      el("span", { class: "hbar-track" }, el("span", { class: `hbar-fill ${tone(k)}`.trim(), style: `width:${Math.round((v / max) * 100)}%` })),
      el("span", { class: "hbar-val" }, String(v)))));
  };
  const riskTone = (k) => ({ High: "danger", Medium: "warn", Low: "ok" }[k] || "");
  const ageTone = (k) => (k.startsWith("Over") ? "danger" : (k.startsWith("91") ? "warn" : ""));
  const two = el("div", { class: "two-cols" });
  viewRoot.append(two);
  two.append(panel("Plan delivery by stage", Object.keys(p.by_stage).length ? bars(p.by_stage) : el("div", { class: "empty" }, "No engagements.")),
    panel("Agreed actions", el("dl", { class: "kv" },
      el("dt", null, "Open"), el("dd", null, String(a.open)),
      el("dt", null, "Overdue"), el("dd", null, String(a.overdue)),
      el("dt", null, "Awaiting validation"), el("dd", null, String(a.awaiting_validation)),
      el("dt", null, "Reopened after validation"), el("dd", null, String(a.reopened)),
      el("dt", null, "Closed"), el("dd", null, String(a.closed)))));
  const two2 = el("div", { class: "two-cols" });
  viewRoot.append(two2);
  two2.append(panel("Open findings by risk", bars(s.open_findings_by_rating, riskTone)),
    panel("Open findings by age", bars(s.open_findings_by_age, ageTone)));

  viewRoot.append(panel("Reports issued", dataTable(s.reports_issued, [
    { key: "report_ref", label: "Report", render: (r) => el("span", { class: "ref" }, r.report_ref) },
    { key: "title", label: "Title" },
    { key: "rating", label: "Overall rating", render: (r) => (r.rating ? el("span", { class: `rating rating-${r.rating.toLowerCase().replace(/\s+/g, "-")}` }, r.rating) : "-") },
    { key: "issued_at", label: "Issued", render: (r) => fmtDate(r.issued_at).split(",")[0] },
  ], { onRow: (r) => openAudit(r.audit_id, "report"), exportName: `reports-issued-FY${p.fiscal_year}.csv`, emptyText: "No reports issued yet." })));
  viewRoot.append(panel("Most overdue actions", dataTable(s.top_overdue, [
    { key: "capa_ref", label: "Action", render: (r) => el("span", { class: "ref" }, r.capa_ref) },
    { key: "title", label: "Description" },
    { key: "owner", label: "Owner", render: (r) => r.owner || "-" },
    { key: "days_overdue", label: "Days overdue", num: true },
    { key: "escalated_to", label: "Escalated to", render: (r) => badge(r.escalated_to) },
  ], { onRow: (r) => openRecord("capa", r.id), exportName: `overdue-actions-FY${p.fiscal_year}.csv`, emptyText: "No overdue actions." })));
}
