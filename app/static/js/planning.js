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

// ==================================================================== universe

async function renderUniverse() {
  clear(viewRoot);
  const msg = el("div");
  viewRoot.append(viewHeader("Audit Universe"), msg);
  const admin = isAdmin();
  try {
    const [locations, units] = await Promise.all([API.get("/api/locations"), API.get("/api/entity-units")]);

    const locCard = el("div", { class: "card" }, el("h3", null, "Locations"));
    if (!locations.length) locCard.append(el("div", { class: "empty" }, "No locations yet."));
    else locCard.append(el("table", null,
      el("thead", null, el("tr", null, el("th", null, "Code"), el("th", null, "Name"), el("th", null, "Units"), el("th", null, "Status"))),
      el("tbody", null, ...locations.map((l) => el("tr", { class: "no-click" },
        el("td", { class: "ref" }, l.code), el("td", null, l.name),
        el("td", null, String(units.filter((u) => u.location_id === l.id).length)),
        el("td", null, badge(l.is_active ? "Active" : "Inactive")))))));
    if (admin) locCard.append(el("div", { style: "margin-top:12px" }, btn("Add location", () => locationForm())));
    viewRoot.append(locCard);

    const unitCard = el("div", { class: "card" }, el("h3", null, "Entity units (auditable entities)"));
    if (!units.length) unitCard.append(el("div", { class: "empty" }, "No entity units yet."));
    else unitCard.append(el("table", null,
      el("thead", null, el("tr", null, el("th", null, "Location"), el("th", null, "Code"), el("th", null, "Entity"),
        el("th", null, "Inherent risk"), el("th", null, "Last audited"), el("th", null, ""))),
      el("tbody", null, ...units.sort((a, b) => b.risk_score - a.risk_score).map((u) => el("tr", { class: "no-click" },
        el("td", null, u.location_name), el("td", { class: "ref" }, u.code), el("td", null, u.name),
        el("td", null, heat(u.risk_score), el("span", { class: "muted" }, ` L${u.risk_likelihood} x I${u.risk_impact}`)),
        el("td", { class: "muted" }, fmtDate(u.last_audited_at)),
        el("td", null, admin ? btn("Edit", () => editUnit(u), "secondary") : null))))));
    if (admin && locations.length) {
      unitCard.append(el("div", { style: "margin-top:12px" }, btn("Add entity unit", () => editUnit(null, locations))));
    }
    viewRoot.append(unitCard);
  } catch (err) { notify(msg, err.message, "error"); }
}

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

