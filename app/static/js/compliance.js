// Follow-up returns (MoF / IAA), Audit Committee register, report distribution, professional practice
// (declarations, CPD, charter, external assessment) and automation rules.

const IMPL_STATUSES = ["Not Implemented", "Partially Implemented", "Fully Implemented", "Withdrawn"];
const ListCache = { at: 0, data: null };
async function loadLists(force = false) {
  if (!force && ListCache.data && Date.now() - ListCache.at < 15000) return ListCache.data;
  ListCache.data = await API.get("/api/config/lists");
  ListCache.at = Date.now();
  return ListCache.data;
}
const isoDay = (d) => (d ? String(d).slice(0, 10) : "");
const dayOnly = (d) => (d ? fmtDate(d).split(",")[0] : "-");

// ------------------------------------------------------------------ Remediation register (sources, statuses, custom fields)
async function prepareCapa(m) {
  const [lists, defs] = await Promise.all([loadLists(), safeGet("/api/custom-fields?module=capa", [])]);
  m.filters = [
    { param: "status", label: "Status", options: ["Open", "In Progress", "Review", "Closed"] },
    { param: "implementation_status", label: "Implementation", options: IMPL_STATUSES },
    { param: "source_body", label: "Source", options: lists.recommendation_sources },
    { param: "severity", label: "Severity", options: SEVERITIES },
  ];
  m.columns = [
    { key: "capa_ref", label: "Ref", ref: true },
    { key: "title", label: "Title" },
    { key: "source_body", label: "Source" },
    { key: "severity", label: "Severity", badge: true },
    { key: "implementation_status", label: "Implementation", badge: true },
    { key: "status", label: "Status", badge: true },
    { key: "due_date", label: "Due", date: true },
  ];
  m.fields = [
    { key: "title", label: "Recommendation / action", required: true },
    { key: "source_body", label: "Source of the recommendation", type: "select", options: lists.recommendation_sources,
      help: "Internal Audit, the Auditor-General's management letter, PAC or Parliament decisions (Act 921 s.88)" },
    { key: "source_reference", label: "Source reference", help: "e.g. management letter or PAC report reference" },
    { key: "description", label: "Finding / observation", type: "textarea" },
    { key: "root_cause", label: "Root cause", type: "textarea" },
    { key: "corrective_action", label: "Recommendation and agreed action", type: "textarea" },
    { key: "preventive_action", label: "Preventive action", type: "textarea" },
    { key: "effectiveness_check", label: "Effectiveness check", type: "textarea" },
    { key: "severity", label: "Severity", type: "select", options: SEVERITIES },
    { key: "timeframe", label: "Implementation timeframe", type: "select", options: lists.action_timeframes },
    { key: "owner_email", label: "Responsible officer (e-mail)", type: "email" },
    { key: "due_date", label: "Due date", type: "date", notPast: true },
    ...(isStaff() ? [{ key: "followup_comment", label: "Internal Audit follow-up comment", type: "textarea",
      help: "Shown in the quarterly follow-up report" },
    { key: "external_closure_ref", label: "Closure reference from the external body",
      help: "Recommendations from the Auditor-General, PAC or Parliament are closed by that body" }] : []),
    ...customFieldDefs(defs),
  ];
}

// Extra follow-up controls on an action's detail page.
function capaFollowupExtras(card, c, refresh) {
  const mine = state.user.email && c.owner_email && state.user.email.toLowerCase() === c.owner_email.toLowerCase();
  const open = ["Open", "In Progress"].includes(c.status);
  card.append(el("dl", { class: "kv two-col fu-extra" },
    el("dt", null, "Implementation status"), el("dd", null, badge(c.implementation_status || "Not Implemented")),
    el("dt", null, "Timeframe"), el("dd", null, c.timeframe || el("span", { class: "muted" }, "Not set")),
    c.external_closure_ref ? el("dt", null, "External closure ref") : null,
    c.external_closure_ref ? el("dd", null, c.external_closure_ref) : null));
  if (c.progress_note) card.append(longBlock("Latest progress update", c.progress_note, ""));
  if (c.followup_comment) card.append(longBlock("Internal Audit follow-up comment", c.followup_comment, ""));
  if (c.withdrawal_reason) {
    card.append(el("div", { class: "callout warn" }, el("i", { class: "bi bi-x-octagon" }),
      el("div", null, el("strong", null, c.implementation_status === "Withdrawn" ? "Withdrawn by the Audit Committee. " : "Withdrawal proposed to the Audit Committee. "),
        c.withdrawal_reason)));
  }
  const btns = el("div", { class: "actions" });
  if (open && (isStaff() || mine)) {
    btns.append(el("button", { class: "btn small secondary", onclick: () => openForm({
      title: `Progress update - ${c.capa_ref}`, key: `capa:${c.id}:progress`, width: 640,
      fields: [{ name: "status", label: "Status now", type: "select", required: true, options: ["Partially Implemented", "Not Implemented"] },
        { name: "note", label: "What has been done so far", type: "textarea", rows: 4, required: true, minLength: 10, maxLength: 10000 }],
      initial: { status: "Partially Implemented" }, submitLabel: "Save progress",
      onSubmit: (v) => API.post(`/api/capa/${c.id}/progress`, v), onDone: () => { toast("Progress recorded"); refresh(); },
    }) }, el("i", { class: "bi bi-graph-up" }), " Progress update"));
  }
  if (c.status !== "Closed" && !c.withdrawal_proposed_at && hasPerm("followup.manage")) {
    btns.append(el("button", { class: "btn small secondary", onclick: () => openForm({
      title: `Propose withdrawal - ${c.capa_ref}`, key: `capa:${c.id}:withdraw`, width: 640,
      intro: "Recommendations that are no longer relevant or feasible are withdrawn by the Audit Committee (MoF follow-up instructions s.6.1(8)).",
      fields: [{ name: "reason", label: "Why it is no longer relevant or feasible", type: "textarea", rows: 4, required: true, minLength: 20, maxLength: 5000 }],
      submitLabel: "Send to the Audit Committee",
      onSubmit: (v) => API.post(`/api/capa/${c.id}/propose-withdrawal`, v), onDone: () => { toast("Sent to the Audit Committee for decision"); refresh(); },
    }) }, el("i", { class: "bi bi-x-octagon" }), " Propose withdrawal"));
  }
  if (btns.childNodes.length) card.append(btns);
}

