// GPHA Audit Workspace - annual planning cycle on the Assurance Plan page:
// preparation -> universe review -> managers' meeting -> draft -> internal review -> submission
// -> Audit Committee decision -> approved version -> GM Audit distribution -> PIA / Manager execution.

const CYCLE_HELP = {
  preparation: "Confirm the preparation checklist: strategy, prior-year results, stakeholder input, resources and regulatory requirements.",
  universe_review: "Review the Audit Universe: risk ratings and units due under the audit cycle. A snapshot is kept with the plan.",
  managers_meeting: "Record the Audit Managers' planning meeting: date, attendees and what was agreed.",
  drafting: "Build the draft plan (engagements, quarters, hours, leads), then submit it for internal review.",
  internal_review: "The GM Audit reviews the draft and approves it with an e-signature, or returns it with comments.",
  submission: "Record the submission of the CAE-approved plan to the approving authority.",
  committee: "Record the Audit Committee's decision. Approval freezes a numbered version.",
  approved: "The approved version is frozen and can be downloaded as a controlled copy.",
  distribution: "The GM Audit distributes the approved version to the PIAs and Audit Managers, who acknowledge receipt.",
  execution: "PIAs and Audit Managers start the engagements; progress is tracked here.",
};

async function renderPlanCycle(slot, plan) {
  clear(slot);
  let c;
  try { c = await API.get(`/api/assurance-plans/${plan.id}/cycle`); }
  catch (err) { slot.append(el("div", { class: "msg error" }, err.message)); return; }
  const reload = () => openPlan(plan.id);
  const steps = el("ol", { class: "cycle-steps", "aria-label": "Annual planning cycle" }, ...c.stages.map((s, i) =>
    el("li", { class: `cycle-step ${s.state}`, "aria-current": s.state === "current" ? "step" : null,
      title: s.completed_at ? `${s.summary || ""}\n${s.completed_by || ""} · ${fmtDate(s.completed_at)}` : CYCLE_HELP[s.code] },
    el("span", { class: "cs-n" }, s.state === "done" ? el("i", { class: "bi bi-check-lg" }) : String(i + 1)),
    el("span", { class: "cs-l" }, s.label),
    s.completed_at && s.state === "done" ? el("span", { class: "cs-d" }, fmtDate(s.completed_at).split(",")[0]) : null)));

  const actions = [];
  const a = (label, fn, kind = "") => actions.push(btn(label, fn, kind));
  if (c.can.preparation) a("Complete preparation", () => cyclePreparation(plan, c, reload));
  if (c.can.universe_review) a("Record universe review", () => cycleUniverse(plan, reload));
  if (c.can.managers_meeting) a("Record planning meeting", () => cycleMeeting(plan, reload));
  if (c.can.submit_review) a("Submit for internal review", () => cycleNote(plan, "submit-review", "Submit the draft for internal review", "Notes for the reviewer", reload));
  if (c.can.internal_review) {
    a("Approve (e-sign)", () => eSignModal({ title: "Approve Assurance Plan", pathOverride: `/api/assurance-plans/${plan.id}/approve`,
      actionLabel: "Sign & Approve", allowReject: true, onDone: reload }));
    a("Return with comments", () => cycleReturn(plan, reload), "secondary");
  }
  if (c.can.submit_authority) a("Record submission", () => cycleSubmit(plan, reload));
  if (c.can.committee) a("Record Committee decision", () => cycleDecision(plan, c, reload));
  if (c.can.distribute) a(c.stage === "execution" ? "Distribute to more people" : "Distribute approved plan", () => cycleDistribute(plan, c, reload), c.stage === "execution" ? "secondary" : "");
  if (c.can.acknowledge) a("Acknowledge receipt", async () => {
    try { await API.post(`/api/assurance-plans/${plan.id}/cycle/acknowledge`); toast("Receipt acknowledged"); reload(); }
    catch (err) { toast(err.message, "error"); }
  });

  const cur = c.stages.find((s) => s.code === c.stage);
  const card = el("div", { class: "card cycle-card" },
    el("div", { class: "card-head" }, el("h3", null, "Annual planning cycle"),
      el("span", { class: "muted small" }, c.current_version ? `Approved version ${c.current_version}` : "No approved version yet")),
    steps,
    el("div", { class: "cycle-now" },
      el("div", null, el("strong", null, c.status === "Closed" ? "Plan year closed" : `Now: ${cur ? cur.label : c.stage_label}`),
        el("div", { class: "muted small" }, CYCLE_HELP[c.stage] || ""),
        !c.enforced ? el("div", { class: "muted small" }, "The cycle is advisory (Configuration > Plan configuration).") : null),
      actions.length ? el("div", { class: "actions" }, ...actions) : null));
  slot.append(card);

  if (c.stage === "execution" || c.distribution.length) {
    const ex = c.execution;
    card.append(el("div", { class: "cycle-sub" },
      el("div", null, el("h4", null, "Distribution"),
        c.distribution.length ? el("table", { class: "compact" }, el("tbody", null, ...c.distribution.map((d) => el("tr", { class: "no-click" },
          el("td", null, d.name, el("div", { class: "muted small" }, d.job_role || "")),
          el("td", null, `v${d.version}`),
          el("td", null, d.acknowledged_at ? el("span", null, el("i", { class: "bi bi-check-circle-fill ok-ico" }), ` ${fmtDate(d.acknowledged_at).split(",")[0]}`)
            : el("span", { class: "muted" }, "Awaiting acknowledgement"))))))
          : el("div", { class: "muted" }, "Not distributed yet.")),
      el("div", null, el("h4", null, "Execution"),
        el("div", null, `${ex.started} of ${ex.engagements} engagements started`),
        el("table", { class: "compact" }, el("tbody", null, ...Object.entries(ex.by_lead).map(([lead, n]) => el("tr", { class: "no-click" },
          el("td", null, lead), el("td", { class: "num" }, `${n.started} started · ${n.planned} to start`))))))));
  }
}

