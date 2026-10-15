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

// ==================================================================== universe (legacy forms; the screens are in universe.js)

const CODE_RULE = { pattern: "^[A-Za-z0-9][A-Za-z0-9_-]{0,19}$", patternMessage: "Use 1-20 letters, digits, '-' or '_' (e.g. TEMA, GJT-01)", maxLength: 20 };

function locationForm() {
  openForm({
    title: "New location",
    key: "location:new",
    meta: { title: "New location" },
    fields: [
      { name: "code", label: "Code", required: true, ...CODE_RULE, help: "Short code, e.g. TEMA" },
      { name: "name", label: "Name", required: true, maxLength: 255, singleLine: true },
      { name: "description", label: "Description", type: "textarea", maxLength: 20000 },
    ],
    submitLabel: "Add location",
    onSubmit: (v) => API.post("/api/locations", { ...v, code: v.code.toUpperCase() }),
    onDone: () => { toast("Location added"); renderUniverse(); },
  });
}

function editUnit(unit, locations = []) {
  const scores = SCORES.map((n) => ({ value: n, label: `${n} - ${["Rare", "Unlikely", "Possible", "Likely", "Almost certain"][n - 1]}` }));
  const impacts = SCORES.map((n) => ({ value: n, label: `${n} - ${["Minimal", "Minor", "Moderate", "Major", "Severe"][n - 1]}` }));
  const fields = [
    ...(unit ? [] : [
      { name: "location_id", label: "Location", type: "select", required: true, options: locations.map((l) => ({ value: l.id, label: `${l.code} - ${l.name}` })) },
      { name: "code", label: "Code", required: true, ...CODE_RULE, help: "e.g. GJT" },
    ]),
    { name: "name", label: "Name", required: true, maxLength: 255, singleLine: true },
    { name: "owner_email", label: "Owner email", type: "email" },
    { name: "risk_likelihood", label: "Likelihood", type: "select", required: true, options: scores },
    { name: "risk_impact", label: "Impact", type: "select", required: true, options: impacts },
    { name: "description", label: "Description", type: "textarea", maxLength: 20000 },
  ];
  openForm({
    title: unit ? `Edit ${unit.name}` : "New entity unit",
    key: unit ? `unit:edit:${unit.id}` : "unit:new",
    meta: { title: unit ? `Edit entity unit ${unit.name}` : "New entity unit" },
    fields,
    initial: unit || { risk_likelihood: 3, risk_impact: 3 },
    submitLabel: "Save",
    onSubmit: (v) => {
      const body = { name: v.name, owner_email: v.owner_email || null, description: v.description || "",
        risk_likelihood: v.risk_likelihood, risk_impact: v.risk_impact };
      return unit ? API.patch(`/api/entity-units/${unit.id}`, body)
        : API.post("/api/entity-units", { ...body, location_id: v.location_id, code: v.code.toUpperCase() });
    },
    onDone: () => { toast("Entity unit saved"); renderUniverse(); },
  });
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
  viewRoot.append(viewHeader("Assurance Plan", [pick, hasPerm("plan.prepare") ? btn("New plan", () => newPlanModal()) : null],
    { sub: "Draft → In Review → Submitted → Approved → Distributed → In Execution → Closed → Archived (Returned and Revised when sent back or revised)" }), msg);
  try {
    const plans = await API.get(filter ? `/api/assurance-plans?lifecycle_status=${encodeURIComponent(filter)}` : "/api/assurance-plans");
    const card = el("div", { class: "card" });
    if (!plans.length) card.append(el("div", { class: "empty" }, "No Assurance Plan yet. Create the plan for the fiscal year to start."));
    else card.append(el("table", null,
      el("thead", null, el("tr", null, el("th", null, "Ref"), el("th", null, "Fiscal year"), el("th", null, "Title"),
        el("th", null, "Status"), el("th", null, "Approved"))),
      el("tbody", null, ...plans.map((p) => el("tr", { onclick: () => openPlan(p.id) },
        el("td", { class: "ref" }, p.plan_ref), el("td", null, `FY${p.fiscal_year}`), el("td", null, p.title),
        el("td", null, badge(p.lifecycle_status), p.current_version ? el("span", { class: "muted small" }, ` v${p.current_version}`) : null),
        el("td", { class: "muted" }, fmtDate(p.approved_at)))))));
    viewRoot.append(card);
  } catch (err) { notify(msg, err.message, "error"); }
}

