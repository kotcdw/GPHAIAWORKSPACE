// GPHA Audit Workspace - planning & risk-control layer UI.
// Audit Universe, Assurance Plan, and the per-audit Risk & Control Matrix.
// Loaded after api.js and before app.js; uses the shared helpers from app.js
// (el, badge, modal, field, toast, notify, eSignModal, tabBar, stat, ...) at
// call time.

const QUARTERS = ["Q1", "Q2", "Q3", "Q4"];
const SCORES = [1, 2, 3, 4, 5];
const CONTROL_TYPES = ["Preventive", "Detective", "Corrective"];
const CONTROL_NATURES = ["Manual", "Automated", "IT-Dependent Manual"];
const FREQUENCIES = ["Annual", "Quarterly", "Monthly", "Weekly", "Daily", "Multiple Daily", "Ad Hoc"];
const TEST_TYPES = ["Walkthrough", "Design", "Operating Effectiveness"];
const TEST_CONCLUSIONS = ["Not Tested", "Effective", "Ineffective"];

function sel(options, value) {
  return el("select", null, ...options.map((o) =>
    el("option", { value: String(o), selected: String(o) === String(value) ? "1" : null }, String(o))));
}

function inp(placeholder, value = "", type = "text") {
  const node = el("input", { placeholder, type });
  node.value = value ?? "";
  return node;
}

function txt(placeholder, value = "") {
  const node = el("textarea", { placeholder });
  node.value = value ?? "";
  return node;
}

function btn(label, onclick, kind = "") {
  return el("button", { class: `btn small ${kind}`.trim(), onclick }, label);
}

function heat(score) {
  const level = score >= 15 ? "High" : score >= 8 ? "Medium" : "Low";
  return el("span", { class: `badge badge-risk-${level.toLowerCase()}`, title: `Score ${score}` }, `${level} (${score})`);
}

// ==================================================================== assurance plan

const PLAN_STATUSES = ["Draft", "In Review", "Submitted", "Returned", "Approved", "Distributed", "In Execution", "Revised", "Closed", "Archived"];

