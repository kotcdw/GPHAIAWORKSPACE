// GPHA Internal Audit Workspace - reporting, follow-up, notifications and two-step verification.
//
// Loaded after planning.js and before app.js; uses helpers from api.js, forms.js
// and app.js (el, badge, modal, toast, openForm, eSignModal, viewHeader ...) at call time.

const REPORT_RATINGS = ["Satisfactory", "Needs Improvement", "Unsatisfactory"];

function isStaff() { return state.user && ["Admin", "Auditor"].includes(state.user.role); }

function longBlock(label, text, empty = "Not written yet") {
  return el("div", { class: "long-field" }, el("div", { class: "lf-label" }, label),
    el("div", { class: `lf-value ${text ? "" : "muted"}`.trim() }, text || empty));
}

// Report progress: Draft -> Management Review -> each review level -> GM Audit approval -> Issued.
function reportStepper(r) {
  const stages = ["Draft", "Management Review", ...(r.review_chain || []).map((x) => `${x} review`), "GM Audit approval", "Issued"];
  const current = r.status === "Manager Review" ? `${r.review_stage_label} review` : r.status === "CAE Approval" ? "GM Audit approval" : r.status;
  return stepper(stages, current);
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
      onclick: post(`/api/reports/${r.id}/submit-for-review`, r.review_chain.length ? `Submitted for ${r.review_chain[0]} review` : "Submitted to the GM Audit") },
    el("i", { class: "bi bi-check2-circle" }), " Submit for review") : null,
    r.can_comment ? el("button", { class: "btn small", onclick: () => commentsForm(r, reload) },
      el("i", { class: "bi bi-chat-left-text" }), " Management comments") : null,
    r.can_manager_review ? el("button", { class: "btn small", onclick: () => eSignModal({
      title: `${r.review_stage_label} review`, pathOverride: `/api/reports/${r.id}/manager-review`, actionLabel: "Sign review",
      allowReject: true, onDone: reload }) }, el("i", { class: "bi bi-pen" }), ` Review as ${r.review_stage_label} (e-sign)`) : null,
    r.can_cae_approve ? el("button", { class: "btn small", onclick: () => eSignModal({
      title: "GM Audit approval - issue report", pathOverride: `/api/reports/${r.id}/cae-approve`, actionLabel: "Approve & issue",
      allowReject: true, onDone: reload }) }, el("i", { class: "bi bi-patch-check" }), " Approve & issue (e-sign)") : null,
    r.can_correct ? el("button", { class: "btn small secondary", onclick: () => reportCorrectionForm(r, reload) }, el("i", { class: "bi bi-arrow-repeat" }), " Correct") : null,
    el("a", { class: "btn small secondary", href: `/api/reports/${r.id}/export.docx` }, el("i", { class: "bi bi-file-earmark-word" }), " Word"),
    el("a", { class: "btn small secondary", href: `/api/reports/${r.id}/print`, target: "_blank", rel: "noopener" },
      el("i", { class: "bi bi-printer" }), " Print / PDF"));

  const head = el("div", { class: "card" },
    el("div", { class: "card-head" },
      el("div", null, el("h3", null, r.title),
        el("div", { class: "view-meta" }, el("span", { class: "ref" }, r.report_ref), badge(r.status),
          r.version > 1 ? el("span", { class: "muted" }, `Version ${r.version}`) : null,
          r.advisory ? el("span", { class: "u-chip" }, "Advisory") : null,
          r.overall_rating ? el("span", { class: `rating rating-${r.overall_rating.toLowerCase().replace(/\s+/g, "-")}` }, r.overall_rating)
            : el("span", { class: "muted" }, "Not rated"))),
      actions),
    reportStepper(r));
  panel.append(head);

  if (r.blockers.length) {
    panel.append(el("div", { class: "callout warn" }, el("i", { class: "bi bi-exclamation-triangle" }),
      el("div", null, el("strong", null, "Before it can go to review"),
        el("ul", null, ...r.blockers.map((b) => el("li", null, b))))));
  }
  if (r.version > 1) {
    panel.append(el("div", { class: "callout warn" }, el("i", { class: "bi bi-arrow-repeat" }),
      el("div", null, el("strong", null, `Version ${r.version} corrects version ${r.version - 1}. `), r.correction_reason || "")));
  }
  reportComplianceCards(panel, r);
  if (r.version > 1) reportVersionsCard(panel, r);
  if (r.status === "Management Review" && !isStaff()) {
    panel.append(el("div", { class: "callout" }, el("i", { class: "bi bi-info-circle" }),
      el("div", null, "Please read the draft, add your management comments and respond to each finding on the Findings tab.")));
  }

  panel.append(el("div", { class: "card" },
    longBlock("Executive summary", r.executive_summary),
    longBlock(r.advisory ? "Conclusion" : "Overall opinion", r.overall_opinion),
    longBlock("Background", r.background),
    longBlock("Scope and objectives", r.scope_objectives),
    longBlock("Methodology", r.methodology),
    longBlock("Management comments", r.management_comments, "None received yet"),
    longBlock("Distribution", r.distribution_list, "Not specified")));

  panel.append(exitMeetingCard(r, canWrite, () => renderReportTab(panel, auditId, canWrite)));
  panel.append(el("div", { class: "card" }, el("h3", null, "Sign-off"),
    el("div", { class: "table-wrap" }, el("table", null,
      el("thead", null, el("tr", null, el("th", null, "Role"), el("th", null, "Name"), el("th", null, "Date"))),
      el("tbody", null, ...r.signoffs.map((s) => el("tr", { class: "no-click" },
        el("td", null, s.role), el("td", null, s.name || el("span", { class: "muted" }, "Pending")),
        el("td", null, s.name && s.at ? fmtDate(s.at).split(",")[0] : "-"))))))));
}

// Open a corrected version of an issued report.
function reportCorrectionForm(r, reload) {
  return openForm({
    title: `Correct ${r.report_ref}`, key: `report:${r.id}:correct`, draftable: false, width: 640,
    fields: [{ name: "reason", label: "Error or omission to correct", type: "textarea", rows: 4, required: true, minLength: 20, maxLength: 5000 }],
    submitLabel: `Open version ${r.version + 1}`,
    onSubmit: (v) => API.post(`/api/reports/${r.id}/correction`, v),
    onDone: () => { toast(`Version ${r.version + 1} opened`); reload(); },
  });
}

async function reportVersionsCard(panel, r) {
  const card = el("div", { class: "card" }, el("h3", null, "Earlier versions"));
  panel.append(card);
  const rows = await safeGet(`/api/reports/${r.id}/versions`, []);
  card.append(dataTable(rows, [
    { key: "version", label: "Version" },
    { key: "issued_at", label: "Issued", render: (x) => (x.issued_at ? dayOnly(x.issued_at) : "-") },
    { key: "superseded_at", label: "Superseded", render: (x) => dayOnly(x.superseded_at) },
    { key: "correction_reason", label: "Corrected because" },
    { key: "opened_by", label: "By" },
    { key: "files", label: "", render: (x) => el("span", { class: "actions" },
      el("a", { class: "btn small secondary", href: `/api/reports/${r.id}/versions/${x.version}/print`, target: "_blank", rel: "noopener" }, "Print"),
      el("a", { class: "btn small secondary", href: `/api/reports/${r.id}/versions/${x.version}/export.docx` }, "Word")) },
  ], { emptyText: "No earlier versions.", pageSize: 10 }));
}

