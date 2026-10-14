// GPHA Audit Workspace - engagement-level screens on the audit page:
// planning memo, time & budget, quality review (QAIP) and the post-audit survey.
// Loaded after workflow.js and before app.js; uses helpers from api.js/forms.js/app.js at call time.

const MEMO_STAGES = ["Draft", "Submitted", "Approved"];

// ==================================================================== planning memo

async function renderMemoTab(panelEl, audit, canWrite) {
  const card = el("div", { class: "card" });
  panelEl.append(card);
  let m;
  try { m = await API.get(`/api/audits/${audit.id}/planning-memo`); }
  catch (err) { card.append(el("div", { class: "empty" }, err.message)); return; }
  const refresh = () => { clear(panelEl); renderMemoTab(panelEl, audit, canWrite); };
  const stage = m.status === "Returned" ? "Draft" : m.status;

  const actions = el("div", { class: "actions" });
  if (m.id && canWrite) {
    actions.append(el("a", { class: "btn small secondary", href: `/api/audits/${audit.id}/planning-memo.docx` },
      el("i", { class: "bi bi-file-earmark-word" }), " Word"));
  }
  if (m.can_edit) actions.append(el("button", { class: "btn small secondary", onclick: () => memoForm(audit, m, refresh) },
    el("i", { class: "bi bi-pencil" }), m.id ? " Edit memo" : " Write memo"));
  if (m.can_edit && m.id) {
    actions.append(el("button", { class: "btn small", disabled: m.missing.length ? "1" : null,
      title: m.missing.length ? `Complete first: ${m.missing.join(", ")}` : "Send to an Audit Manager or the CAE",
      onclick: async () => {
        try { await API.post(`/api/audits/${audit.id}/planning-memo/submit`); toast("Memo submitted for approval"); refresh(); }
        catch (err) { toast(err.message, "error"); }
      } }, el("i", { class: "bi bi-send" }), " Submit for approval"));
  }
  if (m.can_approve) {
    actions.append(el("button", { class: "btn small", onclick: () => eSignModal({
      title: "Approve planning memo (e-sign)", recordType: "planning_memo", recordId: m.id, allowReject: true,
      pathOverride: `/api/audits/${audit.id}/planning-memo/approve`, actionLabel: "Sign",
      onDone: refresh }) }, el("i", { class: "bi bi-pen" }), " Review & sign"));
  }
  card.append(el("div", { class: "card-head" }, el("h3", null, "Planning memo"), actions),
    stepper(MEMO_STAGES, stage));

  if (m.status === "Returned" && m.review_comment) {
    card.append(el("div", { class: "callout warn" }, el("i", { class: "bi bi-arrow-return-left" }),
      el("div", null, el("strong", null, "Returned by the reviewer: "), m.review_comment)));
  }
  if (!m.id) {
    card.append(el("div", { class: "empty" },
      "No planning memo yet. The memo sets out objectives, scope, key risks, approach, team, timeline and budget, ",
      "and must be approved before fieldwork starts (IIA GIAS 13.6)."));
    return;
  }
  if (m.missing.length && m.can_edit) {
    card.append(el("div", { class: "callout warn" }, el("i", { class: "bi bi-list-check" }),
      el("div", null, "To submit, complete: ", el("strong", null, m.missing.join(", ")))));
  }
  const d = (v) => (v ? fmtDate(v).split(",")[0] : "-");
  card.append(el("dl", { class: "kv two-col" },
    el("dt", null, "Fieldwork"), el("dd", null, `${d(m.start_date)} to ${d(m.end_date)}`),
    el("dt", null, "Budget"), el("dd", null, `${m.budget_hours || 0} hours`),
    el("dt", null, "Prepared by"), el("dd", null, m.prepared_by_name || "-"),
    el("dt", null, "Approved by"), el("dd", null, m.approved_by_name ? `${m.approved_by_name} · ${d(m.approved_at)}` : "-")));
  [["Background", "background"], ["Objectives", "objectives"], ["Scope", "scope"], ["Key risks", "key_risks"],
    ["Approach and work programme", "approach"], ["Engagement team", "team"]].forEach(([label, key]) => {
    card.append(el("div", { class: "long-field" }, el("div", { class: "lf-label" }, label),
      el("div", { class: `lf-value ${m[key] ? "" : "muted"}`.trim() }, m[key] || "Not recorded")));
  });
}