function planFields(withYear) {
  const y = new Date().getFullYear();
  return [
    ...(withYear ? [{ name: "fiscal_year", label: "Fiscal year", type: "number", required: true, min: y - 2, max: y + 10 }] : []),
    { name: "title", label: "Title", required: true, maxLength: 255, singleLine: true },
    { name: "total_budget_hours", label: "Total budget hours", type: "number", min: 0, max: 1000000 },
    { name: "description", label: "Description / basis of the plan", type: "textarea", maxLength: 20000 },
  ];
}

function newPlanModal() {
  const y = new Date().getFullYear() + 1;
  openForm({
    title: "New Assurance Plan",
    key: "plan:new",
    meta: { title: "New Assurance Plan" },
    fields: planFields(true),
    initial: { fiscal_year: y, title: `Assurance Plan FY${y}`, total_budget_hours: 0 },
    submitLabel: "Create",
    onSubmit: (v) => API.post("/api/assurance-plans", { ...v, total_budget_hours: v.total_budget_hours || 0, description: v.description || "" }),
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
    onSubmit: (v) => API.patch(`/api/assurance-plans/${plan.id}`, { ...v, total_budget_hours: v.total_budget_hours || 0, description: v.description || "" }),
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
  // HighBond assurance plan: Overview, Entities (coverage grid), Risks, then the GPHA planning cycle records.
  const tabs = [
    { key: "overview", label: "Overview" },
    { key: "entities", label: "Entities" },
    { key: "risks", label: "Risks", count: s.uncovered_high_risk.length || null },
    { key: "cycle", label: "Versions & cycle" },
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
    actions, tabs, side: null,
    onTab: (key, pane) => { state.lastPlanTab = { id, key }; paint(key, pane); },
  });
  viewRoot.append(layout.root);

  function paint(key, pane) {
    if (key === "overview") planOverview(pane, plan);
    if (key === "entities") renderPlanCoverage(pane, plan, "entities");
    if (key === "risks") renderPlanCoverage(pane, plan, "risks");
    if (key === "cycle") renderPlanCycleLog(pane, plan);
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
  layout.select(remembered || "overview");
}

function planOverview(pane, plan) {
  const s = plan.summary;
  const hoursPct = s.budget_hours ? Math.round((100 * s.planned_hours) / s.budget_hours) : null;
  const maxQ = Math.max(1, ...QUARTERS.map((q) => s.by_quarter[q] || 0));
  pane.append(el("div", { class: "stats" },
    stat(s.engagements - s.cancelled, "Planned engagements", `${s.started} started · ${s.planned} not started`),
    stat(`${s.planned_hours}h`, "Hours planned", s.budget_hours ? `${hoursPct}% of ${s.budget_hours}h budget` : "No budget set",
      hoursPct !== null && hoursPct > 100 ? "danger" : ""),
    stat(`${s.coverage_pct}%`, "Universe coverage", `${s.covered_units} of ${s.universe_units} entity units`),
    el("div", { class: "stat" }, el("div", { class: "l" }, "By quarter"),
      el("div", { class: "qbars" }, ...QUARTERS.map((q) => el("div", { class: "qbar" },
        el("div", { class: "qbar-fill", style: `height:${Math.round(((s.by_quarter[q] || 0) / maxQ) * 100)}%` }),
        el("div", { class: "qbar-n" }, String(s.by_quarter[q] || 0)), el("div", { class: "qbar-l" }, q))))),
    stat(s.uncovered_high_risk.length, "High-risk units not planned", s.uncovered_high_risk.length ? "Review before approval" : "All covered",
      s.uncovered_high_risk.length ? "warn" : "ok"),
  ));
  if (s.uncovered_high_risk.length) {
    pane.append(el("div", { class: "callout warn" }, el("i", { class: "bi bi-exclamation-triangle" }),
      el("div", null, el("strong", null, "High-risk entities not in the plan: "),
        ...s.uncovered_high_risk.flatMap((u, i) => [i ? ", " : "", `${u.location_name} / ${u.name} `, heat(u.risk_score)]))));
  }
  if (plan.description) pane.append(el("div", { class: "card" }, el("div", { class: "lf-label" }, "Basis of the plan"), el("div", { class: "lf-value" }, plan.description)));
  const cycleSlot = el("div");
  pane.append(cycleSlot);
  renderPlanCycle(cycleSlot, plan);
  if (plan.committee_meeting_date) pane.append(committeeCard(plan));
  const eng = el("div");
  pane.append(eng);
  renderEngagements(eng, plan);
}

async function renderEngagements(panel, plan) {
  const draft = plan.status === "Draft";
  const approved = plan.status === "Approved";
  const card = el("div", { class: "card" }, el("h3", null, "Planned engagements"));
  panel.append(card);
  if (!plan.engagements.length) card.append(el("div", { class: "empty" }, "No engagements yet."));
  else card.append(el("table", null,
    el("thead", null, el("tr", null, el("th", null, "Quarter"), el("th", null, "Engagement"), el("th", null, "Entity"),
      el("th", null, "Risk"), el("th", null, "Site"), el("th", null, "Hours"), el("th", null, "Status"), el("th", null, ""))),
    el("tbody", null, ...plan.engagements.map((e) => el("tr", { class: "no-click" },
      el("td", null, e.planned_quarter), el("td", null, e.title, e.rationale ? el("div", { class: "muted" }, e.rationale) : null),
      el("td", null, e.entity_unit_name || "-"),
      el("td", null, e.entity_risk_score ? heat(e.entity_risk_score) : "-"),
      el("td", null, e.site_name || el("span", { class: "muted" }, "-")),
      el("td", null, String(e.budget_hours)), el("td", null, badge(e.status)),
      el("td", null, el("div", { class: "actions" },
        e.audit_id ? btn("Open audit", () => openAudit(e.audit_id), "secondary") : null,
        approved && e.status === "Planned" ? btn("Start", async () => {
          try { const r = await API.post(`/api/plan-engagements/${e.id}/start`); toast("Audit project created"); openAudit(r.audit_id); }
          catch (err) { toast(err.message, "error"); }
        }) : null,
        draft ? btn("Edit", () => addEngagement(plan, e), "secondary") : null,
        draft ? btn("Remove", async () => {
          try { await API.del(`/api/plan-engagements/${e.id}`); toast("Removed"); openPlan(plan.id); }
          catch (err) { toast(err.message, "error"); }
        }, "danger-ghost") : null)))))));
  if (draft) card.append(el("div", { style: "margin-top:12px" }, btn("Add engagement", () => addEngagement(plan))));
  else if (approved) {
    card.append(el("p", { class: "muted" }, "The plan is approved and is not edited directly. Changes go through a change request (reason, affected items, resource and coverage impact, review and approval) and create a new version; each change is logged under Plan changes and reported in the Committee pack."));
    if (plan.current_version && hasPerm("plan.prepare", "oversight.port", "audit.memo_approve")) {
      card.append(el("div", { style: "margin-top:12px" }, btn("Request a change", () => changeRequestEditor(plan))));
    }
  }
}

async function addEngagement(plan, eng = null) {
  const units = await safeGet("/api/entity-units?active_only=true", []);
  const leads = isAdmin() ? await safeGet("/api/users", null) : null; // user list is Admin-only
  let sites = [];
  try { sites = await planSites(); } catch { /* optional */ }
  openForm({
    title: eng ? `Edit engagement #${eng.id}` : "Add engagement",
    key: eng ? `engagement:edit:${eng.id}` : `engagement:new:${plan.id}`,
    meta: { title: eng ? `Edit engagement ${eng.title}` : `New engagement (${plan.plan_ref})`, record_type: "assurance_plan", record_id: plan.id },
    fields: [
      { name: "title", label: "Engagement title", required: true, maxLength: 255, singleLine: true },
      { name: "entity_unit_id", label: "Entity unit", type: "select", emptyLabel: "- none -",
        options: units.sort((a, b) => b.risk_score - a.risk_score).map((u) => ({ value: u.id, label: `${u.location_name} / ${u.name} (risk ${u.risk_score})` })) },
      { name: "site_entity_id", label: "Responsible site (HQ / port)", type: "select", emptyLabel: "- choose -",
        options: sites, help: "Decides which copy of the approved plan includes it. Destinations are set up by administrators on the Organizations register." },
      { name: "planned_quarter", label: "Quarter", type: "select", required: true, options: QUARTERS },
      { name: "budget_hours", label: "Budget hours", type: "number", min: 0, max: 10000 },
      ...(Array.isArray(leads) ? [{ name: "lead_auditor_id", label: "Lead auditor", type: "select", emptyLabel: "- not assigned -",
        options: leads.filter((u) => u.is_active && u.role !== "Auditee").map((u) => ({ value: u.id, label: `${u.full_name || u.username} (${u.role})` })) }] : []),
      { name: "rationale", label: "Rationale (risk, regulatory, management request ...)", type: "textarea", maxLength: 20000 },
    ],
    initial: eng || { planned_quarter: "Q1", budget_hours: 0 },
    submitLabel: eng ? "Save changes" : "Add",
    onSubmit: (v) => {
      const body = { ...v, budget_hours: v.budget_hours || 0, rationale: v.rationale || "" };
      return eng ? API.patch(`/api/plan-engagements/${eng.id}`, body) : API.post(`/api/assurance-plans/${plan.id}/engagements`, body);
    },
    onDone: () => { toast(eng ? "Engagement saved" : "Engagement added"); openPlan(plan.id); },
  });
}

// ==================================================================== risk & control matrix (audit tab)

async function renderRcm(panel, auditId) {
  const reload = () => { clear(panel); renderRcm(panel, auditId); };
  let rcm;
  try { rcm = await API.get(`/api/audits/${auditId}/rcm`); }
  catch (err) { panel.append(el("div", { class: "empty" }, err.message)); return; }
  const s = rcm.summary;
  const open = !rcm.locked;

  const eff = s.controls_by_effectiveness;
  panel.append(el("div", { class: "stats" },
    stat(s.objectives, "Objectives"),
    stat(s.risks, "Risks", `${s.risks_by_rating.High} high · ${s.risks_by_rating.Medium} medium · ${s.risks_by_rating.Low} low`,
      s.risks_by_rating.High ? "warn" : ""),
    stat(s.controls, "Controls", `${s.key_controls} key`),
    stat(`${eff.Effective}/${eff.Ineffective}`, "Effective / ineffective", `${eff["Not Tested"]} not tested`, eff.Ineffective ? "danger" : ""),
    stat(s.tests_awaiting_review, "Tests awaiting review", null, s.tests_awaiting_review ? "warn" : ""),
    stat(s.open_issues, "Open issues", null, s.open_issues ? "danger" : ""),
  ));
  const gaps = [
    ...s.risks_without_controls.map((r) => `Risk without a mitigating control: ${r}`),
    ...s.key_controls_untested.map((c) => `Key control not yet tested: ${c}`),
  ];
  if (gaps.length) panel.append(el("div", { class: "callout warn" }, el("i", { class: "bi bi-exclamation-triangle" }),
    el("div", null, el("strong", null, "Coverage gaps"), el("ul", null, ...gaps.map((g) => el("li", null, g))))));
  if (rcm.locked) panel.append(el("p", { class: "muted" }, "The audit is closed - the matrix is read-only."));

  rcm.objectives.forEach((o) => panel.append(objectiveCard(o, open, reload)));
  if (!rcm.objectives.length) panel.append(el("div", { class: "card empty" }, "No objectives yet. Start by adding the audit objectives."));
  if (open) panel.append(el("div", null, btn("Add objective", () => objectiveForm(auditId, null, reload))));
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

function objectiveCard(o, open, reload) {
  const card = el("div", { class: "card" });
  card.append(el("div", { class: "view-head" },
    el("h3", null, el("span", { class: "ref" }, o.ref), " ", o.title),
    open ? el("div", { class: "actions" },
      btn("+ Risk", () => riskModal(o, null, reload), "secondary"),
      btn("+ Control", () => controlModal(o, null, reload), "secondary"),
      btn("From library", () => fromLibraryDialog(o, reload), "secondary"),
      aiRiskAction(o, reload),
      btn("Edit", () => objectiveForm(o.audit_id, o, reload), "secondary"),
      btn("Delete", async () => {
        try { await API.del(`/api/objectives/${o.id}`); toast("Objective deleted"); reload(); }
        catch (err) { toast(err.message, "error"); }
      }, "danger-ghost")) : null));
  if (o.description) card.append(el("p", { class: "muted" }, o.description));

  const riskRef = Object.fromEntries(o.risks.map((r) => [r.id, r.ref]));
  card.append(el("h4", null, "Risks"));
  if (!o.risks.length) card.append(el("div", { class: "empty" }, "No risks identified."));
  else card.append(el("table", null,
    el("thead", null, el("tr", null, el("th", null, "Ref"), el("th", null, "Risk"), el("th", null, "Inherent"),
      el("th", null, "Residual"), el("th", null, "Controls"), el("th", null, ""))),
    el("tbody", null, ...o.risks.map((r) => el("tr", { class: "no-click" },
      el("td", { class: "ref" }, r.ref), el("td", null, r.title, r.enterprise_risk ? el("div", { class: "muted small" }, el("i", { class: "bi bi-link-45deg" }), ` ${r.enterprise_risk}`) : null),
      el("td", null, heat(r.inherent_score)), el("td", null, badge(r.residual_rating)),
      el("td", null, r.control_ids.length ? r.control_ids.map((id) => o.controls.find((c) => c.id === id)?.ref || `#${id}`).join(", ") : el("span", { class: "badge badge-risk-high" }, "none")),
      el("td", null, open ? btn("Edit", () => riskModal(o, r, reload), "secondary") : null))))));

  card.append(el("h4", null, "Controls"));
  if (!o.controls.length) card.append(el("div", { class: "empty" }, "No controls documented."));
  o.controls.forEach((c) => {
    const box = el("div", { class: "control-box" });
    box.append(el("div", { class: "view-head" },
      el("div", null, el("span", { class: "ref" }, c.ref), " ", el("strong", null, c.title), " ",
        c.is_key ? badge("Key") : null, " ", badge(c.effectiveness),
        el("div", { class: "muted" }, `${c.control_type} · ${c.nature} · ${c.frequency}`,
          c.owner_email ? ` · owner ${c.owner_email}` : "",
          ` · mitigates ${c.risk_ids.map((id) => riskRef[id] || `#${id}`).join(", ") || "no risk"}`)),
      open ? el("div", { class: "actions" },
        btn("+ Test", () => testCreateModal({ ...c, audit_id: o.audit_id }, reload)),
        btn("Edit", () => controlModal(o, c, reload), "secondary")) : null));
    if (c.tests.length) box.append(el("table", { class: "tests-table" },
      el("thead", null, el("tr", null, el("th", null, "Test"), el("th", null, "Type"), el("th", null, "Sample"),
        el("th", null, "Exceptions"), el("th", null, "Status"), el("th", null, "Conclusion"), el("th", null, ""))),
      el("tbody", null, ...c.tests.map((t) => el("tr", { class: "no-click" },
        el("td", { class: "ref" }, t.ref), el("td", null, t.test_type),
        el("td", null, t.sample_size ? (t.population_size ? `${t.sample_size} of ${t.population_size}` : String(t.sample_size)) : "-"),
        el("td", null, String(t.exceptions_found)), el("td", null, badge(t.status)), el("td", null, badge(t.conclusion)),
        el("td", null, el("div", { class: "actions" },
          btn("Open", () => testModal({ ...c, audit_id: o.audit_id }, t, open, reload), "secondary"),
          open && t.status === "Completed" && t.performed_by !== state.user.id ? btn("Review (e-sign)", () => eSignModal({
            title: `Review ${t.ref}`, pathOverride: `/api/control-tests/${t.id}/review`, actionLabel: "Sign review",
            allowReject: true, onDone: reload })) : null,
          open && t.conclusion === "Ineffective" && ["Completed", "Reviewed"].includes(t.status) ? btn("Raise issue", async () => {
            try { await API.post(`/api/control-tests/${t.id}/raise-issue`); toast("Issue raised - see Findings"); reload(); }
            catch (err) { toast(err.message, "error"); }
          }) : null)))))));
    card.append(box);
  });
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

function testCreateModal(control, reload) {
  openForm({
    title: `New test on ${control.ref}`,
    key: `rcm:${control.audit_id || "x"}:test:new:${control.id}`,
    meta: { title: `New test (${control.ref})`, record_type: "audit", record_id: control.audit_id || null },
    fields: [
      { name: "test_type", label: "Test type", type: "select", required: true, options: TEST_TYPES },
      { name: "procedure", label: "Test procedure (steps the auditor will perform)", type: "textarea", maxLength: 20000 },
    ],
    initial: { test_type: "Operating Effectiveness" },
    submitLabel: "Add",
    onSubmit: (v) => API.post(`/api/controls/${control.id}/tests`, { ...v, procedure: v.procedure || "" }),
    onDone: () => { toast("Test added"); reload(); },
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
      document.querySelector(".modal-backdrop")?.remove(); reload();
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
  // Criteria library (GIAS 13.4): pick a standard criterion; its text fills the Criteria box.
  const library = canWrite ? (await safeGet("/api/criteria?status=Active", { items: [] })).items : [];
  const current = f && f.criterion_id ? await safeGet(`/api/criteria/${f.criterion_id}`, null) : null;
  const cfDefs = customFieldDefs(await safeGet("/api/custom-fields?module=findings", [])).map((x) => ({ ...x, name: x.key, disabled: ro }));
  if (current && !library.some((c) => c.id === current.id)) library.push(current);
  const issueTypes = canWrite ? await safeGet("/api/findings/issue-types", []) : [];
  if (f && f.issue_type && !issueTypes.includes(f.issue_type)) issueTypes.push(f.issue_type);
  const fields = [
    { name: "title", label: "Issue title", required: true, maxLength: 255, singleLine: true, disabled: ro },
    { name: "risk_rating", label: "Severity (risk rating)", type: "select", required: true, options: RISK_RATINGS, disabled: ro },
    ...(canWrite ? [{ name: "issue_type", label: "Issue type", type: "select", emptyLabel: "- not set -", options: issueTypes }] : []),
    { name: "status", label: "Status", type: "select", required: true, options: FINDING_STATUSES, disabled: ro,
      help: f && f.remediation ? `Remediation: ${f.remediation.state}${f.remediation.refs.length ? ` (${f.remediation.refs.join(", ")})` : ""}. A finding closes when its actions are verified as effective.` : "A finding closes when its remediation actions are verified as effective." },
    { name: "assigned_owner_email", label: "Owner email", type: "email", disabled: ro },
    { type: "heading", label: "Issue attributes" },
    ...(canWrite ? [{ name: "criterion_id", label: "Criterion from the library", type: "select", emptyLabel: library.length ? "- none (write below) -" : "- library is empty -",
      options: library.map((c) => ({ value: c.id, label: `${c.crit_ref} · ${c.title}${c.reference ? ` (${c.reference})` : ""}` })), full: true,
      help: "Choosing one fills the Criteria box; you can still edit the text" }] : []),
    { name: "criteria", label: "Criteria - what should be (policy, standard, control design)", type: "textarea", maxLength: 20000, disabled: ro },
    { name: "condition", label: "Condition - what was found", type: "textarea", maxLength: 20000, disabled: ro },
    { name: "cause", label: "Cause - why it happened", type: "textarea", maxLength: 20000, disabled: ro },
    { name: "effect", label: "Effect - risk / impact", type: "textarea", maxLength: 20000, disabled: ro },
    { name: "recommendation", label: "Recommendation", type: "textarea", maxLength: 20000, disabled: ro },
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
    try { const c = await API.post(`/api/findings/${f.id}/raise-action`); toast(`Action ${c.capa_ref} raised`); document.querySelector(".modal-backdrop")?.remove(); onSaved(); }
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
  const pick = handle.nodes && handle.nodes.criterion_id;
  const box = handle.nodes && handle.nodes.criteria;
  if (pick && box) {
    pick.addEventListener("change", () => {
      const c = library.find((x) => String(x.id) === pick.value);
      if (!c) return;
      const text = `${c.body}${c.reference ? ` (${c.reference})` : ""}`;
      if (!box.value.trim() || box.value.trim() === text) box.value = text;
      else box.value = `${box.value.trim()}\n\n${text}`;
      box.dispatchEvent(new Event("input", { bubbles: true }));
    });
  }
}

// ------------------------------------------------------------------ draft resume handlers

function registerPlanningOpeners() {
  registerFormOpener("location:new", () => { navigate("universe"); locationForm(); });
  registerFormOpener("unit:new", async () => { navigate("universe"); editUnit(null, await API.get("/api/locations")); });
  registerFormOpener("unit:edit:", async (key) => {
    navigate("universe");
    const unit = (await API.get("/api/entity-units")).find((u) => String(u.id) === key.split(":")[2]);
    if (unit) editUnit(unit);
  });
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
      if (mode === "new") return testCreateModal(controls.find((c) => String(c.id) === id), reload);
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
  const card = el("div", { class: "card" }, el("h3", null, "Changes to the plan"),
    el("p", { class: "muted small" }, "Every amendment after approval, with its reason. Reported to the Audit Committee in the Committee pack."));
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