async function renderPlans(filter = state.planFilter || "") {
  state.planFilter = filter;
  clear(viewRoot);
  const msg = el("div");
  const pick = el("select", { class: "compact", "aria-label": "Filter by status" }, el("option", { value: "" }, "All current plans"),
    ...PLAN_STATUSES.map((s) => el("option", { value: s, selected: s === filter ? "1" : null }, s)));
  pick.addEventListener("change", () => renderPlans(pick.value));
  viewRoot.append(viewHeader("Assurance Plans", [pick, hasPerm("plan.prepare") ? btn("+ Create plan", () => newPlanModal()) : null]), msg);
  try {
    const plans = await API.get(filter ? `/api/assurance-plans?lifecycle_status=${encodeURIComponent(filter)}` : "/api/assurance-plans");
    const card = el("div", { class: "card" });
    viewRoot.append(card);
    if (!plans.length) {
      card.append(emptyState({ icon: "calendar-range", title: "No Assurance Plan yet",
        action: hasPerm("plan.prepare") ? btn("+ Create plan", () => newPlanModal()) : null }));
      return;
    }
    const rows = plans.map((p) => {
      const cells = { projects: el("td", { class: "num", "data-label": "Projects" }, "…"), hours: el("td", { "data-label": "Hours" }, "…"),
        progress: el("td", { "data-label": "Progress" }, "…"), coverage: el("td", { class: "num", "data-label": "Coverage" }, "…") };
      API.get(`/api/assurance-plans/${p.id}/program`).then((g) => {
        const m = g.metrics;
        const over = m.hours.available && m.hours.planned > m.hours.available;
        cells.projects.textContent = String(m.projects);
        cells.hours.replaceChildren(el("span", { class: over ? "text-danger" : null }, `${m.hours.planned}h`), el("span", { class: "muted" }, m.hours.available ? ` / ${m.hours.available}h` : " · no budget"));
        cells.progress.replaceChildren(progressBar(m.overall_progress));
        cells.coverage.textContent = `${m.coverage_pct}%`;
      }).catch(() => { Object.values(cells).forEach((c) => { c.textContent = "-"; }); });
      const period = p.period_start ? `${fmtDay(p.period_start)} – ${p.period_end ? fmtDay(p.period_end) : "?"}` : `FY${p.fiscal_year}`;
      return el("tr", { tabindex: "0", onclick: () => openPlan(p.id), onkeydown: (e) => { if (e.key === "Enter") openPlan(p.id); } },
        el("td", { class: "col-wide", "data-label": "Plan" }, el("span", { class: "ref" }, p.plan_ref), ` ${p.title}`, el("div", { class: "muted small" }, period)),
        el("td", { "data-label": "Status" }, statusBadge(p.lifecycle_status), p.current_version ? el("span", { class: "muted small" }, ` v${p.current_version}`) : null),
        cells.projects, cells.hours, cells.progress, cells.coverage,
        el("td", { class: "muted", "data-label": "Approved" }, p.approved_at ? fmtDay(p.approved_at.slice(0, 10)) : "-"));
    });
    card.append(el("div", { class: "table-wrap" }, el("table", { class: "dense" },
      el("thead", null, el("tr", null, ...["Plan", "Status", "Projects", "Hours planned / available", "Progress", "Coverage", "Approved"].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...rows))));
  } catch (err) { notify(msg, err.message, "error"); }
}

function planFields(withYear) {
  const y = currentFiscalYear();
  return [
    ...(withYear ? [{ name: "fiscal_year", label: "Plan year", type: "number", required: true, min: y - 2, max: y + 10 }] : []),
    { name: "title", label: "Plan name", required: true, maxLength: 255, singleLine: true },
    { name: "total_budget_hours", label: "Total available resources (hours)", type: "number", min: 0, max: 1000000,
      help: "The hours the team has for the year; project budgets are compared with it." },
    { name: "period_start", label: "Planning period from", type: "date" },
    { name: "period_end", label: "Planning period to", type: "date" },
    { name: "description", label: "Description / basis of the plan", type: "textarea", maxLength: 20000, full: true },
  ];
}

function newPlanModal() {
  const y = currentFiscalYear() + 1;
  openForm({
    title: "Create plan",
    key: "plan:new",
    meta: { title: "New Assurance Plan" },
    fields: planFields(true),
    initial: { fiscal_year: y, title: `Assurance Plan FY${y}`, total_budget_hours: 0, period_start: `${y}-01-01`, period_end: `${y}-12-31` },
    validate: (v) => (v.period_start && v.period_end && v.period_end < v.period_start ? { period_end: "The period ends before it starts" } : null),
    submitLabel: "Create plan",
    onSubmit: (v) => API.post("/api/assurance-plans", { ...v, total_budget_hours: v.total_budget_hours || 0, description: v.description || "",
      period_start: v.period_start || null, period_end: v.period_end || null }),
    onDone: (plan) => { toast("Plan created"); openPlan(plan.id); },
  });
}

function editPlanModal(plan) {
  openForm({
    title: `Edit ${plan.plan_ref}`,
    key: `plan:edit:${plan.id}`,
    meta: { title: `Edit plan ${plan.plan_ref}`, record_type: "assurance_plan", record_id: plan.id },
    fields: planFields(false),
    initial: plan,
    submitLabel: "Save changes",
    onSubmit: (v) => API.patch(`/api/assurance-plans/${plan.id}`, { ...v, total_budget_hours: v.total_budget_hours || 0, description: v.description || "",
      period_start: v.period_start || null, period_end: v.period_end || null }),
    onDone: () => { toast("Plan saved"); openPlan(plan.id); },
  });
}

async function openPlan(id) {
  setActiveNav("plans");
  clear(viewRoot);
  viewRoot.append(loadingState("Opening the plan…"));
  let plan;
  try { plan = await API.get(`/api/assurance-plans/${id}`); }
  catch (err) { clear(viewRoot); viewRoot.append(errorState(err, () => openPlan(id))); return; }
  clear(viewRoot);
  const draft = plan.status === "Draft";
  const approved = plan.status === "Approved";
  const s = plan.summary;

  const actions = [
    draft ? btn("Edit", () => editPlanModal(plan), "secondary") : null,
    hasPerm("plan.amend") && approved ? btn("Revise plan", () => revisePlanDialog(plan), "secondary") : null,
    hasPerm("plan.amend") && plan.status === "Closed" && !plan.archived_at ? btn("Archive", async () => {
      const ok = await confirmDialog({ title: "Archive plan year", text: "The plan becomes read-only and leaves the default plan list.", confirmLabel: "Archive" });
      if (!ok.ok) return;
      try { await API.post(`/api/assurance-plans/${id}/archive`); toast("Plan archived"); openPlan(id); }
      catch (err) { toast(err.message, "error"); }
    }, "secondary") : null,
    hasPerm("plan.amend") && approved ? btn("Close year", async () => {
      try { await API.post(`/api/assurance-plans/${id}/close`); toast("Plan closed"); openPlan(id); }
      catch (err) { toast(err.message, "error"); }
    }, "secondary") : null,
    iconBtn("printer", "Print", () => window.print()),
  ].filter(Boolean);
  // Diligent Assurance Plans layout: overview, projects, objectives and narratives (kept inside the audits), coverage,
  // strategic risks, resources; then approval and launch (GPHA planning cycle, IIA GIAS 9.4) and the records.
  const tabs = [
    { key: "overview", label: "Overview" },
    { key: "projects", label: "Projects", count: plan.engagements.filter((e) => e.status !== "Cancelled").length || null },
    { key: "objectives", label: "Objectives" },
    { key: "narratives", label: "Narratives" },
    { key: "coverage", label: "Coverage", count: s.uncovered_high_risk.length || null },
    { key: "risks", label: "Strategic risks" },
    { key: "resources", label: "Resources" },
    { key: "cycle", label: "Approval & launch" },
    { key: "crs", label: "Change requests" },
    { key: "activities", label: "Activities" },
  ];
  const layout = recordLayout({
    crumbs: recordCrumbs("plans", plan.plan_ref || `FY${plan.fiscal_year}`),
    back: () => navigate("plans"),
    title: plan.title.includes(String(plan.fiscal_year)) ? plan.title : `${plan.title} (FY${plan.fiscal_year})`,
    ref: plan.plan_ref, status: plan.lifecycle_status,
    meta: [plan.current_version ? el("span", { class: "chip-mini" }, `Version ${plan.current_version}`) : null,
      plan.approved_at ? el("span", { class: "muted small" }, `Approved ${fmtDay(plan.approved_at.slice(0, 10))}`) : null].filter(Boolean),
    band: planStepper(plan, (k) => layout.select(k)),
    actions, tabs, side: null,
    onTab: (key, pane) => { state.lastPlanTab = { id, key }; paint(key, pane); },
  });
  viewRoot.append(layout.root);

  function paint(key, pane) {
    if (key === "overview") renderPlanProgram(pane, plan, (k) => layout.select(k));
    if (key === "projects") renderEngagements(pane, plan);
    if (key === "objectives") renderPlanObjectives(pane, plan);
    if (key === "narratives") renderPlanNarratives(pane, plan);
    if (key === "coverage") renderPlanCoverage(pane, plan, "entities");
    if (key === "risks") renderPlanStrategicRisks(pane, plan);
    if (key === "resources") renderPlanResources(pane, plan);
    if (key === "cycle") {
      const cyc = el("div"); const log = el("div");
      pane.append(cyc);
      if (plan.committee_meeting_date) pane.append(committeeCard(plan));
      pane.append(log);
      renderPlanCycle(cyc, plan);
      renderPlanCycleLog(log, plan);
    }
    if (key === "crs") renderChangeRequests(pane, plan);
    if (key === "activities") {
      const box = el("div");
      let sub = "changes";
      const draw = () => {
        clear(box);
        box.append(subNav([{ key: "changes", label: "Plan changes" }, { key: "history", label: "History" }, { key: "approvals", label: "Approval cycles" }], sub,
          (k) => { sub = k; draw(); }, "Activity views"));
        const inner = el("div");
        box.append(inner);
        if (sub === "changes") renderPlanChanges(inner, plan);
        if (sub === "history") renderHistoryTab(inner, "assurance_plan", id);
        if (sub === "approvals") renderApprovalsTab(inner, "assurance_plan", id);
      };
      draw();
      pane.append(box);
    }
  }
  const remembered = state.lastPlanTab && state.lastPlanTab.id === id ? state.lastPlanTab.key : null;
  const legacy = { entities: "coverage" };
  layout.select(legacy[remembered] || (tabs.some((t) => t.key === remembered) ? remembered : "overview"));
}

async function renderEngagements(panel, plan) {
  const draft = plan.status === "Draft";
  const approved = plan.status === "Approved";
  const reload = () => openPlan(plan.id);
  state.planView = state.planView || "table";
  const canInclude = plan.status !== "Closed" && (draft || hasPerm("plan.amend")) && typeof includeAuditsDialog === "function";
  const card = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, "Projects"),
    el("div", { class: "actions" },
      subNav([{ key: "table", label: "Table" }, { key: "timeline", label: "Timeline" }], state.planView, (k) => { state.planView = k; clear(panel); renderEngagements(panel, plan); }, "Plan views"),
      draft && hasPerm("plan.prepare", "plan.amend") ? btn("+ Add to plan", () => addToPlan(plan)) : null,
      !draft && canInclude ? btn("Link active projects", () => includeAuditsDialog(plan, reload), "secondary") : null)));
  panel.append(card);
  if (state.planView === "timeline" && typeof planTimeline === "function") {
    const box = el("div");
    card.append(box);
    planTimeline(box, plan, reload);
    return;
  }
  if (!plan.engagements.length) card.append(emptyState({ icon: "kanban", title: "No projects yet" }));
  else card.append(el("div", { class: "table-wrap" }, el("table", { class: "dense" },
    el("thead", null, el("tr", null, el("th", null, "Quarter"), el("th", null, "Project"), el("th", null, "Entity"),
      el("th", null, "Risk"), el("th", null, "Site"), el("th", null, "Hours"), el("th", null, "Status"), el("th", null, ""))),
    el("tbody", null, ...plan.engagements.map((e) => el("tr", { class: `no-click ${e.status === "Cancelled" ? "row-muted" : ""}` },
      el("td", null, e.planned_quarter), el("td", { class: "col-wide" }, el("div", { class: "cell-title" }, e.title),
        el("div", { class: "muted small" }, [e.audit_type, e.program_name ? `Programme ${e.program_name}` : null,
          e.source_audit_ref ? `Roll forward of ${e.source_audit_ref}` : null].filter(Boolean).join(" · ")),
        e.rationale ? el("div", { class: "muted small" }, clip(e.rationale, 140)) : null),
      el("td", null, e.entity_unit_name || "-"),
      el("td", null, e.entity_risk_score ? heat(e.entity_risk_score) : "-"),
      el("td", null, e.site_name || el("span", { class: "muted" }, "-")),
      el("td", null, String(e.budget_hours)), el("td", null, badge(e.status)),
      el("td", null, el("div", { class: "actions" },
        e.audit_id ? btn("Open audit", () => openAudit(e.audit_id), "secondary") : null,
        e.audit_id && canInclude && e.status !== "Cancelled" ? btn("Exclude from audit plan", () => excludeFromPlan(plan, e, reload), "danger-ghost") : null,
        approved && e.status === "Planned" ? btn("Start", async () => {
          try { const r = await API.post(`/api/plan-engagements/${e.id}/start`); toast("Audit project created"); openAudit(r.audit_id); }
          catch (err) { toast(err.message, "error"); }
        }) : null,
        draft ? btn("Edit", () => addEngagement(plan, e), "secondary") : null,
        draft ? btn("Remove", async () => {
          try { await API.del(`/api/plan-engagements/${e.id}`); toast("Removed"); openPlan(plan.id); }
          catch (err) { toast(err.message, "error"); }
        }, "danger-ghost") : null))))))));
  if (approved) {
    card.append(el("p", { class: "muted" }, "Approved. Changes go through a change request."));
    if (plan.current_version && hasPerm("plan.prepare", "oversight.port", "audit.memo_approve")) {
      card.append(el("div", { style: "margin-top:12px" }, btn("Request a change", () => changeRequestEditor(plan))));
    }
  }
}