// ------------------------------------------------------------------ Follow-up returns (quarterly report, annual statement)
async function renderFollowupReports(body) {
  clear(body);
  const now = new Date();
  const st = { kind: "quarterly", year: now.getFullYear(), quarter: Math.floor(now.getMonth() / 3) + 1 };
  const out = el("div");
  const kindSel = el("select", { class: "compact" }, el("option", { value: "quarterly" }, "Quarterly follow-up report"),
    el("option", { value: "annual" }, "Annual statement (Act 921 s.88)"));
  const yearSel = el("select", { class: "compact" }, ...[0, 1, 2, 3].map((d) => el("option", { value: st.year - d }, String(st.year - d))));
  const qSel = el("select", { class: "compact" }, ...[1, 2, 3, 4].map((q) => el("option", { value: q, selected: q === st.quarter ? "1" : null }, `Q${q}`)));
  const go = () => { st.kind = kindSel.value; st.year = Number(yearSel.value); st.quarter = Number(qSel.value); qSel.hidden = st.kind !== "quarterly"; paint(); };
  [kindSel, yearSel, qSel].forEach((s) => s.addEventListener("change", go));
  body.append(el("div", { class: "card" },
    el("div", { class: "card-head" }, el("h3", null, el("i", { class: "bi bi-file-earmark-bar-graph" }), " Statutory follow-up returns"),
      el("div", { class: "actions" }, kindSel, yearSel, qSel)),
    el("p", { class: "muted small" }, "Quarterly report on the implementation of recommendations to the Audit Committee and the Internal Audit Agency (Act 921 s.83(5)(e)), and the annual statement on implementation status (Act 921 s.88(1)(b)). Recipients and due dates are set under Configuration > Follow-up & reporting."),
    out));
  const reg = el("div");
  body.append(reg);

  async function paint() {
    clear(out);
    const qs = `year=${st.year}${st.kind === "quarterly" ? `&quarter=${st.quarter}` : ""}`;
    let d;
    try { d = await API.get(`/api/follow-up/${st.kind}?${qs}`); } catch (err) { out.append(el("div", { class: "msg error" }, err.message)); return; }
    const s = d.summary;
    out.append(el("div", { class: "stats" },
      ...IMPL_STATUSES.map((k) => stat(s.by_status[k] || 0, k, "", k === "Not Implemented" && s.by_status[k] ? "danger" : (k === "Fully Implemented" ? "ok" : ""))),
      stat(s.overdue, "Overdue", "past the agreed date", s.overdue ? "danger" : "ok"),
      stat(s.implementation_rate == null ? "-" : `${s.implementation_rate}%`, "Implementation rate", "fully implemented, excl. withdrawn")));
    out.append(el("div", { class: "actions", style: "margin:8px 0" },
      el("span", { class: "muted small" }, `${d.period_label} · to ${d.recipients.join(", ")}${d.due_date ? ` · due ${dayOnly(d.due_date)}` : ""}`),
      el("a", { class: "btn small secondary", href: `/api/follow-up/${st.kind}.docx?${qs}` }, el("i", { class: "bi bi-file-earmark-word" }), " Word"),
      el("a", { class: "btn small secondary", href: `/api/follow-up/${st.kind}.xlsx?${qs}` }, el("i", { class: "bi bi-file-earmark-excel" }), " Excel"),
      hasPerm("followup.report") ? el("button", { class: "btn small", onclick: () => submitDialog(d) }, el("i", { class: "bi bi-send-check" }), " Record submission") : null));
    out.append(dataTable(d.rows, [
      { key: "ref", label: "Ref" }, { key: "source", label: "Source" }, { key: "finding", label: "Finding" },
      { key: "recommendation", label: "Recommendation" }, { key: "responsible_officer", label: "Responsible officer" },
      { key: "due_date", label: "Due" }, { key: "status", label: "Status", render: (r) => badge(r.status) },
      { key: "iau_comment", label: "IAU comment" }, { key: "days_overdue", label: "Days overdue" },
    ], { onRow: (r) => openRecord("capa", r.id), pageSize: 15, emptyText: "No recommendations in this period." }));
    paintRegister();
  }

  function submitDialog(d) {
    openForm({
      title: `Record submission - ${d.period_label}`, key: `fu-sub:${d.kind}:${d.year}:${d.quarter || 0}`, width: 620, draftable: false,
      intro: "A frozen copy of the report as it stands now is kept with the submission.",
      fields: [
        { name: "recipients", label: "Submitted to", type: "checklist", options: d.recipients, required: true },
        { name: "submitted_at", label: "Date submitted", type: "date", required: true },
        { name: "reference", label: "Letter / e-mail reference", maxLength: 120, singleLine: true },
      ],
      initial: { recipients: d.recipients, submitted_at: isoDay(new Date().toISOString()) },
      submitLabel: "Record submission",
      onSubmit: (v) => API.post("/api/follow-up/submissions", { kind: d.kind, year: d.year, quarter: d.quarter, recipients: v.recipients,
        submitted_at: `${v.submitted_at}T12:00:00`, reference: v.reference || "" }),
      onDone: () => { toast("Submission recorded"); paintRegister(); },
    });
  }

  async function paintRegister() {
    clear(reg);
    const rows = await safeGet("/api/follow-up/submissions", []);
    reg.append(el("div", { class: "card" }, el("h3", null, "Register of follow-up reports submitted"),
      dataTable(rows, [
        { key: "period_label", label: "Period" }, { key: "kind", label: "Type", render: (r) => (r.kind === "annual" ? "Annual statement" : "Quarterly report") },
        { key: "recipients", label: "Submitted to", render: (r) => r.recipients.join(", ") },
        { key: "submitted_at", label: "Date", render: (r) => dayOnly(r.submitted_at) }, { key: "reference", label: "Reference" },
        { key: "counts", label: "Fully / Partially / Not", render: (r) => {
          const b = (r.counts && r.counts.by_status) || {};
          return `${b["Fully Implemented"] || 0} / ${b["Partially Implemented"] || 0} / ${b["Not Implemented"] || 0}`;
        } },
        { key: "id", label: "Copy", render: (r) => el("a", { href: `/api/follow-up/submissions/${r.id}/export.docx`, onclick: (e) => e.stopPropagation() }, "Word") },
      ], { emptyText: "Nothing recorded yet.", pageSize: 10 })));
  }
  paint();
}

