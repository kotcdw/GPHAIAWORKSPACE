// GPHA Audit Workspace - Assurance Plan pages (Diligent Assurance Plans layout, IIA GIAS 9.4):
//   header stepper (plan lifecycle), Overview (key metrics, projects and strategic alignment, coverage by entity
//   category, strategic risks, resources, getting started), Projects (+ Add to plan: new, link, roll forward),
//   Objectives and Narratives across the plan's audits (narrative import), Coverage, Strategic risks, Resources.
// Loaded after planning.js / fieldwork.js (openPlan, renderEngagements, donutChart, progressBar).

const PLAN_LIFECYCLE = ["Draft", "In Review", "Submitted", "Approved", "Distributed", "In Execution", "Closed"];

// Plan lifecycle under the title: Draft > In Review > Submitted > Approved > Distributed > In Execution > Closed.
function planStepper(plan, goTo) {
  const st = { Returned: "In Review", Revised: "Approved", Archived: "Closed" }[plan.lifecycle_status] || plan.lifecycle_status;
  const at = Math.max(0, PLAN_LIFECYCLE.indexOf(st));
  return el("ol", { class: "phase-track plan-track", "aria-label": "Plan status" }, ...PLAN_LIFECYCLE.map((label, i) => {
    const cls = i < at ? "done" : i === at ? "current" : "";
    return el("li", { class: `phase ${cls} ${plan.lifecycle_status === "Returned" && i === at ? "returned" : ""}`, "aria-current": i === at ? "step" : null },
      el("button", { type: "button", class: "phase-btn", onclick: () => goTo("cycle"), title: "Approval & launch" },
        el("span", { class: "phase-dot", "aria-hidden": "true" }, i < at ? el("i", { class: "bi bi-check-lg" }) : String(i + 1)),
        el("span", { class: "phase-l" }, i === at && plan.lifecycle_status === "Returned" ? "Returned" : label)));
  }));
}

function impactSquares(n, max = 5) {
  const v = Math.max(0, Math.min(max, n || 0));
  const tone = v >= 4 ? "hi" : v === 3 ? "md" : "lo";
  return el("span", { class: `impact-sq ${tone}`, role: "img", "aria-label": `Impact ${v} of ${max}`, title: `Impact ${v} of ${max}` },
    ...Array.from({ length: max }, (_, i) => el("i", { class: i < v ? "on" : "" })));
}

function hoursBar(h) {
  const over = h.available && h.planned > h.available;
  const pct = h.available ? Math.min(100, (100 * h.planned) / h.available) : 0;
  return el("div", { class: "hours-bar" },
    el("div", { class: "hb-top" }, el("span", null, "Planned hours"),
      el("strong", { class: over ? "text-danger" : null }, `${h.planned}h / ${h.available ? `${h.available}h` : "no budget set"}`)),
    el("span", { class: `pbar wide ${over ? "bad" : ""}`, role: "progressbar", "aria-valuenow": String(Math.round(pct)), "aria-valuemin": "0", "aria-valuemax": "100" },
      el("span", { class: "pbar-fill", style: `width:${pct}%` })),
    el("div", { class: "hb-foot muted small" },
      el("span", null, `${h.actual}h charged`),
      el("span", { class: over ? "text-danger" : null }, h.available ? (over ? `${h.over}h over the available hours` : `${h.available - h.planned}h not yet allocated`) : "Set the available hours on the plan")));
}

// ------------------------------------------------------------------ Overview