const APPROVAL_LABEL = { "Unit Head": "Unit Head", Manager: "Audit Manager", PIA: "PIA", CAE: "GM Audit" };

async function addEngagement(plan, eng = null) {
  const units = await safeGet("/api/entity-units?active_only=true", []);
  const leads = await safeGet("/api/users/directory", null);
  const programs = (await safeGet("/api/audit-programs", [])).filter((p) => p.status === "Active" && p.step_count);
  let types = [];
  try { types = (await loadEntityConfig()).types.audit_types || []; } catch { /* optional */ }
  let sites = [];
  try { sites = await planSites(); } catch { /* optional */ }
  openForm({
    title: eng ? `Edit project #${eng.id}` : "Create a new project",
    key: eng ? `engagement:edit:${eng.id}` : `engagement:new:${plan.id}`,
    meta: { title: eng ? `Edit engagement ${eng.title}` : `New engagement (${plan.plan_ref})`, record_type: "assurance_plan", record_id: plan.id },
    fields: [
      { name: "title", label: "Project title", required: true, maxLength: 255, singleLine: true },
      { name: "audit_type", label: "Audit type", type: "select", options: types, emptyLabel: "- choose -",
        help: "Decides the fieldwork workflow and whether the engagement is advisory." },
      { name: "entity_unit_id", label: "Auditable entity", type: "select", emptyLabel: "- none -",
        options: units.sort((a, b) => b.risk_score - a.risk_score).map((u) => ({ value: u.id, label: `${u.location_name} / ${u.name} (risk ${u.risk_score})` })) },
      { name: "site_entity_id", label: "Responsible site (HQ / port)", type: "select", emptyLabel: "- choose -",
        options: sites, help: "Decides which copy of the approved plan includes it. Destinations are set up by administrators on the Organizations register." },
      { name: "planned_quarter", label: "Quarter", type: "select", required: true, options: QUARTERS },
      { name: "budget_hours", label: "Budget hours", type: "number", min: 0, max: 10000 },
      ...(Array.isArray(leads) ? [{ name: "lead_auditor_id", label: "Lead auditor", type: "select", emptyLabel: "- not assigned -",
        options: leads.map((u) => ({ value: u.id, label: u.approval_level ? `${u.name} (${APPROVAL_LABEL[u.approval_level] || u.approval_level})` : u.name })) }] : []),
      ...(eng && eng.source_audit_id ? [] : [{ name: "program_id", label: "Audit programme (Project Library)", type: "select", emptyLabel: "- none: scope from the entity -",
        options: programs.map((p) => ({ value: p.id, label: `${p.prog_ref} ${p.name} (${p.step_count} steps)` })),
        help: "Its objectives, risks, controls and test steps are copied into the audit when it starts. Without one, the entity's linked risks and controls are scoped in." }]),
      { name: "rationale", label: "Rationale (risk, regulatory, management request ...)", type: "textarea", maxLength: 20000 },
    ],
    initial: eng ? { ...eng, audit_type: eng.audit_type || "", program_id: eng.program_id || "" } : { planned_quarter: "Q1", budget_hours: 0 },
    submitLabel: eng ? "Save changes" : "Add",
    onSubmit: (v) => {
      const body = { ...v, budget_hours: v.budget_hours || 0, rationale: v.rationale || "", audit_type: v.audit_type || "" };
      if ("program_id" in v) body.program_id = v.program_id ? Number(v.program_id) : 0;
      if (!eng) { body.audit_type = body.audit_type || null; if (!body.program_id) delete body.program_id; }
      return eng ? API.patch(`/api/plan-engagements/${eng.id}`, body) : API.post(`/api/assurance-plans/${plan.id}/engagements`, body);
    },
    onDone: () => { toast(eng ? "Project saved" : "Project added"); openPlan(plan.id); },
  });
}