// ------------------------------------------------------------------ Audit report: response deadline + distribution
async function reportComplianceCards(panel, r) {
  if (r.response_due_at) {
    const late = !r.response_received_at && new Date(`${r.response_due_at}Z`) < new Date();
    panel.append(el("div", { class: `callout ${r.response_received_at ? "ok" : (late ? "danger" : "")}` }, el("i", { class: "bi bi-hourglass-split" }),
      el("div", null, r.response_received_at
        ? `Management responded on ${dayOnly(r.response_received_at)} (due ${dayOnly(r.response_due_at)}).`
        : `Management response due by ${dayOnly(r.response_due_at)} (L.I. 1994 reg. 43(2))${late ? " - overdue." : "."}`)));
  }
  if (r.status !== "Issued") return;
  const card = el("div", { class: "card" });
  panel.append(card);
  const paint = async () => {
    clear(card);
    let d;
    try { d = await API.get(`/api/reports/${r.id}/distribution`); } catch { return; }
    card.append(el("div", { class: "card-head" }, el("h3", null, el("i", { class: "bi bi-envelope-check" }), " Distribution of the issued report"),
      isStaff() ? el("button", { class: "btn small", onclick: () => openForm({
        title: "Record a copy sent", key: `dist:${r.id}`, width: 600, draftable: false,
        fields: [
          { name: "recipient", label: "Recipient", type: "select", required: true, options: [...new Set([...d.missing, ...d.required])] },
          { name: "channel", label: "How", type: "select", required: true, options: d.channels },
          { name: "sent_at", label: "Date sent", type: "date", required: true },
          { name: "reference", label: "Letter / e-mail reference", maxLength: 120, singleLine: true },
        ],
        initial: { recipient: d.missing[0] || d.required[0], channel: "Letter", sent_at: isoDay(new Date().toISOString()) },
        submitLabel: "Record",
        onSubmit: (v) => API.post(`/api/reports/${r.id}/distribution`, { ...v, sent_at: `${v.sent_at}T12:00:00`, reference: v.reference || "" }),
        onDone: () => { toast("Copy recorded"); paint(); },
      }) }, el("i", { class: "bi bi-plus-lg" }), " Record copy sent") : null));
    if (d.missing.length) {
      card.append(el("div", { class: "callout warn" }, el("i", { class: "bi bi-exclamation-triangle" }),
        el("div", null, el("strong", null, "Still to receive a copy: "), d.missing.join(", "),
          el("div", { class: "muted small" }, "Internal Audit Agency Act, 2003 (Act 658) s.16. The list is set under Configuration > Follow-up & reporting."))));
    }
    card.append(dataTable(d.sent, [
      { key: "recipient", label: "Recipient" }, { key: "channel", label: "How" },
      { key: "sent_at", label: "Date", render: (x) => dayOnly(x.sent_at) }, { key: "reference", label: "Reference" },
    ], { emptyText: "No copies recorded yet.", pageSize: 10 }));
  };
  paint();
}

// ------------------------------------------------------------------ Audit Committee meetings register
async function renderCommitteeMeetings(body) {
  clear(body);
  const canRecord = hasPerm("committee.record");
  let data;
  try { data = await API.get("/api/committee/meetings"); } catch (err) { body.append(el("div", { class: "msg error" }, err.message)); return; }
  const queue = await safeGet("/api/committee/for-decision", []);
  body.append(el("div", { class: "card" },
    el("div", { class: "card-head" }, el("h3", null, el("i", { class: "bi bi-people" }), " Meetings, minutes and decisions"),
      canRecord ? el("button", { class: "btn small", onclick: () => openForm({
        title: "Schedule a Committee meeting", key: "acm:new", width: 640, draftable: false,
        fields: [
          { name: "meeting_date", label: "Date and time", type: "datetime-local", required: true },
          { name: "meeting_type", label: "Type", type: "select", required: true, options: data.types },
          { name: "venue", label: "Venue", maxLength: 160, singleLine: true },
          { name: "agenda", label: "Agenda", type: "textarea", rows: 5, maxLength: 20000 },
        ],
        initial: { meeting_type: "Ordinary", agenda: "1. Opening and apologies\n2. Minutes of the previous meeting\n3. Quarterly follow-up report on audit recommendations\n4. Audit reports issued\n5. Internal audit plan progress\n6. Any other business" },
        submitLabel: "Create",
        onSubmit: (v) => API.post("/api/committee/meetings", v),
        onDone: (m) => { toast("Meeting created"); openMeeting(m.id, () => renderCommitteeMeetings(body)); },
      }) }, el("i", { class: "bi bi-plus-lg" }), " New meeting") : null),
    el("p", { class: "muted small" }, "PFM Act 2016 (Act 921) ss.86-88: the Audit Committee considers the quarterly follow-up report at each meeting and decides on the closure, withdrawal or extension of recommendations."),
    dataTable(data.items, [
      { key: "meeting_ref", label: "Ref" }, { key: "meeting_date", label: "Date", render: (m) => dayOnly(m.meeting_date) },
      { key: "meeting_type", label: "Type" }, { key: "status", label: "Status", render: (m) => badge(m.status) },
      { key: "decisions_count", label: "Decisions" },
      { key: "followup_report_considered", label: "Follow-up report", render: (m) => (m.followup_report_considered ? "Considered" : "-") },
    ], { onRow: (m) => openMeeting(m.id, () => renderCommitteeMeetings(body)), emptyText: "No meetings recorded yet.", pageSize: 10 })));
  body.append(el("div", { class: "card" }, el("h3", null, `Recommendations for the Committee's decision (${queue.length})`),
    dataTable(queue, [
      { key: "capa_ref", label: "Ref" }, { key: "title", label: "Recommendation" }, { key: "source_body", label: "Source" },
      { key: "implementation_status", label: "Status", render: (q) => badge(q.implementation_status) },
      { key: "reasons", label: "For decision", render: (q) => q.reasons.join("; ") },
    ], { onRow: (q) => openRecord("capa", q.id), emptyText: "Nothing waiting for the Committee.", pageSize: 10 })));
}

