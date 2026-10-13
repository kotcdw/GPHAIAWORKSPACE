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

// Small form-in-a-modal helper: `fields` = [[label, node], ...]; `submit` gets
// called and should throw on error.
function formModal(title, fields, submitLabel, submit) {
  const msg = el("div");
  let instance;
  instance = modal({
    title,
    body: el("div", null, el("div", { class: "grid cols-2" }, ...fields.map(([l, n]) => field(l, n))), msg),
    footer: el("div", { class: "actions" },
      el("button", { class: "btn secondary", onclick: () => instance.close() }, "Cancel"),
      el("button", { class: "btn", onclick: async () => {
        try { await submit(); instance.close(); } catch (err) { notify(msg, err.message, "error"); }
      } }, submitLabel)),
    width: 720,
  });
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
    if (admin) {
      const code = inp("Code (e.g. TEMA)");
      const name = inp("Name (e.g. Tema Port)");
      locCard.append(el("div", { class: "row", style: "margin-top:12px" },
        field("Code", code), field("Name", name),
        el("div", { style: "flex:0" }, btn("Add location", async () => {
          try {
            await API.post("/api/locations", { code: code.value.trim(), name: name.value.trim() });
            toast("Location added"); renderUniverse();
          } catch (err) { notify(msg, err.message, "error"); }
        }))));
    }
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

function editUnit(unit, locations = []) {
  const loc = sel(locations.map((l) => l.id), unit?.location_id);
  locations.forEach((l, i) => { loc.options[i].textContent = `${l.code} - ${l.name}`; });
  const code = inp("Code", unit?.code);
  const name = inp("Name", unit?.name);
  const owner = inp("Owner email", unit?.owner_email, "email");
  const lik = sel(SCORES, unit?.risk_likelihood ?? 3);
  const imp = sel(SCORES, unit?.risk_impact ?? 3);
  const desc = txt("Description", unit?.description);
  const fields = unit
    ? [["Name", name], ["Owner email", owner], ["Likelihood (1-5)", lik], ["Impact (1-5)", imp], ["Description", desc]]
    : [["Location", loc], ["Code", code], ["Name", name], ["Owner email", owner],
      ["Likelihood (1-5)", lik], ["Impact (1-5)", imp], ["Description", desc]];
  formModal(unit ? `Edit ${unit.name}` : "New entity unit", fields, "Save", async () => {
    const body = {
      name: name.value.trim(), owner_email: owner.value.trim() || null, description: desc.value,
      risk_likelihood: Number(lik.value), risk_impact: Number(imp.value),
    };
    if (unit) await API.patch(`/api/entity-units/${unit.id}`, body);
    else await API.post("/api/entity-units", { ...body, location_id: Number(loc.value), code: code.value.trim() });
    toast("Saved"); renderUniverse();
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

function newPlanModal() {
  const fy = inp("Fiscal year", String(new Date().getFullYear() + 1), "number");
  const title = inp("Title", `Assurance Plan FY${new Date().getFullYear() + 1}`);
  const hours = inp("Total budget hours", "0", "number");
  const desc = txt("Description / basis of the plan");
  formModal("New Assurance Plan", [["Fiscal year", fy], ["Title", title], ["Budget hours", hours], ["Description", desc]],
    "Create", async () => {
      const plan = await API.post("/api/assurance-plans", {
        fiscal_year: Number(fy.value), title: title.value.trim(), total_budget_hours: Number(hours.value || 0),
        description: desc.value,
      });
      toast("Plan created"); openPlan(plan.id);
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
        draft ? btn("Remove", async () => {
          try { await API.del(`/api/plan-engagements/${e.id}`); toast("Removed"); openPlan(plan.id); }
          catch (err) { toast(err.message, "error"); }
        }, "secondary") : null)))))));
  if (draft) card.append(el("div", { style: "margin-top:12px" }, btn("Add engagement", () => addEngagement(plan))));
  else if (approved) card.append(el("p", { class: "muted" }, "The plan is approved and frozen. Reopen it (Admin) to change engagements; it must then be re-approved."));
}

