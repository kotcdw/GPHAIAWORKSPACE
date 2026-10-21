// Issue follow-up and remediation (Issue Follow-up & Remediation walkthrough):
//   Activity Center › Issues & Actions, the Issue Tracker list (Details), the issue page (Issue Information,
//   Follow-up & Remediation with Actions, Retest Information, Retest & sign-off) and the action's Complete Action.
// Loaded after fieldwork.js / workflow.js / walk.js / blueprint.js.

function issueTrackerFrame(title, crumb, actions = []) {
  return wsPage({ app: "Issue Tracker", util: [{ label: "Search", onClick: () => { const s = document.querySelector("#globalSearch, .global-search input"); if (s) s.focus(); } },
    { label: "Profile", onClick: () => navigate("profile") }], crumb, title, actions });
}

// ------------------------------------------------------------------ Activity Center › Issues & Actions

async function renderActivityCenter(filters = state.acFilters || {}) {
  state.acFilters = filters;
  const f = wsPage({ app: "Activity Center", util: [{ label: "Issue Tracker", onClick: () => navigate("issues") }, { label: "Reports", onClick: () => navigate("reports") }],
    crumb: ["Activity Center", "Issues & Actions"], title: "Monitor remediation across projects" });
  f.body.append(loadingState());
  const sp = new URLSearchParams(Object.entries(filters).filter(([, v]) => v));
  let d;
  try { d = await API.get(`/api/activity-center/issues-actions?${sp}`); } catch (err) { clear(f.body); f.body.append(errorState(err, () => renderActivityCenter(filters))); return; }
  clear(f.body);
  const project = wsSelect([{ value: "", label: "All projects" }, ...d.projects.map((p) => ({ value: p.id, label: p.title }))], filters.audit_id || "", { "aria-label": "Project", class: "ws-input compact" });
  const owner = wsInput(filters.owner || "", { type: "search", placeholder: "Owner e-mail", "aria-label": "Owner", class: "ws-input compact" });
  project.addEventListener("change", () => renderActivityCenter({ ...filters, audit_id: project.value }));
  owner.addEventListener("keydown", (e) => { if (e.key === "Enter") renderActivityCenter({ ...filters, owner: owner.value.trim() }); });
  f.setHead("Monitor remediation across projects", [project, owner, wsAction("Reset filters", () => renderActivityCenter({}))]);
  f.body.append(wsGrid(
    wsCard("Open issues", el("p", { class: "ws-big" }, String(d.open_issues)), wsTag("Across accessible projects")),
    wsCard("Actions by due date", el("p", null, `Overdue　${d.actions.overdue}　　Due soon　${d.actions.due_soon}　　Completed　${d.actions.completed}`),
      wsMeter(d.actions.open, Math.max(d.actions.open - d.actions.overdue, 0)))));
  const art = (r) => el("article", { tabindex: "0", onclick: () => openIssue(r.id), onkeydown: (e) => { if (e.key === "Enter") openIssue(r.id); } },
    `${r.title} · ${r.due_state || r.remediation_status}`);
  f.body.append(el("div", { class: "ws-kanban" },
    el("div", null, el("b", null, "Issues by due date"), ...(d.issues_by_due_date.length ? d.issues_by_due_date.map(art) : [el("p", { class: "muted small" }, "Nothing overdue or due soon.")])),
    el("div", null, el("b", null, "Open issues"), ...(d.open_issue_list.length ? d.open_issue_list.slice(0, 8).map((r) => el("article", { tabindex: "0", onclick: () => openIssue(r.id) }, `${r.title} · ${r.status}`)) : [el("p", { class: "muted small" }, "No open issues.")])),
    el("div", null, el("b", null, "Actions by priority"), el("article", null, `High · ${d.actions_by_priority.High}　 Medium · ${d.actions_by_priority.Medium}　 Low · ${d.actions_by_priority.Low}`))));
  f.body.append(el("h3", { class: "ws-h", style: "margin-top:18px" }, "Report outcomes and carry actions forward"));
  f.body.append(dataTable(d.follow_up, [
    { key: "title", label: "Issue", render: (r) => el("span", null, r.title, el("div", { class: "ws-caption" }, r.project)) },
    { key: "owner", label: "Owner" }, { key: "remediation_status", label: "Action status" }, { key: "retest", label: "Retest" },
  ], { onRow: (r) => openIssue(r.id), exportName: "follow-up-status", emptyText: "No open issues." }));
  f.body.append(el("p", { class: "ws-caption" }, d.note));
}