async function renderPlanCycleLog(panelEl, plan) {
  let c;
  try { c = await API.get(`/api/assurance-plans/${plan.id}/cycle`); }
  catch (err) { panelEl.append(el("div", { class: "empty" }, err.message)); return; }
  if (c.versions.length) {
    panelEl.append(el("div", { class: "card" }, el("h3", null, "Approved versions"), dataTable(c.versions, [
      { key: "version", label: "Version", render: (v) => el("strong", null, `v${v.version}`) },
      { key: "decision", label: "Decision" },
      { key: "committee_reference", label: "Committee ref", render: (v) => v.committee_reference || "-" },
      { key: "approved_at", label: "Approved", render: (v) => fmtDate(v.approved_at).split(",")[0] },
      { key: "engagements", label: "Engagements", num: true },
      { key: "iaa_reference", label: "Internal Audit Agency", render: (v) => (v.iaa_submitted_at
        ? `${fmtDate(v.iaa_submitted_at).split(",")[0]} · ${v.iaa_reference}`
        : (hasPerm("plan.amend") ? btn("Record IAA submission", () => iaaSubmission(plan, v), "small") : el("span", { class: "muted" }, "Not yet submitted"))) },
      { key: "dl", label: "", render: (v) => el("a", { class: "btn small secondary", href: `/api/assurance-plans/${plan.id}/versions/${v.version}/export.docx` },
        el("i", { class: "bi bi-file-earmark-word" }), " Controlled copy") },
    ], { pageSize: 20 })));
  }
  panelEl.append(el("div", { class: "card" }, el("h3", null, "Cycle record"), c.events.length ? el("div", { class: "timeline" },
    ...c.events.map((e) => el("div", { class: "tl-item" },
      el("div", { class: "tl-head" }, el("strong", null, e.stage_label), ` · ${e.action}`, e.decision ? ` · ${e.decision}` : "",
        el("span", { class: "muted small" }, ` — ${e.by || "system"}, ${fmtDate(e.at)}`)),
      e.meeting_date ? el("div", { class: "small" }, `Date: ${fmtDate(e.meeting_date).split(",")[0]}${e.reference ? ` · ref ${e.reference}` : ""}`)
        : e.reference ? el("div", { class: "small" }, `Ref ${e.reference}`) : null,
      e.attendees ? el("div", { class: "small" }, `Attendees: ${e.attendees}`) : null,
      e.notes ? el("div", { class: "small pre" }, e.notes) : null,
      e.data && e.data.due_count !== undefined ? el("div", { class: "small muted" },
        `Universe: ${e.data.units} units (${e.data.by_rating.High} high, ${e.data.by_rating.Medium} medium, ${e.data.by_rating.Low} low); ${e.data.due_count} due under the audit cycle`) : null,
      e.data && e.data.checks ? el("div", { class: "small muted" }, `${e.data.checks.length} preparation items confirmed`) : null)))
    : el("div", { class: "empty" }, "No cycle steps recorded yet.")));
}