async function openMeeting(id, back) {
  let m;
  try { m = await API.get(`/api/committee/meetings/${id}`); } catch (err) { toast(err.message, "error"); return; }
  const canRecord = hasPerm("committee.record");
  const locked = m.status === "Minutes approved";
  const reopen = () => { dlg.close(); openMeeting(id, back); back(); };
  const body = el("div", null,
    el("div", { class: "view-meta" }, el("span", { class: "ref" }, m.meeting_ref), badge(m.status),
      el("span", { class: "muted" }, `${fmtDate(m.meeting_date)} · ${m.meeting_type} · ${m.venue || "venue not set"}`)),
    longBlock("Agenda", m.agenda, "-"), longBlock("Present", m.attendees, "Not recorded"), longBlock("Apologies", m.apologies, "-"),
    el("p", { class: "small" }, `Quorum: ${m.quorum ? "Yes" : "No"} · Quarterly follow-up report considered: ${m.followup_report_considered ? "Yes" : "No"}`),
    longBlock("Minutes", m.minutes, "Not recorded"),
    el("h4", null, "Decisions"),
    dataTable(m.decisions, [
      { key: "subject", label: "Subject", render: (d) => d.subject || "Other matter" }, { key: "decision", label: "Decision", render: (d) => badge(d.decision) },
      { key: "new_due_date", label: "New due date", render: (d) => (d.new_due_date ? dayOnly(d.new_due_date) : "-") },
      { key: "reference", label: "Reference" }, { key: "notes", label: "Notes" },
    ], { emptyText: "No decisions recorded.", pageSize: 20 }));
  const actions = [];
  if (canRecord && !locked) {
    actions.push(el("button", { class: "btn secondary", onclick: () => openForm({
      title: `Record proceedings - ${m.meeting_ref}`, key: `acm:${id}:edit`, width: 820,
      fields: [
        { name: "status", label: "Status", type: "select", required: true, options: ["Scheduled", "Held", "Cancelled"] },
        { name: "meeting_date", label: "Date and time", type: "datetime-local", required: true },
        { name: "venue", label: "Venue", maxLength: 160, singleLine: true },
        { name: "attendees", label: "Present", type: "textarea", rows: 3 },
        { name: "apologies", label: "Apologies", type: "textarea", rows: 2 },
        { name: "quorum", label: "Quorum formed", type: "checkbox" },
        { name: "followup_report_considered", label: "Quarterly follow-up report considered", type: "checkbox" },
        { name: "agenda", label: "Agenda", type: "textarea", rows: 4, full: true },
        { name: "minutes", label: "Minutes", type: "textarea", rows: 10, full: true, maxLength: 100000 },
      ],
      initial: { ...m, meeting_date: String(m.meeting_date).slice(0, 16) },
      submitLabel: "Save",
      onSubmit: (v) => API.patch(`/api/committee/meetings/${id}`, v),
      onDone: () => { toast("Meeting saved"); reopen(); },
    }) }, el("i", { class: "bi bi-pencil" }), " Record proceedings"));
  }
  if (canRecord && m.status === "Held") {
    actions.push(el("button", { class: "btn secondary", onclick: async () => {
      const queue = await safeGet("/api/committee/for-decision", []);
      const all = await safeGet("/api/capa?status=Open", { items: [] });
      const inprog = await safeGet("/api/capa?status=In Progress", { items: [] });
      const options = [...queue.map((q) => ({ value: q.id, label: `${q.capa_ref} ${q.title} [${q.reasons.join("; ")}]` })),
        ...[...(all.items || []), ...(inprog.items || [])].filter((c) => !queue.some((q) => q.id === c.id)).map((c) => ({ value: c.id, label: `${c.capa_ref} ${c.title}` }))];
      openForm({
        title: "Record a Committee decision", key: `acm:${id}:decision`, width: 760, draftable: false,
        fields: [
          { name: "subject_id", label: "Recommendation (leave empty for another matter)", type: "select", options, emptyLabel: "- other matter -", full: true },
          { name: "decision", label: "Decision", type: "select", required: true, options: ["Close", "Withdraw", "Extend deadline", "Escalate to management", "Noted"] },
          { name: "new_due_date", label: "New due date (extensions)", type: "date" },
          { name: "reference", label: "Minute / external closure reference", maxLength: 120, singleLine: true,
            help: "For recommendations from the Auditor-General, PAC or Parliament give that body's closure reference" },
          { name: "notes", label: "Notes", type: "textarea", rows: 3, full: true },
        ],
        initial: { decision: "Noted" },
        submitLabel: "Record decision",
        onSubmit: (v) => API.post(`/api/committee/meetings/${id}/decisions`, {
          subject_type: v.subject_id ? "capa" : "other", subject_id: v.subject_id ? Number(v.subject_id) : null, decision: v.decision,
          new_due_date: v.new_due_date ? `${v.new_due_date}T00:00:00` : null, reference: v.reference || "", notes: v.notes || "" }),
        onDone: () => { toast("Decision recorded"); reopen(); },
      });
    } }, el("i", { class: "bi bi-hammer" }), " Record decision"));
    actions.push(el("button", { class: "btn", onclick: async () => {
      try { await API.post(`/api/committee/meetings/${id}/approve-minutes`); toast("Minutes approved and locked"); reopen(); }
      catch (err) { toast(err.message, "error"); }
    } }, el("i", { class: "bi bi-lock" }), " Approve minutes"));
  }
  actions.push(el("a", { class: "btn secondary", href: `/api/committee/meetings/${id}/minutes.docx` }, el("i", { class: "bi bi-file-earmark-word" }), " Minutes (Word)"));
  const dlg = modal({ title: `Audit Committee meeting ${m.meeting_ref}`, body, width: 900,
    footer: el("div", { class: "form-foot-wrap" }, el("button", { class: "btn secondary", onclick: () => dlg.close() }, "Close"), el("div", { class: "actions" }, ...actions)) });
}

// ------------------------------------------------------------------ Engagement declarations (audit page)
async function renderDeclarationCard(slot, audit) {
  const s = await safeGet(`/api/proficiency/audits/${audit.id}/status`, null);
  if (!s) return;
  const card = el("div", { class: "card" }, el("div", { class: "card-head" },
    el("h3", null, el("i", { class: "bi bi-person-check" }), " Independence declarations"),
    !s.mine || s.mine.review_status === "Reassigned" ? el("button", { class: "btn small", onclick: () => declarationForm("engagement", audit, () => { clear(slot); renderDeclarationCard(slot, audit); }) },
      el("i", { class: "bi bi-pen" }), " Declare for this engagement") : null));
  if (s.blockers.length && audit.status === "Planned") {
    card.append(el("div", { class: `callout ${s.required ? "warn" : ""}` }, el("i", { class: "bi bi-shield-exclamation" }),
      el("div", null, el("strong", null, s.required ? "Before fieldwork can start: " : "Outstanding: "), el("ul", null, ...s.blockers.map((b) => el("li", null, b))))));
  }
  card.append(dataTable(s.declarations, [
    { key: "user", label: "Auditor" }, { key: "signed_at", label: "Signed", render: (d) => dayOnly(d.signed_at) },
    { key: "has_conflict", label: "Conflict declared", render: (d) => (d.has_conflict ? d.conflict_details : "None") },
    { key: "review_status", label: "Review", render: (d) => badge(d.review_status) },
  ], { emptyText: "No declarations yet.", pageSize: 10 }));
  slot.append(card);
}

async function declarationForm(kind, audit, done) {
  const t = await API.get("/api/proficiency/declarations/texts");
  openForm({
    title: kind === "annual" ? `Annual declaration ${new Date().getFullYear()}` : `Declaration - ${audit.title}`,
    key: `decl:${kind}:${audit ? audit.id : "y"}`, width: 720, draftable: false,
    intro: kind === "annual" ? t.annual : t.engagement,
    fields: [
      { name: "independence_confirmed", label: "I confirm my independence and objectivity as stated", type: "checkbox" },
      { name: "ethics_confirmed", label: "I will comply with the Code of Ethics and the Standards", type: "checkbox" },
      { name: "confidentiality_confirmed", label: "I will keep information confidential (Act 658 s.20)", type: "checkbox" },
      { name: "has_conflict", label: "I have a relationship, interest or circumstance to disclose", type: "checkbox" },
      { name: "conflict_details", label: "Details of the conflict or impairment", type: "textarea", rows: 3, full: true },
    ],
    initial: {},
    validate: (v) => (v.has_conflict && (v.conflict_details || "").trim().length < 10 ? { conflict_details: "Describe the conflict" } : null),
    submitLabel: "Sign declaration",
    onSubmit: (v) => API.post("/api/proficiency/declarations", { ...v, kind, audit_id: audit ? audit.id : null }),
    onDone: (d) => { toast(d.has_conflict ? "Signed - your disclosure was sent for review" : "Declaration signed"); done(); },
  });
}

// ------------------------------------------------------------------ Professional practice page
async function renderPractice(tab = state.practiceTab || "mine") {
  state.practiceTab = tab;
  clear(viewRoot);
  viewRoot.append(viewHeader("Professional practice", null, { sub: "Independence and ethics declarations, continuing professional development, the internal audit charter and quality assessments (IIA GIAS Domains II-IV)" }));
  const tabs = [{ key: "mine", label: "My declarations & CPD" }];
  if (hasPerm("proficiency.manage")) tabs.push({ key: "team", label: "Team" });
  if (hasPerm("governance.charter", "governance.view", "committee.record", "oversight.qaip")) tabs.push({ key: "charter", label: "Charter & external assessment" });
  viewRoot.append(tabBar(tabs, tab, (k) => renderPractice(k)));
  const body = el("div");
  viewRoot.append(body);
  if (tab === "mine") paintMine(body);
  if (tab === "team") paintTeam(body);
  if (tab === "charter") paintCharter(body);
}