async function renderPlanProgram(pane, plan, goTo) {
  pane.append(loadingState());
  let p;
  try { p = await API.get(`/api/assurance-plans/${plan.id}/program`); } catch (err) { clear(pane); pane.append(errorState(err, () => { clear(pane); renderPlanProgram(pane, plan, goTo); })); return; }
  clear(pane);
  const m = p.metrics;
  pane.append(gettingStarted(plan, p, goTo));
  const over = m.hours.available && m.hours.planned > m.hours.available;
  pane.append(el("div", { class: "kpi-row" },
    kpi("Projects in the plan", m.projects, ` / ${m.max_projects} max`),
    kpi("Strategic risks aligned", m.strategic_risks),
    kpi("Entity coverage", `${m.coverage_pct}%`, ` · ${m.covered} of ${m.entities}`),
    kpi("Allocated hours", `${m.hours.planned}h`, m.hours.available ? ` / ${m.hours.available}h` : " · no budget", over ? "danger" : "")));

  const projects = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, "Projects and strategic alignment"),
    el("button", { class: "link-btn", type: "button", onclick: () => goTo("projects") }, "All projects")));
  if (!p.projects.length) projects.append(emptyState({ icon: "kanban", title: "No projects yet", text: "Add projects to the plan: new, linked or rolled forward.",
    action: plan.status === "Draft" ? btn("+ Add to plan", () => addToPlan(plan)) : null }));
  else projects.append(el("div", { class: "table-wrap" }, el("table", { class: "dense" },
    el("thead", null, el("tr", null, ...["Project", "Progress", "Phase", "Strategic risks", "Assignees"].map((h) => el("th", { scope: "col" }, h)))),
    el("tbody", null, ...p.projects.filter((r) => !r.cancelled).map((r) => el("tr", { class: r.audit_id ? "" : "no-click", tabindex: r.audit_id ? "0" : null,
      onclick: r.audit_id ? () => openAudit(r.audit_id) : null, onkeydown: r.audit_id ? (e) => { if (e.key === "Enter") openAudit(r.audit_id); } : null },
      el("td", { class: "col-wide", "data-label": "Project" }, el("div", { class: "cell-title" }, r.title),
        el("div", { class: "muted small" }, [r.quarter, r.audit_type, r.entity].filter(Boolean).join(" · "))),
      el("td", { "data-label": "Progress" }, progressBar(r.progress)),
      el("td", { "data-label": "Phase" }, el("span", { class: `phase-chip ph-${{ "Not started": "plan", Planning: "plan", Fieldwork: "perform", Reporting: "communicate", Completed: "completed" }[r.phase]}` }, r.phase)),
      el("td", { class: "num", "data-label": "Strategic risks" }, String(r.strategic_risks)),
      el("td", { "data-label": "Assignees" }, el("span", { class: "muted" }, el("i", { class: "bi bi-people" }), ` ${r.assignees}`))))))));

  const cats = p.categories.filter((c) => c.covered);
  const coverage = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, "Coverage by entity category"),
    el("button", { class: "link-btn", type: "button", onclick: () => goTo("coverage") }, "View by entity")));
  if (!p.categories.length) coverage.append(el("p", { class: "muted small" }, "No auditable entities yet (Audit universe)."));
  else {
    if (cats.length) coverage.append(donutChart("Entities covered", cats.map((c) => ({ label: c.name, count: c.covered })), {}, "covered"));
    coverage.append(el("ul", { class: "cat-cov" }, ...p.categories.map((c) => el("li", null,
      el("span", null, c.name), el("span", { class: "muted small" }, `${c.covered} of ${c.entities}`), progressBar(c.pct, c.pct < 50 ? "warn" : "")))));
  }
  pane.append(el("div", { class: "two-col-wide" }, projects, coverage));

  const risks = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, "Strategic risks"),
    el("button", { class: "link-btn", type: "button", onclick: () => goTo("risks") }, "All risks")),
  el("p", { class: "muted small" }, "Risk Manager risks linked to the plan's entities or to risks in its audits, with the strategic objective they threaten."));
  if (!p.strategic_risks.length) risks.append(el("p", { class: "muted small" }, "No strategic risk is linked yet. Link Risk Manager risks to the auditable entities (Process library) or to audit risks."));
  else risks.append(strategicRiskTable(p.strategic_risks.slice(0, 6)));
  const res = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, "Resources and progress"),
    el("button", { class: "link-btn", type: "button", onclick: () => goTo("resources") }, "Details")),
  hoursBar(m.hours),
  el("div", { class: "hours-bar" }, el("div", { class: "hb-top" }, el("span", null, "Overall plan progress"), el("strong", null, `${m.overall_progress}%`)),
    el("span", { class: "pbar wide" }, el("span", { class: "pbar-fill", style: `width:${m.overall_progress}%` }))),
  p.not_covered_high ? el("div", { class: "callout warn" }, el("i", { class: "bi bi-exclamation-triangle" }),
    el("div", null, `${p.not_covered_high} high-risk entit${p.not_covered_high === 1 ? "y is" : "ies are"} not covered by the plan.`,
      " ", el("button", { class: "link-btn", type: "button", onclick: () => goTo("coverage") }, "Review coverage"))) : null);
  pane.append(el("div", { class: "two-col-wide" }, risks, res));
  if (plan.description) pane.append(el("div", { class: "card" }, el("div", { class: "lf-label" }, "Basis of the plan"), el("div", { class: "lf-value" }, plan.description)));
}