function cyclePost(plan, path, body, msg, reload) {
  return API.post(`/api/assurance-plans/${plan.id}/cycle/${path}`, body).then((r) => { toast(msg); reload(); return r; });
}

function cyclePreparation(plan, c, reload) {
  openForm({
    title: "Planning preparation", draftable: false, width: 640,
    fields: [
      { name: "checks", label: "Preparation checklist", type: "checklist", required: true,
        options: c.preparation_checks.map((x) => ({ value: x.key, label: x.label })), full: true },
      { name: "notes", label: "Notes (strategy themes, key inputs)", type: "textarea", maxLength: 8000, full: true },
    ],
    submitLabel: "Complete preparation",
    onSubmit: (v) => API.post(`/api/assurance-plans/${plan.id}/cycle/preparation`, { checks: v.checks || [], notes: v.notes || "" }),
    onDone: () => { toast("Preparation recorded"); reload(); },
  });
}

async function cycleUniverse(plan, reload) {
  let u;
  try { u = await API.get(`/api/assurance-plans/${plan.id}/cycle/universe`); } catch (err) { toast(err.message, "error"); return; }
  const notes = el("textarea", { rows: "4", maxlength: "8000", "aria-label": "Review notes", placeholder: "What was reviewed, ratings changed, new risks or units added" });
  const m = modal({ title: "Risk / universe review", width: 760, body: el("div", null,
    el("div", { class: "stats" }, stat(u.units, "Active units"), stat(u.by_rating.High, "High risk", null, u.by_rating.High ? "warn" : ""),
      stat(u.by_rating.Medium, "Medium"), stat(u.by_rating.Low, "Low"), stat(u.due_count, "Due under the audit cycle", null, u.due_count ? "warn" : "")),
    u.due.length ? el("div", { class: "table-wrap", style: "max-height:240px;overflow:auto" }, el("table", { class: "compact" },
      el("thead", null, el("tr", null, el("th", null, "Unit"), el("th", null, "Risk"), el("th", null, "Last audited"))),
      el("tbody", null, ...u.due.map((d) => el("tr", { class: "no-click" }, el("td", null, d.name), el("td", null, `${d.risk} (${d.score})`),
        el("td", null, d.last_audited || "Never")))))) : null,
    el("p", { class: "muted small" }, "Update ratings in the Audit Universe first if needed; this snapshot is stored with the plan."),
    field("Review notes", notes)),
  footer: el("div", { class: "actions" }, btn("Open Audit Universe", () => { m.close(); navigate("universe"); }, "secondary"),
    btn("Record review", async () => {
      try { await cyclePost(plan, "universe-review", { notes: notes.value }, "Universe review recorded", reload); m.close(); }
      catch (err) { toast(err.message, "error"); }
    })) });
}

function cycleMeeting(plan, reload) {
  openForm({
    title: "Audit Managers' planning meeting", draftable: false, width: 640,
    fields: [
      { name: "meeting_date", label: "Meeting date", type: "date", required: true, notFuture: true },
      { name: "attendees", label: "Attendees", required: true, minLength: 3, maxLength: 4000, type: "textarea", full: true },
      { name: "minutes", label: "Minutes / what was agreed", type: "textarea", required: true, minLength: 10, maxLength: 20000, full: true },
    ],
    submitLabel: "Save meeting",
    onSubmit: (v) => API.post(`/api/assurance-plans/${plan.id}/cycle/managers-meeting`, { ...v, meeting_date: `${v.meeting_date}T09:00:00` }),
    onDone: () => { toast("Planning meeting recorded"); reload(); },
  });
}

function cycleNote(plan, path, title, label, reload) {
  openForm({
    title, draftable: false, width: 560,
    fields: [{ name: "notes", label, type: "textarea", maxLength: 8000, full: true }],
    submitLabel: "Submit",
    onSubmit: (v) => API.post(`/api/assurance-plans/${plan.id}/cycle/${path}`, { notes: v.notes || "" }),
    onDone: () => { toast("Submitted"); reload(); },
  });
}