function reportForm(r, reload) {
  const fields = [
    { name: "title", label: "Report title", required: true, maxLength: 255, singleLine: true },
    ...(r.advisory ? [] : [{ name: "overall_rating", label: "Overall rating", type: "select", options: REPORT_RATINGS, emptyLabel: "- choose -" }]),
    { name: "executive_summary", label: "Executive summary", type: "textarea", rows: 5, maxLength: 50000,
      help: "What the reader must know: the overall conclusion and the most significant issues." },
    { name: "overall_opinion", label: r.advisory ? "Conclusion" : "Overall opinion", type: "textarea", rows: 3, maxLength: 50000 },
    { name: "background", label: "Background", type: "textarea", rows: 3, maxLength: 50000 },
    { name: "scope_objectives", label: "Scope and objectives", type: "textarea", rows: 3, maxLength: 50000 },
    { name: "methodology", label: "Methodology", type: "textarea", rows: 3, maxLength: 50000 },
    { name: "distribution_list", label: "Distribution list", type: "textarea", rows: 2, maxLength: 5000,
      placeholder: "e.g. Director-General; Deputy Director-General (Finance); Audit Committee" },
  ];
  const handle = openForm({
    actions: [aiSummaryAction(r.id, () => handle, fields)],
    title: `Edit ${r.report_ref}`,
    key: `report:${r.id}:edit`,
    meta: { title: `Edit report ${r.report_ref}`, record_type: "audit_report", record_id: r.id },
    width: 860,
    fields,
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
    const where = c.escalation_level >= 4 ? "Reported to the Audit Committee." : c.escalation_level === 3 ? "Escalated to the CAE."
      : (c.escalation_level === 2 ? "Escalated to Audit Managers." : "The owner has been reminded.");
    card.append(el("div", { class: "callout danger" }, el("i", { class: "bi bi-alarm" }),
      el("div", null, el("strong", null, "Overdue. "), where)));
  }
  if (c.due_date) {
    const extended = c.extension_count && c.original_due_date;
    card.append(el("dl", { class: "kv two-col fu-extra" },
      el("dt", null, "Target date"), el("dd", null, fmtDate(c.due_date).split(",")[0],
        extended ? el("span", { class: "muted small" }, ` (originally ${fmtDate(c.original_due_date).split(",")[0]}; revised ${c.extension_count} time${c.extension_count === 1 ? "" : "s"})`) : null)));
  }
  const RISK_STEP = { Proposed: "Risk acceptance proposed - awaiting the GM Audit. ", Committee: "Risk acceptance agreed by the GM Audit - awaiting the Audit Committee. ",
    Accepted: "Closed - risk accepted. " };
  if (c.risk_acceptance && RISK_STEP[c.risk_acceptance_status]) {
    card.append(el("div", { class: "callout warn" }, el("i", { class: "bi bi-shield-exclamation" }),
      el("div", null, el("strong", null, RISK_STEP[c.risk_acceptance_status]), c.risk_acceptance,
        c.risk_acceptance_status === "Proposed" && state.user.review_level === "CAE" && ![c.risk_proposed_by, c.created_by].includes(state.user.id)
          ? el("div", { class: "actions" }, el("button", { class: "btn small", onclick: () => capaRiskDecisionForm(c, refresh) }, el("i", { class: "bi bi-check2-square" }), " Decide")) : null)));
  }
  if (c.reopen_count) card.append(el("p", { class: "muted small" }, `Reopened ${c.reopen_count} time(s) after validation.`));
  card.append(longBlock("Implementation evidence", c.implementation_evidence, "Not recorded yet"));
  if (c.implemented_at) card.append(el("p", { class: "muted small" }, `Recorded ${fmtDate(c.implemented_at)}`));
  if (c.validation_result) {
    card.append(el("div", { class: "long-field" }, el("div", { class: "lf-label" }, "Auditor validation"),
      el("div", { class: "lf-value" }, badge(c.validation_result), c.validation_comment ? ` ${c.validation_comment}` : "",
        el("div", { class: "muted small" }, `Validated ${fmtDate(c.validated_at)}`))));
    if (c.validation_procedures) card.append(longBlock("Follow-up testing performed", c.validation_procedures, ""));
  }
  if (c.status === "Review" && c.validation_result === "Effective") {
    card.append(el("p", { class: "muted small" }, "Validated as effective - the Audit Manager or CAE can now close it with an e-signature, or the Audit Committee closes it (see Audit Committee > Meetings)."));
  }
  capaFollowupExtras(card, c, refresh);
  capaManageActions(card, c, refresh);
  panel.append(card);
  panel.append(capaEvidenceCard(c, refresh));
  panel.append(capaTimelineCard(c));
}

// GM Audit decision on a proposed risk acceptance.
function capaRiskDecisionForm(c, refresh) {
  return openForm({
    title: `Risk acceptance - ${c.capa_ref}`, key: `capa:${c.id}:riskdecide`, draftable: false, width: 640,
    fields: [
      { name: "decision", label: "Decision", type: "select", required: true, options: ["Agree", "Disagree"] },
      { name: "comment", label: "Discussion with senior management and conclusion", type: "textarea", rows: 4, required: true, minLength: 10, maxLength: 5000 },
    ],
    initial: { decision: "Agree" },
    submitLabel: "Record decision",
    onSubmit: (v) => API.post(`/api/capa/${c.id}/risk-acceptance/decision`, v),
    onDone: () => { toast("Decision recorded"); refresh(); },
  });
}

// Revise the target date, accept the risk, reopen (follow-up manager: Audit Manager / CAE).
function capaManageActions(card, c, refresh) {
  if (!hasPerm("followup.manage")) return;
  const btns = el("div", { class: "actions" });
  if (c.status !== "Closed" && c.due_date) {
    btns.append(el("button", { class: "btn small secondary", onclick: () => capaReviseDateForm(c, refresh) }, el("i", { class: "bi bi-calendar-plus" }), " Revise target date"));
  }
  if (c.status !== "Closed" && c.created_by !== state.user.id && !["Proposed", "Committee"].includes(c.risk_acceptance_status)) {
    btns.append(el("button", { class: "btn small secondary", onclick: () => capaRiskProposalForm(c, refresh) }, el("i", { class: "bi bi-shield-exclamation" }), " Propose risk acceptance"));
  }
  if (c.status === "Closed") {
    btns.append(el("button", { class: "btn small secondary", onclick: () => capaReopenForm(c, refresh) }, el("i", { class: "bi bi-arrow-counterclockwise" }), " Reopen"));
  }
  if (btns.childNodes.length) card.append(btns);
}

// Revise an action's target date.
function capaReviseDateForm(c, refresh) {
  return openForm({
    title: `Revise target date - ${c.capa_ref}`, key: `capa:${c.id}:extend`, draftable: false, width: 600,
    intro: `Current target date: ${fmtDate(c.due_date).split(",")[0]}. The original date, the new date and your reason are kept in the follow-up timeline, and escalation restarts from the new date.`,
    fields: [
      { name: "due_date", label: "New target date", type: "date", required: true, notPast: true },
      { name: "reason", label: "Reason (agreed with management)", type: "textarea", rows: 3, required: true, minLength: 10, maxLength: 2000 },
    ],
    submitLabel: "Revise target date",
    onSubmit: (v) => API.patch(`/api/capa/${c.id}`, { due_date: `${v.due_date}T00:00:00`, due_date_reason: v.reason }),
    onDone: () => { toast("Target date revised"); refresh(); },
  });
}

// Propose accepting the risk instead of implementing.
function capaRiskProposalForm(c, refresh) {
  return openForm({
    title: `Propose risk acceptance - ${c.capa_ref}`, key: `capa:${c.id}:risk`, draftable: false, width: 640,
    fields: [
      { name: "accepted_by", label: "Accepted by (name and position)", required: true, minLength: 3, maxLength: 255, singleLine: true },
      { name: "reason", label: "Why the risk is accepted, and any compensating controls", type: "textarea", rows: 4, required: true, minLength: 20, maxLength: 5000 },
    ],
    submitLabel: "Send to the GM Audit",
    onSubmit: (v) => API.post(`/api/capa/${c.id}/accept-risk`, v),
    onDone: () => { toast("Sent to the GM Audit"); refresh(); },
  });
}

// Reopen a closed action.
function capaReopenForm(c, refresh) {
  return openForm({
    title: `Reopen ${c.capa_ref}`, key: `capa:${c.id}:reopen`, draftable: false, width: 600,
    fields: [{ name: "reason", label: "Why the action is reopened", type: "textarea", rows: 4, required: true, minLength: 20, maxLength: 5000 }],
    submitLabel: "Reopen",
    onSubmit: (v) => API.post(`/api/capa/${c.id}/reopen`, v),
    onDone: () => { toast("Action reopened"); refresh(); },
  });
}

function capaEvidenceCard(c, refresh) {
  const mine = state.user.email && c.owner_email && state.user.email.toLowerCase() === c.owner_email.toLowerCase();
  const canAdd = c.status !== "Closed" && (isStaff() || mine);
  const list = el("div", null, loadingState());
  const input = el("input", { type: "file", class: "hidden", "aria-label": "Choose an evidence file" });
  input.addEventListener("change", async () => {
    if (!input.files.length) return;
    const fd = new FormData();
    fd.append("file", input.files[0]);
    try { await API.request("POST", `/api/capa/${c.id}/files`, { form: fd }); toast("Evidence file attached"); refresh(); }
    catch (err) { toast(err.message, "error"); }
    input.value = "";
  });
  const card = el("div", { class: "card" },
    el("div", { class: "card-head" }, el("h3", null, "Evidence files"),
      canAdd ? el("div", { class: "actions" }, input, el("button", { class: "btn small secondary", onclick: () => input.click() },
        el("i", { class: "bi bi-paperclip" }), " Attach file")) : null),
    list);
  API.get(`/api/capa/${c.id}/files`).then((files) => {
    clear(list);
    if (!files.length) { list.append(el("p", { class: "muted small" }, canAdd ? "No files yet. Attach signed documents, screenshots or reports that show the action was done." : "No files.")); return; }
    list.append(el("div", { class: "table-wrap" }, el("table", null,
      el("thead", null, el("tr", null, el("th", null, "File"), el("th", null, "Uploaded by"), el("th", null, "When"), el("th", { class: "num" }, "Size"), el("th", null, ""))),
      el("tbody", null, ...files.map((f) => el("tr", { class: "no-click" },
        el("td", null, el("a", { href: `/api/capa-files/${f.id}/download` }, f.original_name),
          el("div", { class: "muted small", title: f.sha256 }, `SHA-256 ${f.sha256.slice(0, 16)}…`)),
        el("td", null, f.uploaded_by || "-"), el("td", { class: "muted" }, fmtDate(f.uploaded_at)),
        el("td", { class: "num" }, `${Math.max(1, Math.round(f.size_bytes / 1024))} KB`),
        el("td", { class: "num" }, isStaff() && c.status !== "Closed" ? el("button", { class: "btn small danger-ghost", title: "Withdraw (kept in the trail)",
          onclick: async () => {
            const ok = await confirmDialog({ title: "Withdraw this file?", text: `${f.original_name} is hidden from the action but kept, with a record of who withdrew it.`, confirmLabel: "Withdraw", danger: true });
            if (!ok.ok) return;
            try { await API.del(`/api/capa-files/${f.id}`); toast("File withdrawn"); refresh(); } catch (err) { toast(err.message, "error"); }
          } }, "Withdraw") : null)))))));
  }).catch((err) => { clear(list); list.append(el("p", { class: "muted small" }, err.message)); });
  return card;
}

const CAPA_EVENT_ICONS = { created: "flag", progress: "graph-up", implementation: "clipboard-check", evidence_file: "paperclip",
  validation: "shield-check", extension: "calendar-plus", escalation: "alarm", reopened: "arrow-counterclockwise",
  risk_proposed: "shield", risk_rejected: "shield-x", risk_accepted: "shield-exclamation", withdrawal: "x-octagon", closed: "lock", note: "chat-left-text" };

function capaTimelineCard(c) {
  const body = el("div", null, loadingState());
  const card = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, "Follow-up timeline"),
    el("span", { class: "muted small" }, "Every step, in order. Entries cannot be edited or deleted.")), body);
  API.get(`/api/capa/${c.id}/timeline`).then((rows) => {
    clear(body);
    body.append(activityTimeline(rows.slice().reverse().map((e) => {
      const dates = e.kind === "extension" && e.new_due_date
        ? ` ${e.old_due_date ? fmtDate(e.old_due_date).split(",")[0] : "none"} → ${fmtDate(e.new_due_date).split(",")[0]}.` : "";
      return { at: e.created_at, who: e.user || "", icon: CAPA_EVENT_ICONS[e.kind] || "dot",
        text: el("span", null, el("strong", null, e.label), dates, e.text ? ` ${e.text}` : "") };
    }), { emptyText: "Nothing recorded yet." }));
  }).catch((err) => { clear(body); body.append(el("p", { class: "muted small" }, err.message)); });
  return card;
}