// ==================================================================== risk & control matrix (audit tab)

async function renderRcm(panel, auditId) {
  const reload = () => { clear(panel); renderRcm(panel, auditId); };
  let rcm;
  try { rcm = await API.get(`/api/audits/${auditId}/rcm`); }
  catch (err) { panel.append(errorState(err, reload)); return; }
  const s = rcm.summary;
  const open = !rcm.locked;
  const eff = s.controls_by_effectiveness;
  const line = statusLine([[s.objectives, `objective${s.objectives === 1 ? "" : "s"}`], [s.risks, `risk${s.risks === 1 ? "" : "s"}`],
    [s.risks_by_rating.High, "high", "danger"], [s.controls, `control${s.controls === 1 ? "" : "s"}`], [s.key_controls, "key"],
    [eff.Effective, "effective", "ok"], [eff.Ineffective, "ineffective", "danger"], [s.tests_awaiting_review, "tests awaiting review", "warn"]]);
  if (line) panel.append(line);
  if (s.risks_without_controls.length) panel.append(el("div", { class: "callout warn" }, el("i", { class: "bi bi-exclamation-triangle" }),
    el("div", null, el("strong", null, "Risks without a mitigating control"), el("ul", null, ...s.risks_without_controls.map((g) => el("li", null, g))))));
  if (rcm.locked) panel.append(el("p", { class: "muted" }, "The audit is closed - the matrix is read-only."));
  if (!rcm.objectives.length) {
    panel.append(emptyState({ icon: "bullseye", title: "No objectives yet",
      action: open ? btn("Add objective", () => objectiveForm(auditId, null, reload)) : null }));
    return;
  }
  rcm.objectives.forEach((o) => panel.append(objectiveCard(o, open, reload)));
  if (open) panel.append(el("div", null, btn("Add objective", () => objectiveForm(auditId, null, reload), "secondary")));
}

function objectiveForm(auditId, o, reload) {
  openForm({
    title: o ? `Edit ${o.ref}` : "New objective",
    key: o ? `rcm:${auditId}:objective:edit:${o.id}` : `rcm:${auditId}:objective:new`,
    meta: { title: o ? `Edit objective ${o.ref}` : "New audit objective", record_type: "audit", record_id: auditId },
    fields: [
      { name: "title", label: "Objective", required: true, maxLength: 255, singleLine: true,
        placeholder: "e.g. Revenue is completely and accurately billed" },
      { name: "description", label: "Description", type: "textarea", maxLength: 20000 },
    ],
    initial: o || {},
    submitLabel: o ? "Save changes" : "Add",
    onSubmit: (v) => (o ? API.patch(`/api/objectives/${o.id}`, { ...v, description: v.description || "" })
      : API.post(`/api/audits/${auditId}/objectives`, { ...v, description: v.description || "" })),
    onDone: () => { toast("Objective saved"); reload(); },
  });
}

// Design result from the walkthrough / design test; operating result from the operating-effectiveness tests.
function controlResults(c) {
  const done = (c.tests || []).filter((t) => ["Completed", "Reviewed"].includes(t.status));
  const design = done.filter((t) => t.test_type !== "Operating Effectiveness");
  const oe = done.filter((t) => t.test_type === "Operating Effectiveness");
  const pick = (list, good, bad, none) => (list.some((t) => t.conclusion === "Ineffective") ? [bad, "danger"]
    : list.some((t) => t.conclusion === "Effective") ? [good, "ok"] : [none, ""]);
  return { design: pick(design, "Adequate", "Deficient", "Not assessed"), operating: pick(oe, "Effective", "Ineffective", "Not tested") };
}