// ------------------------------------------------------------------ Issue Tracker list

async function renderIssueTracker(view = state.issueTab || "list") {
  state.issueTab = view;
  const f = issueTrackerFrame("Find the issue to follow up", ["Issue Tracker", view === "kpis" ? "KPIs" : "Issues List"],
    [wsAction(view === "kpis" ? "Issues list" : "KPIs", () => renderIssueTracker(view === "kpis" ? "list" : "kpis"))]);
  const body = f.body;
  let owners = [];
  let types = [];
  try { const s = await API.get("/api/findings/register/summary"); owners = s.owners; types = s.issue_types; }
  catch (err) { body.append(errorState(err, () => renderIssueTracker(view))); return; }
  if (view === "kpis") { renderIssueKpis(body); return; }
  const audits = await safeGet("/api/audits", []);
  const table = serverTable({
    url: "/api/findings/register", storageKey: "issues", defaultSort: "-updated_at", exportName: "issue-tracker", placeholder: "Search title…",
    filters: [
      { key: "audit_id", label: "Project", options: audits.map((a) => ({ value: a.id, label: a.title })) },
      { key: "status", label: "Status", options: ["Open", "Remediating", "Closed"] },
      { key: "severity", label: "Severity", options: ["High", "Medium", "Low"] },
      { key: "owner", label: "Owner", options: owners.map((o) => ({ value: o.email, label: o.name })) },
      { key: "issue_type", label: "Issue type", options: [...types, { value: "(none)", label: "Not set" }] },
      { key: "published", label: "Published", options: [{ value: "true", label: "Yes" }, { value: "false", label: "No" }] },
      { key: "overdue", label: "Deadline", options: [{ value: "true", label: "Overdue" }] },
    ],
    columns: [
      { key: "title", label: "Issue", sort: true, render: (r) => el("span", { class: "cell-title" }, r.title), csv: (r) => `${r.ref} ${r.title}` },
      { key: "audit", label: "Project", sort: true },
      { key: "owner", label: "Owner", sort: true },
      { key: "remediation_status", label: "Remediation status", sort: true },
      { key: "remediation_deadline", label: "Deadline", sort: true,
        render: (r) => (r.remediation_deadline ? el("span", { class: r.overdue ? "text-danger" : null }, fmtDay(r.remediation_deadline), r.overdue ? " · overdue" : "") : "-"),
        csv: (r) => r.remediation_deadline || "" },
      { key: "status", label: "Status", sort: true, render: (r) => statusBadge(r.status), csv: (r) => r.status },
      { key: "severity", label: "Severity", sort: true, render: (r) => statusBadge(r.severity), csv: (r) => r.severity, hidden: true },
      { key: "issue_type", label: "Issue type", sort: true, hidden: true },
      { key: "published", label: "Published", sort: true, render: (r) => (r.published ? "Yes" : "No"), hidden: true },
      { key: "signoffs", label: "Sign-offs", render: (r) => signoffDots(r.signoffs), csv: (r) => `${r.signoffs.filter((d) => d.done).length}/${r.signoffs.length}`, hidden: true },
      { key: "retest", label: "Retest", hidden: true },
      { key: "details", label: "", render: (r) => el("button", { class: "ws-action primary", type: "button", onclick: (e) => { e.stopPropagation(); openIssue(r.id); } }, "Details"), csv: () => "" },
    ],
    onRow: (r) => openIssue(r.id),
    emptyTitle: "No issues yet", emptyText: "Issues raised in projects appear here.",
  });
  body.append(table.root);
}

// ------------------------------------------------------------------ the issue page