function implementForm(c, refresh) {
  openForm({
    title: `Record implementation - ${c.capa_ref}`,
    key: `capa:${c.id}:implement`,
    meta: { title: `Implementation of ${c.capa_ref}`, record_type: "capa", record_id: c.id },
    fields: [{ name: "evidence", label: "What was done, when, and where the evidence is", type: "textarea", rows: 6,
      required: true, minLength: 10, maxLength: 20000,
      help: "Be specific: dates, documents, system changes. Attach supporting files under Evidence files on this page." }],
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
      { name: "procedures", label: "Follow-up testing performed", type: "textarea", rows: 4, maxLength: 20000,
        help: "What you did to confirm the action works: re-performance, sample tested, documents inspected. Required when effective." },
      { name: "comment", label: "Validation notes", type: "textarea", rows: 3, maxLength: 20000,
        help: "Required when not effective: say what is still missing." },
    ],
    validate: (v) => {
      if (v.result === "Not Effective" && (v.comment || "").trim().length < 5) return { comment: "Explain why it is not effective" };
      if (v.result === "Effective" && (v.procedures || "").trim().length < 10) return { procedures: "Describe the follow-up testing (at least 10 characters)" };
      return {};
    },
    initial: { result: "Effective" },
    submitLabel: "Save validation",
    onSubmit: (v) => API.post(`/api/capa/${c.id}/validate`, { result: v.result, comment: v.comment || "", procedures: v.procedures || "" }),
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
    stat(lvl(4), "Reported to the Audit Committee", "escalated after the committee threshold", lvl(4) ? "danger" : ""),
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
  const agingBox = el("div", null, loadingState());
  root.append(panel("Aging of open actions", agingBox,
    el("a", { class: "btn small secondary", href: "/api/followup/aging.csv" }, el("i", { class: "bi bi-filetype-csv" }), " Export")));
  API.get("/api/followup/aging").then((a) => {
    clear(agingBox);
    const tones = { "Not yet due": "ok", "1-30 days": "warn", "31-60 days": "warn", "61-90 days": "danger", "Over 90 days": "danger" };
    agingBox.append(el("div", { class: "stats" }, ...Object.entries(a.buckets).map(([k, v]) => stat(v, k, k === "Not yet due" ? "open, on time" : "overdue", v ? tones[k] : ""))));
    if (a.by_owner.length) {
      agingBox.append(el("div", { class: "table-wrap" }, el("table", null,
        el("thead", null, el("tr", null, el("th", null, "Owner"), el("th", { class: "num" }, "Open"), el("th", { class: "num" }, "Overdue"), el("th", { class: "num" }, "Target date revised"))),
        el("tbody", null, ...a.by_owner.map((o) => el("tr", { class: "no-click" }, el("td", null, o.owner),
          el("td", { class: "num" }, String(o.open)), el("td", { class: "num" }, o.overdue ? el("strong", null, String(o.overdue)) : "0"),
          el("td", { class: "num" }, String(o.extended))))))));
    }
  }).catch((err) => { clear(agingBox); agingBox.append(el("p", { class: "muted small" }, err.message)); });
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
    const data = await API.getBackground("/api/notifications?unread_only=true&limit=1");
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
    if (type === "erm_risk") return openRisk(id);
    if (type === "regulation") return openRegulation(id);
    if (type === "policy") return openPolicy(id);
    if (type === "asset") return openAsset(id);
    if (type === "attestation") return navigate("portal");
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
    card.append(el("p", { class: "muted" }, "Sign in with your password plus a code from an authenticator app."),
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
      const wasGated = !!state.mfaSetupRequired;
      state.user = me.user; state.perms = me.permissions || state.perms; state.mfaSetupRequired = me.mfa_setup_required;
      toast("Two-step verification is on");
      if (wasGated && !state.mfaSetupRequired) { showApp(); return; }  // unlock the whole workspace
      paintMfa(card);
    },
  });
}