async function paintMine(body) {
  const year = new Date().getFullYear();
  const [decls, cpd] = await Promise.all([safeGet("/api/proficiency/declarations", []), safeGet(`/api/proficiency/cpd?year=${year}`, null)]);
  const annual = decls.find((d) => d.kind === "annual" && d.year === year);
  body.append(el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, `Annual declaration ${year}`),
    annual ? badge("Signed") : el("button", { class: "btn small", onclick: () => declarationForm("annual", null, () => renderPractice("mine")) }, el("i", { class: "bi bi-pen" }), " Sign now")),
  annual ? el("p", { class: "muted small" }, `Signed ${fmtDate(annual.signed_at)}${annual.has_conflict ? ` · disclosure: ${annual.conflict_details} (${annual.review_status})` : ""}`)
    : el("div", { class: "callout warn" }, el("i", { class: "bi bi-exclamation-triangle" }), el("div", null, "Not signed yet. It is required before you start fieldwork on any engagement.")),
  dataTable(decls, [
    { key: "kind", label: "Type", render: (d) => (d.kind === "annual" ? `Annual ${d.year}` : d.audit_title) },
    { key: "signed_at", label: "Signed", render: (d) => dayOnly(d.signed_at) },
    { key: "has_conflict", label: "Disclosure", render: (d) => (d.has_conflict ? d.conflict_details : "None") },
    { key: "review_status", label: "Review", render: (d) => badge(d.review_status) },
  ], { emptyText: "No declarations yet.", pageSize: 10 })));
  if (!cpd) return;
  const pct = cpd.target ? Math.min(100, Math.round((100 * cpd.hours) / cpd.target)) : 100;
  body.append(el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, `CPD ${year}: ${cpd.hours} of ${cpd.target} hours (${cpd.ethics_hours} of ${cpd.ethics_target} ethics)`),
    el("button", { class: "btn small", onclick: () => openForm({
      title: "Record CPD", key: "cpd:new", width: 640, draftable: false,
      fields: [
        { name: "activity", label: "Activity", required: true, maxLength: 255, singleLine: true, full: true },
        { name: "provider", label: "Provider", maxLength: 160, singleLine: true },
        { name: "category", label: "Category", type: "select", required: true, options: cpd.categories },
        { name: "activity_date", label: "Date", type: "date", required: true },
        { name: "hours", label: "Hours", type: "number", required: true, min: 0.5, max: 200, step: "0.5" },
        { name: "ethics_hours", label: "Of which ethics hours", type: "number", min: 0, max: 200, step: "0.5" },
        { name: "evidence_ref", label: "Certificate / evidence reference", maxLength: 255, singleLine: true },
      ],
      initial: { ethics_hours: 0 },
      submitLabel: "Save",
      onSubmit: (v) => API.post("/api/proficiency/cpd", { ...v, activity_date: `${v.activity_date}T00:00:00`, ethics_hours: v.ethics_hours || 0, provider: v.provider || "", evidence_ref: v.evidence_ref || "" }),
      onDone: () => { toast("CPD recorded"); renderPractice("mine"); },
    }) }, el("i", { class: "bi bi-plus-lg" }), " Record CPD")),
  el("div", { class: "progress" }, el("div", { class: "bar", style: `width:${pct}%` })),
  dataTable(cpd.records, [
    { key: "activity_date", label: "Date", render: (r) => dayOnly(r.activity_date) }, { key: "activity", label: "Activity" },
    { key: "category", label: "Category" }, { key: "hours", label: "Hours" }, { key: "ethics_hours", label: "Ethics" },
    { key: "verified_at", label: "Verified", render: (r) => (r.verified_at ? dayOnly(r.verified_at) : "-") },
  ], { emptyText: "No CPD recorded this year.", pageSize: 10 })));
  body.append(el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, "Certifications"),
    el("button", { class: "btn small secondary", onclick: () => openForm({
      title: "Add certification", key: "cert:new", width: 600, draftable: false,
      fields: [
        { name: "name", label: "Certification", required: true, maxLength: 160, singleLine: true, placeholder: "e.g. CIA, ACCA, ICAG, CISA" },
        { name: "issuer", label: "Issuer", maxLength: 160, singleLine: true }, { name: "number", label: "Membership / certificate no.", maxLength: 80, singleLine: true },
        { name: "obtained_on", label: "Obtained", type: "date" }, { name: "expires_on", label: "Expires / renewal due", type: "date" },
      ],
      submitLabel: "Add",
      onSubmit: (v) => API.post("/api/proficiency/certifications", { ...v, issuer: v.issuer || "", number: v.number || "",
        obtained_on: v.obtained_on ? `${v.obtained_on}T00:00:00` : null, expires_on: v.expires_on ? `${v.expires_on}T00:00:00` : null }),
      onDone: () => { toast("Certification added"); renderPractice("mine"); },
    }) }, el("i", { class: "bi bi-plus-lg" }), " Add")),
  dataTable(cpd.certifications, [
    { key: "name", label: "Certification" }, { key: "issuer", label: "Issuer" }, { key: "number", label: "Number" },
    { key: "expires_on", label: "Expires", render: (c) => (c.expires_on ? el("span", { class: c.expired ? "text-danger" : "" }, dayOnly(c.expires_on)) : "-") },
  ], { emptyText: "None recorded.", pageSize: 10 })));
}

async function paintTeam(body) {
  const t = await safeGet("/api/proficiency/team", null);
  if (!t) return;
  if (t.pending_reviews.length) {
    body.append(el("div", { class: "card" }, el("h3", null, `Disclosures awaiting your review (${t.pending_reviews.length})`),
      dataTable(t.pending_reviews, [
        { key: "user", label: "Auditor" }, { key: "audit_title", label: "Engagement", render: (d) => d.audit_title || `Annual ${d.year}` },
        { key: "conflict_details", label: "Disclosure" }, { key: "signed_at", label: "Signed", render: (d) => dayOnly(d.signed_at) },
      ], { onRow: (d) => openForm({
        title: `Review disclosure - ${d.user}`, key: `declrev:${d.id}`, width: 640, draftable: false, intro: d.conflict_details,
        fields: [{ name: "decision", label: "Decision", type: "select", required: true, options: ["Cleared", "Reassigned"] },
          { name: "notes", label: "Safeguards / reasons", type: "textarea", rows: 3, required: true, minLength: 5 }],
        submitLabel: "Record review",
        onSubmit: (v) => API.post(`/api/proficiency/declarations/${d.id}/review`, v),
        onDone: () => { toast("Review recorded"); renderPractice("team"); },
      }), pageSize: 10 })));
  }
  body.append(el("div", { class: "card" }, el("h3", null, `Team ${t.year}: declarations and CPD (target ${t.target} hours)`),
    dataTable(t.staff, [
      { key: "name", label: "Auditor" },
      { key: "annual_declaration", label: "Annual declaration", render: (s) => badge(s.annual_declaration ? "Signed" : "Missing") },
      { key: "cpd_hours", label: "CPD hours", render: (s) => `${s.cpd_hours} / ${s.cpd_target}` },
      { key: "on_track", label: "CPD", render: (s) => badge(s.on_track ? "On track" : "Below target") },
      { key: "certifications", label: "Certifications", render: (s) => s.certifications.join(", ") || "-" },
      { key: "expiring", label: "Expiring within 90 days", render: (s) => s.expiring.join(", ") || "-" },
    ], { pageSize: 25, exportName: `team-proficiency-${t.year}` })));
}