// One objective of the risk & control matrix: a single matrix with a row per risk x control.
function objectiveCard(o, open, reload) {
  const card = el("div", { class: "card rcm-obj" });
  const attrs = typeof editAttributes === "function";
  card.append(el("div", { class: "card-head" },
    el("h3", null, el("span", { class: "ref" }, o.ref), ` ${o.title}`,
      typeof signoffCell === "function" ? el("span", { class: "muted small rcm-so" }, "Sign-offs ", signoffCell("rcm", o.id, o.rcm_signoffs, o.audit_id, `${o.ref} risk & control matrix`, reload)) : null),
    el("div", { class: "actions" },
      open ? btn("+ Risk", () => riskModal(o, null, reload), "secondary") : null,
      open ? btn("+ Control", () => controlModal(o, null, reload), "secondary") : null,
      open ? aiRiskAction(o, reload) : null,
      moreMenu([
        open ? ["Add controls from the library", () => fromLibraryDialog(o, reload)] : null,
        open ? ["Edit objective", () => objectiveForm(o.audit_id, o, reload)] : null,
        attrs ? ["Objective attributes", () => editAttributes("objectives", o.id, o.ref, reload, !open)] : null,
        open ? ["Delete objective", async () => {
          const ok = await confirmDialog({ title: "Delete objective", text: `${o.ref} and its risks and controls will be deleted.`, confirmLabel: "Delete", danger: true });
          if (!ok.ok) return;
          try { await API.del(`/api/objectives/${o.id}`); toast("Objective deleted"); reload(); } catch (err) { toast(err.message, "error"); }
        }, true] : null,
      ]))));
  if (o.description) card.append(el("p", { class: "muted small" }, o.description));
  if (!o.risks.length && !o.controls.length) {
    card.append(el("p", { class: "muted small" }, "No risks or controls yet."));
    return card;
  }
  const byId = Object.fromEntries(o.controls.map((c) => [c.id, c]));
  const linked = new Set(o.risks.flatMap((r) => r.control_ids));
  const riskCell = (r, span) => el("td", { class: "rcm-risk", rowspan: span > 1 ? String(span) : null, "data-label": "Risk" },
    el("button", { class: "rcm-link", type: "button", disabled: open ? null : "1", title: open ? "Edit the risk" : null, onclick: () => riskModal(o, r, reload) },
      el("span", { class: "ref" }, r.ref), ` ${r.title}`),
    r.enterprise_risk ? el("div", { class: "rcm-sub" }, el("i", { class: "bi bi-link-45deg" }), ` ${r.enterprise_risk}`) : null,
    attrs ? el("button", { class: "icon-link", type: "button", title: `${r.ref} attributes`, "aria-label": `${r.ref} attributes`,
      onclick: () => editAttributes("risks", r.id, r.ref, reload, !open) }, el("i", { class: "bi bi-sliders" })) : null);
  const ratingCell = (label, node, span) => el("td", { rowspan: span > 1 ? String(span) : null, "data-label": label }, node);
  const controlCells = (c) => {
    const res = controlResults(c);
    return [
      el("td", { "data-label": "Control" },
        el("button", { class: "rcm-link", type: "button", disabled: open ? null : "1", title: open ? "Edit the control" : null, onclick: () => controlModal(o, c, reload) },
          el("span", { class: "ref" }, c.ref), ` ${c.title}`),
        attrs ? el("button", { class: "icon-link", type: "button", title: `${c.ref} attributes`, "aria-label": `${c.ref} attributes`,
          onclick: () => editAttributes("controls", c.id, c.ref, reload, !open) }, el("i", { class: "bi bi-sliders" })) : null,
        c.owner_email ? el("div", { class: "rcm-sub" }, c.owner_email) : null),
      el("td", { "data-label": "Key" }, c.is_key ? "Yes" : "No"),
      el("td", { "data-label": "Type" }, c.control_type, el("div", { class: "rcm-sub" }, `${c.nature} · ${c.frequency}`)),
      el("td", { "data-label": "Design" }, el("span", { class: `outcome ${res.design[1] === "danger" ? "bad" : res.design[1]}` }, res.design[0])),
      el("td", { "data-label": "Operating" }, el("span", { class: `outcome ${res.operating[1] === "danger" ? "bad" : res.operating[1]}` }, res.operating[0])),
    ];
  };
  const rows = [];
  o.risks.forEach((r) => {
    const cs = r.control_ids.map((id) => byId[id]).filter(Boolean);
    const span = Math.max(cs.length, 1);
    if (!cs.length) {
      rows.push(el("tr", { class: "no-click rcm-first" }, riskCell(r, 1), ratingCell("Inherent", heat(r.inherent_score), 1),
        el("td", { colspan: "5", class: "rcm-gap", "data-label": "Control" }, el("i", { class: "bi bi-exclamation-triangle" }), " No mitigating control"),
        ratingCell("Residual", badge(r.residual_rating), 1)));
      return;
    }
    cs.forEach((c, i) => rows.push(el("tr", { class: `no-click ${i === 0 ? "rcm-first" : ""}` },
      ...(i === 0 ? [riskCell(r, span), ratingCell("Inherent", heat(r.inherent_score), span)] : []),
      ...controlCells(c),
      ...(i === 0 ? [ratingCell("Residual", badge(r.residual_rating), span)] : []))));
  });
  const orphans = o.controls.filter((c) => !linked.has(c.id));
  orphans.forEach((c, i) => rows.push(el("tr", { class: `no-click ${i === 0 ? "rcm-first" : ""}` },
    ...(i === 0 ? [el("td", { class: "rcm-risk muted", rowspan: orphans.length > 1 ? String(orphans.length) : null, "data-label": "Risk" }, "Not linked to a risk"),
      el("td", { rowspan: orphans.length > 1 ? String(orphans.length) : null }, "-")] : []),
    ...controlCells(c),
    ...(i === 0 ? [el("td", { rowspan: orphans.length > 1 ? String(orphans.length) : null }, "-")] : []))));
  card.append(el("div", { class: "table-wrap" }, el("table", { class: "dense rcm-matrix" },
    el("thead", null, el("tr", null, ...["Risk", "Inherent", "Control", "Key", "Type", "Design", "Operating", "Residual"].map((h) => el("th", { scope: "col" }, h)))),
    el("tbody", null, ...rows))));
  return card;
}

const LIKELIHOOD = SCORES.map((n) => ({ value: n, label: `${n} - ${["Rare", "Unlikely", "Possible", "Likely", "Almost certain"][n - 1]}` }));
const IMPACT = SCORES.map((n) => ({ value: n, label: `${n} - ${["Minimal", "Minor", "Moderate", "Major", "Severe"][n - 1]}` }));

async function riskModal(o, risk, reload) {
  const ers = (await safeGet("/api/object-library/options", { risks: [] })).risks;
  openForm({
    title: risk ? `Edit ${risk.ref}` : `New risk under ${o.ref}`,
    key: risk ? `rcm:${o.audit_id}:risk:edit:${risk.id}` : `rcm:${o.audit_id}:risk:new:${o.id}`,
    meta: { title: risk ? `Edit risk ${risk.ref}` : `New risk (${o.ref})`, record_type: "audit", record_id: o.audit_id },
    fields: [
      { name: "title", label: "Risk", required: true, maxLength: 255, singleLine: true, placeholder: "What could go wrong?" },
      { name: "likelihood", label: "Likelihood", type: "select", required: true, options: LIKELIHOOD },
      { name: "impact", label: "Impact", type: "select", required: true, options: IMPACT },
      { name: "enterprise_risk_id", label: "Tests enterprise risk (Risk Manager)", type: "select", emptyLabel: "- none -",
        options: ers.map((r) => ({ value: r.id, label: r.label })) },
      { name: "description", label: "Description", type: "textarea", maxLength: 20000 },
    ],
    initial: risk || { likelihood: 3, impact: 3 },
    submitLabel: "Save",
    onSubmit: (v) => {
      const body = { ...v, description: v.description || "", enterprise_risk_id: v.enterprise_risk_id ? Number(v.enterprise_risk_id) : (risk ? 0 : null) };
      return risk ? API.patch(`/api/risks/${risk.id}`, body) : API.post(`/api/objectives/${o.id}/risks`, body);
    },
    onDone: (r) => { toast(`Risk saved - inherent ${r.inherent_rating} (${r.inherent_score})`); reload(); },
  });
}