async function openIssue(id, tab = null) {
  setActiveNav("issues");
  clear(viewRoot);
  viewRoot.append(loadingState("Opening the issue…"));
  let f; let audit; let opts; let actions;
  try {
    f = await API.get(`/api/findings/${id}`);
    [audit, opts, actions] = await Promise.all([API.get(`/api/audits/${f.audit_id}`), remediationOptions(), API.get(`/api/findings/${id}/actions`)]);
  } catch (err) { clear(viewRoot); viewRoot.append(errorState(err, () => openIssue(id, tab))); return; }
  clear(viewRoot);
  const staff = isStaff();
  const canWrite = staff && canWriteModule("audits");
  const reload = (t) => { state.issueTabFor = { id, tab: t }; openIssue(id, t); };
  const tabs = [
    { key: "info", label: "Issue Information" },
    { key: "remediation", label: "Follow-up & Remediation", count: actions.filter((a) => a.status !== "Closed").length || null },
    { key: "retest", label: "Retest Information" },
    ...(staff ? [{ key: "verify", label: "Retest & sign-off" }] : []),
  ];
  const layout = recordLayout({
    app: "Issue Tracker", crumbs: recordCrumbs("issues", `Issue #${f.id}`), back: () => navigate("issues"),
    title: f.title, ref: `ISS-${String(f.id).padStart(4, "0")}`, status: f.status,
    meta: [el("span", { class: "chip-mini" }, f.risk_rating)],
    utility: [
      { label: "Project", icon: "kanban", onClick: () => openAudit(audit.id) },
      ...(staff ? [{ label: "Sign-offs", icon: "pen", onClick: () => layout.select("verify") }] : []),
      { label: "History", icon: "clock-history", onClick: () => openAudit(audit.id, "history") },
    ],
    actions: [
      canWrite && !f.published ? wsAction("Publish", async () => {
        try { await API.post(`/api/findings/${f.id}/publish`); toast("Published - the owner has been notified"); reload("info"); } catch (err) { toast(err.message, "error"); }
      }) : null,
      wsAction(staff ? "Edit issue" : "Respond", () => issueForm(f, audit.id, canWrite, () => reload("info"))),
    ].filter(Boolean),
    tabs, side: null,
    onTab: (key, pane) => {
      if (key === "info") issueInfoPane(pane, f, audit);
      if (key === "remediation") issueRemediationPane(pane, f, audit, opts, actions, reload);
      if (key === "retest") issueRetestPane(pane, f, audit, opts, staff, reload);
      if (key === "verify") issueVerifyPane(pane, f, audit, actions, reload);
    },
  });
  viewRoot.append(layout.root);
  layout.select(tab || "info");
}

function issueInfoPane(pane, f, audit) {
  const v = (x) => (x && String(x).trim() ? el("span", { class: "pre" }, x) : el("span", { class: "muted" }, "-"));
  pane.append(el("h3", { class: "ws-h" }, "Issue Information"));
  pane.append(wsCard(null, wsFieldRows([
    { label: "Project", control: el("button", { class: "ws-crumb-link", type: "button", onclick: () => openAudit(audit.id) }, `AUD-${String(audit.id).padStart(4, "0")} ${audit.title}`) },
    { label: "Severity", control: v(f.risk_rating) }, { label: "Overall status", control: v(f.status) },
    { label: "Owner", control: v(f.assigned_owner_email) }, { label: "Published", control: v(f.published ? `Yes${f.published_at ? `, ${fmtDay(f.published_at.slice(0, 10))}` : ""}` : "No") },
    { label: "Criteria", control: v(f.criteria) }, { label: "Condition / details", control: v(f.condition || f.description) },
    { label: "Cause", control: v(f.cause) }, { label: "Effect", control: v(f.effect) }, { label: "Recommendation", control: v(f.recommendation) },
  ])));
}