// ==================================================================== data table: sort, page, export, keyboard

function csvCell(v) {
  const s = v === null || v === undefined ? "" : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

async function downloadCsv(filename, columns, items) {
  // Exports are part of the audit trail and need the export permission: record first, download only if allowed.
  try { await API.post("/api/export.log", { title: String(filename).replace(/\.csv$/i, "").slice(0, 100), rows: items.length, format: "csv" }); }
  catch (err) { toast(err.message, "error"); return; }
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
        exportName && hasPerm("data.export") ? el("button", { class: "btn small secondary", onclick: () => downloadXlsx(exportName.replace(/\.csv$/, ""), columns, rows) },
          el("i", { class: "bi bi-file-earmark-excel" }), " Excel") : null,
        exportName && hasPerm("data.export") ? el("button", { class: "btn small secondary", onclick: () => downloadCsv(exportName, columns, rows) },
          el("i", { class: "bi bi-filetype-csv" }), " CSV") : null)));
  }
  paint();
  return wrap;
}

// ==================================================================== System Configuration (Admin)
// One section at a time, picked from a grouped drop-down (with search across every setting).
// Each setting is a row: what it does on the left, the control on the right. Lists and long texts
// fold away behind a summary until opened. Edits are kept while switching sections and saved together.

const CONFIG_GROUP_ICONS = { "Audit workflow": "diagram-3", "Action plans": "alarm", Security: "shield-lock", Reports: "file-earmark-text", Organizations: "building", "KPI targets": "speedometer2", AI: "stars", "Follow-up & reporting": "file-earmark-bar-graph", "Professional practice": "person-check", "Audit methodology": "journal-check", "Plan configuration": "calendar3", "Risk & compliance": "clipboard2-pulse", Regional: "globe2", "Data & attachments": "paperclip", Backups: "hdd-stack" };
const CONFIG_CATEGORIES = [
  { name: "General", groups: ["Regional"] },
  { name: "Audit process", groups: ["Audit workflow", "Audit methodology", "Plan configuration", "Professional practice", "Reports"] },
  { name: "Issues & follow-up", groups: ["Action plans", "Follow-up & reporting", "Risk & compliance"] },
  { name: "Organization & access", groups: ["Organizations", "Security", "Data & attachments", "Backups"] },
  { name: "Performance & services", groups: ["KPI targets", "AI"] },
];
const CONFIG_EXTRA = [
  { key: "@orgfields", name: "Organization fields", icon: "input-cursor-text", desc: "Extra inputs on organization forms", render: (c) => renderCustomFieldsCard(c) },
  { key: "@recordfields", name: "Record fields", icon: "ui-checks", desc: "Extra inputs on audits, findings and actions", render: (c) => renderRecordFieldsCard(c) },
];

const CONFIG_WORKFLOW = [
  { key: "@sla", name: "SLA time limits", icon: "stopwatch", desc: "Working days allowed per task in My work", render: (c) => renderSlaPoliciesCard(c) },
];

const cfgSummary = (r, v) => {
  if (r.kind === "bool") return v ? "On" : "Off";
  if (r.kind === "roles" || r.kind === "list") {
    const items = (Array.isArray(v) ? v : String(v || "").split("\n")).map((x) => String(x).trim()).filter(Boolean);
    if (!items.length) return "None";
    return `${items.length} item${items.length === 1 ? "" : "s"}: ${items.slice(0, 3).join(", ")}${items.length > 3 ? ", …" : ""}`;
  }
  const t = String(v ?? "").replace(/\s+/g, " ").trim();
  return t ? (t.length > 70 ? `${t.slice(0, 70)}…` : t) : "Empty";
};
const cfgSame = (a, b) => JSON.stringify(a) === JSON.stringify(b);
// A list whose entries come from fixed choices (working days, review chain): shown as tick boxes.
const cfgChoiceList = (r) => r.kind === "list" && Array.isArray(r.options) && r.options.length > 0;

const cfgValueText = (v) => {
  if (v === null || v === undefined) return "-";
  if (typeof v === "boolean") return v ? "On" : "Off";
  if (Array.isArray(v)) return v.length ? v.join(", ") : "None";
  if (typeof v === "object") return "(updated)";
  const t = String(v).replace(/\s+/g, " ").trim();
  return t ? (t.length > 160 ? `${t.slice(0, 160)}…` : t) : "Empty";
};

// Settings history (append-only on the server): one setting, or every setting the user manages.
async function openConfigHistory(key = null, label = "") {
  const body = el("div", null, loadingState("Loading the history…"));
  detailPanel({ title: key ? `History: ${label}` : "Recent changes to settings", body, width: 620 });
  let rows;
  try { rows = await API.get(`/api/config/history?limit=200${key ? `&key=${encodeURIComponent(key)}` : ""}`); }
  catch (err) { clear(body); body.append(errorState(err)); return; }
  clear(body);
  body.append(el("p", { class: "muted small" }, "Every change is kept: who made it, when, the value before and after, and the reason given. The record cannot be edited or deleted."));
  if (!rows.length) { body.append(el("p", { class: "muted" }, "No changes recorded yet.")); return; }
  body.append(el("ul", { class: "cfg-history" }, ...rows.map((h) => el("li", null,
    el("div", { class: "cfg-history-head" }, el("strong", null, key ? (h.action === "reset" ? "Reset to default" : "Changed") : h.label),
      el("span", { class: "muted small" }, ` · ${h.by} · ${fmtDate(h.at)}`)),
    key ? null : el("div", { class: "muted small" }, `${h.group}${h.action === "reset" ? " · reset to default" : ""}`),
    h.key === "app_customization" ? null : el("div", { class: "cfg-history-change small" },
      el("span", { class: "cfg-old" }, cfgValueText(h.old)), el("i", { class: "bi bi-arrow-right", "aria-hidden": "true" }), el("span", { class: "cfg-new" }, cfgValueText(h.new))),
    h.reason ? el("div", { class: "small" }, el("span", { class: "muted" }, "Reason: "), h.reason) : null))));
}

// Storage: what the encrypted attachments take up on disk, by file type.
async function renderStorageCard(container) {
  const card = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, el("i", { class: "bi bi-hdd" }), " Storage")), loadingState());
  container.append(card);
  let s;
  try { s = await API.get("/api/admin/storage"); } catch (err) { card.lastChild.remove(); card.append(errorState(err)); return; }
  card.lastChild.remove();
  const mb = (b) => (b >= 1073741824 ? `${(b / 1073741824).toFixed(1)} GB` : b >= 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);
  card.append(el("div", { class: "stats" },
    stat(s.files.toLocaleString(), "Stored files", "encrypted"),
    stat(mb(s.bytes), "Space used", "attachments"),
    s.disk ? stat(mb(s.disk.free_bytes), "Free on the server", `of ${mb(s.disk.total_bytes)}`, s.disk.free_bytes / s.disk.total_bytes < 0.1 ? "danger" : "ok") : null));
  if (s.by_type.length) card.append(el("div", { class: "table-wrap" }, el("table", { class: "compact-table" },
    el("thead", null, el("tr", null, el("th", null, "Type"), el("th", { class: "num" }, "Files"), el("th", { class: "num" }, "Space"))),
    el("tbody", null, ...s.by_type.map((t) => el("tr", { class: "no-click" }, el("td", null, t.type), el("td", { class: "num" }, String(t.files)), el("td", { class: "num" }, mb(t.bytes))))))));
  else card.append(el("p", { class: "muted" }, "No files stored yet."));
}