async function paintCharter(body) {
  const [ch, eqa, conf] = await Promise.all([safeGet("/api/charter", null), safeGet("/api/quality/external-assessments", null), safeGet("/api/quality/conformance", null)]);
  if (conf) {
    body.append(el("div", { class: "card" }, el("h3", null, "Conformance statement (Audit Committee pack)"), el("p", null, conf.statement),
      el("dl", { class: "kv" }, el("dt", null, "Charter"), el("dd", null, conf.charter), el("dt", null, "Internal assessment"), el("dd", null, conf.internal_assessment),
        el("dt", null, "External assessment"), el("dd", null, conf.external_assessment))));
  }
  if (ch) {
    const draft = ch.versions.find((v) => ["Draft", "Submitted"].includes(v.status));
    const canEdit = hasPerm("governance.charter");
    const editForm = (v) => openForm({
      title: v ? `Edit charter v${v.version}` : "New charter version", key: v ? `charter:${v.id}` : "charter:new", width: 900,
      fields: [{ name: "title", label: "Title", required: true, maxLength: 200, singleLine: true, full: true },
        { name: "change_summary", label: "What changed", type: "textarea", rows: 2, full: true },
        { name: "content", label: "Charter text", type: "textarea", rows: 22, required: true, full: true, maxLength: 60000 }],
      initial: v || { title: "Internal Audit Charter - Ghana Ports and Harbours Authority", content: ch.current ? ch.current.content : ch.template },
      submitLabel: "Save draft",
      onSubmit: (x) => (v ? API.put(`/api/charter/${v.id}`, x) : API.post("/api/charter", x)),
      onDone: () => { toast("Charter saved"); renderPractice("charter"); },
    });
    const head = el("div", { class: "card-head" }, el("h3", null, el("i", { class: "bi bi-journal-text" }), " Internal audit charter (GIAS 6.2)"),
      el("div", { class: "actions" },
        canEdit && !draft ? el("button", { class: "btn small", onclick: () => editForm(null) }, el("i", { class: "bi bi-plus-lg" }), " New version") : null,
        canEdit && draft && draft.status === "Draft" ? el("button", { class: "btn small secondary", onclick: () => editForm(draft) }, " Edit draft") : null,
        canEdit && draft && draft.status === "Draft" ? el("button", { class: "btn small", onclick: async () => {
          try { await API.post(`/api/charter/${draft.id}/submit`); toast("Submitted to the Audit Committee"); renderPractice("charter"); } catch (err) { toast(err.message, "error"); }
        } }, " Submit to Committee") : null,
        hasPerm("committee.record") && draft && draft.status === "Submitted" ? el("button", { class: "btn small", onclick: async () => {
          const meetings = (await safeGet("/api/committee/meetings", { items: [] })).items;
          openForm({ title: `Record Committee approval - v${draft.version}`, key: `charterok:${draft.id}`, width: 600, draftable: false,
            fields: [{ name: "approved_at", label: "Date approved", type: "date", required: true },
              { name: "approval_reference", label: "Minute reference", required: true, maxLength: 120, singleLine: true },
              { name: "meeting_id", label: "Meeting", type: "select", options: meetings.map((m) => ({ value: m.id, label: `${m.meeting_ref} ${dayOnly(m.meeting_date)}` })), emptyLabel: "-" }],
            submitLabel: "Record approval",
            onSubmit: (v) => API.post(`/api/charter/${draft.id}/approve`, { approved_at: `${v.approved_at}T12:00:00`, approval_reference: v.approval_reference, meeting_id: v.meeting_id ? Number(v.meeting_id) : null }),
            onDone: () => { toast("Charter approved"); renderPractice("charter"); } });
        } }, " Record approval") : null));
    const card = el("div", { class: "card" }, head);
    if (ch.current) {
      card.append(el("div", { class: `callout ${ch.current.review_overdue ? "danger" : "ok"}` }, el("i", { class: "bi bi-patch-check" }),
        el("div", null, `Version ${ch.current.version} approved ${dayOnly(ch.current.approved_at)} (${ch.current.approval_reference}). Next review ${dayOnly(ch.current.next_review_due)}${ch.current.review_overdue ? " - overdue" : ""}.`)));
    } else card.append(el("div", { class: "callout warn" }, el("i", { class: "bi bi-exclamation-triangle" }), el("div", null, "No approved charter recorded.")));
    card.append(dataTable(ch.versions, [
      { key: "version", label: "Version" }, { key: "status", label: "Status", render: (v) => badge(v.status) },
      { key: "change_summary", label: "Changes" }, { key: "approved_at", label: "Approved", render: (v) => (v.approved_at ? dayOnly(v.approved_at) : "-") },
      { key: "id", label: "Word", render: (v) => el("a", { href: `/api/charter/${v.id}/export.docx`, onclick: (e) => e.stopPropagation() }, "Download") },
    ], { emptyText: "No versions yet.", pageSize: 10 }));
    body.append(card);
  }
  if (eqa) {
    body.append(el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, el("i", { class: "bi bi-award" }), " External quality assessment (GIAS 8.4)"),
      hasPerm("governance.charter") ? el("button", { class: "btn small", onclick: () => openForm({
        title: "Record an external quality assessment", key: "eqa:new", width: 720, draftable: false,
        fields: [{ name: "assessment_type", label: "Type", type: "select", required: true, options: eqa.types },
          { name: "assessor", label: "Assessor / team", required: true, maxLength: 200, singleLine: true },
          { name: "assessor_independent", label: "The assessor is qualified and independent of GPHA", type: "checkbox" },
          { name: "completed_at", label: "Completed", type: "date", required: true },
          { name: "conclusion", label: "Conclusion", type: "select", required: true, options: eqa.conclusions },
          { name: "report_reference", label: "Report reference", maxLength: 120, singleLine: true },
          { name: "reported_to_committee_at", label: "Reported to the Audit Committee", type: "date" },
          { name: "scope", label: "Scope", type: "textarea", rows: 2, full: true }, { name: "action_plan", label: "Improvement action plan", type: "textarea", rows: 3, full: true }],
        initial: { assessor_independent: true },
        submitLabel: "Record",
        onSubmit: (v) => API.post("/api/quality/external-assessments", { ...v, completed_at: `${v.completed_at}T00:00:00`,
          reported_to_committee_at: v.reported_to_committee_at ? `${v.reported_to_committee_at}T00:00:00` : null, scope: v.scope || "", action_plan: v.action_plan || "", report_reference: v.report_reference || "" }),
        onDone: () => { toast("Assessment recorded"); renderPractice("charter"); },
      }) }, el("i", { class: "bi bi-plus-lg" }), " Record assessment") : null),
    el("div", { class: `callout ${eqa.status.overdue ? "warn" : "ok"}` }, el("i", { class: "bi bi-calendar-check" }), el("div", null, eqa.status.message)),
    dataTable(eqa.items, [
      { key: "completed_at", label: "Completed", render: (e) => dayOnly(e.completed_at) }, { key: "assessment_type", label: "Type" },
      { key: "assessor", label: "Assessor" }, { key: "conclusion", label: "Conclusion", render: (e) => badge(e.conclusion) },
      { key: "next_due", label: "Next due", render: (e) => dayOnly(e.next_due) },
    ], { emptyText: "None recorded.", pageSize: 10 })));
  }
}