async function addEngagement(plan) {
  const units = await safeGet("/api/entity-units?active_only=true", []);
  const unit = el("select", null, el("option", { value: "" }, "- none -"),
    ...units.sort((a, b) => b.risk_score - a.risk_score).map((u) =>
      el("option", { value: u.id }, `${u.location_name} / ${u.name} (risk ${u.risk_score})`)));
  const title = inp("Engagement title");
  const quarter = sel(QUARTERS, "Q1");
  const hours = inp("Budget hours", "0", "number");
  const rationale = txt("Rationale (risk, regulatory, management request ...)");
  formModal("Add engagement", [["Entity unit", unit], ["Title", title], ["Quarter", quarter], ["Budget hours", hours],
    ["Rationale", rationale]], "Add", async () => {
    await API.post(`/api/assurance-plans/${plan.id}/engagements`, {
      title: title.value.trim(), entity_unit_id: unit.value ? Number(unit.value) : null,
      planned_quarter: quarter.value, budget_hours: Number(hours.value || 0), rationale: rationale.value,
    });
    toast("Engagement added"); openPlan(plan.id);
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
  if (open) panel.append(el("div", null, btn("Add objective", () => {
    const title = inp("Objective (e.g. Revenue is completely and accurately billed)");
    const desc = txt("Description");
    formModal("New objective", [["Objective", title], ["Description", desc]], "Add", async () => {
      await API.post(`/api/audits/${auditId}/objectives`, { title: title.value.trim(), description: desc.value });
      toast("Objective added"); reload();
    });
  })));
}

function objectiveCard(o, open, reload) {
  const card = el("div", { class: "card" });
  card.append(el("div", { class: "view-head" },
    el("h3", null, el("span", { class: "ref" }, o.ref), " ", o.title),
    open ? el("div", { class: "actions" },
      btn("Add risk", () => riskModal(o, null, reload)),
      btn("Add control", () => controlModal(o, null, reload)),
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
        btn("Add test", () => testCreateModal(c, reload)),
        btn("Edit", () => controlModal(o, c, reload), "secondary")) : null));
    if (c.tests.length) box.append(el("table", null,
      el("thead", null, el("tr", null, el("th", null, "Test"), el("th", null, "Type"), el("th", null, "Sample"),
        el("th", null, "Exceptions"), el("th", null, "Status"), el("th", null, "Conclusion"), el("th", null, ""))),
      el("tbody", null, ...c.tests.map((t) => el("tr", { class: "no-click" },
        el("td", { class: "ref" }, t.ref), el("td", null, t.test_type),
        el("td", null, t.sample_size ? `${t.sample_size} of ${t.population_size}` : "-"),
        el("td", null, String(t.exceptions_found)), el("td", null, badge(t.status)), el("td", null, badge(t.conclusion)),
        el("td", null, el("div", { class: "actions" },
          btn("Open", () => testModal(c, t, open, reload), "secondary"),
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

function riskModal(o, risk, reload) {
  const title = inp("Risk", risk?.title);
  const desc = txt("Description", risk?.description);
  const lik = sel(SCORES, risk?.likelihood ?? 3);
  const imp = sel(SCORES, risk?.impact ?? 3);
  formModal(risk ? `Edit ${risk.ref}` : "New risk", [["Risk", title], ["Likelihood (1-5)", lik], ["Impact (1-5)", imp],
    ["Description", desc]], "Save", async () => {
    const body = { title: title.value.trim(), description: desc.value, likelihood: Number(lik.value), impact: Number(imp.value) };
    if (risk) await API.patch(`/api/risks/${risk.id}`, body);
    else await API.post(`/api/objectives/${o.id}/risks`, body);
    toast("Risk saved"); reload();
  });
}

function controlModal(o, control, reload) {
  const title = inp("Control", control?.title);
  const desc = txt("Control description (what, who, when, evidence)", control?.description);
  const type = sel(CONTROL_TYPES, control?.control_type || "Preventive");
  const nature = sel(CONTROL_NATURES, control?.nature || "Manual");
  const freq = sel(FREQUENCIES, control?.frequency || "Monthly");
  const owner = inp("Control owner email", control?.owner_email, "email");
  const key = el("input", { type: "checkbox" });
  key.checked = control ? control.is_key : true;
  const risks = el("div", { class: "checklist" }, ...o.risks.map((r) => {
    const box = el("input", { type: "checkbox", value: r.id });
    box.checked = control ? control.risk_ids.includes(r.id) : false;
    return el("label", { class: "check" }, box, ` ${r.ref} ${r.title}`);
  }));
  formModal(control ? `Edit ${control.ref}` : "New control", [["Control", title], ["Owner", owner], ["Type", type],
    ["Nature", nature], ["Frequency", freq], ["Key control", key], ["Mitigates risks", risks], ["Description", desc]],
  "Save", async () => {
    const riskIds = [...risks.querySelectorAll("input:checked")].map((b) => Number(b.value));
    const body = { title: title.value.trim(), description: desc.value, control_type: type.value, nature: nature.value,
      frequency: freq.value, owner_email: owner.value.trim() || null, is_key: key.checked };
    if (control) {
      await API.patch(`/api/controls/${control.id}`, body);
      await API.put(`/api/controls/${control.id}/risks`, { risk_ids: riskIds });
    } else await API.post(`/api/objectives/${o.id}/controls`, { ...body, risk_ids: riskIds });
    toast("Control saved"); reload();
  });
}

function testCreateModal(control, reload) {
  const type = sel(TEST_TYPES, "Operating Effectiveness");
  const proc = txt("Test procedure (steps the auditor will perform)");
  formModal(`New test on ${control.ref}`, [["Test type", type], ["Procedure", proc]], "Add", async () => {
    await API.post(`/api/controls/${control.id}/tests`, { test_type: type.value, procedure: proc.value });
    toast("Test added"); reload();
  });
}

async function testModal(control, t, open, reload) {
  const locked = !open || t.status === "Reviewed";
  const proc = txt("Procedure", t.procedure);
  const results = txt("Results / exceptions noted", t.results);
  const exceptions = inp("Exceptions", String(t.exceptions_found), "number");
  const conclusion = sel(TEST_CONCLUSIONS, t.conclusion);
  const status = sel(["In Progress", "Completed"], t.status === "Not Started" ? "In Progress" : t.status);
  const population = inp("Population size", t.population_size ?? "", "number");
  const sample = inp("Sample size (blank = recommended)", t.sample_size ?? "", "number");
  const rec = await safeGet(`/api/control-tests/${t.id}/sample-recommendation`, null);
  if (locked) [proc, results, exceptions, conclusion, status, population, sample].forEach((n) => { n.disabled = true; });

  const info = el("div", { class: "muted", style: "grid-column:1/-1" },
    rec ? `Recommended sample: ${rec.recommended_size} - ${rec.basis}.` : "",
    t.sample_items ? el("div", null, `Selected items: ${t.sample_items} (seed ${t.sample_seed})`) : null,
    t.reviewed_at ? el("div", null, `Reviewed ${fmtDate(t.reviewed_at)}${t.review_comment ? `: ${t.review_comment}` : ""}`) : null,
    !t.reviewed_at && t.review_comment ? el("div", null, `Review note: ${t.review_comment}`) : null);
  const sampleBtn = locked ? el("span") : btn("Draw random sample", async () => {
    try {
      await API.post(`/api/control-tests/${t.id}/sample`, {
        population_size: Number(population.value), sample_size: sample.value ? Number(sample.value) : null });
      toast("Sample drawn"); document.querySelector(".modal-backdrop")?.remove(); reload();
    } catch (err) { toast(err.message, "error"); }
  }, "secondary");
  const fields = [["Procedure", proc], ["Population size", population], ["Sample size", sample], ["", sampleBtn],
    ["Exceptions found", exceptions], ["Conclusion", conclusion], ["Status", status], ["Results", results]];
  if (locked) {
    modal({ title: `${t.ref} - ${t.test_type} (${t.status})`, width: 720,
      body: el("div", null, el("div", { class: "grid cols-2" }, ...fields.map(([l, n]) => field(l, n))), info) });
    return;
  }
  formModal(`${t.ref} - ${t.test_type}`, [...fields, ["", info]], "Save", async () => {
    await API.patch(`/api/control-tests/${t.id}`, {
      procedure: proc.value, results: results.value, exceptions_found: Number(exceptions.value || 0),
      conclusion: conclusion.value, status: status.value,
    });
    toast("Test saved"); reload();
  });
}

// ==================================================================== issue (finding) detail

function issueModal(f, auditId, canWrite, onSaved) {
  const editable = canWrite;
  const nodes = {
    criteria: txt("Criteria - what should be (policy, standard, control design)", f.criteria),
    condition: txt("Condition - what was found", f.condition),
    cause: txt("Cause - why it happened", f.cause),
    effect: txt("Effect - the risk / impact", f.effect),
    recommendation: txt("Recommendation", f.recommendation),
  };
  const whys = [0, 1, 2, 3, 4].map((i) => inp(`Why ${i + 1}?`, (f.root_cause_whys || [])[i] || ""));
  const response = txt("Management response (auditee / process owner)", f.management_response);
  Object.values(nodes).concat(whys).forEach((n) => { n.disabled = !editable; });
  const body = el("div", null,
    el("div", { class: "grid cols-2" }, ...Object.entries(nodes).map(([k, n]) => field(k[0].toUpperCase() + k.slice(1), n))),
    el("h4", null, "Root cause - 5 Whys"), el("div", { class: "grid cols-2" }, ...whys),
    el("h4", null, "Management response"), response);
  const msg = el("div");
  body.append(msg);
  let instance;
  const footer = el("div", { class: "actions" },
    el("button", { class: "btn secondary", onclick: () => instance.close() }, "Close"),
    editable ? el("button", { class: "btn secondary", onclick: async () => {
      try { const c = await API.post(`/api/findings/${f.id}/raise-action`); toast(`Action ${c.capa_ref} raised`); instance.close(); onSaved(); }
      catch (err) { notify(msg, err.message, "error"); }
    } }, "Raise action (CAPA)") : null,
    el("button", { class: "btn", onclick: async () => {
      try {
        if (editable) {
          await API.patch(`/api/findings/${f.id}`, {
            ...Object.fromEntries(Object.entries(nodes).map(([k, n]) => [k, n.value])),
            root_cause_whys: whys.map((w) => w.value.trim()).filter(Boolean),
          });
        }
        if (response.value.trim() && response.value !== (f.management_response || "")) {
          await API.post(`/api/findings/${f.id}/response`, { management_response: response.value.trim() });
        }
        toast("Issue saved"); instance.close(); onSaved();
      } catch (err) { notify(msg, err.message, "error"); }
    } }, "Save"));
  instance = modal({ title: `Issue #${f.id}: ${f.title}`, body, footer, width: 820 });
}