async function renderConfiguration(focusKey = null) {
  clear(viewRoot);
  const msg = el("div");
  let rules;
  const headActions = el("div", { class: "actions" },
    el("button", { class: "btn small secondary", type: "button", onclick: () => openConfigHistory() }, el("i", { class: "bi bi-clock-history" }), " History"),
    hasPerm("data.export") ? el("button", { class: "btn small secondary", type: "button", onclick: () => downloadXlsx("Workspace settings", [
      { key: "group", label: "Section" }, { key: "label", label: "Setting" }, { key: "value", label: "Current value", csv: (r) => cfgValueText(r.value) },
      { key: "default", label: "Default", csv: (r) => cfgValueText(r.default) }, { key: "is_default", label: "Changed", csv: (r) => (r.is_default ? "" : "Yes") },
      { key: "updated_at", label: "Last changed", csv: (r) => (r.updated_at ? fmtDate(r.updated_at) : "") }, { key: "updated_by", label: "Changed by" },
    ], rules || []) }, el("i", { class: "bi bi-download" }), " Export") : null);
  viewRoot.append(viewHeader("Configuration", headActions), msg);
  try { rules = await API.get("/api/config"); } catch (err) { notify(msg, err.message, "error"); return; }

  const known = new Set(CONFIG_CATEGORIES.flatMap((c) => c.groups));
  const present = new Set(rules.map((r) => r.group));
  const others = [...present].filter((g) => !known.has(g));
  const sections = [];
  const categories = [...CONFIG_CATEGORIES, ...(others.length ? [{ name: "Other", groups: others }] : [])].map((c) => {
    const list = c.groups.filter((g) => present.has(g)).map((g) => {
      const items = rules.filter((r) => r.group === g);
      return { key: g, name: g, icon: CONFIG_GROUP_ICONS[g] || "gear", items, desc: `${items.length} setting${items.length === 1 ? "" : "s"}` };
    });
    sections.push(...list);
    return { name: c.name, sections: list };
  }).filter((c) => c.sections.length);
  categories.push({ name: "Workflow", sections: CONFIG_WORKFLOW });
  sections.push(...CONFIG_WORKFLOW);
  categories.push({ name: "Custom fields", sections: CONFIG_EXTRA });
  sections.push(...CONFIG_EXTRA);
  if (hasPerm("system.technical", "system.config")) {
    const storage = [{ key: "@storage", name: "Storage", icon: "hdd", desc: "Space used by attachments", render: (c) => renderStorageCard(c) }];
    categories.push({ name: "Data", sections: storage });
    sections.push(...storage);
  }

  const byKey = Object.fromEntries(rules.map((r) => [r.key, r]));
  const saved = Object.fromEntries(rules.map((r) => [r.key, r.kind === "list" ? (r.value || []) : r.value]));
  const edits = {}; // key -> edited value (kept across section switches)
  const current = (key) => (key in edits ? edits[key] : saved[key]);
  const focusSection = focusKey && byKey[focusKey] ? byKey[focusKey].group : null;
  let active = sections.find((s) => s.key === (focusSection || state.configSection)) || sections[0];

  // ---------------------------------------------------------------- section picker (drop-down)
  const trigger = el("button", { class: "cfg-picker-btn", type: "button", "aria-haspopup": "listbox", "aria-expanded": "false" });
  const search = el("input", { type: "search", class: "cfg-search", placeholder: "Find a setting…", "aria-label": "Find a setting", autocomplete: "off" });
  const menuList = el("div", { class: "cfg-menu-list", role: "listbox" });
  const menu = el("div", { class: "cfg-menu hidden" }, el("div", { class: "cfg-menu-search" }, el("i", { class: "bi bi-search", "aria-hidden": "true" }), search), menuList);
  const picker = el("div", { class: "cfg-picker" }, trigger, menu);
  const prev = el("button", { class: "btn small secondary icon-only", type: "button", title: "Previous section", "aria-label": "Previous section" }, el("i", { class: "bi bi-chevron-left" }));
  const next = el("button", { class: "btn small secondary icon-only", type: "button", title: "Next section", "aria-label": "Next section" }, el("i", { class: "bi bi-chevron-right" }));
  const customisedCount = el("span", { class: "muted small cfg-custom-count" });
  const toolbar = el("div", { class: "cfg-toolbar" }, picker,
    el("div", { class: "cfg-stepper" }, prev, next), customisedCount);
  const panelHost = el("div", { class: "cfg-panel-host" });
  const saveBar = el("div", { class: "cfg-savebar hidden", role: "region", "aria-label": "Unsaved changes" });
  viewRoot.append(toolbar, panelHost, saveBar);

  const isChanged = (s) => (s.items || []).some((r) => !r.is_default);
  const dirtyIn = (s) => (s.items || []).filter((r) => r.key in edits).length;

  const paintTrigger = () => {
    clear(trigger);
    trigger.append(...[el("i", { class: `bi bi-${active.icon} cfg-ico`, "aria-hidden": "true" }),
      el("span", { class: "cfg-picker-text" }, el("strong", null, active.name), el("span", { class: "muted small" }, active.desc)),
      dirtyIn(active) ? el("span", { class: "cfg-dot dirty", title: "Unsaved changes" }) : null,
      el("i", { class: "bi bi-chevron-down cfg-caret", "aria-hidden": "true" })].filter(Boolean));
    const n = rules.filter((r) => !r.is_default).length;
    customisedCount.textContent = n ? `${n} changed` : "";
    customisedCount.title = n ? `${n} setting${n === 1 ? "" : "s"} changed from default` : "";
    const i = sections.indexOf(active);
    prev.disabled = i <= 0; next.disabled = i >= sections.length - 1;
  };

  const openMenu = (open) => {
    menu.classList.toggle("hidden", !open);
    trigger.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) { search.value = ""; paintMenu(); setTimeout(() => search.focus(), 20); }
  };
  const choose = (s, settingKey = null) => { openMenu(false); select(s, settingKey); };

  const paintMenu = () => {
    clear(menuList);
    const q = search.value.trim().toLowerCase();
    if (!q) {
      categories.forEach((c) => {
        menuList.append(el("div", { class: "cfg-menu-cat" }, c.name));
        c.sections.forEach((s) => menuList.append(el("button", { type: "button", role: "option", "aria-selected": s === active ? "true" : "false",
          class: `cfg-menu-item ${s === active ? "active" : ""}`, onclick: () => choose(s) },
        el("i", { class: `bi bi-${s.icon} cfg-ico`, "aria-hidden": "true" }),
        el("span", { class: "cfg-menu-text" }, s.name, el("span", { class: "muted small" }, s.desc)),
        dirtyIn(s) ? el("span", { class: "cfg-dot dirty", title: "Unsaved changes" }) : (isChanged(s) ? el("span", { class: "cfg-dot", title: "Changed from default" }) : null))));
      });
      return;
    }
    const hitsS = sections.filter((s) => s.name.toLowerCase().includes(q));
    const hitsR = rules.filter((r) => `${r.label} ${r.help || ""} ${r.key}`.toLowerCase().includes(q));
    if (!hitsS.length && !hitsR.length) { menuList.append(el("div", { class: "cfg-menu-empty muted" }, "No setting matches.")); return; }
    if (hitsS.length) {
      menuList.append(el("div", { class: "cfg-menu-cat" }, "Sections"));
      hitsS.forEach((s) => menuList.append(el("button", { type: "button", class: "cfg-menu-item", onclick: () => choose(s) },
        el("i", { class: `bi bi-${s.icon} cfg-ico`, "aria-hidden": "true" }), el("span", { class: "cfg-menu-text" }, s.name, el("span", { class: "muted small" }, s.desc)))));
    }
    if (hitsR.length) {
      menuList.append(el("div", { class: "cfg-menu-cat" }, `Settings (${hitsR.length})`));
      hitsR.slice(0, 40).forEach((r) => {
        const s = sections.find((x) => x.key === r.group);
        menuList.append(el("button", { type: "button", class: "cfg-menu-item", onclick: () => choose(s, r.key) },
          el("i", { class: `bi bi-${s.icon} cfg-ico`, "aria-hidden": "true" }),
          el("span", { class: "cfg-menu-text" }, r.label, el("span", { class: "muted small" }, r.group))));
      });
    }
  };

  trigger.addEventListener("click", () => openMenu(menu.classList.contains("hidden")));
  search.addEventListener("input", paintMenu);
  search.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { openMenu(false); trigger.focus(); }
    if (e.key === "Enter") { e.preventDefault(); menuList.querySelector(".cfg-menu-item")?.click(); }
    if (e.key === "ArrowDown") { e.preventDefault(); menuList.querySelector(".cfg-menu-item")?.focus(); }
  });
  menuList.addEventListener("keydown", (e) => {
    const items = [...menuList.querySelectorAll(".cfg-menu-item")];
    const i = items.indexOf(document.activeElement);
    if (e.key === "ArrowDown") { e.preventDefault(); items[Math.min(items.length - 1, i + 1)]?.focus(); }
    if (e.key === "ArrowUp") { e.preventDefault(); (i <= 0 ? search : items[i - 1]).focus(); }
    if (e.key === "Escape") { openMenu(false); trigger.focus(); }
  });
  const outside = (e) => {
    if (!document.body.contains(picker)) { document.removeEventListener("mousedown", outside); return; }
    if (!picker.contains(e.target)) openMenu(false);
  };
  document.addEventListener("mousedown", outside);
  prev.addEventListener("click", () => select(sections[sections.indexOf(active) - 1]));
  next.addEventListener("click", () => select(sections[sections.indexOf(active) + 1]));

  // ---------------------------------------------------------------- one setting row
  const control = (r, onChange) => {
    const v = current(r.key);
    const id = `cfg-${r.key}`;
    if (r.kind === "bool") {
      const box = el("input", { type: "checkbox", id, role: "switch" });
      box.checked = !!v;
      box.addEventListener("change", () => onChange(box.checked));
      return el("label", { class: "switch", title: r.label }, box, el("span", { class: "slider" }));
    }
    if (r.kind === "int") {
      const inp = el("input", { type: "number", id, class: "cfg-num", min: r.min ?? null, max: r.max ?? null, step: "1", value: v ?? "" });
      inp.addEventListener("input", () => onChange(inp.value === "" ? "" : Number(inp.value)));
      return inp;
    }
    if (r.options && r.options.length && r.kind === "text") {
      const sel = el("select", { id, class: "cfg-select" }, ...r.options.map((o) => el("option", { value: o, selected: o === v ? "1" : null }, o)));
      sel.addEventListener("change", () => onChange(sel.value));
      return sel;
    }
    if (r.kind === "roles" || cfgChoiceList(r)) {
      const wanted = new Set((v || []).map(String));
      const wrap = el("div", { class: "cfg-chips", role: "group", "aria-label": r.label });
      r.options.forEach((o) => {
        const b = el("input", { type: "checkbox", value: o });
        b.checked = wanted.has(o);
        b.addEventListener("change", () => onChange([...wrap.querySelectorAll("input:checked")].map((x) => x.value)));
        wrap.append(el("label", { class: "cfg-chip" }, b, el("span", null, o)));
      });
      return wrap;
    }
    if (r.kind === "list" || r.kind === "longtext") {
      const ta = el("textarea", { id, rows: r.kind === "list" ? "6" : "5", maxlength: "5000",
        placeholder: r.kind === "list" ? "One per line" : "" });
      ta.value = r.kind === "list" ? (Array.isArray(v) ? v.join("\n") : String(v || "")) : String(v ?? "");
      ta.addEventListener("input", () => onChange(r.kind === "list" ? ta.value.split("\n").map((x) => x.trim()).filter(Boolean) : ta.value));
      return ta;
    }
    const inp = el("input", { type: "text", id, maxlength: "200", value: v ?? "" });
    inp.addEventListener("input", () => onChange(inp.value));
    return inp;
  };

  // A small "more" menu for one setting: when it was changed, Reset to default, History.
  const rowMenu = (r, defText) => {
    const btn = el("button", { class: "cfg-more", type: "button", "aria-haspopup": "menu", "aria-expanded": "false", title: "More", "aria-label": `More for ${r.label}` },
      el("i", { class: "bi bi-three-dots", "aria-hidden": "true" }));
    const menu = el("div", { class: "cfg-more-menu hidden", role: "menu" });
    const close = () => { menu.classList.add("hidden"); btn.setAttribute("aria-expanded", "false"); document.removeEventListener("mousedown", away); };
    const away = (e) => { if (!menu.contains(e.target) && e.target !== btn && !btn.contains(e.target)) close(); };
    const item = (icon, label, fn, danger = false) => el("button", { class: `cfg-more-item ${danger ? "danger" : ""}`, type: "button", role: "menuitem", onclick: () => { close(); fn(); } },
      el("i", { class: `bi bi-${icon}`, "aria-hidden": "true" }), label);
    btn.addEventListener("click", () => {
      const open = menu.classList.contains("hidden");
      if (!open) { close(); return; }
      clear(menu);
      menu.append(el("div", { class: "cfg-more-head muted small" }, r.updated_at ? `Changed ${fmtDay(r.updated_at)}${r.updated_by ? ` by ${r.updated_by}` : ""}` : "Not changed yet",
        el("br"), `Default: ${defText.length > 60 ? `${defText.slice(0, 60)}…` : defText || "empty"}`));
      if (!r.is_default) menu.append(item("arrow-counterclockwise", "Reset to default", async () => {
        const ok = await confirmDialog({ title: "Reset to default?", text: `${r.label}: ${defText.slice(0, 200) || "empty"}`, confirmLabel: "Reset" });
        if (!ok.ok) return;
        try {
          await API.post(`/api/config/${r.key}/reset`); toast("Reset to default");
          try { setRegional(await API.get("/api/config/regional")); } catch { /* ignore */ }
          renderConfiguration(r.key);
        } catch (e) { toast(e.message, "error"); }
      }));
      menu.append(item("clock-history", "History", () => openConfigHistory(r.key, r.label)));
      menu.classList.remove("hidden"); btn.setAttribute("aria-expanded", "true");
      setTimeout(() => document.addEventListener("mousedown", away), 0);
    });
    menu.addEventListener("keydown", (e) => { if (e.key === "Escape") { close(); btn.focus(); } });
    return el("div", { class: "cfg-more-wrap" }, btn, menu);
  };

  const settingRow = (r, refresh) => {
    const err = el("div", { class: "field-error", role: "alert" });
    const defText = Array.isArray(r.default) ? (r.default.join(", ") || "none") : (r.kind === "bool" ? (r.default ? "On" : "Off") : String(r.default ?? ""));
    const mark = el("span", { class: "cfg-mark" });
    const paintMark = () => {
      mark.className = `cfg-mark ${r.key in edits ? "dirty" : (!r.is_default ? "changed" : "")}`;
      mark.title = r.key in edits ? "Unsaved" : (!r.is_default ? "Changed from default" : "");
    };
    let summary = null;
    const onChange = (val) => {
      err.textContent = "";
      if (cfgSame(val, saved[r.key])) delete edits[r.key]; else edits[r.key] = val;
      paintMark(); refresh(); if (summary) summary.textContent = cfgSummary(r, current(r.key));
    };
    paintMark();
    const info = r.help ? el("i", { class: "bi bi-info-circle cfg-info", title: r.help, tabindex: "0", "aria-label": r.help }) : null;
    const label = el("label", { class: "cfg-label", for: `cfg-${r.key}` }, mark, r.label, info);
    const more = rowMenu(r, defText);
    if ((r.kind === "list" && !cfgChoiceList(r)) || r.kind === "longtext") {
      summary = el("span", { class: "cfg-summary muted small" }, cfgSummary(r, current(r.key)));
      const det = el("details", { class: "cfg-row cfg-fold", "data-key": r.key, open: r.key === focusKey ? "1" : null },
        el("summary", null, el("div", { class: "cfg-text" }, label, summary), more, el("i", { class: "bi bi-chevron-down cfg-fold-caret", "aria-hidden": "true" })),
        el("div", { class: "cfg-fold-body" }, control(r, onChange), err));
      return { node: det, err };
    }
    const wide = r.kind === "roles" || cfgChoiceList(r);
    return { node: el("div", { class: `cfg-row ${wide ? "cfg-row-wide" : ""} ${r.kind === "bool" ? "cfg-row-bool" : ""}`, "data-key": r.key },
      el("div", { class: "cfg-text" }, label, err), el("div", { class: "cfg-control" }, control(r, onChange)), more), err };
  };

  // ---------------------------------------------------------------- the selected section
  let rowErrs = {};
  const reasonBox = el("input", { type: "text", class: "compact cfg-reason", maxlength: "500", placeholder: "Reason (optional)", "aria-label": "Reason for the change" });
  const paintSaveBar = () => {
    const keys = Object.keys(edits);
    saveBar.classList.toggle("hidden", !keys.length);
    clear(saveBar);
    if (!keys.length) return;
    const groups = [...new Set(keys.map((k) => byKey[k].group))];
    saveBar.append(el("i", { class: "bi bi-pencil-square", "aria-hidden": "true" }),
      el("span", { class: "cfg-savebar-text" }, `${keys.length} unsaved change${keys.length === 1 ? "" : "s"}`,
        el("span", { class: "muted small" }, ` in ${groups.join(", ")}`)),
      reasonBox,
      el("div", { class: "actions" },
        el("button", { class: "btn secondary small", type: "button", onclick: () => { Object.keys(edits).forEach((k) => delete edits[k]); reasonBox.value = ""; select(active); } }, "Discard"),
        el("button", { class: "btn small", type: "button", onclick: saveAll }, el("i", { class: "bi bi-check2" }), " Save changes")));
  };

  async function saveAll() {
    const values = {};
    for (const [k, v] of Object.entries(edits)) {
      const r = byKey[k];
      if (r.kind === "int") {
        if (v === "" || !Number.isFinite(v)) return problem(k, "Enter a whole number");
        if (r.min !== null && r.min !== undefined && v < r.min) return problem(k, `At least ${r.min}`);
        if (r.max !== null && r.max !== undefined && v > r.max) return problem(k, `At most ${r.max}`);
      }
      if (r.kind === "text" && !String(v).trim()) return problem(k, "This setting cannot be empty");
      values[k] = v;
    }
    try { await API.put("/api/config", { values, reason: reasonBox.value.trim() || null }); }
    catch (e) { toast(e.message, "error"); return; }
    toast(`${Object.keys(values).length} setting${Object.keys(values).length === 1 ? "" : "s"} saved`);
    try { setRegional(await API.get("/api/config/regional")); } catch { /* keeps the previous format */ }
    renderConfiguration();
  }
  function problem(key, text) {
    const s = sections.find((x) => x.key === byKey[key].group);
    if (s !== active) select(s, key);
    const e = rowErrs[key];
    if (e) e.textContent = text;
    const row = panelHost.querySelector(`[data-key="${key}"]`);
    if (row) { if (row.tagName === "DETAILS") row.open = true; row.scrollIntoView({ block: "center", behavior: "smooth" }); row.querySelector("input,textarea,select")?.focus(); }
    toast(`${byKey[key].label}: ${text}`, "error");
  }

  function select(s, settingKey = null) {
    if (!s) return;
    active = s;
    state.configSection = s.key;
    clear(panelHost);
    rowErrs = {};
    paintTrigger();
    if (!s.items) { s.render(panelHost); paintSaveBar(); return; }
    const card = el("section", { class: "card cfg-panel", "aria-label": s.name });
    panelHost.append(card);
    const refresh = () => { paintTrigger(); paintSaveBar(); };
    const order = { bool: 0, int: 1, text: 2, roles: 3, list: 4, longtext: 5 };
    const items = [...s.items].sort((a, b) => (order[cfgChoiceList(a) ? "roles" : a.kind] ?? 9) - (order[cfgChoiceList(b) ? "roles" : b.kind] ?? 9));
    const list = el("div", { class: "cfg-rows" });
    card.append(list);
    items.forEach((r) => { const { node, err } = settingRow(r, refresh); rowErrs[r.key] = err; list.append(node); });
    paintSaveBar();
    if (settingKey) {
      const row = card.querySelector(`[data-key="${settingKey}"]`);
      if (row) {
        if (row.tagName === "DETAILS") row.open = true;
        row.classList.add("cfg-flash");
        setTimeout(() => row.scrollIntoView({ block: "center", behavior: "smooth" }), 30);
        setTimeout(() => row.classList.remove("cfg-flash"), 2200);
      }
    }
  }

  select(active, focusKey);
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