// ------------------------------------------------------------------ Automation rules
async function renderAutomations() {
  clear(viewRoot);
  const msg = el("div");
  viewRoot.append(viewHeader("Automations", [
    el("button", { class: "btn small secondary", onclick: async () => {
      try { const r = await API.post("/api/automations/run"); toast(`${r.fired} reminder(s) sent`); renderAutomations(); } catch (err) { toast(err.message, "error"); }
    } }, el("i", { class: "bi bi-play" }), " Run scheduled rules now"),
    el("button", { class: "btn small", onclick: () => ruleEditor(null) }, el("i", { class: "bi bi-plus-lg" }), " New rule"),
  ], { sub: "When something happens (or a date approaches), notify people or create tasks. Rules run every hour and fire once per record." }), msg);
  let rules; let cat;
  try { [rules, cat] = await Promise.all([API.get("/api/automations"), API.get("/api/automations/catalog")]); } catch (err) { notify(msg, err.message, "error"); return; }
  window.__autoCat = cat;
  viewRoot.append(el("div", { class: "card" }, dataTable(rules, [
    { key: "name", label: "Rule" }, { key: "trigger_label", label: "When" },
    { key: "offset_days", label: "Days", render: (r) => (r.kind === "schedule" ? r.offset_days : "-") },
    { key: "actions", label: "Then", render: (r) => r.actions.map((a) => `${a.type === "task" ? "Task" : "Notify"} ${a.to.map((t) => recipientLabel(cat, t)).join(", ")}`).join("; ") },
    { key: "active", label: "Status", render: (r) => badge(r.active ? "Active" : "Inactive") },
    { key: "last_run_at", label: "Last run", render: (r) => (r.last_run_at ? fmtDate(r.last_run_at) : "-") },
  ], { onRow: (r) => ruleEditor(r), pageSize: 25 })));
  const log = await safeGet("/api/automations/runs?limit=50", []);
  viewRoot.append(el("div", { class: "card" }, el("h3", null, "Recent activity"),
    dataTable(log, [{ key: "fired_at", label: "When", render: (x) => fmtDate(x.fired_at) }, { key: "rule", label: "Rule" },
      { key: "record_type", label: "Record", render: (x) => `${x.record_type} #${x.record_id}` }, { key: "outcome", label: "Outcome" }],
    { emptyText: "No automations have fired yet.", pageSize: 15 })));
}

function recipientLabel(cat, token) {
  if (cat.people[token]) return cat.people[token].toLowerCase();
  const [kind, value] = token.split(":");
  if (kind === "role") return (cat.roles.find((r) => r.code === value) || {}).name || value;
  if (kind === "perm") return `holders of "${cat.permissions[value] || value}"`;
  if (kind === "tier") return `all ${value} users`;
  return token;
}