function controlModal(o, control, reload) {
  openForm({
    title: control ? `Edit ${control.ref}` : `New control under ${o.ref}`,
    key: control ? `rcm:${o.audit_id}:control:edit:${control.id}` : `rcm:${o.audit_id}:control:new:${o.id}`,
    meta: { title: control ? `Edit control ${control.ref}` : `New control (${o.ref})`, record_type: "audit", record_id: o.audit_id },
    fields: [
      { name: "title", label: "Control", required: true, maxLength: 255, singleLine: true },
      { name: "owner_email", label: "Control owner email", type: "email" },
      { name: "control_type", label: "Type", type: "select", required: true, options: CONTROL_TYPES },
      { name: "nature", label: "Nature", type: "select", required: true, options: CONTROL_NATURES },
      { name: "frequency", label: "Frequency", type: "select", required: true, options: FREQUENCIES },
      { name: "is_key", label: "Key control", type: "checkbox" },
      { name: "risk_ids", label: "Mitigates risks", type: "checklist", emptyLabel: "Add risks to this objective first.",
        options: o.risks.map((r) => ({ value: r.id, label: `${r.ref} ${r.title}` })) },
      { name: "description", label: "Control description (what, who, when, evidence)", type: "textarea", maxLength: 20000 },
    ],
    validate: (v) => (!v.risk_ids.length && o.risks.length ? { risk_ids: "Link the control to at least one risk it mitigates" } : {}),
    initial: control || { control_type: "Preventive", nature: "Manual", frequency: "Monthly", is_key: true, risk_ids: [] },
    submitLabel: "Save",
    onSubmit: async (v) => {
      const { risk_ids: riskIds, ...rest } = v;
      const body = { ...rest, owner_email: rest.owner_email || null, description: rest.description || "" };
      if (control) {
        await API.patch(`/api/controls/${control.id}`, body);
        return API.put(`/api/controls/${control.id}/risks`, { risk_ids: riskIds });
      }
      return API.post(`/api/objectives/${o.id}/controls`, { ...body, risk_ids: riskIds });
    },
    onDone: () => { toast("Control saved"); reload(); },
  });
}

async function testModal(control, t, open, reload) {
  const locked = !open || t.status === "Reviewed";
  const rec = await safeGet(`/api/control-tests/${t.id}/sample-recommendation`, null);
  const info = el("div", { class: "muted test-info" },
    rec ? el("div", null, `Recommended sample: ${rec.recommended_size} - ${rec.basis}.`) : null,
    t.sample_items ? el("div", null, `Selected items: ${t.sample_items} (seed ${t.sample_seed})`) : null,
    t.reviewed_at ? el("div", null, `Reviewed ${fmtDate(t.reviewed_at)}${t.review_comment ? `: ${t.review_comment}` : ""}`) : null,
    !t.reviewed_at && t.review_comment ? el("div", null, `Review note: ${t.review_comment}`) : null);
  const fields = [
    { name: "population_size", label: "Population size", type: "number", min: 0, max: 1000000, disabled: locked },
    { name: "sample_size", label: "Sample size", type: "number", min: 0, max: 1000000, disabled: locked,
      help: rec ? `Leave blank when drawing a sample to use the recommended ${rec.recommended_size}` : undefined },
    { name: "exceptions_found", label: "Exceptions found", type: "number", min: 0, disabled: locked },
    { name: "conclusion", label: "Conclusion", type: "select", required: true, options: TEST_CONCLUSIONS, disabled: locked },
    { name: "status", label: "Status", type: "select", required: true, options: ["In Progress", "Completed"], disabled: locked },
    { name: "procedure", label: "Procedure", type: "textarea", maxLength: 20000, disabled: locked },
    { name: "results", label: "Results / exceptions noted", type: "textarea", maxLength: 20000, disabled: locked },
  ];
  const validate = (v) => {
    const e = {};
    if (v.sample_size != null && v.population_size != null && v.sample_size > v.population_size) e.sample_size = "Sample size cannot exceed the population";
    const limit = v.sample_size ?? v.population_size;
    if (v.exceptions_found != null && limit != null && v.exceptions_found > limit) e.exceptions_found = `Cannot exceed the ${limit} items tested`;
    if (v.status === "Completed" && v.conclusion === "Not Tested") e.conclusion = "Record a conclusion before completing";
    if (v.status === "Completed" && v.conclusion === "Ineffective" && !(v.results || "").trim()) e.results = "Describe the exceptions found";
    if (v.conclusion === "Ineffective" && !v.exceptions_found) e.exceptions_found = "An ineffective conclusion needs at least one exception";
    if (v.conclusion === "Effective" && v.exceptions_found > 0) e.conclusion = "Exceptions were found - the control cannot be concluded Effective";
    return e;
  };
  let handle;
  const sampleBtn = locked ? null : el("button", { class: "btn secondary", type: "button", onclick: async () => {
    const v = handle.values();
    if (!v.population_size) { toast("Enter the population size first", "error"); return; }
    try {
      await handle.flush();
      await API.post(`/api/control-tests/${t.id}/sample`, { population_size: v.population_size, sample_size: v.sample_size || null });
      toast("Sample drawn - reopen the test to see the selected items");
      closeFormPanel(); reload();
    } catch (err) { toast(err.message, "error"); }
  } }, "Draw random sample");
  const initial = { ...t, status: t.status === "Not Started" ? "In Progress" : t.status };
  if (locked) {
    const holder = el("div");
    const h = mountForm(holder, { fields, initial, draftable: false, onSubmit: async () => {} });
    modal({ title: `${t.ref} - ${t.test_type} (${t.status})`, body: el("div", null, h.body, info), width: 760 });
    return;
  }
  handle = openForm({
    title: `${t.ref} - ${t.test_type}`,
    key: `rcm:${control.audit_id || "x"}:test:edit:${t.id}`,
    meta: { title: `Test ${t.ref} on ${control.ref}`, record_type: "audit", record_id: control.audit_id || null },
    fields, initial, validate, extra: info,
    actions: sampleBtn ? [sampleBtn] : [],
    submitLabel: "Save",
    onSubmit: (v) => API.patch(`/api/control-tests/${t.id}`, {
      procedure: v.procedure || "", results: v.results || "", exceptions_found: v.exceptions_found || 0,
      population_size: v.population_size, sample_size: v.sample_size, conclusion: v.conclusion, status: v.status,
    }),
    onDone: () => { toast("Test saved"); reload(); },
  });
}

// ==================================================================== issue (finding) detail