function issueRemediationPane(pane, f, audit, opts, actions, reload) {
  const staff = isStaff();
  const mayRemediate = f.status !== "Closed" && (staff ? hasPerm("audit.findings", "followup.manage") : !!f.published);
  pane.append(el("h3", { class: "ws-h" }, "Document management's remediation plan"));
  const status = wsSelect(opts.statuses, f.remediation_status || "Open", { name: "remediation_status", disabled: mayRemediate ? null : "1" });
  const plan = wsText(f.remediation_plan || "", { name: "remediation_plan", rows: "3", maxlength: "10000", disabled: mayRemediate ? null : "1" });
  const deadline = wsInput((f.remediation_deadline || "").slice(0, 10), { type: "date", name: "remediation_deadline", disabled: mayRemediate ? null : "1" });
  const actual = wsInput((f.actual_remediation_date || "").slice(0, 10), { type: "date", name: "actual_remediation_date", disabled: mayRemediate ? null : "1" });
  const box = wsCard(null, wsFieldRows([
    { label: "Overall status", control: el("span", null, f.status), help: "The issue closes only after verification and the required approvals." },
    { label: "Remediation status", control: status }, { label: "Remediation plan", control: plan },
    { label: "Remediation deadline", control: deadline },
    { label: "Actual remediation date", control: actual, help: actual.value ? null : "Not completed" },
  ]), mayRemediate ? wsToolbar(wsAction("Save", async () => {
    try {
      await API.post(`/api/findings/${f.id}/remediation`, { remediation_status: status.value, remediation_plan: plan.value,
        remediation_deadline: deadline.value || null, actual_remediation_date: actual.value || null });
      toast("Remediation saved"); reload("remediation");
    } catch (err) { wsShowErrors(box, err); }
  }, { primary: true, focus: true })) : null);
  pane.append(box);
  if (!mayRemediate) pane.append(wsNote("Management response fields and who can edit them depend on your role. This page is read-only for you."));

  // Management response: action plan, action owner, target date.
  const canRespond = f.status !== "Closed" && audit.status !== "Closed";
  const resp = wsText(f.management_response || "", { rows: "3", maxlength: "10000", name: "management_response", disabled: canRespond ? null : "1" });
  const officer = wsInput(f.responsible_officer || "", { maxlength: "255", name: "responsible_officer", placeholder: "Name, or e-mail to make them the action owner", disabled: canRespond ? null : "1" });
  const target = wsInput((f.target_date || "").slice(0, 10), { type: "date", name: "target_date", disabled: canRespond ? null : "1" });
  const mr = wsCard("Management response", wsFieldRows([{ label: "Management response", control: resp }, { label: "Action owner", control: officer },
    { label: "Target date", control: target }]), canRespond ? wsToolbar(wsAction("Save", async () => {
    if (!resp.value.trim()) { toast("Enter the planned corrective action", "error"); return; }
    try { await API.post(`/api/findings/${f.id}/response`, { management_response: resp.value, responsible_officer: officer.value.trim() || null, target_date: target.value || null }); toast("Management response saved"); reload("remediation"); }
    catch (err) { wsShowErrors(mr, err); }
  })) : null);
  pane.append(mr);

  // Actions.
  const canAdd = staff && f.status !== "Closed" && hasPerm("audit.findings", "followup.manage");
  const list = wsCard("Actions", ...(actions.length ? actions.map((a) => wsRow(el("span", null, el("b", null, a.title), el("span", { class: "ws-caption" },
    `${a.ref} · ${a.owner_email || "No owner"} · due ${a.due_date ? fmtDay(String(a.due_date).slice(0, 10)) : "-"} · ${a.status}${a.validation_result ? ` · ${a.validation_result}` : ""}`)),
  el("span", { class: "ws-inline" }, wsTag(`${a.priority} priority`, a.priority === "High" ? "bad" : ""), wsAction("View/Discuss", () => openRecord("capa", a.id))))) : [el("p", { class: "muted small" }, "No actions yet.")]),
  canAdd ? wsToolbar(wsAction("Add", () => { form.hidden = false; title.focus(); }, { primary: true, focus: !actions.length })) : null);
  pane.append(list);
  if (!canAdd) return;
  const title = wsInput("", { name: "title", maxlength: "255", placeholder: "e.g. Document and approve quarterly access review" });
  const owner = wsInput("", { name: "owner_email", type: "email", maxlength: "255", placeholder: "Owner's e-mail address" });
  const desc = wsText("", { name: "description", rows: "3", maxlength: "10000" });
  const due = wsInput("", { name: "due_date", type: "date" });
  const prio = wsSelect(["High", "Medium", "Low"], f.risk_rating, { name: "priority", "aria-label": "Priority" });
  const now = el("input", { type: "checkbox", checked: "1" });
  const rem = el("input", { type: "checkbox", checked: "1" });
  const form = wsCard("Add action", wsFieldRows([
    { label: "Title", control: title }, { label: "Owner", control: owner }, { label: "Description", control: desc },
    { label: "Due date / priority", control: el("div", { class: "ws-inline" }, due, el("span", null, "/"), prio) },
    { label: "Notification / reminders", control: el("div", { class: "ws-inline" }, el("label", null, "Send now ", now), el("label", null, "Reminders ", rem)) },
  ]), wsToolbar(wsAction("Cancel", () => { form.hidden = true; }), wsAction("Save", async () => {
    try {
      const r = await API.post(`/api/findings/${f.id}/actions`, { title: title.value.trim(), owner_email: owner.value.trim() || null, description: desc.value,
        due_date: due.value || null, priority: prio.value, notify_now: now.checked, reminders: rem.checked });
      toast(r.notified ? `Action ${r.ref} saved; the owner has been notified` : `Action ${r.ref} saved`); reload("remediation");
    } catch (err) { wsShowErrors(form, err); }
  }, { primary: true })));
  form.hidden = true;
  pane.append(form);
}