async function renderCommittee(year = null, tab = state.committeeTab || "pack") {
  state.committeeTab = tab;
  const committeeTabs = () => tabBar([{ key: "pack", label: "Reporting pack" }, { key: "meetings", label: "Meetings & decisions" }], tab,
    (k) => renderCommittee(year, k));
  if (tab === "meetings") {
    clear(viewRoot);
    viewRoot.append(viewHeader("Audit Committee", null, { sub: "Meetings register, minutes and decisions on recommendations" }), committeeTabs());
    const b = el("div");
    viewRoot.append(b);
    renderCommitteeMeetings(b);
    return;
  }
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
  { sub: `Status of the Internal Audit Plan, reports and agreed actions · prepared ${fmtDate(s.generated_at)}` }), committeeTabs(), msg);

  const p = s.plan;
  const a = s.actions;
  const openTotal = Object.values(s.open_findings_by_rating).reduce((x, y) => x + y, 0);
  viewRoot.append(el("div", { class: "stats" },
    stat(`${p.completed_pct}%`, "Plan completed", p.plan_ref ? `${p.engagements} engagements in ${p.plan_ref}` : "no plan this year", p.completed_pct >= 75 ? "ok" : ""),
    stat(s.reports_issued.length, "Reports issued", Object.entries(s.ratings).map(([k, v]) => `${v} ${k}`).join(" · ") || "none yet"),
    stat(openTotal, "Open findings", `${s.open_findings_by_rating.High || 0} high risk`, (s.open_findings_by_rating.High || 0) ? "danger" : ""),
    stat(a.overdue, "Overdue actions", `${a.with_cae} with the CAE · ${a.for_committee || 0} for this Committee`, a.overdue ? "danger" : "ok")));
  viewRoot.append(el("div", { class: `callout ${p.committee_meeting_date ? "ok" : "warn"}` }, el("i", { class: "bi bi-patch-check" }),
    el("div", null, p.committee_meeting_date
      ? `The FY${p.fiscal_year} plan was approved by the Audit Committee on ${fmtDate(p.committee_meeting_date).split(",")[0]} (ref ${p.committee_reference}).`
      : `Audit Committee approval of the FY${p.fiscal_year} plan is not yet recorded (open the Assurance Plan to record it).`)));

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
  viewRoot.append(panel("Changes to the approved plan", dataTable(s.plan_changes || [], [
    { key: "date", label: "Date" },
    { key: "type", label: "Change", render: (c) => badge(c.type) },
    { key: "description", label: "What changed" },
    { key: "reason", label: "Reason" },
  ], { exportName: `plan-changes-FY${p.fiscal_year}.csv`, emptyText: "No changes since the plan was approved." })));
}