async function issueForm(f, auditId, canWrite, onSaved) {
  const isNew = !f;
  const respondOnly = !canWrite;
  const ro = respondOnly;
  const auditType = auditId ? ((await safeGet(`/api/audits/${auditId}`, {})).audit_type || "") : "";
  const cfDefs = customFieldDefs(await safeGet(`/api/custom-fields?module=findings&audit_type=${encodeURIComponent(auditType)}`, [])).map((x) => ({ ...x, name: x.key, disabled: ro }));
  const issueTypes = canWrite ? await safeGet("/api/findings/issue-types", []) : [];
  if (f && f.issue_type && !issueTypes.includes(f.issue_type)) issueTypes.push(f.issue_type);
  const fields = [
    { name: "title", label: "Title/Headline", required: true, maxLength: 255, singleLine: true, disabled: ro },
    { name: "risk_rating", label: "Severity", type: "select", required: true, options: RISK_RATINGS, disabled: ro },
    ...(canWrite ? [{ name: "issue_type", label: "Issue type", type: "select", emptyLabel: "- not set -", options: issueTypes }] : []),
    { name: "status", label: "Status", type: "select", required: true, options: FINDING_STATUSES, disabled: ro,
      help: f && f.remediation ? `Remediation: ${f.remediation.state}${f.remediation.refs.length ? ` (${f.remediation.refs.join(", ")})` : ""}. A finding closes when its actions are verified as effective.` : "A finding closes when its remediation actions are verified as effective." },
    { name: "assigned_owner_email", label: "Owner", type: "email", disabled: ro, help: "The owner's e-mail; they are notified once the issue is published" },
    { name: "criteria", label: "Criteria (what should be)", type: "textarea", maxLength: 20000, disabled: ro, full: true },
    { name: "condition", label: "Condition (what was found)", type: "textarea", maxLength: 20000, disabled: ro, full: true },
    { name: "recommendation", label: "Recommendation", type: "textarea", maxLength: 20000, disabled: ro },
    { type: "heading", label: "Show more" },
    { name: "effect", label: "Effect (Risk / Impact)", type: "textarea", maxLength: 20000, disabled: ro },
    { name: "cause", label: "Cause", type: "textarea", maxLength: 20000, disabled: ro },
    { name: "root_cause_whys", label: "Root cause - 5 Whys", type: "whys", disabled: ro },
    { name: "description", label: "Additional notes", type: "textarea", maxLength: 20000, disabled: ro },
    ...cfDefs,
    ...(isNew ? [] : [
      { type: "heading", label: "Responses (GPHA working paper template)" },
      { name: "client_response", label: "Audit client response (Head of Department)", type: "textarea", maxLength: 10000, full: true,
        disabled: !canWrite && f.client_confirmed_at_exit,
        help: f.client_confirmed_at_exit ? "Confirmed at the exit meeting" : "As captured and confirmed at the exit meeting" },
      ...(canWrite ? [{ name: "client_confirmed_at_exit", label: "Confirmed at the exit meeting", type: "checkbox" }] : []),
      { name: "management_response", label: "Management response - action plan", type: "textarea", maxLength: 10000, full: true },
      { name: "responsible_officer", label: "Responsible officer", maxLength: 255, singleLine: true,
        help: "Name, or e-mail to make them the owner of the corrective action" },
      { name: "target_date", label: "Target date", type: "date" },
    ]),
  ];
  const raiseAction = !isNew && canWrite ? el("button", { class: "btn secondary", type: "button", onclick: async () => {
    try { const c = await API.post(`/api/findings/${f.id}/raise-action`); toast(`Action ${c.capa_ref} raised`); closeFormPanel(); onSaved(); }
    catch (err) { toast(err.message, "error"); }
  } }, "Raise remediation") : null;
  const aiAction = !isNew && canWrite ? aiFindingAction(f.id, () => handle, fields) : null;
  const handle = openForm({
    title: isNew ? "New finding / issue" : `Issue #${f.id}: ${f.title}`,
    key: isNew ? `finding:new:${auditId}` : `finding:edit:${f.id}`,
    meta: { title: isNew ? "New finding" : `Issue #${f.id} ${f.title}`, record_type: "audit", record_id: auditId },
    fields,
    initial: f ? { ...f, ...Object.fromEntries(Object.entries(f.custom_fields || {}).map(([k, x]) => [`cf_${k}`, x])) } : { risk_rating: "Medium", status: "Open" },
    width: 900,
    actions: [aiAction, raiseAction, ...(typeof issueExtraActions === "function" ? issueExtraActions(f, auditId, canWrite && !isNew, onSaved) : [])].filter(Boolean),
    intro: f && canWrite ? el("div", { class: "issue-meta" },
      f.published ? el("span", { class: "outcome ok" }, el("i", { class: "bi bi-eye" }), ` Published${f.published_at ? ` ${fmtDay(f.published_at.slice(0, 10))}` : ""}`)
        : el("span", { class: "outcome" }, el("i", { class: "bi bi-eye-slash" }), " Not published - the auditee cannot see this issue yet"),
      f.signoffs ? el("span", { class: "issue-so" }, "Sign-offs ", signoffDots(f.signoffs)) : null,
      f.procedure_id ? el("span", { class: "muted small" }, "Raised from a Workplan procedure") : null) : null,
    validate: (v) => (v.status === "Closed" && !respondOnly && !(v.recommendation || "").trim() && !(v.condition || "").trim()
      ? { condition: "Document the condition (or recommendation) before closing the issue" } : {}),
    submitLabel: isNew ? "Create" : "Save",
    onSubmit: async (v) => {
      const { management_response: response, responsible_officer: officer, target_date: target,
        client_response: clientText, client_confirmed_at_exit: confirmed, ...all } = v;
      const saveResponses = async () => {
        const text = (clientText || "").trim();
        if (text && (text !== (f.client_response || "") || (canWrite && !!confirmed !== !!f.client_confirmed_at_exit))) {
          await API.post(`/api/findings/${f.id}/client-response`, { client_response: text, confirmed_at_exit: canWrite ? !!confirmed : false });
        }
        const plan = (response || "").trim();
        const changed = plan !== (f.management_response || "") || (officer || "") !== (f.responsible_officer || "")
          || (target || "") !== (f.target_date || "").slice(0, 10);
        if (plan && changed) {
          return API.post(`/api/findings/${f.id}/response`, { management_response: plan, responsible_officer: (officer || "").trim() || null, target_date: target || null });
        }
        return null;
      };
      if (respondOnly) {
        if (!(clientText || "").trim() && !(response || "").trim()) {
          throw Object.assign(new Error("Enter a response"), { errors: [{ field: "client_response", message: "Enter your response or an action plan" }] });
        }
        return (await saveResponses()) || f;
      }
      const rest = {};
      const custom = {};
      Object.entries(all).forEach(([k, x]) => { if (k.startsWith("cf_")) custom[k.slice(3)] = x === "" ? null : x; else rest[k] = x; });
      const body = { ...rest, assigned_owner_email: rest.assigned_owner_email || null, ...("issue_type" in rest ? { issue_type: rest.issue_type || null } : {}), ...(cfDefs.length ? { custom_fields: custom } : {}) };
      const saved = isNew ? await API.post(`/api/audits/${auditId}/findings`, body) : await API.patch(`/api/findings/${f.id}`, body);
      if (!isNew) await saveResponses();
      return saved;
    },
    onDone: () => { toast(isNew ? "Finding created" : "Issue saved"); onSaved(); },
  });
}