async function renderPlans() {
  clear(viewRoot);
  const msg = el("div");
  viewRoot.append(viewHeader("Assurance Plan", btn("New plan", () => newPlanModal())), msg);
  try {
    const plans = await API.get("/api/assurance-plans");
    const card = el("div", { class: "card" });
    if (!plans.length) card.append(el("div", { class: "empty" }, "No Assurance Plan yet. Create the plan for the fiscal year to start."));
    else card.append(el("table", null,
      el("thead", null, el("tr", null, el("th", null, "Ref"), el("th", null, "Fiscal year"), el("th", null, "Title"),
        el("th", null, "Status"), el("th", null, "Approved"))),
      el("tbody", null, ...plans.map((p) => el("tr", { onclick: () => openPlan(p.id) },
        el("td", { class: "ref" }, p.plan_ref), el("td", null, `FY${p.fiscal_year}`), el("td", null, p.title),
        el("td", null, badge(p.status)), el("td", { class: "muted" }, fmtDate(p.approved_at)))))));
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
  clear(viewRoot);
  const msg = el("div");
  viewRoot.append(msg);
  let plan;
  try { plan = await API.get(`/api/assurance-plans/${id}`); } catch (err) { notify(msg, err.message, "error"); return; }
  const draft = plan.status === "Draft";
  const approved = plan.status === "Approved";
  const s = plan.summary;

  viewRoot.append(viewHeader(plan.title.includes(String(plan.fiscal_year)) ? plan.title : `${plan.title} (FY${plan.fiscal_year})`, el("div", { class: "view-actions" },
    el("span", { class: "ref" }, plan.plan_ref), badge(plan.status),
    draft ? btn("Edit", () => editPlanModal(plan), "secondary") : null,
    isAdmin() && draft ? btn("Approve (e-sign)", () => eSignModal({
      title: "Approve Assurance Plan", pathOverride: `/api/assurance-plans/${id}/approve`, actionLabel: "Sign & Approve",
      allowReject: true, onDone: () => openPlan(id) })) : null,
    isAdmin() && approved ? btn("Reopen", async () => {
      try { await API.post(`/api/assurance-plans/${id}/reopen`); toast("Plan reopened"); openPlan(id); }
      catch (err) { toast(err.message, "error"); }
    }, "secondary") : null,
    isAdmin() && approved ? btn("Close year", async () => {
      try { await API.post(`/api/assurance-plans/${id}/close`); toast("Plan closed"); openPlan(id); }
      catch (err) { toast(err.message, "error"); }
    }, "secondary") : null,
    btn("Print", () => window.print(), "secondary"),
    btn("Back", () => navigate("plans"), "secondary"))));

  viewRoot.append(el("div", { class: "grid cols-3" },
    stat(s.engagements - s.cancelled, "Engagements planned"),
    stat(s.started, "Started (projects)"),
    stat(`${s.planned_hours} / ${s.budget_hours || "-"}`, "Hours planned / budget"),
    stat(`${s.coverage_pct}%`, `Universe coverage (${s.covered_units}/${s.universe_units} units)`),
    stat(QUARTERS.map((q) => `${q}:${s.by_quarter[q] || 0}`).join("  "), "By quarter"),
    stat(s.uncovered_high_risk.length, "High-risk units not planned"),
  ));
  if (s.uncovered_high_risk.length) {
    viewRoot.append(el("div", { class: "card warn" }, el("h3", null, "High-risk entities not in the plan"),
      el("ul", null, ...s.uncovered_high_risk.map((u) =>
        el("li", null, `${u.location_name} / ${u.name} `, heat(u.risk_score))))));
  }
  if (plan.description) viewRoot.append(el("div", { class: "card" }, el("p", null, plan.description)));

  const tabs = [{ key: "eng", label: "Engagements" }, { key: "history", label: "History" },
    { key: "approvals", label: "Approval Cycles" }];
  let active = "eng";
  const detail = el("div");
  viewRoot.append(detail);
  const paint = () => {
    clear(detail);
    detail.append(tabBar(tabs, active, (k) => { active = k; paint(); }));
    const panel = el("div");
    detail.append(panel);
    if (active === "eng") renderEngagements(panel, plan);
    if (active === "history") renderHistoryTab(panel, "assurance_plan", id);
    if (active === "approvals") renderApprovalsTab(panel, "assurance_plan", id);
  };
  paint();
}

async function renderEngagements(panel, plan) {
  const draft = plan.status === "Draft";
  const approved = plan.status === "Approved";
  const card = el("div", { class: "card" }, el("h3", null, "Planned engagements"));
  panel.append(card);
  if (!plan.engagements.length) card.append(el("div", { class: "empty" }, "No engagements yet."));
  else card.append(el("table", null,
    el("thead", null, el("tr", null, el("th", null, "Quarter"), el("th", null, "Engagement"), el("th", null, "Entity"),
      el("th", null, "Risk"), el("th", null, "Hours"), el("th", null, "Status"), el("th", null, ""))),
    el("tbody", null, ...plan.engagements.map((e) => el("tr", { class: "no-click" },
      el("td", null, e.planned_quarter), el("td", null, e.title, e.rationale ? el("div", { class: "muted" }, e.rationale) : null),
      el("td", null, e.entity_unit_name || "-"),
      el("td", null, e.entity_risk_score ? heat(e.entity_risk_score) : "-"),
      el("td", null, String(e.budget_hours)), el("td", null, badge(e.status)),
      el("td", null, el("div", { class: "actions" },
        e.audit_id ? btn("Open audit", () => openAudit(e.audit_id), "secondary") : null,
        approved && e.status === "Planned" ? btn("Start", async () => {
          try { const r = await API.post(`/api/plan-engagements/${e.id}/start`); toast("Audit project created"); openAudit(r.audit_id); }
          catch (err) { toast(err.message, "error"); }
        }) : null,
        approved && e.status === "Planned" && isAdmin() ? btn("Cancel", async () => {
          try { await API.post(`/api/plan-engagements/${e.id}/cancel`); toast("Cancelled"); openPlan(plan.id); }
          catch (err) { toast(err.message, "error"); }
        }, "secondary") : null,
        draft ? btn("Edit", () => addEngagement(plan, e), "secondary") : null,
        draft ? btn("Remove", async () => {
          try { await API.del(`/api/plan-engagements/${e.id}`); toast("Removed"); openPlan(plan.id); }
          catch (err) { toast(err.message, "error"); }
        }, "secondary") : null)))))));
  if (draft) card.append(el("div", { style: "margin-top:12px" }, btn("Add engagement", () => addEngagement(plan))));
  else if (approved) card.append(el("p", { class: "muted" }, "The plan is approved and frozen. Reopen it (Admin) to change engagements; it must then be re-approved."));
}

async function addEngagement(plan, eng = null) {
  const units = await safeGet("/api/entity-units?active_only=true", []);
  const leads = isAdmin() ? await safeGet("/api/users", null) : null; // user list is Admin-only
  openForm({
    title: eng ? `Edit engagement #${eng.id}` : "Add engagement",
    key: eng ? `engagement:edit:${eng.id}` : `engagement:new:${plan.id}`,
    meta: { title: eng ? `Edit engagement ${eng.title}` : `New engagement (${plan.plan_ref})`, record_type: "assurance_plan", record_id: plan.id },
    fields: [
      { name: "title", label: "Engagement title", required: true, maxLength: 255, singleLine: true },
      { name: "entity_unit_id", label: "Entity unit", type: "select", emptyLabel: "- none -",
        options: units.sort((a, b) => b.risk_score - a.risk_score).map((u) => ({ value: u.id, label: `${u.location_name} / ${u.name} (risk ${u.risk_score})` })) },
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

  panel.append(el("div", { class: "grid cols-3" },
    stat(s.objectives, "Objectives"),
    stat(`${s.risks} (H${s.risks_by_rating.High} M${s.risks_by_rating.Medium} L${s.risks_by_rating.Low})`, "Risks"),
    stat(`${s.controls} (${s.key_controls} key)`, "Controls"),
    stat(`${s.controls_by_effectiveness.Effective} / ${s.controls_by_effectiveness.Ineffective}`, "Controls effective / ineffective"),
    stat(s.tests_awaiting_review, "Tests awaiting review"),
    stat(s.open_issues, "Open issues"),
  ));
  const gaps = [
    ...s.risks_without_controls.map((r) => `Risk without a mitigating control: ${r}`),
    ...s.key_controls_untested.map((c) => `Key control not yet tested: ${c}`),
  ];
  if (gaps.length) panel.append(el("div", { class: "card warn" }, el("h3", null, "Coverage gaps"),
    el("ul", null, ...gaps.map((g) => el("li", null, g)))));
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
      btn("Add risk", () => riskModal(o, null, reload)),
      btn("Add control", () => controlModal(o, null, reload)),
      btn("Edit", () => objectiveForm(o.audit_id, o, reload), "secondary"),
      btn("Delete", async () => {
        try { await API.del(`/api/objectives/${o.id}`); toast("Objective deleted"); reload(); }
        catch (err) { toast(err.message, "error"); }
      }, "secondary")) : null));
  if (o.description) card.append(el("p", { class: "muted" }, o.description));

  const riskRef = Object.fromEntries(o.risks.map((r) => [r.id, r.ref]));
  card.append(el("h4", null, "Risks"));
  if (!o.risks.length) card.append(el("div", { class: "empty" }, "No risks identified."));
  else card.append(el("table", null,
    el("thead", null, el("tr", null, el("th", null, "Ref"), el("th", null, "Risk"), el("th", null, "Inherent"),
      el("th", null, "Residual"), el("th", null, "Controls"), el("th", null, ""))),
    el("tbody", null, ...o.risks.map((r) => el("tr", { class: "no-click" },
      el("td", { class: "ref" }, r.ref), el("td", null, r.title),
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
        btn("Add test", () => testCreateModal({ ...c, audit_id: o.audit_id }, reload)),
        btn("Edit", () => controlModal(o, c, reload), "secondary")) : null));
    if (c.tests.length) box.append(el("table", null,
      el("thead", null, el("tr", null, el("th", null, "Test"), el("th", null, "Type"), el("th", null, "Sample"),
        el("th", null, "Exceptions"), el("th", null, "Status"), el("th", null, "Conclusion"), el("th", null, ""))),
      el("tbody", null, ...c.tests.map((t) => el("tr", { class: "no-click" },
        el("td", { class: "ref" }, t.ref), el("td", null, t.test_type),
        el("td", null, t.sample_size ? `${t.sample_size} of ${t.population_size}` : "-"),
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

function riskModal(o, risk, reload) {
  openForm({
    title: risk ? `Edit ${risk.ref}` : `New risk under ${o.ref}`,
    key: risk ? `rcm:${o.audit_id}:risk:edit:${risk.id}` : `rcm:${o.audit_id}:risk:new:${o.id}`,
    meta: { title: risk ? `Edit risk ${risk.ref}` : `New risk (${o.ref})`, record_type: "audit", record_id: o.audit_id },
    fields: [
      { name: "title", label: "Risk", required: true, maxLength: 255, singleLine: true, placeholder: "What could go wrong?" },
      { name: "likelihood", label: "Likelihood", type: "select", required: true, options: LIKELIHOOD },
      { name: "impact", label: "Impact", type: "select", required: true, options: IMPACT },
      { name: "description", label: "Description", type: "textarea", maxLength: 20000 },
    ],
    initial: risk || { likelihood: 3, impact: 3 },
    submitLabel: "Save",
    onSubmit: (v) => {
      const body = { ...v, description: v.description || "" };
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

function issueForm(f, auditId, canWrite, onSaved) {
  const isNew = !f;
  const respondOnly = !canWrite;
  const ro = respondOnly;
  const fields = [
    { name: "title", label: "Issue title", required: true, maxLength: 255, singleLine: true, disabled: ro },
    { name: "risk_rating", label: "Risk rating", type: "select", required: true, options: RISK_RATINGS, disabled: ro },
    { name: "status", label: "Status", type: "select", required: true, options: FINDING_STATUSES, disabled: ro },
    { name: "assigned_owner_email", label: "Owner email", type: "email", disabled: ro },
    { type: "heading", label: "Issue attributes" },
    { name: "criteria", label: "Criteria - what should be (policy, standard, control design)", type: "textarea", maxLength: 20000, disabled: ro },
    { name: "condition", label: "Condition - what was found", type: "textarea", maxLength: 20000, disabled: ro },
    { name: "cause", label: "Cause - why it happened", type: "textarea", maxLength: 20000, disabled: ro },
    { name: "effect", label: "Effect - risk / impact", type: "textarea", maxLength: 20000, disabled: ro },
    { name: "recommendation", label: "Recommendation", type: "textarea", maxLength: 20000, disabled: ro },
    { name: "root_cause_whys", label: "Root cause - 5 Whys", type: "whys", disabled: ro },
    { name: "description", label: "Additional notes", type: "textarea", maxLength: 20000, disabled: ro },
    ...(isNew ? [] : [{ name: "management_response", label: "Management response (auditee / process owner)", type: "textarea", maxLength: 10000 }]),
  ];
  const raiseAction = !isNew && canWrite ? el("button", { class: "btn secondary", type: "button", onclick: async () => {
    try { const c = await API.post(`/api/findings/${f.id}/raise-action`); toast(`Action ${c.capa_ref} raised`); document.querySelector(".modal-backdrop")?.remove(); onSaved(); }
    catch (err) { toast(err.message, "error"); }
  } }, "Raise action (CAPA)") : null;
  openForm({
    title: isNew ? "New finding / issue" : `Issue #${f.id}: ${f.title}`,
    key: isNew ? `finding:new:${auditId}` : `finding:edit:${f.id}`,
    meta: { title: isNew ? "New finding" : `Issue #${f.id} ${f.title}`, record_type: "audit", record_id: auditId },
    fields,
    initial: f || { risk_rating: "Medium", status: "Open" },
    width: 900,
    actions: raiseAction ? [raiseAction] : [],
    validate: (v) => (v.status === "Closed" && !respondOnly && !(v.recommendation || "").trim() && !(v.condition || "").trim()
      ? { condition: "Document the condition (or recommendation) before closing the issue" } : {}),
    submitLabel: isNew ? "Create" : "Save",
    onSubmit: async (v) => {
      if (respondOnly) {
        if (!(v.management_response || "").trim()) throw Object.assign(new Error("Enter a response"), { errors: [{ field: "management_response", message: "Enter your response" }] });
        return API.post(`/api/findings/${f.id}/response`, { management_response: v.management_response.trim() });
      }
      const { management_response: response, ...rest } = v;
      const body = { ...rest, assigned_owner_email: rest.assigned_owner_email || null };
      const saved = isNew ? await API.post(`/api/audits/${auditId}/findings`, body) : await API.patch(`/api/findings/${f.id}`, body);
      if (!isNew && (response || "").trim() && response !== (f.management_response || "")) {
        await API.post(`/api/findings/${f.id}/response`, { management_response: response.trim() });
      }
      return saved;
    },
    onDone: () => { toast(isNew ? "Finding created" : "Issue saved"); onSaved(); },
  });
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
