// GPHA INTERNAL AUDIT WORKSPACE - engagement-level screens on the audit page:
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

// ==================================================================== IIA Topical Requirements (e.g. Cybersecurity)
// For each requirement the team records whether its topic is in scope and why; when it is, every requirement is
// assessed (conclusion, work done, issue raised) or excluded with a rationale. Mandatory for assurance engagements.
async function renderTopicalTab(pane, audit, canWrite) {
  clear(pane);
  pane.append(loadingState());
  let d;
  try { d = await API.get(`/api/audits/${audit.id}/topical`); } catch (err) { clear(pane); pane.append(errorState(err, () => renderTopicalTab(pane, audit, canWrite))); return; }
  clear(pane);
  const canPlan = canWrite && !d.closed && hasPerm("audit.plan");
  const canAssess = canWrite && !d.closed && hasPerm("audit.fieldwork");
  const reload = (view) => { if (view) { d = view; } renderTopicalTab(pane, audit, canWrite); };
  pane.append(el("div", { class: `callout ${d.open_points.length ? "warn" : "ok"}` },
    el("i", { class: `bi bi-${d.open_points.length ? "exclamation-circle" : "check-circle"}`, "aria-hidden": "true" }),
    el("div", null, el("strong", null, `${d.nature} engagement: ${d.mandatory ? "mandatory" : "recommended"}`),
      d.open_points.length ? el("ul", { class: "small" }, ...d.open_points.map((p) => el("li", null, p))) : el("div", { class: "small" }, "Every topical requirement is decided and assessed."))));
  d.requirements.forEach((r) => pane.append(topicalCard(audit, d, r, canPlan, canAssess, reload)));
}

function topicalCard(audit, d, r, canPlan, canAssess, reload) {
  const card = el("section", { class: "card topical-card" });
  const dec = r.decision;
  card.append(el("div", { class: "card-head" },
    el("div", null, el("h3", null, r.title), el("div", { class: "muted small" }, `IIA Topical Requirement ${r.version}${r.effective_on ? ` · in force ${fmtDay(r.effective_on)}` : ""}`)),
    r.source_url ? el("a", { class: "btn small secondary", href: r.source_url, target: "_blank", rel: "noopener noreferrer" }, "IIA text") : null));
  const decide = (inScope) => openForm({
    title: `${r.title}: ${inScope ? "in scope" : "not in scope"}`, key: `topical:${audit.id}:${r.id}`, draftable: false, width: 560,
    fields: inScope
      ? [{ name: "trigger", label: "How it came into scope", type: "select", required: true, options: d.triggers.map((t) => ({ value: t, label: t })) },
        { name: "rationale", label: "Notes", type: "textarea", maxLength: 5000, full: true }]
      : [{ name: "rationale", label: "Why it is not in scope", type: "textarea", required: true, minLength: 10, maxLength: 5000, full: true }],
    initial: dec ? { trigger: dec.trigger || d.triggers[0], rationale: dec.rationale } : { trigger: d.triggers[0] },
    submitLabel: "Save",
    onSubmit: (v) => API.put(`/api/audits/${audit.id}/topical/${r.id}`, { in_scope: inScope, trigger: v.trigger || null, rationale: v.rationale || "" }),
    onDone: (view) => { closeFormPanel(); toast("Decision recorded"); reload(view); },
  });
  if (!dec) {
    card.append(el("p", null, "Is this topic in scope of the engagement?"),
      canPlan ? el("div", { class: "actions" }, el("button", { class: "btn", type: "button", onclick: () => decide(true) }, "In scope"),
        el("button", { class: "btn secondary", type: "button", onclick: () => decide(false) }, "Not in scope")) : el("p", { class: "muted small" }, "Not decided yet."));
    return card;
  }
  card.append(el("div", { class: "adm-row" },
    el("div", null, el("strong", null, dec.in_scope ? `In scope · ${dec.trigger}` : "Not in scope"),
      dec.rationale ? el("div", { class: "muted small" }, dec.rationale) : null,
      el("div", { class: "muted small" }, `${dec.decided_by || "-"} · ${fmtDate(dec.decided_at)}`)),
    canPlan ? el("button", { class: "btn small secondary", type: "button", onclick: () => decide(!dec.in_scope) }, dec.in_scope ? "Mark not in scope" : "Mark in scope") : null));
  if (!dec.in_scope) return card;
  const p = r.progress;
  card.append(el("div", { class: "topical-progress" },
    el("progress", { max: String(p.total), value: String(p.done), "aria-label": "Requirements done" }),
    el("span", { class: "small" }, `${p.done} of ${p.total} done · ${p.assessed} assessed · ${p.excluded} excluded · ${p.exceptions} with exceptions`)));
  const assess = (it) => openForm({
    title: `${it.ref} · ${r.title}`, key: `topical:${audit.id}:${r.id}:${it.item_id}`, draftable: false, width: 620,
    intro: it.text,
    fields: [
      { name: "outcome", label: "Outcome", type: "select", required: true, options: [{ value: "Assessed", label: "Assessed" }, { value: "Excluded", label: "Excluded (give the rationale)" }] },
      { name: "conclusion", label: "Conclusion (when assessed)", type: "select", options: d.conclusions.map((c) => ({ value: c, label: c })) },
      { name: "finding_id", label: "Issue raised", type: "select", emptyLabel: "- none -", options: d.findings.map((f) => ({ value: f.id, label: `#${f.id} ${f.title}` })) },
      { name: "notes", label: "Work done / rationale", type: "textarea", rows: 4, maxLength: 10000, full: true },
    ],
    initial: { outcome: it.outcome || "Assessed", conclusion: it.conclusion || "", finding_id: it.finding_id || "", notes: it.notes || "" },
    submitLabel: "Save",
    onSubmit: (v) => API.put(`/api/audits/${audit.id}/topical/${r.id}/items/${it.item_id}`,
      { outcome: v.outcome, conclusion: v.outcome === "Assessed" ? v.conclusion : null, finding_id: v.outcome === "Assessed" && v.finding_id ? Number(v.finding_id) : null, notes: v.notes || "" }),
    onDone: (view) => { closeFormPanel(); toast("Requirement saved"); reload(view); },
  });
  const areas = [...new Set(r.items.map((i) => i.area))];
  card.append(el("div", { class: "table-wrap" }, el("table", { class: "compact-table topical-table" },
    el("thead", null, el("tr", null, ...["Ref", "Requirement", "Outcome", "Conclusion / rationale", ""].map((h) => el("th", null, h)))),
    el("tbody", null, ...areas.flatMap((a) => [
      el("tr", { class: "no-click group-row" }, el("th", { colspan: "5" }, a)),
      ...r.items.filter((i) => i.area === a).map((it) => el("tr", { class: "no-click" },
        el("td", null, it.ref), el("td", null, it.text),
        el("td", null, it.outcome ? badge(it.outcome) : el("span", { class: "muted" }, "Open")),
        el("td", { class: "small" }, it.conclusion || "", it.finding_id ? el("div", null, `Issue #${it.finding_id}`) : null,
          it.notes ? el("div", { class: "muted" }, clip(it.notes, 140)) : null),
        el("td", null, canAssess ? el("button", { class: "btn small secondary", type: "button", onclick: () => assess(it) }, it.outcome ? "Edit" : "Assess") : null)))])))));
  return card;
}