async function issueRetestPane(pane, f, audit, opts, staff, reload) {
  const may = staff && f.status !== "Closed" && hasPerm("followup.validate", "audit.findings");
  const wps = await safeGet(`/api/audits/${audit.id}/working-papers`, []);
  const papers = (Array.isArray(wps) ? wps : wps.items || []).map((w) => ({ value: w.id, label: `${w.title} v${w.version_number}` }));
  pane.append(el("h3", { class: "ws-h" }, "Auditor retests the control or process"));
  if (opts.retest_required_severities.includes(f.risk_rating)) pane.append(wsNote(`${f.risk_rating}-rated issues close only after a retest concluded Effective.`));
  const dis = may ? null : "1";
  const deadline = wsInput((f.retest_deadline || "").slice(0, 10), { type: "date", name: "retest_deadline", disabled: dis });
  const date = wsInput((f.retest_date || "").slice(0, 10), { type: "date", name: "retest_date", disabled: dis });
  const notes = wsText(f.retest_notes || "", { name: "retest_notes", rows: "4", maxlength: "10000", placeholder: "Describe sample checked, evidence reviewed, and outcome…", disabled: dis });
  const result = wsSelect([{ value: "", label: "- not yet retested -" }, ...opts.retest_results], f.retest_result || "", { name: "retest_result", disabled: dis });
  const wp = wsSelect([{ value: "", label: "- none -" }, ...papers], f.retest_working_paper_id || "", { name: "retest_working_paper_id", disabled: dis });
  const file = el("input", { type: "file", "aria-label": "Upload retesting documentation", disabled: dis });
  const box = wsCard(null, wsFieldRows([
    { label: "Retest deadline date", control: deadline }, { label: "Actual retest date", control: date },
    { label: "Retesting results overview", control: notes }, { label: "Retest result", control: result, help: "Effective closes the issue when its actions are validated; Not effective returns it to management." },
    { label: "Attached retesting documentation", control: el("div", { class: "ws-inline" }, wp, file), help: "Choose a working paper of this project, or upload a file to create one." },
  ]), may ? wsToolbar(wsAction("Save", async () => {
    try {
      let wpId = wp.value ? Number(wp.value) : null;
      if (file.files.length) {
        const form = new FormData();
        form.append("title", `Retest - Issue #${f.id} ${f.title}`.slice(0, 200));
        form.append("file", file.files[0]);
        wpId = (await API.upload(`/api/audits/${audit.id}/working-papers`, form)).id;
      }
      const r = await API.post(`/api/findings/${f.id}/retest`, { retest_deadline: deadline.value || null, retest_date: date.value || null,
        retest_result: result.value || null, retest_notes: notes.value || null, retest_working_paper_id: wpId });
      toast(r.status === "Closed" ? "Retest recorded - issue closed as verified" : "Retest recorded"); reload("retest");
    } catch (err) { wsShowErrors(box, err); }
  }, { primary: true, focus: true })) : null);
  pane.append(box);
  if (!may) pane.append(wsNote(staff ? "The retest is recorded by an auditor with the validate permission while the issue is open." : "The audit team records the retest."));
}