function memoForm(audit, m, onDone) {
  openForm({
    key: `memo:${audit.id}`, title: `Planning memo · ${audit.title}`, width: 820,
    meta: { title: `Planning memo of ${audit.title}`, record_type: "audit", record_id: audit.id },
    intro: "Save at any time. Submit for approval once every section is complete.",
    fields: [
      { name: "background", label: "Background", type: "textarea", rows: 3, maxLength: 20000 },
      { name: "objectives", label: "Objectives", type: "textarea", rows: 3, maxLength: 20000, help: "What the engagement will conclude on" },
      { name: "scope", label: "Scope", type: "textarea", rows: 3, maxLength: 20000, help: "Processes, locations, period covered and exclusions" },
      { name: "key_risks", label: "Key risks", type: "textarea", rows: 3, maxLength: 20000 },
      { name: "approach", label: "Approach and work programme", type: "textarea", rows: 4, maxLength: 20000, help: "Walkthroughs, analytics, sampling, tests" },
      { name: "team", label: "Engagement team", type: "textarea", rows: 2, maxLength: 5000 },
      { name: "start_date", label: "Fieldwork start", type: "date" },
      { name: "end_date", label: "Fieldwork end", type: "date" },
      { name: "budget_hours", label: "Budget (hours)", type: "number", min: 0, max: 20000 },
    ],
    initial: { ...m, budget_hours: m.budget_hours || null },
    validate: (v) => (v.start_date && v.end_date && v.end_date < v.start_date ? { end_date: "End date must be on or after the start date" } : null),
    submitLabel: "Save memo",
    onSubmit: (v) => API.put(`/api/audits/${audit.id}/planning-memo`, { ...v, budget_hours: v.budget_hours || 0 }),
    onDone: () => { toast("Planning memo saved"); onDone(); },
  });
}

// ==================================================================== time & budget on an audit

async function renderAuditTimeTab(panelEl, audit) {
  const card = el("div", { class: "card" });
  panelEl.append(card);
  card.append(el("div", { class: "card-head" }, el("h3", null, "Time & budget"),
    el("button", { class: "btn small", onclick: () => timeEntryForm({ audit_id: audit.id, category: "Audit" }, () => { clear(panelEl); renderAuditTimeTab(panelEl, audit); }) },
      el("i", { class: "bi bi-plus-lg" }), " Log time")));
  try {
    const [entries, summary] = await Promise.all([
      API.get(`/api/capacity/time?audit_id=${audit.id}`),
      API.get("/api/capacity/summary"),
    ]);
    const b = summary.audits.find((x) => x.audit_id === audit.id) || { budget_hours: 0, actual_hours: entries.reduce((s, e) => s + e.hours, 0) };
    const pct = b.budget_hours ? Math.round((100 * b.actual_hours) / b.budget_hours) : 0;
    card.append(el("div", { class: "stats" },
      stat(b.budget_hours || "-", "Budget hours", b.budget_hours ? "from the planning memo / plan" : "set it in the planning memo"),
      stat(b.actual_hours, "Hours charged", b.budget_hours ? `${pct}% of budget` : "", pct > 100 ? "danger" : pct > 85 ? "warn" : ""),
      stat(b.budget_hours ? Math.round((b.budget_hours - b.actual_hours) * 100) / 100 : "-", "Remaining", null, b.budget_hours && b.actual_hours > b.budget_hours ? "danger" : "")));
    if (b.budget_hours) {
      card.append(el("div", { class: "progress", role: "progressbar", "aria-valuenow": String(pct), "aria-valuemin": "0", "aria-valuemax": "100", "aria-label": "Budget used" },
        el("div", { class: `progress-fill ${pct > 100 ? "over" : ""}`, style: `width:${Math.min(pct, 100)}%` })));
    }
    card.append(dataTable(entries, [
      { key: "entry_date", label: "Date", render: (e) => fmtDate(e.entry_date).split(",")[0], sortValue: (e) => e.entry_date },
      { key: "user_name", label: "Auditor" },
      { key: "category", label: "Category" },
      { key: "hours", label: "Hours", num: true },
      { key: "description", label: "Work done", render: (e) => e.description || el("span", { class: "muted" }, "-") },
    ], { exportName: `AUD-${String(audit.id).padStart(4, "0")}-time.csv`, emptyText: "No time charged to this audit yet." }));
  } catch (err) { card.append(el("div", { class: "empty" }, err.message)); }
}