function kpi(label, value, sub = "", tone = "") {
  return el("div", { class: `kpi ${tone}` }, el("div", { class: "kpi-l" }, label),
    el("div", { class: "kpi-v" }, el("strong", null, String(value)), sub ? el("span", { class: "kpi-s" }, sub) : null));
}

function strategicRiskTable(rows) {
  return el("div", { class: "table-wrap" }, el("table", { class: "dense" },
    el("thead", null, el("tr", null, ...["Risk", "Impact", "Projects", "Progress"].map((h) => el("th", { scope: "col" }, h)))),
    el("tbody", null, ...rows.map((r) => el("tr", { class: "no-click" },
      el("td", { class: "col-wide", "data-label": "Risk" }, el("span", { class: "ref" }, r.ref), ` ${r.title}`,
        r.objective ? el("div", { class: "muted small" }, el("i", { class: "bi bi-bullseye" }), ` ${r.objective}`) : null),
      el("td", { "data-label": "Impact" }, impactSquares(r.impact)),
      el("td", { class: "num", "data-label": "Projects" }, String(r.projects)),
      el("td", { "data-label": "Progress" }, progressBar(r.progress)))))));
}

// Getting started: the lifecycle from the audit universe to launching the plan, with where each step stands.
function gettingStarted(plan, p, goTo) {
  const st = plan.lifecycle_status;
  const launched = ["Distributed", "In Execution", "Closed", "Archived", "Revised"].includes(st);
  const started = p.projects.filter((r) => r.audit_id).length;
  const steps = [
    ["Define the audit universe", p.metrics.entities > 0, `${p.metrics.entities} auditable entit${p.metrics.entities === 1 ? "y" : "ies"}`, () => navigate("universe")],
    ["Assess and prioritise risk", null, "Audit risk assessment", () => navigate("riskassess")],
    ["Create the plan", true, `${plan.plan_ref} · FY${plan.fiscal_year}`, null],
    ["Add projects", p.metrics.projects > 0, `${p.metrics.projects} project${p.metrics.projects === 1 ? "" : "s"}`, () => goTo("projects")],
    ["Approve and launch", launched, launched ? st : `Now: ${st}`, () => goTo("cycle")],
    ["Perform the audits", started > 0 && started === p.metrics.projects, `${started} of ${p.metrics.projects} started`, () => goTo("projects")],
  ];
  const nextIdx = steps.findIndex((s) => s[1] === false);
  return el("details", { class: "card guide", open: nextIdx >= 0 && nextIdx <= 4 ? "1" : null },
    el("summary", null, el("span", { class: "fw-k" }, "Getting started"),
      el("span", null, nextIdx >= 0 ? `Next: ${steps[nextIdx][0]}` : "Every step is under way")),
    el("ol", { class: "guide-steps" }, ...steps.map(([label, done, sub, go], i) => el("li", { class: done ? "done" : i === nextIdx ? "next" : "" },
      el("span", { class: "gs-n" }, done ? el("i", { class: "bi bi-check-lg" }) : String(i + 1)),
      el("span", { class: "gs-t" }, go ? el("button", { class: "link-btn", type: "button", onclick: go }, label) : el("strong", null, label),
        el("span", { class: "muted small" }, sub))))));
}