// ------------------------------------------------------------------ Configuration > Topical requirements
// The IIA Topical Requirements catalogue: holders of "Audit object library" add requirements, edit their checklist
// until an engagement uses it, and publish changes as a new version.
async function renderTopicalCatalogueCard(container) {
  const card = el("div", { class: "card" });
  container.append(card);
  const canEdit = hasPerm("method.library");
  const reload = () => { card.remove(); renderTopicalCatalogueCard(container); };
  card.append(el("div", { class: "card-head" }, el("h3", null, el("i", { class: "bi bi-journal-check" }), " Topical requirements"),
    canEdit ? el("button", { class: "btn small", type: "button", onclick: () => topicalReqForm(null, reload) }, el("i", { class: "bi bi-plus-lg" }), " New requirement") : null));
  let rows;
  try { rows = await API.get("/api/topical-requirements?include_inactive=true"); } catch (err) { card.append(el("div", { class: "muted" }, err.message)); return; }
  const stateOf = (r) => (!r.is_active ? ["Inactive", "muted-chip"] : r.in_force ? ["In force", "ok-chip"] : ["Not yet in force", "warn-chip"]);
  card.append(el("div", { class: "table-wrap" }, el("table", { class: "compact-table topical-catalogue" },
    el("thead", null, el("tr", null, ...["Requirement", "Version", "In force from", "Status", "Checklist", "Used on", ""].map((h) => el("th", null, h)))),
    el("tbody", null, ...rows.map((r) => {
      const [label, cls] = stateOf(r);
      return el("tr", { class: "no-click" },
        el("td", null, el("strong", null, r.title)), el("td", null, r.version || "-"),
        el("td", null, r.effective_on ? fmtDay(r.effective_on) : "-"),
        el("td", null, el("span", { class: `chip-mini ${cls}` }, label)),
        el("td", { class: "num" }, String(r.items.length)), el("td", { class: "num" }, String(r.used_on)),
        el("td", { class: "row-actions" }, dropMenu("Actions", [
          ["Checklist", () => topicalItemsPanel(r, canEdit, reload)],
          canEdit ? ["Edit", () => topicalReqForm(r, reload)] : null,
          canEdit ? ["New version", () => topicalVersionForm(r, reload)] : null,
          canEdit ? [r.is_active ? "Deactivate" : "Activate", async () => {
            try { await API.patch(`/api/topical-requirements/${r.id}`, { is_active: !r.is_active }); toast(r.is_active ? "Deactivated" : "Activated"); reload(); }
            catch (err) { toast(err.message, "error"); }
          }, r.is_active] : null,
        ])));
    })))));
}