function cycleReturn(plan, reload) {
  openForm({
    title: "Return the draft plan", draftable: false, width: 560,
    fields: [{ name: "comment", label: "What needs to change", type: "textarea", required: true, minLength: 5, maxLength: 4000, full: true }],
    submitLabel: "Return to preparer",
    onSubmit: (v) => API.post(`/api/assurance-plans/${plan.id}/cycle/return`, v),
    onDone: () => { toast("Plan returned for revision"); reload(); },
  });
}

function cycleSubmit(plan, reload) {
  openForm({
    title: "Submission to the approving authority", draftable: false, width: 600,
    fields: [
      { name: "authority", label: "Approving authority", required: true, maxLength: 255, singleLine: true },
      { name: "submitted_on", label: "Date submitted", type: "date", required: true, notFuture: true },
      { name: "reference", label: "Submission reference / memo no.", maxLength: 100, singleLine: true },
      { name: "notes", label: "Notes", type: "textarea", maxLength: 8000, full: true },
    ],
    initial: { authority: "Audit Committee" },
    submitLabel: "Record submission",
    onSubmit: (v) => API.post(`/api/assurance-plans/${plan.id}/cycle/submit-authority`, { ...v, submitted_on: `${v.submitted_on}T09:00:00` }),
    onDone: () => { toast("Submission recorded"); reload(); },
  });
}

function cycleDecision(plan, c, reload) {
  openForm({
    title: "Audit Committee decision", draftable: false, width: 600,
    fields: [
      { name: "decision", label: "Decision", type: "select", required: true, options: c.committee_decisions },
      { name: "meeting_date", label: "Meeting date", type: "date", required: true, notFuture: true },
      { name: "reference", label: "Minute / resolution reference", required: true, maxLength: 100, singleLine: true },
      { name: "notes", label: "Committee comments / amendments", type: "textarea", maxLength: 8000, full: true,
        help: "Required when approved with amendments. 'Returned for revision' sends the plan back to drafting." },
    ],
    submitLabel: "Record decision",
    onSubmit: (v) => API.post(`/api/assurance-plans/${plan.id}/cycle/committee-decision`, { ...v, meeting_date: `${v.meeting_date}T09:00:00` }),
    onDone: (r) => { toast(r.current_version && r.stage === "distribution" ? `Approved version ${r.current_version} frozen` : "Decision recorded"); reload(); },
  });
}

async function cycleDistribute(plan, c, reload) {
  let people;
  try { people = await API.get(`/api/assurance-plans/${plan.id}/cycle/recipients`); } catch (err) { toast(err.message, "error"); return; }
  const already = new Set(c.distribution.filter((d) => d.version === c.current_version).map((d) => d.user_id));
  const options = people.filter((p) => !already.has(p.id));
  if (!options.length) { toast("Everyone has already received this version", "error"); return; }
  openForm({
    title: `Distribute approved version ${c.current_version}`, draftable: false, width: 640,
    intro: "Controlled distribution: each recipient is notified and must acknowledge receipt. PIAs and Audit Managers are pre-selected.",
    fields: [
      { name: "user_ids", label: "Recipients", type: "checklist", required: true, full: true,
        options: options.map((p) => ({ value: String(p.id), label: `${p.name}${p.job_role ? ` · ${p.job_role}` : ""}` })) },
      { name: "note", label: "Covering note", type: "textarea", maxLength: 4000, full: true },
    ],
    initial: { user_ids: options.filter((p) => p.suggested).map((p) => String(p.id)) },
    submitLabel: "Distribute",
    onSubmit: (v) => API.post(`/api/assurance-plans/${plan.id}/cycle/distribute`, { user_ids: (v.user_ids || []).map(Number), note: v.note || "" }),
    onDone: () => { toast("Plan distributed"); reload(); },
  });
}

function iaaSubmission(plan, v) {
  openForm({
    title: `Submit version ${v.version} to the Internal Audit Agency`, draftable: false, width: 560,
    intro: "Record the submission of the Audit Committee-approved plan (or amended version) to the Internal Audit Agency.",
    fields: [
      { name: "submitted_on", label: "Date submitted", type: "date", required: true, notFuture: true },
      { name: "reference", label: "Letter / submission reference", required: true, maxLength: 100, singleLine: true },
    ],
    submitLabel: "Record submission",
    onSubmit: (x) => API.post(`/api/assurance-plans/${plan.id}/versions/${v.version}/iaa-submission`, { ...x, submitted_on: `${x.submitted_on}T09:00:00` }),
    onDone: () => { toast("IAA submission recorded"); openPlan(plan.id); },
  });
}