// ------------------------------------------------------------------ + Add to plan

function addToPlan(plan) {
  const reload = () => openPlan(plan.id);
  const choice = (icon, title, text, fn) => el("button", { class: "add-choice", type: "button", onclick: () => { m.close(true); fn(); } },
    el("i", { class: `bi bi-${icon}`, "aria-hidden": "true" }), el("span", null, el("strong", null, title), el("span", { class: "muted small" }, text)));
  const m = modal({
    drawer: true, title: "Add to plan", width: 560,
    body: el("div", { class: "add-choices" },
      el("p", { class: "muted small" }, `Add projects to ${plan.plan_ref}. A plan holds up to the configured number of projects.`),
      choice("plus-square", "Create a new project", "Title, audit type, auditable entity, quarter, hours and lead; optionally an audit programme from the Project Library.", () => addEngagement(plan)),
      choice("link-45deg", "Link active projects", "Bring audits that are already running and not on a plan into this plan.", () => includeAuditsDialog(plan, reload)),
      choice("arrow-repeat", "Roll forward a project", "Plan a new project from an earlier audit; it starts with that audit's objectives, risks, controls, test plan and narratives.", () => rollForwardForm(plan))),
    footer: el("button", { class: "btn secondary", type: "button", onclick: () => m.close() }, "Close"),
  });
}

async function rollForwardForm(plan) {
  const cands = await safeGet(`/api/assurance-plans/${plan.id}/rollforward-candidates`, []);
  const leads = await safeGet("/api/users/directory", null);
  openForm({
    title: "Roll forward a project", key: `rollforward:${plan.id}`, width: 680,
    meta: { title: `Roll forward (${plan.plan_ref})`, record_type: "assurance_plan", record_id: plan.id },
    intro: "The new project keeps the earlier audit's entity, audit type and site. When it starts it receives that audit's objectives, risks, controls with their test plan, and narratives - not its results.",
    fields: [
      { name: "audit_id", label: "Audit to roll forward", type: "select", required: true, full: true, emptyLabel: "- choose -",
        options: cands.map((a) => ({ value: a.id, label: `${a.ref} ${a.title}${a.plan ? ` (${a.plan})` : ""} · ${a.status}` })) },
      { name: "title", label: "New project title", required: true, maxLength: 255, singleLine: true, full: true },
      { name: "planned_quarter", label: "Quarter", type: "select", required: true, options: QUARTERS },
      { name: "budget_hours", label: "Budget hours", type: "number", min: 0, max: 10000 },
      ...(Array.isArray(leads) ? [{ name: "lead_auditor_id", label: "Lead auditor", type: "select", emptyLabel: "- not assigned -",
        options: leads.map((u) => ({ value: u.id, label: u.name })) }] : []),
    ],
    initial: { planned_quarter: "Q1", budget_hours: 0 },
    validate: (v) => (!cands.length ? { audit_id: "There is no earlier audit to roll forward" } : null),
    submitLabel: "Save and roll forward",
    onSubmit: (v) => API.post(`/api/assurance-plans/${plan.id}/rollforward`, {
      audit_id: Number(v.audit_id), title: v.title, planned_quarter: v.planned_quarter, budget_hours: v.budget_hours || 0,
      lead_auditor_id: v.lead_auditor_id ? Number(v.lead_auditor_id) : null }),
    onDone: () => { toast("Project rolled forward"); openPlan(plan.id); },
  });
}