// ------------------------------------------------------------------ draft resume handlers

function registerPlanningOpeners() {
  registerFormOpener("plan:new", () => { navigate("plans"); newPlanModal(); });
  registerFormOpener("plan:edit:", async (key) => {
    const id = key.split(":")[2];
    await openPlan(id);
    editPlanModal(await API.get(`/api/assurance-plans/${id}`));
  });
  registerFormOpener("engagement:new:", async (key) => {
    const id = key.split(":")[2];
    await openPlan(id);
    addEngagement(await API.get(`/api/assurance-plans/${id}`));
  });
  registerFormOpener("engagement:edit:", async (key, d) => {
    const plan = await API.get(`/api/assurance-plans/${d.record_id}`);
    await openPlan(plan.id);
    const eng = plan.engagements.find((e) => String(e.id) === key.split(":")[2]);
    if (eng) addEngagement(plan, eng);
  });
  registerFormOpener("finding:new:", async (key) => { const aid = key.split(":")[2]; await openAudit(aid); issueForm(null, aid, true, () => openAudit(aid)); });
  registerFormOpener("finding:edit:", async (key, d) => {
    const f = await API.get(`/api/findings/${key.split(":")[2]}`);
    await openAudit(f.audit_id);
    issueForm(f, f.audit_id, canWriteModule("audits"), () => openAudit(f.audit_id));
  });
  // rcm:<auditId>:<kind>:<new|edit>:<id>
  registerFormOpener("rcm:", async (key) => {
    const [, aid, kind, mode, id] = key.split(":");
    await openAudit(aid);
    const rcm = await API.get(`/api/audits/${aid}/rcm`);
    const reload = () => openAudit(aid);
    const objectives = rcm.objectives;
    const controls = objectives.flatMap((o) => o.controls.map((c) => ({ ...c, audit_id: Number(aid) })));
    if (kind === "objective") return objectiveForm(aid, mode === "edit" ? objectives.find((o) => String(o.id) === id) : null, reload);
    if (kind === "risk") {
      if (mode === "new") return riskModal(objectives.find((o) => String(o.id) === id), null, reload);
      const o = objectives.find((x) => x.risks.some((r) => String(r.id) === id));
      return o && riskModal(o, o.risks.find((r) => String(r.id) === id), reload);
    }
    if (kind === "control") {
      if (mode === "new") return controlModal(objectives.find((o) => String(o.id) === id), null, reload);
      const o = objectives.find((x) => x.controls.some((c) => String(c.id) === id));
      return o && controlModal(o, o.controls.find((c) => String(c.id) === id), reload);
    }
    if (kind === "test") {
      const c = controls.find((x) => x.tests.some((t) => String(t.id) === id));
      return c && testModal(c, c.tests.find((t) => String(t.id) === id), !rcm.locked, reload);
    }
    return null;
  });
}

// ==================================================================== Audit Committee approval + plan changes (GIAS 9.4)

function committeeCard(plan) {
  const canRecord = hasPerm("plan.amend") && plan.status === "Approved" && !!plan.committee_meeting_date;
  const card = el("div", { class: `callout ${plan.committee_meeting_date ? "ok" : "warn"}` },
    el("i", { class: `bi bi-${plan.committee_meeting_date ? "patch-check" : "people"}` }),
    el("div", { style: "flex:1" }, plan.committee_meeting_date
      ? [el("strong", null, "Approved by the Audit Committee"), ` on ${fmtDate(plan.committee_meeting_date).split(",")[0]} (ref ${plan.committee_reference}).`,
        plan.committee_notes ? el("div", { class: "muted small" }, plan.committee_notes) : null]
      : [el("strong", null, "Audit Committee approval not yet recorded. "), "After the CAE's approval, present the plan to the Audit Committee and record its decision here."]),
    canRecord ? btn(plan.committee_meeting_date ? "Update" : "Record Audit Committee approval", () => committeeForm(plan), plan.committee_meeting_date ? "secondary" : "") : null);
  return card;
}

function committeeForm(plan) {
  openForm({
    key: `committee:${plan.id}`, title: "Audit Committee approval", width: 600, draftable: false,
    fields: [
      { name: "meeting_date", label: "Meeting date", type: "date", required: true, notFuture: true },
      { name: "reference", label: "Minute / resolution reference", required: true, maxLength: 100, singleLine: true },
      { name: "notes", label: "Committee comments", type: "textarea", maxLength: 5000, full: true },
    ],
    initial: { meeting_date: plan.committee_meeting_date, reference: plan.committee_reference || "", notes: plan.committee_notes || "" },
    submitLabel: "Save",
    onSubmit: (v) => API.post(`/api/assurance-plans/${plan.id}/committee-approval`, { ...v, meeting_date: `${v.meeting_date}T00:00:00` }),
    onDone: () => { toast("Audit Committee approval recorded"); openPlan(plan.id); },
  });
}

async function renderPlanChanges(panelEl, plan) {
  const card = el("div", { class: "card" }, el("h3", null, "Changes to the plan"));
  panelEl.append(card);
  try {
    const rows = await API.get(`/api/assurance-plans/${plan.id}/changes`);
    card.append(dataTable(rows, [
      { key: "changed_at", label: "Date", render: (c) => fmtDate(c.changed_at).split(",")[0], sortValue: (c) => c.changed_at },
      { key: "change_type", label: "Change", render: (c) => badge(c.change_type) },
      { key: "description", label: "What changed" },
      { key: "reason", label: "Reason", render: (c) => c.reason || el("span", { class: "muted" }, "-") },
      { key: "changed_by", label: "By" },
    ], { exportName: `${plan.plan_ref}-changes.csv`, emptyText: "No changes since approval." }));
  } catch (err) { card.append(el("div", { class: "muted" }, err.message)); }
}

