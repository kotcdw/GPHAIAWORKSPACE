// GPHA Audit Workspace - Assurance Plans (Assurance Plans walkthrough):
//   Assurance plans list and Activity, + Create plan, the plan page (Plan overview: Annual Program Overview,
//   Projects, Coverage, Risks, Progress & resources, approval, change requests, activities), + Add to plan with its
//   three paths (create a new project: basic information > objectives > entities > review; link active projects;
//   roll forward a project) and next-cycle planning signals.
// Loaded after planning.js / fieldwork.js / walk.js.

const PLAN_LIFECYCLE = ["Draft", "In Review", "Submitted", "Approved", "Distributed", "In Execution", "Closed"];

function plansFrame(opts) {
  return wsPage({
    app: "Assurance Plans", context: opts.context || null,
    util: [{ label: "Home", onClick: () => navigate("dashboard") },
      hasPerm("system.config") ? { label: "Settings", onClick: () => { state.configSection = "Plan configuration"; navigate("configuration"); } } : null,
      { label: "Profile", onClick: () => navigate("profile") }],
    side: opts.side || [{ key: "plans", label: "Assurance plans" }, { key: "activity", label: "Activity" }],
    active: opts.active || "plans",
    onSide: opts.onSide || ((k) => (k === "activity" ? renderPlansActivity() : renderPlans())),
    crumb: opts.crumb, title: opts.title, actions: opts.actions || [],
  });
}

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

// ------------------------------------------------------------------ Assurance plans list, Activity, Create plan

async function renderPlans(filter = state.planFilter || "") {
  state.planFilter = filter;
  const pick = el("select", { class: "ws-input compact", "aria-label": "Filter by status" }, el("option", { value: "" }, "All current plans"),
    ...PLAN_STATUSES.map((s) => el("option", { value: s, selected: s === filter ? "1" : null }, s)));
  pick.addEventListener("change", () => renderPlans(pick.value));
  const signals = hasPerm("plan.prepare", "plan.amend", "plan.approve", "oversight.portfolio", "governance.view")
    ? wsAction("Next-cycle signals", () => planSignalsDialog()) : null;
  const f = plansFrame({ crumb: ["Assurance Plans", "Assurance plans"], title: "Assurance plans",
    actions: [pick, signals, hasPerm("plan.prepare") ? wsAction("+ Create plan", () => planCreatePage(), { primary: true, focus: true }) : null] });
  f.body.append(loadingState());
  let plans;
  try { plans = await API.get(filter ? `/api/assurance-plans?lifecycle_status=${encodeURIComponent(filter)}` : "/api/assurance-plans"); }
  catch (err) { clear(f.body); f.body.append(errorState(err, () => renderPlans(filter))); return; }
  clear(f.body);
  if (!plans.length) {
    f.body.append(emptyState({ icon: "calendar-range", title: "No Assurance Plan yet",
      action: hasPerm("plan.prepare") ? wsAction("+ Create plan", () => planCreatePage(), { primary: true }) : null }));
    return;
  }
  const rows = plans.map((p) => {
    const cells = { projects: el("td", { class: "num", "data-label": "Projects" }, "…"), hours: el("td", { "data-label": "Hours" }, "…"),
      progress: el("td", { "data-label": "Progress" }, "…"), coverage: el("td", { class: "num", "data-label": "Coverage" }, "…") };
    API.get(`/api/assurance-plans/${p.id}/program`).then((g) => {
      const m = g.metrics;
      const over = m.hours.available && m.hours.planned > m.hours.available;
      cells.projects.textContent = `${m.projects} / ${m.max_projects}`;
      cells.hours.replaceChildren(el("span", { class: over ? "text-danger" : null }, m.hours.planned.toLocaleString()),
        el("span", { class: "muted" }, m.hours.available ? ` / ${m.hours.available.toLocaleString()} hrs` : " hrs · no budget"));
      cells.progress.replaceChildren(`${m.overall_progress}% `, wsBar(m.overall_progress));
      cells.coverage.textContent = `${m.coverage_pct}%`;
    }).catch(() => { Object.values(cells).forEach((c) => { c.textContent = "-"; }); });
    const period = p.period_start ? `${fmtDay(p.period_start)} – ${p.period_end ? fmtDay(p.period_end) : "?"}` : `FY${p.fiscal_year}`;
    return el("tr", { class: "clickable", tabindex: "0", onclick: () => openPlan(p.id), onkeydown: (e) => { if (e.key === "Enter") openPlan(p.id); } },
      el("td", { "data-label": "Plan" }, el("u", null, p.title), el("div", { class: "ws-caption" }, `${p.plan_ref} · ${period}`)),
      el("td", { "data-label": "Status" }, statusBadge(p.lifecycle_status)),
      cells.projects, cells.hours, cells.progress, cells.coverage);
  });
  f.body.append(el("div", { class: "table-wrap" }, el("table", { class: "ws-table" },
    el("thead", null, el("tr", null, ...["Plan", "Status", "Projects", "Hours", "Progress", "Coverage"].map((h) => el("th", { scope: "col" }, h)))),
    el("tbody", null, ...rows))));
}