async function issueVerifyPane(pane, f, audit, actions, reload) {
  pane.append(el("h3", { class: "ws-h" }, "Confirm resolution before closing"));
  const done = actions.filter((a) => a.status === "Closed" || a.implemented_at);
  const valid = actions.filter((a) => a.validation_result === "Effective");
  pane.append(wsGrid(
    wsCard("Remediation evidence", el("p", null, actions.length ? `${done.length} of ${actions.length} action${actions.length === 1 ? "" : "s"} completed; ${valid.length} validated Effective.` : "No remediation action yet."),
      wsTag(done.length && done.length === actions.length ? "Evidence attached" : "Awaiting evidence", done.length && done.length === actions.length ? "ok" : "warn")),
    wsCard("Auditor retest", el("p", null, f.retest_result ? `Retest outcome: ${f.retest_result}${f.retest_date ? ` on ${fmtDay(f.retest_date.slice(0, 10))}` : ""}.` : "Not retested yet."),
      wsTag(f.retest_result === "Effective" ? "Ready for review" : "Retest pending", f.retest_result === "Effective" ? "ok" : ""))));
  pane.append(wsCard(null, wsFieldRows([{ label: "Issue status", control: el("span", null, `${f.status} → Closed only after verification and required approvals`) },
    { label: "Remediation status", control: el("span", null, f.remediation_status || "Open") }]),
  f.status !== "Closed" && hasPerm("audit.findings", "followup.manage") ? wsToolbar(wsAction("Return for more work", async () => {
    try { await API.post(`/api/findings/${f.id}/remediation`, { remediation_status: "Management Remediating", remediation_plan: f.remediation_plan,
      remediation_deadline: (f.remediation_deadline || "").slice(0, 10) || null, actual_remediation_date: null }); toast("Returned to management"); reload("verify"); }
    catch (err) { toast(err.message, "error"); }
  })) : null));
  const so = el("div");
  pane.append(wsCard("Sign-offs", so));
  try { so.append(await signoffSection("finding", f.id, audit.id, () => reload("verify"))); } catch (err) { so.append(errorState(err)); }
  pane.append(wsNote("Status names and closure rules are configurable. Do not mark an issue resolved until the required verification and review steps are complete."));
}

// ------------------------------------------------------------------ action › Complete Action

function renderCapaComplete(panel, c, refresh) {
  const mine = state.user.email && c.owner_email && state.user.email.toLowerCase() === c.owner_email.toLowerCase();
  const canImplement = ["Open", "In Progress"].includes(c.status) && (isStaff() || mine);
  const canValidate = isStaff() && c.status === "Review" && c.implemented_at && !c.validation_result && c.implemented_by !== state.user.id;
  panel.append(el("h3", { class: "ws-h" }, "Complete Action"));
  panel.append(wsCard(null, wsFieldRows([
    { label: "Completion date", control: el("span", null, c.implemented_at ? fmtDate(c.implemented_at) : "Not completed") },
    { label: "State", control: el("span", null, c.status) },
    { label: "Implementation evidence", control: el("span", { class: "pre" }, c.implementation_evidence || "-") },
    { label: "Validation", control: el("span", null, c.validation_result || "Not validated yet") },
  ]), wsToolbar(canImplement ? wsAction(c.reopen_count ? "Record new evidence" : "Complete Action", () => implementForm(c, refresh), { primary: true, focus: true }) : null,
    canValidate ? wsAction("Validate", () => validateForm(c, refresh), { primary: true }) : null)));
  panel.append(wsNote("Completing the action records the date and the evidence; the audit team then validates it. Closing it needs the e-signed Close action."));
}