// ------------------------------------------------------------------ Objectives and narratives across the plan

async function renderPlanObjectives(pane, plan) {
  pane.append(loadingState());
  const rows = await safeGet(`/api/assurance-plans/${plan.id}/objectives`, []);
  clear(pane);
  const open = rows.filter((r) => r.open);
  const audits = [...new Map(open.map((r) => [r.audit_id, r])).values()];
  const add = canWriteModule("audits") && hasPerm("audit.fieldwork", "audit.plan") ? btn("+ New objective", async () => {
    const started = await planOpenAudits(plan);
    if (!started.length) { toast("Start a project first; objectives are kept inside each audit", "error"); return; }
    chooseAudit(started, "New objective in", (aid) => objectiveForm(aid, null, () => openPlan(plan.id)));
  }) : null;
  const card = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, "Objectives"), add),
    el("p", { class: "muted small" }, "Every engagement objective of the plan's audits (IIA GIAS 13.3). Objectives live inside each audit; open one to add its risks and controls."));
  pane.append(card);
  if (!rows.length) { card.append(emptyState({ icon: "bullseye", title: "No objectives yet", text: audits.length ? "" : "Objectives are set inside each audit once its project has started." })); return; }
  card.append(el("div", { class: "table-wrap" }, el("table", { class: "dense" },
    el("thead", null, el("tr", null, ...["Objective", "Audit", "Lead", "Target", "Risks", "Controls", "Narratives", ""].map((h) => el("th", { scope: "col" }, h)))),
    el("tbody", null, ...rows.map((r) => el("tr", { class: "no-click" },
      el("td", { class: "col-wide", "data-label": "Objective" }, el("span", { class: "ref" }, r.ref), ` ${r.title}`, r.description ? el("div", { class: "muted small" }, clip(r.description, 90)) : null),
      el("td", { "data-label": "Audit" }, el("span", { class: "ref" }, r.audit_ref), el("div", { class: "muted small" }, clip(r.audit, 40))),
      el("td", { "data-label": "Lead" }, r.lead || el("span", { class: "muted" }, "-")),
      el("td", { "data-label": "Target" }, r.target_date ? fmtDay(r.target_date) : r.quarter),
      el("td", { class: "num", "data-label": "Risks" }, String(r.risks)),
      el("td", { class: "num", "data-label": "Controls" }, String(r.controls)),
      el("td", { class: "num", "data-label": "Narratives" }, String(r.narratives)),
      el("td", null, el("div", { class: "actions" }, btn(r.open ? "Add risk / control" : "Open", () => {
        state.fwSub = state.fwSub || {}; state.fwSub[r.audit_id] = r.workflow === "Workplan" ? "plan" : "rcm"; openAudit(r.audit_id, "fieldwork");
      }, "secondary")))))))));
}

async function planOpenAudits(plan) {
  const p = await API.get(`/api/assurance-plans/${plan.id}`);
  return p.engagements.filter((e) => e.audit_id && e.status !== "Cancelled").map((e) => ({ id: e.audit_id, title: e.title }));
}

function chooseAudit(audits, title, then) {
  if (audits.length === 1) { then(audits[0].id); return; }
  openForm({
    title, draftable: false, width: 520,
    fields: [{ name: "audit_id", label: "Audit", type: "select", required: true, full: true, options: audits.map((a) => ({ value: a.id, label: `AUD-${String(a.id).padStart(4, "0")} ${a.title}` })) }],
    submitLabel: "Continue",
    onSubmit: async (v) => v.audit_id,
    onDone: (aid) => { closeFormPanel(); then(Number(aid)); },
  });
}