// ==================================================================== exit meeting (GIAS 15.1)

function exitMeetingCard(r, canWrite, refresh) {
  const held = !!r.exit_meeting_date;
  const card = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, "Exit meeting"),
    canWrite && r.status !== "Issued" ? el("button", { class: "btn small secondary", onclick: () => exitMeetingForm(r, refresh) }, el("i", { class: "bi bi-people" }), held ? " Edit" : " Record exit meeting") : null));
  if (!held) card.append(el("p", { class: "muted" }, "Hold the exit meeting with management to discuss the findings before the report is final."));
  else {
    card.append(el("dl", { class: "kv" }, el("dt", null, "Held on"), el("dd", null, fmtDate(r.exit_meeting_date).split(",")[0]),
      el("dt", null, "Attendees"), el("dd", null, r.exit_meeting_attendees || "-")));
    if (r.exit_meeting_notes) card.append(longBlock("What was agreed", r.exit_meeting_notes, ""));
  }
  return card;
}

// Record the exit meeting.
function exitMeetingForm(r, refresh) {
  return openForm({
    key: `exit:${r.id}`, title: "Exit meeting", width: 640,
    meta: { title: `Exit meeting ${r.report_ref}`, record_type: "audit_report", record_id: r.id },
    fields: [
      { name: "meeting_date", label: "Date held", type: "date", required: true, notFuture: true },
      { name: "attendees", label: "Attendees (names and roles)", type: "textarea", rows: 2, required: true, minLength: 3, maxLength: 5000, full: true },
      { name: "notes", label: "What was agreed", type: "textarea", rows: 4, maxLength: 20000, full: true },
    ],
    initial: { meeting_date: r.exit_meeting_date, attendees: r.exit_meeting_attendees || "", notes: r.exit_meeting_notes || "" },
    submitLabel: "Save",
    onSubmit: (v) => API.put(`/api/reports/${r.id}/exit-meeting`, { ...v, meeting_date: `${v.meeting_date}T00:00:00` }),
    onDone: () => { toast("Exit meeting recorded"); refresh(); },
  });
}