function topicalReqForm(r, done) {
  return openForm({
    title: r ? `Edit ${r.title}` : "New topical requirement", key: `topreq:${r ? r.id : "new"}`, draftable: false, width: 620,
    fields: [
      { name: "title", label: "Title", required: true, minLength: 3, maxLength: 200, singleLine: true, full: true },
      { name: "version", label: "Version", maxLength: 40, singleLine: true },
      { name: "effective_on", label: "In force from", type: "date" },
      { name: "source_url", label: "IIA page (https://)", maxLength: 500, singleLine: true, full: true },
      { name: "description", label: "Applicability", type: "textarea", rows: 3, maxLength: 5000, full: true },
    ],
    initial: r ? { title: r.title, version: r.version, effective_on: r.effective_on, source_url: r.source_url, description: r.description } : {},
    submitLabel: r ? "Save" : "Create",
    onSubmit: (v) => {
      const b = { title: v.title, version: v.version || "", effective_on: v.effective_on || null, source_url: v.source_url || "", description: v.description || "" };
      return r ? API.patch(`/api/topical-requirements/${r.id}`, b) : API.post("/api/topical-requirements", { ...b, is_active: false });
    },
    onDone: (x) => { toast(r ? "Saved" : "Created (inactive until you activate it)"); done(); if (!r) topicalItemsPanel(x, true, done); },
  });
}

function topicalVersionForm(r, done) {
  return openForm({
    title: `New version of ${r.title}`, key: `topver:${r.id}`, draftable: false, width: 520,
    fields: [{ name: "version", label: "Version", required: true, maxLength: 40, singleLine: true },
      { name: "effective_on", label: "In force from", type: "date" }],
    initial: { effective_on: r.effective_on },
    submitLabel: "Create version",
    onSubmit: (v) => API.post(`/api/topical-requirements/${r.id}/new-version`, { version: v.version, effective_on: v.effective_on || null }),
    onDone: (x) => { toast("New version created (inactive)"); done(); topicalItemsPanel(x, true, done); },
  });
}

function topicalItemsPanel(r, canEdit, done) {
  const locked = r.used_on > 0;
  const body = el("div");
  let dlg;
  const refresh = (x) => { dlg.close(); done(); topicalItemsPanel(x, canEdit, done); };
  const itemForm = (it) => openForm({
    title: it ? `Edit ${it.ref}` : `Add to ${r.title}`, key: `topitem:${r.id}:${it ? it.id : "new"}`, draftable: false, width: 600,
    fields: [
      { name: "area", label: "Area", type: "select", required: true, options: ["Governance", "Risk management", "Control processes"] },
      { name: "ref", label: "Ref", required: true, maxLength: 10, singleLine: true },
      { name: "text", label: "Requirement", type: "textarea", rows: 3, required: true, minLength: 10, maxLength: 2000, full: true },
    ],
    initial: it ? { area: it.area, ref: it.ref, text: it.text } : { area: "Governance" },
    submitLabel: "Save",
    onSubmit: (v) => (it ? API.put(`/api/topical-requirement-items/${it.id}`, v) : API.post(`/api/topical-requirements/${r.id}/items`, v)),
    onDone: (x) => { closeFormPanel(); toast("Checklist saved"); refresh(x); },
  });
  const del = async (it) => {
    const ok = await confirmDialog({ title: `Remove ${it.ref}`, text: it.text, confirmLabel: "Remove", danger: true });
    if (!ok.ok) return;
    try { refresh(await API.del(`/api/topical-requirement-items/${it.id}`)); toast("Removed"); } catch (err) { toast(err.message, "error"); }
  };
  const edit = canEdit && !locked;
  if (locked && canEdit) body.append(el("p", { class: "muted small" }, `Used on ${r.used_on} engagement(s): the checklist is fixed. Use New version to change it.`));
  const areas = ["Governance", "Risk management", "Control processes"].filter((a) => r.items.some((i) => i.area === a));
  body.append(r.items.length ? el("div", { class: "table-wrap" }, el("table", { class: "compact-table topical-table" },
    el("tbody", null, ...areas.flatMap((a) => [
      el("tr", { class: "no-click group-row" }, el("th", { colspan: edit ? "3" : "2" }, a)),
      ...r.items.filter((i) => i.area === a).map((it) => el("tr", { class: "no-click" }, el("td", null, it.ref), el("td", null, it.text),
        edit ? el("td", { class: "row-actions" }, dropMenu("Actions", [["Edit", () => itemForm(it)], ["Remove", () => del(it), true]])) : null))]))))
    : el("p", { class: "muted" }, "No requirements yet."));
  dlg = modal({ title: `${r.title} ${r.version || ""}`.trim(), body, width: 820,
    footer: edit ? el("div", { class: "actions" }, el("button", { class: "btn", type: "button", onclick: () => itemForm(null) }, el("i", { class: "bi bi-plus-lg" }), " Add requirement")) : null });
}