async function renderPlanNarratives(pane, plan) {
  pane.append(loadingState());
  const [rows, objs] = await Promise.all([safeGet(`/api/assurance-plans/${plan.id}/narratives`, []), safeGet(`/api/assurance-plans/${plan.id}/objectives`, [])]);
  clear(pane);
  const targets = objs.filter((o) => o.open && o.workflow !== "Workplan");
  const imp = canWriteModule("audits") && targets.length ? btn("Import narrative", () => importNarrativeForm(plan, targets)) : null;
  const card = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, "Process narratives"), imp),
    el("p", { class: "muted small" }, "Narratives describe how each process works (IIA GIAS 13.2). They belong to an objective inside an audit that uses the Internal Control workflow. Import a Word, Excel or text document to create one."));
  pane.append(card);
  if (!rows.length) { card.append(emptyState({ icon: "journal-text", title: "No narratives yet", text: targets.length ? "Import a document or add narratives in the audit's Fieldwork." : "Start an Internal Control project and add its objectives first." })); return; }
  card.append(el("div", { class: "table-wrap" }, el("table", { class: "dense" },
    el("thead", null, el("tr", null, ...["Narrative", "Objective", "Audit", "Controls", "Updated", ""].map((h) => el("th", { scope: "col" }, h)))),
    el("tbody", null, ...rows.map((n) => el("tr", { class: "no-click" },
      el("td", { class: "col-wide", "data-label": "Narrative" }, el("span", { class: "ref" }, n.ref), ` ${n.title}`, el("div", { class: "muted small" }, `${n.length.toLocaleString()} characters`)),
      el("td", { "data-label": "Objective" }, clip(n.objective, 50)),
      el("td", { "data-label": "Audit" }, clip(n.audit, 40)),
      el("td", { class: "num", "data-label": "Controls" }, String(n.controls)),
      el("td", { "data-label": "Updated" }, fmtDay(n.updated_at.slice(0, 10))),
      el("td", null, btn("Open", () => { state.fwSub = state.fwSub || {}; state.fwSub[n.audit_id] = "narr"; openAudit(n.audit_id, "fieldwork"); }, "secondary"))))))));
}

function importNarrativeForm(plan, targets) {
  const file = el("input", { type: "file", accept: ".docx,.xlsx,.txt", "aria-label": "Narrative document" });
  const obj = el("select", { "aria-label": "Objective" }, ...targets.map((o) => el("option", { value: o.id }, `${o.audit_ref} · ${o.ref} ${clip(o.title, 60)}`)));
  const title = el("input", { maxlength: "60", placeholder: "Defaults to the file name", "aria-label": "Narrative title" });
  const msg = el("div");
  const m = modal({
    drawer: true, title: "Import narrative", width: 620,
    body: el("div", { class: "form-body" }, msg,
      el("div", { class: "drop-zone" }, el("i", { class: "bi bi-cloud-arrow-up" }), el("div", null, "Choose a .docx, .xlsx or .txt document"), file),
      field("Objective (audit)", obj), field("Narrative title", title)),
    footer: el("div", { class: "form-foot-wrap" },
      el("button", { class: "btn secondary", type: "button", onclick: () => m.close() }, "Close"),
      el("button", { class: "btn", type: "button", onclick: async () => {
        if (!file.files.length) { notify(msg, "Choose a document first", "error"); return; }
        const fd = new FormData();
        fd.append("file", file.files[0]);
        fd.append("title", title.value.trim());
        try {
          const r = await API.upload(`/api/objectives/${obj.value}/narratives/import`, fd);
          notify(msg, `${r.ref} ${r.title} created from the document (${r.characters.toLocaleString()} characters).`, "ok");
          file.value = ""; title.value = "";
          toast("Narrative imported");
        } catch (err) { notify(msg, err.message, "error"); }
      } }, "Import")),
    onClose: () => openPlan(plan.id),
  });
}

// ------------------------------------------------------------------ Strategic risks and resources