function timeEntryForm(initial, onDone) {
  const audits = API.get("/api/audits").catch(() => []);
  audits.then((list) => {
    openForm({
      key: "time:new", title: "Log time", width: 620, draftable: false,
      fields: [
        { name: "entry_date", label: "Date", type: "date", required: true, notFuture: true },
        { name: "hours", label: "Hours", type: "number", required: true, min: 0.25, max: 24, step: "0.25", help: "Quarter hours, e.g. 1.5" },
        { name: "category", label: "Category", type: "select", required: true, options: ["Audit", "Follow-up", "Training", "Administration", "Leave", "Other"] },
        { name: "audit_id", label: "Audit", type: "select", emptyLabel: "- not audit work -",
          options: list.filter((a) => a.status !== "Closed" || a.id === initial.audit_id).map((a) => ({ value: a.id, label: `AUD-${String(a.id).padStart(4, "0")} · ${a.title}` })) },
        { name: "description", label: "Work done", type: "textarea", rows: 2, maxLength: 2000, full: true },
      ],
      initial: { entry_date: new Date().toISOString().slice(0, 10), ...initial },
      validate: (v) => {
        const e = {};
        if (["Audit", "Follow-up"].includes(v.category) && !v.audit_id) e.audit_id = `Choose the audit for ${v.category} time`;
        if (v.hours && Math.round(v.hours * 4) !== v.hours * 4) e.hours = "Use quarter hours (e.g. 1.25, 3.5)";
        return Object.keys(e).length ? e : null;
      },
      submitLabel: "Save time",
      onSubmit: (v) => API.post("/api/capacity/time", v),
      onDone: () => { toast("Time saved"); onDone(); },
    });
  });
}

// ==================================================================== quality review (QAIP)

async function renderQualityTab(panelEl, audit) {
  const card = el("div", { class: "card" });
  panelEl.append(card);
  let r;
  try { r = await API.get(`/api/audits/${audit.id}/quality-review`); }
  catch (err) { card.append(el("div", { class: "empty" }, err.message)); return; }
  const done = !!r.completed_at;
  card.append(el("div", { class: "card-head" },
    el("h3", null, "Engagement quality review"),
    r.score !== null && r.score !== undefined ? el("span", { class: `badge ${r.score >= 85 ? "badge-closed" : r.score >= 70 ? "badge-medium" : "badge-high"}` }, `${r.score}% conformance`) : null));
  card.append(el("p", { class: "muted" }, done
    ? `Completed by ${r.reviewer_name} on ${fmtDate(r.completed_at).split(",")[0]}.`
    : "Checklist against the IIA Global Internal Audit Standards, completed by a reviewer who did not prepare the audit. "
      + "The system's evidence is shown under each line; the reviewer decides."));
  if (!r.can_edit && !done) {
    card.append(el("div", { class: "callout warn" }, el("i", { class: "bi bi-person-x" }),
      el("div", null, audit.created_by === state.user.id
        ? "You prepared this audit, so another auditor must do its quality review."
        : "The quality review is done once the audit is in Review or Closed.")));
  }
  const editable = r.can_edit && ["Review", "Closed"].includes(audit.status);
  const rows = r.items.map((it) => {
    const sel = el("select", { "aria-label": `Answer: ${it.question}`, disabled: editable ? null : "1" },
      el("option", { value: "" }, "- choose -"), ...r.answer_options.map((o) => el("option", { value: o, selected: o === it.answer ? "1" : null }, o)));
    const com = el("input", { placeholder: "Comment / evidence", value: it.comment || "", maxlength: "2000", "aria-label": `Comment: ${it.question}`, disabled: editable ? null : "1" });
    return { it, sel, com, node: el("div", { class: "qa-row" },
      el("div", { class: "qa-q" }, el("span", { class: "chip-mini" }, it.standard), " ", it.question,
        it.hint ? el("div", { class: "muted small" }, el("i", { class: "bi bi-lightbulb" }), ` ${it.hint}`) : null),
      el("div", { class: "qa-a" }, sel, com)) };
  });
  card.append(el("div", { class: "qa-list" }, ...rows.map((x) => x.node)));
  const conclusion = el("textarea", { rows: 3, maxlength: "5000", disabled: editable ? null : "1", id: "qa-conclusion" });
  conclusion.value = r.conclusion || "";
  card.append(el("div", { class: "form-field" }, el("label", { for: "qa-conclusion" }, "Overall conclusion"), conclusion));
  if (editable) {
    const save = async (complete) => {
      const answers = Object.fromEntries(rows.filter((x) => x.sel.value || x.com.value.trim())
        .map((x) => [x.it.key, { answer: x.sel.value, comment: x.com.value.trim() }]));
      try {
        await API.put(`/api/audits/${audit.id}/quality-review`, { answers, conclusion: conclusion.value, complete });
        toast(complete ? "Quality review completed" : "Quality review saved");
        clear(panelEl); renderQualityTab(panelEl, audit);
      } catch (err) { toast(err.errors && err.errors.length ? err.errors.map((e) => e.message).join("; ") : err.message, "error"); }
    };
    card.append(el("div", { class: "actions end" },
      el("button", { class: "btn secondary", onclick: () => save(false) }, "Save"),
      el("button", { class: "btn", onclick: () => save(true) }, el("i", { class: "bi bi-check2-circle" }), " Complete review")));
  }
}