// ==================================================================== review notes (supervision, GIAS 12.3)

async function renderReviewNotesTab(panelEl, audit) {
  const card = el("div", { class: "card" });
  panelEl.append(card);
  const refresh = () => { clear(panelEl); renderReviewNotesTab(panelEl, audit); };
  const canRaise = audit.status !== "Closed" && hasPerm("review.notes") && (audit.created_by !== state.user.id || isAdmin() || ["Manager", "CAE"].includes(state.user.review_level));
  card.append(el("div", { class: "card-head" }, el("h3", null, "Review notes"),
    canRaise ? el("button", { class: "btn small", onclick: () => raiseNoteForm(audit, refresh) }, el("i", { class: "bi bi-chat-square-text" }), " Raise review note") : null),
  el("p", { class: "muted small" }, "The reviewer raises a note on the audit, a working paper, a test or a finding; the preparer answers; the reviewer clears it. All notes must be cleared before the audit can close."));
  let notes;
  try { notes = await API.get(`/api/audits/${audit.id}/review-notes`); } catch (err) { card.append(el("div", { class: "muted" }, err.message)); return; }
  if (!notes.length) { card.append(el("div", { class: "empty" }, "No review notes.")); return; }
  const open = notes.filter((n) => n.status !== "Cleared").length;
  card.append(el("p", null, badge(open ? `${open} open` : "All cleared")));
  notes.forEach((n) => {
    const item = el("div", { class: `note-item ${n.status.toLowerCase()}` },
      el("div", { class: "note-head" }, badge(n.status), el("strong", null, ` ${n.target_label}`),
        el("span", { class: "muted small" }, ` · ${n.raised_by_name || "-"}, ${fmtDate(n.raised_at)}`)),
      el("div", { class: "note-body" }, n.note),
      n.response ? el("div", { class: "note-response" }, el("span", { class: "muted small" }, `Answer by ${n.responded_by_name || "-"}, ${fmtDate(n.responded_at)}`),
        el("div", null, n.response)) : null,
      n.cleared_at ? el("div", { class: "muted small" }, `Cleared by ${n.cleared_by_name}, ${fmtDate(n.cleared_at)}`) : null,
      el("div", { class: "actions" },
        n.can_respond ? el("button", { class: "btn small secondary", onclick: () => answerNoteForm(n, audit, refresh) }, n.response ? "Edit answer" : "Answer") : null,
        n.can_clear ? el("button", { class: "btn small", onclick: async () => {
          try { await API.post(`/api/review-notes/${n.id}/clear`); toast("Note cleared"); refresh(); } catch (err) { toast(err.message, "error"); }
        } }, el("i", { class: "bi bi-check2" }), " Clear") : null));
    card.append(item);
  });
}

// Answer a review note.
function answerNoteForm(n, audit, refresh) {
  return openForm({
    key: `note:respond:${n.id}`, title: "Answer review note", width: 560, draftable: true,
    meta: { title: `Answer review note #${n.id}`, record_type: "audit", record_id: audit.id },
    fields: [{ name: "response", label: "Your answer", type: "textarea", rows: 4, required: true, minLength: 3, maxLength: 5000, full: true }],
    initial: { response: n.response || "" },
    submitLabel: "Send answer",
    onSubmit: (v) => API.post(`/api/review-notes/${n.id}/respond`, v),
    onDone: () => { toast("Answer sent"); refresh(); },
  });
}

async function raiseNoteForm(audit, onDone) {
  const opts = await safeGet(`/api/audits/${audit.id}/xref-options`, { tests: [], findings: [], working_papers: [] });
  const targets = [{ value: "audit:", label: "The audit as a whole" },
    ...opts.working_papers.map((p) => ({ value: `working_paper:${p.id}`, label: `Working paper: ${p.label}` })),
    ...opts.tests.map((t) => ({ value: `control_test:${t.id}`, label: `Test: ${t.label}` })),
    ...opts.findings.map((f) => ({ value: `finding:${f.id}`, label: `Finding: ${f.label}` }))];
  openForm({
    key: `note:new:${audit.id}`, title: "Raise review note", width: 640,
    meta: { title: `Review note on ${audit.title}`, record_type: "audit", record_id: audit.id },
    fields: [
      { name: "target", label: "About", type: "select", required: true, options: targets, full: true },
      { name: "note", label: "Note to the preparer", type: "textarea", rows: 4, required: true, minLength: 3, maxLength: 5000, full: true },
    ],
    initial: { target: "audit:" },
    submitLabel: "Raise note",
    onSubmit: (v) => {
      const [type, id] = String(v.target).split(":");
      return API.post(`/api/audits/${audit.id}/review-notes`, { target_type: type, target_id: id ? Number(id) : null, note: v.note });
    },
    onDone: () => { toast("Review note raised"); onDone(); },
  });
}

// Working paper cross-reference + sign-off dialogs.
async function workPaperXrefForm(p, auditId, onDone) {
  const opts = await safeGet(`/api/audits/${auditId}/xref-options`, { tests: [], findings: [] });
  openForm({
    key: `wpref:${p.id}`, title: `Cross-reference · ${p.title}`, width: 560, draftable: false,
    fields: [
      { name: "wp_ref", label: "Working-paper reference", maxLength: 30, singleLine: true, pattern: "^[A-Za-z0-9 ._/\\-]*$",
        patternMessage: "Letters, numbers, spaces and . _ / - only", help: "e.g. A.1, B.2.3 - the index used in the file" },
      { name: "test_id", label: "Supports test", type: "select", emptyLabel: "- none -", options: opts.tests.map((t) => ({ value: t.id, label: t.label })) },
      { name: "finding_id", label: "Supports finding", type: "select", emptyLabel: "- none -", options: opts.findings.map((f) => ({ value: f.id, label: f.label })) },
    ],
    initial: { wp_ref: p.wp_ref || "", test_id: p.test_id, finding_id: p.finding_id },
    submitLabel: "Save",
    onSubmit: (v) => API.patch(`/api/working-papers/${p.id}/xref`, { wp_ref: v.wp_ref || null, test_id: v.test_id ?? null, finding_id: v.finding_id ?? null }),
    onDone: () => { toast("Cross-reference saved"); onDone(); },
  });
}