async function renderPlanStrategicRisks(pane, plan) {
  pane.append(loadingState());
  const p = await safeGet(`/api/assurance-plans/${plan.id}/program`, null);
  clear(pane);
  if (!p) { pane.append(errorState({ message: "Could not load the plan" })); return; }
  const card = el("div", { class: "card" }, el("h3", null, "Strategic risks"),
    el("p", { class: "muted small" }, "Risk Manager risks that the plan addresses: linked to its auditable entities, or to a risk inside one of its audits. Impact is the residual impact; progress is the average progress of the projects addressing the risk."));
  card.append(p.strategic_risks.length ? strategicRiskTable(p.strategic_risks)
    : emptyState({ icon: "shield-exclamation", title: "No strategic risk is linked yet", text: "Link Risk Manager risks to the auditable entities or their processes, or to audit risks." }));
  pane.append(card);
  const ent = el("div");
  pane.append(ent);
  renderPlanCoverage(ent, plan, "risks");
}

async function renderPlanResources(pane, plan) {
  pane.append(loadingState());
  const p = await safeGet(`/api/assurance-plans/${plan.id}/program`, null);
  clear(pane);
  if (!p) { pane.append(errorState({ message: "Could not load the plan" })); return; }
  const live = p.projects.filter((r) => !r.cancelled);
  const byQ = QUARTERS.map((q) => ({ q, hours: live.filter((r) => r.quarter === q).reduce((a, r) => a + r.hours, 0) }));
  const maxQ = Math.max(1, ...byQ.map((x) => x.hours));
  const byLead = Object.entries(live.reduce((acc, r) => { const k = r.lead || "Not assigned"; acc[k] = (acc[k] || 0) + r.hours; return acc; }, {})).sort((a, b) => b[1] - a[1]);
  pane.append(el("div", { class: "two-col-wide" },
    el("div", { class: "card" }, el("h3", null, "Hours"), hoursBar(p.metrics.hours),
      el("div", { class: "hours-bar" }, el("div", { class: "hb-top" }, el("span", null, "Overall plan progress"), el("strong", null, `${p.metrics.overall_progress}%`)),
        el("span", { class: "pbar wide" }, el("span", { class: "pbar-fill", style: `width:${p.metrics.overall_progress}%` }))),
      el("p", { class: "muted small" }, "Progress of a project counts its phases - planning memo, each fieldwork step and the report - as not started (0), in process (1) or completed (2). A closed audit is 100%.")),
    el("div", { class: "card" }, el("h3", null, "Hours by quarter"),
      el("div", { class: "qbars tall" }, ...byQ.map((x) => el("div", { class: "qbar" },
        el("div", { class: "qbar-fill", style: `height:${Math.round((x.hours / maxQ) * 100)}%` }),
        el("div", { class: "qbar-n" }, `${x.hours}h`), el("div", { class: "qbar-l" }, x.q)))))));
  pane.append(el("div", { class: "two-col-wide" },
    el("div", { class: "card" }, el("h3", null, "Projects"),
      live.length ? el("div", { class: "table-wrap" }, el("table", { class: "dense" },
        el("thead", null, el("tr", null, ...["Project", "Quarter", "Budget", "Charged", "Progress"].map((h) => el("th", { scope: "col" }, h)))),
        el("tbody", null, ...live.map((r) => el("tr", { class: "no-click" },
          el("td", { class: "col-wide" }, r.title), el("td", null, r.quarter), el("td", { class: "num" }, `${r.hours}h`),
          el("td", { class: `num ${r.actual_hours > r.hours && r.hours ? "text-danger" : ""}` }, `${r.actual_hours}h`),
          el("td", null, progressBar(r.progress))))))) : el("p", { class: "muted small" }, "No projects yet.")),
    el("div", { class: "card" }, el("h3", null, "Hours by lead auditor"),
      byLead.length ? el("ul", { class: "cat-cov" }, ...byLead.map(([who, h]) => el("li", null, el("span", null, who), el("span", { class: "muted small" }, `${h}h`),
        progressBar(p.metrics.hours.planned ? (100 * h) / p.metrics.hours.planned : 0)))) : el("p", { class: "muted small" }, "No hours planned yet."))));
}