async function renderPlansActivity() {
  const f = plansFrame({ active: "activity", crumb: ["Assurance Plans", "Activity"], title: "Activity" });
  f.body.append(loadingState());
  const plans = (await safeGet("/api/assurance-plans", [])).slice(0, 8);
  const lists = await Promise.all(plans.map((p) => safeGet(`/api/records/assurance_plan/${p.id}/history`, []).then((items) => items.map((h) => ({ ...h, plan: p })))));
  const items = lists.flat().sort((a, b) => String(b.timestamp).localeCompare(String(a.timestamp))).slice(0, 100);
  clear(f.body);
  if (!items.length) { f.body.append(emptyState({ icon: "clock-history", title: "No plan activity yet" })); return; }
  f.body.append(el("table", { class: "ws-table" },
    el("thead", null, el("tr", null, ...["When", "Plan", "Who", "Activity"].map((h) => el("th", { scope: "col" }, h)))),
    el("tbody", null, ...items.map((h) => el("tr", { class: "clickable", onclick: () => openPlan(h.plan.id) },
      el("td", null, fmtDate(h.timestamp)), el("td", null, h.plan.plan_ref), el("td", null, h.user || "System"), el("td", null, h.action))))));
}

function planCreatePage() {
  const y = currentFiscalYear() + 1;
  const f = plansFrame({ crumb: ["Assurance Plans", "Assurance plans", "Create plan"], title: "Create new plan" });
  const name = wsInput(`FY${y} Assurance Plan`, { name: "title", maxlength: "255" });
  const desc = wsInput("", { name: "description", maxlength: "20000", placeholder: "Optional" });
  const hours = wsInput("", { name: "total_budget_hours", type: "number", min: "0", max: "1000000", placeholder: "e.g. 5000" });
  const start = wsInput(`${y}-01-01`, { name: "period_start", type: "date", "aria-label": "Start date" });
  const end = wsInput(`${y}-12-31`, { name: "period_end", type: "date", "aria-label": "End date" });
  const box = wsCard(null, wsFieldRows([
    { label: "Assurance plan name", control: name },
    { label: "Description (optional)", control: desc },
    { label: "Total available resources (hours)", control: hours },
    { label: "Planning period", control: el("div", { class: "ws-inline" }, el("span", { class: "ws-caption" }, "Start date"), start, el("span", { class: "ws-caption" }, "End date"), end) },
  ]), wsToolbar(wsAction("Cancel", () => renderPlans()), wsAction("Create plan", async () => {
    if (!start.value || !end.value) { toast("Set the planning period", "error"); return; }
    if (end.value < start.value) { toast("The planning period ends before it starts", "error"); return; }
    try {
      const plan = await API.post("/api/assurance-plans", { fiscal_year: fiscalYearOf(new Date(`${start.value}T12:00:00`)), title: name.value.trim(),
        description: desc.value.trim(), total_budget_hours: Number(hours.value || 0), period_start: start.value, period_end: end.value });
      toast("Plan created"); openPlan(plan.id);
    } catch (err) { wsShowErrors(box, err); }
  }, { primary: true })));
  f.body.append(box);
  name.focus();
}

// ------------------------------------------------------------------ Plan overview (Annual Program Overview)

function metricTile(title, value) {
  return el("div", { class: "ws-choice static" }, el("strong", null, title), el("span", { class: "ws-big" }, value));
}