function ruleEditor(rule) {
  const cat = window.__autoCat;
  const r = rule || { name: "", description: "", trigger: cat.triggers[0].key, offset_days: 7, conditions: [], actions: [{ type: "notify", to: ["owner"], title: "", body: "", email: true, due_days: 7 }], active: true };
  const st = JSON.parse(JSON.stringify(r));
  const body = el("div");
  const trigSel = el("select", null, ...cat.triggers.map((t) => el("option", { value: t.key, selected: t.key === st.trigger ? "1" : null }, `${t.kind === "schedule" ? "⏱ " : "⚡ "}${t.label}`)));
  const name = el("input", { type: "text", value: st.name, maxlength: 160 });
  const desc = el("input", { type: "text", value: st.description || "", maxlength: 2000 });
  const offset = el("input", { type: "number", min: 0, max: 730, value: st.offset_days });
  const active = el("input", { type: "checkbox", checked: st.active ? "1" : null });
  const condBox = el("div"); const actBox = el("div"); const preview = el("div");
  const trig = () => cat.triggers.find((t) => t.key === trigSel.value);
  const recipientOptions = () => [
    ...Object.entries(cat.people).filter(([k]) => (trig().people || []).includes(k)).map(([k, v]) => ({ value: k, label: v })),
    ...cat.roles.map((x) => ({ value: `role:${x.code}`, label: `Role: ${x.name}` })),
    { value: "level:CAE", label: "Chief Audit Executive (GM Audit)" }, { value: "level:Manager", label: "Managers with review authority" },
    ...Object.entries(cat.permissions).map(([k, v]) => ({ value: `perm:${k}`, label: `Permission: ${v}` })),
  ];
  const field = (label, input, help) => el("div", { class: "form-field" }, el("label", null, label), input, help ? el("div", { class: "help" }, help) : null);
  function paintConds() {
    clear(condBox);
    st.conditions.forEach((c, i) => {
      const f = el("select", null, ...Object.entries(trig().fields).map(([k, v]) => el("option", { value: k, selected: k === c.field ? "1" : null }, v)));
      const op = el("select", null, ...Object.entries(cat.ops).map(([k, v]) => el("option", { value: k, selected: k === c.op ? "1" : null }, v)));
      const val = el("input", { type: "text", value: c.value || "" });
      f.onchange = () => { c.field = f.value; }; op.onchange = () => { c.op = op.value; }; val.oninput = () => { c.value = val.value; };
      if (!c.field) c.field = f.value;
      condBox.append(el("div", { class: "inline-row" }, f, op, val, el("button", { class: "btn small danger-ghost", type: "button", onclick: () => { st.conditions.splice(i, 1); paintConds(); } }, "×")));
    });
    condBox.append(el("button", { class: "btn small secondary", type: "button", onclick: () => { st.conditions.push({ field: "", op: "eq", value: "" }); paintConds(); } }, "+ Condition"));
  }
  function paintActs() {
    clear(actBox);
    const fieldsHelp = `Placeholders: ${Object.keys(trig().fields).map((k) => `{${k}}`).join(" ")}`;
    st.actions.forEach((a, i) => {
      const type = el("select", null, el("option", { value: "notify", selected: a.type === "notify" ? "1" : null }, "Notify (in-app + e-mail)"), el("option", { value: "task", selected: a.type === "task" ? "1" : null }, "Create a task"));
      const to = el("select", { multiple: "1", size: 6 }, ...recipientOptions().map((o) => el("option", { value: o.value, selected: a.to.includes(o.value) ? "1" : null }, o.label)));
      const title = el("input", { type: "text", value: a.title || "", maxlength: 255 });
      const text = el("textarea", { rows: 3 }, a.body || "");
      const due = el("input", { type: "number", min: 0, max: 365, value: a.due_days || 7 });
      type.onchange = () => { a.type = type.value; paintActs(); };
      to.onchange = () => { a.to = [...to.selectedOptions].map((o) => o.value); };
      title.oninput = () => { a.title = title.value; }; text.oninput = () => { a.body = text.value; }; due.oninput = () => { a.due_days = Number(due.value); };
      actBox.append(el("div", { class: "ai-row" }, field("Action", type), field("To (Ctrl/Cmd-click for several)", to),
        field("Title", title, fieldsHelp), field("Message", text), a.type === "task" ? field("Task due in (days)", due) : null,
        st.actions.length > 1 ? el("button", { class: "btn small danger-ghost", type: "button", onclick: () => { st.actions.splice(i, 1); paintActs(); } }, "Remove action") : null));
    });
    if (st.actions.length < 5) actBox.append(el("button", { class: "btn small secondary", type: "button", onclick: () => { st.actions.push({ type: "notify", to: [], title: "", body: "", email: true, due_days: 7 }); paintActs(); } }, "+ Action"));
  }
  const offsetField = field("Days", offset, " ");
  const syncTrig = () => { offsetField.hidden = trig().kind !== "schedule"; offsetField.querySelector(".help").textContent = trig().offset_help; paintConds(); paintActs(); };
  trigSel.onchange = () => { st.trigger = trigSel.value; st.conditions = []; syncTrig(); };
  body.append(field("Rule name", name), field("Description", desc), field("When", trigSel), offsetField,
    el("h4", null, "Only if (optional)"), condBox, el("h4", null, "Then"), actBox, el("label", { class: "check" }, active, " Active"), preview);
  syncTrig();
  const save = async () => {
    const payload = { name: name.value.trim(), description: desc.value.trim(), trigger: trigSel.value, offset_days: Number(offset.value) || 0,
      conditions: st.conditions.filter((c) => c.field), actions: st.actions, active: active.checked };
    try {
      if (rule) await API.put(`/api/automations/${rule.id}`, payload); else await API.post("/api/automations", payload);
      dlg.close(); toast("Rule saved"); renderAutomations();
    } catch (err) { toast(err.message, "error"); }
  };
  const footer = el("div", { class: "form-foot-wrap" },
    el("button", { class: "btn secondary", onclick: () => dlg.close() }, "Cancel"),
    el("div", { class: "actions" },
      rule && rule.kind === "schedule" ? el("button", { class: "btn secondary", onclick: async () => {
        clear(preview);
        const p = await safeGet(`/api/automations/${rule.id}/preview`, { matches: [] });
        preview.append(el("h4", null, `Would match now (${p.matches.length})`), dataTable(p.matches, [{ key: "title", label: "Message" }, { key: "plan", label: "Recipients" },
          { key: "already_sent", label: "Already sent", render: (x) => (x.already_sent ? "Yes" : "No") }], { pageSize: 10, emptyText: "Nothing matches today." }));
      } }, "Preview") : null,
      rule && !rule.builtin ? el("button", { class: "btn danger-ghost", onclick: async () => {
        try { await API.del(`/api/automations/${rule.id}`); dlg.close(); toast("Rule deleted"); renderAutomations(); } catch (err) { toast(err.message, "error"); }
      } }, "Delete") : null,
      el("button", { class: "btn", onclick: save }, "Save rule")));
  const dlg = modal({ title: rule ? `Rule: ${rule.name}` : "New automation rule", body, footer, width: 860 });
}

// ------------------------------------------------------------------ Custom fields for more record types (Configuration)
async function renderRecordFieldsCard(container) {
  const modules = { audits: "Audits", findings: "Findings", capa: "Remediation / recommendations" };
  const card = el("div", { class: "card" });
  container.append(card);
  let module = "audits";
  const sel = el("select", { class: "compact" }, ...Object.entries(modules).map(([k, v]) => el("option", { value: k }, v)));
  const list = el("div");
  const types = { text: "Short text", longtext: "Long text", number: "Number", date: "Date", select: "Drop-down", yesno: "Yes / No" };
  const paint = async () => {
    clear(list);
    const defs = await safeGet(`/api/custom-fields?module=${module}&include_inactive=true`, []);
    list.append(dataTable(defs, [
      { key: "label", label: "Field" }, { key: "field_type", label: "Type", render: (d) => types[d.field_type] || d.field_type },
      { key: "required", label: "Required", render: (d) => (d.required ? "Yes" : "No") }, { key: "active", label: "Status", render: (d) => badge(d.active ? "Active" : "Inactive") },
    ], { onRow: (d) => fieldForm(d), emptyText: "No custom fields yet.", pageSize: 10 }));
  };
  const fieldForm = (def) => openForm({
    key: def ? `rf:${def.id}` : `rf:new:${module}`, title: def ? `Edit field · ${def.label}` : `Add field to ${modules[module]}`, width: 600, draftable: false,
    fields: [
      { name: "label", label: "Field name", required: true, maxLength: 100, singleLine: true },
      ...(def ? [] : [{ name: "field_type", label: "Type", type: "select", required: true, options: Object.entries(types).map(([value, label]) => ({ value, label })) }]),
      { name: "options", label: "Choices (drop-down only)", type: "textarea", rows: 3, help: "One per line", full: true },
      { name: "help", label: "Help text", maxLength: 255, singleLine: true },
      { name: "required", label: "Required", type: "checkbox" },
      ...(def ? [{ name: "active", label: "Active", type: "checkbox" }] : []),
    ],
    initial: def ? { ...def, options: def.options.join("\n") } : { field_type: "text", required: false },
    submitLabel: def ? "Save field" : "Add field",
    onSubmit: (v) => {
      const b = { ...v, options: (v.options || "").split("\n").map((x) => x.trim()).filter(Boolean) };
      return def ? API.patch(`/api/custom-fields/${def.id}`, b) : API.post("/api/custom-fields", { ...b, module });
    },
    onDone: () => { toast("Saved"); paint(); },
  });
  sel.addEventListener("change", () => { module = sel.value; paint(); });
  card.append(el("div", { class: "card-head" }, el("h3", null, el("i", { class: "bi bi-input-cursor" }), " Fields on audits, findings and recommendations"),
    el("div", { class: "actions" }, sel, el("button", { class: "btn small", onclick: () => fieldForm(null) }, el("i", { class: "bi bi-plus-lg" }), " Add field"))),
  el("p", { class: "muted small" }, "Extra inputs your team needs on these forms (for example budget code, amount at risk, ministry reference). They appear on the forms and in exports."), list);
  paint();
}