// ==================================================================== post-audit survey

async function renderSurveyTab(panelEl, audit) {
  const card = el("div", { class: "card" });
  panelEl.append(card);
  let s;
  try { s = await API.get(`/api/audits/${audit.id}/survey`); }
  catch (err) { card.append(el("div", { class: "empty" }, err.message)); return; }
  const staff = state.user.role !== "Auditee";
  card.append(el("div", { class: "card-head" }, el("h3", null, "Post-audit survey"),
    staff && s.average !== null && s.average !== undefined ? el("span", { class: "badge" }, `${s.average} / 5`) : null));
  if (!s.open) {
    card.append(el("div", { class: "empty" }, "The survey opens when the report is issued or the audit is closed. Auditees are then asked to rate the audit."));
    return;
  }
  if (staff) {
    card.append(el("p", { class: "muted" }, `${s.responses} of ${s.invited} auditee(s) responded.`));
    if (s.responses) {
      card.append(el("div", { class: "bars" }, ...s.questions.map((q) => {
        const v = s.by_question[q.key] || 0;
        return el("div", { class: "bar-row" }, el("span", { class: "bar-label" }, q.text),
          el("span", { class: "bar-track", role: "img", "aria-label": `${v} out of 5` }, el("span", { class: `bar-fill ${v < 3 ? "danger" : v < 4 ? "warn" : ""}`, style: `width:${(v / 5) * 100}%` })),
          el("strong", { class: "bar-val" }, v.toFixed(1)));
      })));
      if (s.comments.length) card.append(el("h4", null, "Comments"), el("ul", { class: "plain-list quotes" }, ...s.comments.map((c) => el("li", null, `"${c}"`))));
    }
    return;
  }
  if (s.my_response) {
    card.append(el("div", { class: "callout ok" }, el("i", { class: "bi bi-check2-circle" }), el("div", null, "Thank you - your feedback was recorded.")));
    return;
  }
  if (!s.can_respond) { card.append(el("div", { class: "empty" }, "This survey is for the audit's auditees.")); return; }
  card.append(el("p", { class: "muted" }, "Rate each statement from 1 (strongly disagree) to 5 (strongly agree). It takes about two minutes."));
  const picks = {};
  const form = el("div", { class: "survey" }, ...s.questions.map((q) => {
    const group = el("div", { class: "rating", role: "radiogroup", "aria-label": q.text },
      ...[1, 2, 3, 4, 5].map((n) => el("label", { class: "rating-opt" },
        el("input", { type: "radio", name: `sv-${q.key}`, value: String(n), onchange: () => { picks[q.key] = n; } }), el("span", null, String(n)))));
    return el("fieldset", { class: "survey-q" }, el("legend", null, q.text), group);
  }));
  const comments = el("textarea", { rows: 3, maxlength: "5000", id: "sv-comments" });
  card.append(form, el("div", { class: "form-field" }, el("label", { for: "sv-comments" }, "Anything else? (optional)"), comments));
  card.append(el("div", { class: "actions end" }, el("button", { class: "btn", onclick: async () => {
    const missing = s.questions.filter((q) => !picks[q.key]);
    if (missing.length) { toast(`Please rate every statement (${missing.length} left)`, "error"); return; }
    try { await API.post(`/api/audits/${audit.id}/survey`, { scores: picks, comments: comments.value }); toast("Thank you for your feedback"); clear(panelEl); renderSurveyTab(panelEl, audit); }
    catch (err) { toast(err.message, "error"); }
  } }, "Send feedback")));
}