async function renderPlanProgram(pane, plan, goTo) {
  pane.append(loadingState());
  let p;
  try { p = await API.get(`/api/assurance-plans/${plan.id}/program`); } catch (err) { clear(pane); pane.append(errorState(err, () => { clear(pane); renderPlanProgram(pane, plan, goTo); })); return; }
  clear(pane);
  const m = p.metrics;
  const draft = plan.status === "Draft";
  pane.append(wsToolbar(
    draft && hasPerm("plan.prepare", "plan.amend") ? wsAction("+ Add to plan", () => addToPlan(plan), { primary: true, focus: !m.projects }) : null,
    draft ? wsAction("Edit plan", () => editPlanModal(plan)) : null));
  pane.append(el("h3", { class: "ws-h" }, "Annual Program Overview"), el("b", null, "Top key metrics"));
  pane.append(el("div", { class: "ws-grid four kpi-row" },
    metricTile("Projects active", `${m.projects} / ${m.max_projects} max`),
    metricTile("Strategic risks aligned", String(m.strategic_risks)),
    metricTile("Total assurance coverage", `${m.coverage_pct}%`),
    metricTile("Allocated resources", `${m.hours.planned.toLocaleString()} hrs / ${(m.hours.available || 0).toLocaleString()} hrs`)));
  const live = p.projects.filter((r) => !r.cancelled);
  const scope = wsCard("Strategic risk alignment & project scope",
    live.length ? el("table", { class: "ws-table" },
      el("thead", null, el("tr", null, ...["Project", "Progress", "Status", "Risks"].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...live.map((r) => el("tr", { class: r.audit_id ? "clickable" : null, onclick: r.audit_id ? () => openAudit(r.audit_id) : null },
        el("td", null, r.title), el("td", null, `${r.progress}%`), el("td", null, r.phase === "Not started" ? "Planning" : r.phase), el("td", { class: "num" }, String(r.strategic_risks))))))
      : el("p", { class: "muted" }, "No projects yet."));
  const covered = p.categories.reduce((a, c) => a + c.covered, 0);
  const total = p.categories.reduce((a, c) => a + c.entities, 0);
  const coverage = wsCard("Coverage monitoring", el("p", null, "By entity category"),
    p.categories.length ? el("div", { class: "ws-meter cat", role: "img", "aria-label": `${covered} of ${total} entities covered` },
      ...p.categories.map((c, i) => el("span", { style: `width:${total ? (100 * c.entities) / total : 0}%;background:${c.covered ? CHART_TONES[i % CHART_TONES.length] : "#e9edf1"};opacity:${c.entities ? Math.max(0.35, c.covered / c.entities) : 1}`, title: `${c.name}: ${c.covered} of ${c.entities} covered` })))
      : el("p", { class: "muted small" }, "No auditable entities yet."),
    el("p", null, p.categories.map((c) => `${c.name} ${c.pct}%`).join("　")),
    wsAction("View by individual entity", () => goTo("coverage")));
  pane.append(wsGrid(scope, coverage));
  pane.append(progressCard(p));
  if (p.not_covered_high) pane.append(wsNote(`${p.not_covered_high} high-risk entit${p.not_covered_high === 1 ? "y is" : "ies are"} not covered by the plan. `,
    el("button", { class: "ws-crumb-link", type: "button", onclick: () => goTo("coverage") }, "Review coverage")));
}

function progressCard(p) {
  const m = p.metrics;
  const h = m.hours;
  const live = p.projects.filter((r) => !r.cancelled);
  const remaining = Math.max(0, (h.available || 0) - h.planned);
  return wsCard(`Overall progress: ${m.overall_progress}%`, el("div", { class: "ws-meter" }, el("span", { class: "ok", style: `width:${m.overall_progress}%` })),
    ...live.slice(0, 8).map((r) => el("p", null, `${r.title}: ${r.progress}% `, wsBar(r.progress))),
    el("p", null, `Total available resources (hours): ${(h.available || 0).toLocaleString()}`),
    wsMeter(h.planned, h.available || 0),
    el("p", null, "Resource usage　", el("strong", null, `${h.planned.toLocaleString()} hrs planned`), "　",
      h.available ? (h.over ? el("span", { class: "text-danger" }, `${h.over.toLocaleString()} hrs overage`) : `${remaining.toLocaleString()} hrs remaining`) : el("span", { class: "muted" }, "Set the available hours on the plan")));
}

// ------------------------------------------------------------------ + Add to plan and its three paths

function planPageFrame(plan, active, crumb, title) {
  const back = () => openPlan(plan.id);
  return plansFrame({ context: plan.title, side: [{ key: "overview", label: "Plan overview" }, { key: active, label: crumb[crumb.length - 1] }],
    active, onSide: (k) => { if (k === "overview") back(); }, crumb: ["Assurance Plans", { label: plan.title, onClick: back }, ...crumb], title });
}

async function addToPlan(plan) {
  const program = await safeGet(`/api/assurance-plans/${plan.id}/program`, { metrics: { projects: 0, max_projects: 100 } });
  const f = planPageFrame(plan, "add", ["Add to plan"], "Add projects to the plan");
  const creator = hasPerm("audit.create");
  const why = "Needs the Project Creator permission (create audits)";
  const full = program.metrics.projects >= program.metrics.max_projects;
  f.body.append(wsCard(null, el("div", { class: "ws-grid three add-choices" },
    wsChoice("Create a new project", "Start a project and add it here", () => newProjectPage(plan), { disabled: !creator || full, why: full ? "The plan is full" : why }),
    wsChoice("Link active projects", "Attach existing active work", () => linkProjectsPage(plan, "link"), { disabled: full, why: "The plan is full" }),
    wsChoice("Rollforward project", "Reuse a project, archived project, or template", () => linkProjectsPage(plan, "rollforward"), { disabled: !creator || full, why: full ? "The plan is full" : why })),
  el("p", { class: "ws-caption" }, `A plan can contain up to ${program.metrics.max_projects} projects (${program.metrics.projects} now).`)));
}

async function newProjectPage(plan) {
  let types = [];
  try { types = (await loadEntityConfig()).types.audit_types || []; } catch { /* optional */ }
  const [fo, units] = await Promise.all([safeGet(`/api/assurance-plans/${plan.id}/framework-objectives`, { linked: [], all: [] }),
    safeGet("/api/entity-units?active_only=true", [])]);
  const data = { title: "", audit_type: "", planned_quarter: "Q1", budget_hours: "", objectives: new Set(), entities: new Set() };
  const steps = [{ key: "basic", label: "Basic information" }, { key: "objectives", label: "Objectives" }, { key: "entities", label: "Entities" }, { key: "review", label: "Review" }];
  const back = () => openPlan(plan.id);
  const objKey = (o) => `${o.program_id}|${o.title}`;
  const f = plansFrame({ context: plan.title, side: steps, active: "basic", onSide: (k) => go(k),
    crumb: ["Assurance Plans", { label: plan.title, onClick: back }, "Add to plan", "Create a new project"] });
  function go(k) {
    if (k !== "basic" && !data.title.trim()) { toast("Enter the project name first", "error"); k = "basic"; }
    f.setActive(k); clear(f.body);
    if (k === "basic") basic();
    if (k === "objectives") objectives();
    if (k === "entities") entities();
    if (k === "review") review();
  }
  function basic() {
    f.setHead("New project · Basic information");
    const name = wsInput(data.title, { name: "title", maxlength: "255", placeholder: "Project name" });
    const type = wsSelect([{ value: "", label: "- choose -" }, ...types], data.audit_type, { name: "audit_type" });
    const q = wsSelect(QUARTERS, data.planned_quarter, { name: "planned_quarter", "aria-label": "Quarter" });
    const hrs = wsInput(data.budget_hours, { name: "budget_hours", type: "number", min: "0", max: "10000" });
    f.body.append(wsCard(null, wsFieldRows([
      { label: "Project name", control: name },
      { label: "Project type", control: type, help: "The project type decides the workflow (Workplan or Internal Control)." },
      { label: "Estimated project start", control: el("div", { class: "ws-inline" }, q, el("span", null, `FY${plan.fiscal_year}`)) },
      { label: "Budgeted hours", control: hrs },
    ]), wsToolbar(wsAction("Cancel", back), wsAction("Continue", () => {
      data.title = name.value; data.audit_type = type.value; data.planned_quarter = q.value; data.budget_hours = hrs.value;
      go("objectives");
    }, { primary: true, focus: true }))));
    name.focus();
  }
  function objectives() {
    f.setHead("Select frameworks, objectives, and organizational coverage");
    const box = (o) => {
      const cb = el("input", { type: "checkbox", checked: data.objectives.has(objKey(o)) ? "1" : null });
      cb.addEventListener("change", () => { if (cb.checked) data.objectives.add(objKey(o)); else data.objectives.delete(objKey(o)); });
      return cb;
    };
    const linkedRows = fo.linked.map((o) => wsRow(el("label", null, box(o), ` ${o.title}`), wsTag(`Framework: ${o.framework}`)));
    const allRows = fo.all.map((o) => wsRow(el("label", null, box(o), ` ${o.title}`), wsTag("Objective")));
    f.body.append(wsCard("Objectives linked to strategic risks", ...(linkedRows.length ? linkedRows : [el("p", { class: "muted small" }, "No framework objective is linked to a strategic risk yet (Strategy › Treatment).")]),
      el("p", null, el("b", null, "All objectives"), "　", el("span", { class: "ws-caption" }, "Includes objectives linked to strategic risks")),
      ...(allRows.length ? allRows : [el("p", { class: "muted small" }, "No framework objectives yet (Project Library).")])),
    wsToolbar(wsAction("Back", () => go("basic")), wsAction("Continue", () => go("entities"), { primary: true, focus: true })));
  }
  function entities() {
    f.setHead("Select frameworks, objectives, and organizational coverage");
    const rows = units.map((u) => {
      const cb = el("input", { type: "checkbox", checked: data.entities.has(u.id) ? "1" : null });
      cb.addEventListener("change", () => { if (cb.checked) data.entities.add(u.id); else data.entities.delete(u.id); });
      return wsRow(el("label", null, cb, ` ${u.name}`), el("span", null, u.location_name));
    });
    f.body.append(wsCard("Entities (optional)", ...(rows.length ? rows : [el("p", { class: "muted small" }, "No auditable entities yet (Audit universe).")])),
      wsToolbar(wsAction("Back", () => go("objectives")), wsAction("Continue", () => go("review"), { primary: true, focus: true })));
  }
  function review() {
    f.setHead("Review");
    const objs = fo.all.filter((o) => data.objectives.has(objKey(o)));
    const ents = units.filter((u) => data.entities.has(u.id));
    f.body.append(wsCard(null, wsFieldRows([
      { label: "Project name", control: el("span", null, data.title) },
      { label: "Project type", control: el("span", null, data.audit_type || "-") },
      { label: "Estimated project start", control: el("span", null, `${data.planned_quarter} FY${plan.fiscal_year}`) },
      { label: "Budgeted hours", control: el("span", null, String(data.budget_hours || 0)) },
      { label: "Objectives", control: el("span", null, objs.length ? objs.map((o) => o.title).join("; ") : "None yet") },
      { label: "Entities", control: el("span", null, ents.length ? ents.map((u) => u.name).join("; ") : "None") },
    ])), wsToolbar(wsAction("Back", () => go("entities")), wsAction("Create project", async () => {
      try {
        await API.post(`/api/assurance-plans/${plan.id}/engagements`, { title: data.title.trim(), audit_type: data.audit_type || null,
          planned_quarter: data.planned_quarter, budget_hours: Number(data.budget_hours || 0), entity_unit_id: ents.length ? ents[0].id : null,
          objectives: objs.map((o) => ({ program_id: o.program_id, title: o.title })), entity_unit_ids: ents.map((u) => u.id) });
        toast("Project created"); openPlan(plan.id);
      } catch (err) { toast(err.message, "error"); if ((err.errors || []).some((e) => e.field === "title")) go("basic"); }
    }, { primary: true, focus: true })));
  }
  go("basic");
}

async function linkProjectsPage(plan, mode) {
  const back = () => openPlan(plan.id);
  const creator = hasPerm("audit.create");
  const [active, cands] = await Promise.all([safeGet(`/api/assurance-plans/${plan.id}/includable-audits`, []),
    creator ? safeGet(`/api/assurance-plans/${plan.id}/rollforward-candidates`, []) : Promise.resolve([])]);
  const f = plansFrame({ context: plan.title, side: [{ key: "add", label: "Add to plan" }, { key: "projects", label: "Projects" }], active: "add",
    onSide: (k) => (k === "projects" ? openPlanTab(plan.id, "projects") : addToPlan(plan)),
    crumb: ["Assurance Plans", { label: plan.title, onClick: back }, "Add to plan"], title: "Choose an existing project path" });
  // Link active projects.
  const chosen = new Set();
  const quarter = wsSelect(QUARTERS, "Q1", { "aria-label": "Quarter", class: "ws-input compact" });
  const reason = plan.status === "Approved" ? wsText("", { placeholder: "Reason for changing the approved plan", "aria-label": "Reason", maxlength: "2000" }) : null;
  const linkCard = wsCard("Link active projects",
    ...(active.length ? active.map((a) => {
      const cb = el("input", { type: "checkbox", onchange: (e) => { if (e.target.checked) chosen.add(a.id); else chosen.delete(a.id); } });
      return wsRow(el("label", null, cb, ` ${a.title}`), wsTag(a.status === "In Progress" ? "Active" : a.status));
    }) : [el("p", { class: "muted small" }, "No active project outside a plan.")]),
    reason, wsToolbar(el("label", { class: "ws-caption" }, "Quarter "), quarter, wsAction("Link projects", async () => {
      if (!chosen.size) { toast("Select at least one project", "error"); return; }
      try {
        const r = await API.post(`/api/assurance-plans/${plan.id}/include`, { audit_ids: [...chosen], quarter: quarter.value, reason: reason ? reason.value : "" });
        toast(`${r.included} project(s) linked`); back();
      } catch (err) { toast(err.message, "error"); }
    }, { primary: true, focus: mode === "link" })));
  // Rollforward a project.
  const search = wsInput("", { type: "search", placeholder: "Search project name", "aria-label": "Search or filter" });
  const list = el("div", { class: "ws-list-pick" });
  const paint = () => {
    const q = search.value.trim().toLowerCase();
    list.replaceChildren(...cands.filter((a) => !q || `${a.ref} ${a.title}`.toLowerCase().includes(q)).map((a) => wsRow(
      el("label", null, el("input", { type: "radio", name: "rf-src", value: String(a.id) }), ` ${a.title}`,
        el("span", { class: "ws-caption" }, `${a.ref}${a.plan ? ` · ${a.plan}` : ""} · ${a.status}`)),
      wsAction("Continue", () => rollforwardDetails(plan, a)))));
    if (!list.children.length) list.append(el("p", { class: "muted small" }, creator ? "No earlier project to roll forward." : "Rolling forward needs the Project Creator permission."));
  };
  search.addEventListener("input", paint);
  paint();
  const rfCard = wsCard("Rollforward a project", wsField("Search or filter", search), list,
    el("p", null, "Next: provide basic information → ", el("b", null, "Continue"), " → review → ", el("b", null, "Save and rollforward project"), "."));
  f.body.append(mode === "rollforward" ? rfCard : linkCard, mode === "rollforward" ? linkCard : rfCard);
  if (mode === "rollforward") search.focus();
}

function rollforwardDetails(plan, source) {
  const back = () => openPlan(plan.id);
  const steps = [{ key: "basic", label: "Basic information" }, { key: "review", label: "Review" }];
  const data = { title: source.title.replace(/\b(FY)?20\d\d\b/, `FY${plan.fiscal_year}`), planned_quarter: "Q1", budget_hours: "" };
  const f = plansFrame({ context: plan.title, side: steps, active: "basic", onSide: (k) => go(k),
    crumb: ["Assurance Plans", { label: plan.title, onClick: back }, "Add to plan", "Rollforward project"] });
  function go(k) {
    f.setActive(k); clear(f.body);
    if (k === "basic") {
      f.setHead(`Rollforward ${source.ref} · Basic information`);
      const name = wsInput(data.title, { name: "title", maxlength: "255" });
      const q = wsSelect(QUARTERS, data.planned_quarter, { name: "planned_quarter" });
      const hrs = wsInput(data.budget_hours, { name: "budget_hours", type: "number", min: "0", max: "10000" });
      f.body.append(wsCard(null, wsFieldRows([{ label: "Source project", control: el("span", null, `${source.ref} ${source.title}`) },
        { label: "Project name", control: name }, { label: "Estimated project start", control: el("div", { class: "ws-inline" }, q, el("span", null, `FY${plan.fiscal_year}`)) },
        { label: "Budgeted hours", control: hrs }]),
      wsToolbar(wsAction("Back", () => linkProjectsPage(plan, "rollforward")), wsAction("Continue", () => {
        if (!name.value.trim()) { toast("Enter the project name", "error"); return; }
        data.title = name.value; data.planned_quarter = q.value; data.budget_hours = hrs.value; go("review");
      }, { primary: true, focus: true }))));
    } else {
      f.setHead("Review");
      f.body.append(wsCard(null, wsFieldRows([{ label: "Source project", control: el("span", null, `${source.ref} ${source.title}`) },
        { label: "Project name", control: el("span", null, data.title) }, { label: "Estimated project start", control: el("span", null, `${data.planned_quarter} FY${plan.fiscal_year}`) },
        { label: "Budgeted hours", control: el("span", null, String(data.budget_hours || 0)) },
        { label: "Carried forward", control: el("span", null, "Objectives, risks, controls with their test plan, narratives and procedures. Results and sign-offs are not carried forward.") }]),
      wsToolbar(wsAction("Back", () => go("basic")), wsAction("Save and rollforward project", async () => {
        try {
          await API.post(`/api/assurance-plans/${plan.id}/rollforward`, { audit_id: source.id, title: data.title.trim(), planned_quarter: data.planned_quarter,
            budget_hours: Number(data.budget_hours || 0) });
          toast("Project rolled forward"); back();
        } catch (err) { toast(err.message, "error"); }
      }, { primary: true, focus: true }))));
    }
  }
  go("basic");
}

function openPlanTab(id, tab) { state.lastPlanTab = { id, key: tab }; openPlan(id); }

// ------------------------------------------------------------------ Coverage, Risks, Progress & resources

async function renderPlanCoverage(pane, plan) {
  const values = state.covFilter && state.covFilter.plan === plan.id ? state.covFilter : { plan: plan.id, view: "entities", filter: "" };
  state.covFilter = values;
  const reload = () => { clear(pane); renderPlanCoverage(pane, plan); };
  pane.append(loadingState());
  let cov;
  try { cov = await API.get(`/api/assurance-plans/${plan.id}/coverage`); } catch (err) { clear(pane); pane.append(errorState(err, reload)); return; }
  clear(pane);
  pane.append(el("h3", { class: "ws-h" }, "Coverage monitoring"));
  const view = wsSelect([{ value: "entities", label: "Entities" }, { value: "categories", label: "Categories" }], values.view, { "aria-label": "Coverage view", class: "ws-input compact" });
  view.addEventListener("change", () => { values.view = view.value; values.filter = ""; reload(); });
  const cats = [...new Map(cov.entities.map((u) => [u.location_id, u.location])).entries()].sort((a, b) => a[1].localeCompare(b[1]));
  const filterOpts = values.view === "entities"
    ? [{ value: "", label: "All categories" }, ...cats.map(([id, n]) => ({ value: id, label: n })), { value: "uncovered", label: "Entities not covered" }]
    : [{ value: "", label: "All categories" }, ...cats.map(([id, n]) => ({ value: id, label: n }))];
  const filt = wsSelect(filterOpts, values.filter, { "aria-label": "Coverage filter", class: "ws-input compact" });
  filt.addEventListener("change", () => { values.filter = filt.value; reload(); });
  pane.append(wsCard(null, wsRow(el("span", null, "Show coverage in　", view), filt)));
  const live = cov.engagements;
  if (!live.length) { pane.append(emptyState({ icon: "grid-3x3", title: "No projects in the plan yet" })); return; }
  let cols;
  let covers;
  if (values.view === "entities") {
    cols = cov.entities.filter((u) => !values.filter || (values.filter === "uncovered" ? !u.covered : String(u.location_id) === String(values.filter)));
    covers = (e, u) => (e.entity_ids || []).includes(u.id);
  } else {
    const locOf = Object.fromEntries(cov.entities.map((u) => [u.id, u.location_id]));
    cols = cats.filter(([id]) => !values.filter || String(id) === String(values.filter)).map(([id, name]) => ({ id, name }));
    covers = (e, c) => (e.entity_ids || []).some((x) => locOf[x] === c.id);
  }
  pane.append(el("div", { class: "table-wrap cov-wrap" }, el("table", { class: "ws-table cov-grid" },
    el("thead", null, el("tr", null, ...["Project", "Status", "Hours", "Progress"].map((h) => el("th", { scope: "col" }, h)),
      ...cols.map((c) => el("th", { scope: "col", title: c.location ? `${c.location} / ${c.name} · risk ${c.risk}` : c.name }, c.name)))),
    el("tbody", null, ...live.map((e) => el("tr", { class: `${e.audit_id ? "clickable" : ""} ${e.cancelled ? "row-muted" : ""}`, onclick: e.audit_id ? () => openAudit(e.audit_id) : null },
      el("td", null, e.title), el("td", null, e.status === "In Progress" ? "Active" : e.status), el("td", { class: "num" }, e.hours.toLocaleString()),
      el("td", null, `${e.progress}% `, wsBar(e.progress)),
      ...cols.map((c) => el("td", { class: "ws-check" }, covers(e, c) ? el("span", { "aria-label": "Covered", title: `${e.title} covers ${c.name}` }, "✓") : null)))),
    values.view === "entities" && cols.length ? el("tr", { class: "cov-foot" }, el("td", { class: "muted small" }, "Coverage"), el("td"), el("td"), el("td"),
      ...cols.map((u) => el("td", null, u.covered ? wsTag("Covered", "ok") : wsTag("Not covered", u.risk === "High" ? "bad" : "")))) : null))));
  pane.append(el("p", { class: "ws-caption" }, "Coverage comes from the entities each project is tagged with."));
}

async function renderPlanStrategicRisks(pane, plan) {
  pane.append(loadingState());
  const p = await safeGet(`/api/assurance-plans/${plan.id}/program`, null);
  clear(pane);
  if (!p) { pane.append(errorState({ message: "Could not load the plan" })); return; }
  pane.append(el("h3", { class: "ws-h" }, "Strategic risks"));
  if (!p.strategic_risks.length) {
    pane.append(emptyState({ icon: "shield-exclamation", title: "No strategic risk is linked yet" }),
      wsNote("Strategic risks appear here when they are linked to the plan's projects: through Strategy › Treatment (framework or project objectives), audit risks that test them, or the projects' entities."));
    return;
  }
  const heatCell = (pct, score) => el("td", null, el("span", { class: "heat-pct", style: `color:${pct >= 60 ? "var(--ws-red)" : pct >= 32 ? "#c27c0e" : "var(--ws-green)"};font-size:20px` }, `${pct}%`),
    el("br"), el("span", { class: "ws-caption" }, `Score: ${score}`));
  pane.append(el("div", { class: "table-wrap" }, el("table", { class: "ws-table" },
    el("thead", null, el("tr", null, ...["Risk", "Inherent Risk Heat", "Residual Risk Heat", "Overall Assurance", "Description"].map((h) => el("th", { scope: "col" }, h)))),
    el("tbody", null, ...p.strategic_risks.map((r) => el("tr", { class: "clickable", onclick: () => openRisk(r.id) },
      el("td", null, el("span", { class: "ref" }, r.ref), ` ${r.title}`, el("div", { class: "ws-caption" }, `${r.projects} project${r.projects === 1 ? "" : "s"}`)),
      heatCell(r.inherent_heat, r.inherent_score), heatCell(r.residual_heat, r.score),
      el("td", null, r.overall_assurance === null ? el("span", { class: "muted" }, "Not tested") : [`${r.overall_assurance}% `, wsBar(r.overall_assurance)]),
      el("td", null, r.description || el("span", { class: "muted" }, "-"))))))));
  pane.append(el("p", { class: "ws-caption" }, "Heat = score ÷ 25 (likelihood × impact). Overall assurance = treated controls tested and effective, from the risk's Assurance view."));
}

async function renderPlanResources(pane, plan) {
  pane.append(loadingState());
  const p = await safeGet(`/api/assurance-plans/${plan.id}/program`, null);
  clear(pane);
  if (!p) { pane.append(errorState({ message: "Could not load the plan" })); return; }
  const live = p.projects.filter((r) => !r.cancelled);
  pane.append(el("h3", { class: "ws-h" }, "Progress & resources"), progressCard(p));
  pane.append(wsCard("Projects", live.length ? el("table", { class: "ws-table" },
    el("thead", null, el("tr", null, ...["Project", "Budget", "Charged", "Progress"].map((h) => el("th", { scope: "col" }, h)))),
    el("tbody", null, ...live.map((r) => el("tr", { class: r.audit_id ? "clickable" : null, onclick: r.audit_id ? () => openAudit(r.audit_id) : null },
      el("td", null, r.title), el("td", { class: "num" }, `${r.hours.toLocaleString()} hrs`),
      el("td", { class: `num ${r.actual_hours > r.hours && r.hours ? "text-danger" : ""}` }, `${r.actual_hours} hrs`),
      el("td", null, `${r.progress}% `, wsBar(r.progress)))))) : el("p", { class: "muted" }, "No projects yet.")));
  pane.append(el("p", { class: "ws-caption" }, "Project progress: each phase counts Not Started 0, In Process 1, Completed 2; overall progress is the average of the projects."));
}

// ------------------------------------------------------------------ narratives: import a document into an objective

function importNarrativeForm(targets, after) {
  const file = el("input", { type: "file", accept: ".docx,.xlsx,.txt", "aria-label": "Narrative document" });
  const obj = el("select", { class: "ws-input", "aria-label": "Objective" }, ...targets.map((o) => el("option", { value: o.id }, `${o.ref} ${clip(o.title, 60)}`)));
  const title = wsInput("", { maxlength: "60", placeholder: "Defaults to the file name", "aria-label": "Narrative title" });
  const m = modal({
    title: "Import narrative", width: 620,
    body: wsFieldRows([{ label: "Document", control: file }, { label: "Objective", control: obj }, { label: "Title", control: title }]),
    footer: el("div", { class: "actions" }, wsAction("Cancel", () => m.close()), wsAction("Import", async () => {
      if (!file.files.length) { toast("Choose a document first", "error"); return; }
      const fd = new FormData();
      fd.append("file", file.files[0]);
      fd.append("title", title.value.trim());
      try { const r = await API.upload(`/api/objectives/${obj.value}/narratives/import`, fd); toast(`${r.ref} created from the document`); m.close(); if (after) after(); }
      catch (err) { toast(err.message, "error"); }
    }, { primary: true })),
  });
}
