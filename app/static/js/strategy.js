// Strategy (Risk Manager) - Strategy walkthrough and Risk-Based Assurance Planning walkthrough:
//   the risk page (Details, Assessment, Treatment, Metrics, Assurance), Define Risk Treatment, the Risk Library and
//   Planning feedback for the next assurance cycle.
// Loaded after grc.js / walk.js.

async function openRisk(id, tab = null) {
  clear(viewRoot);
  let r;
  try { r = await API.get(`/api/grc/risks/${id}`); } catch (err) { toast(err.message, "error"); return; }
  grcOpened("risk");
  const reload = (t) => openRisk(id, t);
  const tabs = [{ key: "details", label: "Details" }, { key: "assessment", label: "Assessment" }, { key: "treatment", label: "Treatment" },
    { key: "metrics", label: "Metrics", count: r.kris.filter((k) => k.rag === "Red").length || null }, { key: "assurance", label: "Assurance" }];
  const layout = recordLayout({
    app: "Risk Manager", crumbs: recordCrumbs("risk", r.ref), back: grcBack(() => renderRiskManager()), title: r.title, ref: r.ref, status: r.status,
    meta: [r.category ? el("span", { class: "chip-mini" }, r.category) : null, r.review_overdue ? el("span", { class: "chip-mini warn" }, "Review overdue") : null].filter(Boolean),
    utility: [{ label: "Heatmaps", icon: "grid-3x3", onClick: () => renderRiskManager("heat") }, { label: "Assurance Plans", icon: "calendar3", onClick: () => navigate("plans") }],
    actions: [r.can_edit ? wsAction("Edit", () => riskForm(r), { icon: "pencil" }) : null].filter(Boolean),
    tabs, side: null,
    onTab: (key, pane) => {
      if (key === "details") riskDetailsPane(pane, r, reload);
      if (key === "assessment") riskAssessmentPane(pane, r);
      if (key === "treatment") riskTreatmentPane(pane, r, reload);
      if (key === "metrics") riskMetricsPane(pane, r, reload);
      if (key === "assurance") riskAssurancePane(pane, r);
    },
  });
  viewRoot.append(layout.root);
  layout.select(tab || "details");
}

function riskDetailsPane(pane, r, reload) {
  const v = (x) => (x ? el("span", { class: "pre" }, x) : el("span", { class: "muted" }, "-"));
  pane.append(el("h3", { class: "ws-h" }, "Describe the risk and map its context"));
  pane.append(wsCard(null, wsFieldRows([
    { label: "Risk name", control: v(r.title) }, { label: "Description", control: v(r.description) },
    { label: "Strategic objectives", control: v(r.objective) }, { label: "Operating segments / entity", control: v(r.entity) },
    { label: "Risk owner / attributes", control: v([r.owner, r.category, r.appetite ? `Appetite ${r.appetite}` : null].filter(Boolean).join("　/　")) },
    { label: "Causes", control: v(r.cause) }, { label: "Consequences", control: v(r.consequence) },
    { label: "Treatment response", control: v([r.treatment, r.treatment_plan].filter(Boolean).join(": ")) },
  ]), r.can_edit ? wsToolbar(wsAction("Edit details", () => riskForm(r), { primary: true })) : null));
  pane.append(linksCard("risk", r.id, r.links, ["control", "requirement", "asset", "unit", "policy"], r.can_edit, () => reload("details")));
}

function riskAssessmentPane(pane, r) {
  pane.append(el("h3", { class: "ws-h" }, "Assess inherent risk"));
  const pos = (lk, im, label) => el("div", { class: "score-box" }, el("div", { class: "muted small" }, label),
    lk ? levelChip(GRC_band(lk * im), lk * im) : el("span", { class: "muted" }, "-"), lk ? el("div", { class: "muted small" }, `Likelihood ${lk} × Impact ${im}`) : null);
  pane.append(wsCard(null, wsFieldRows([{ label: "Strategic objectives", control: el("span", null, r.objective || "-") }]),
    el("div", { class: "score-row" }, pos(r.inherent_likelihood, r.inherent_impact, "Inherent"), el("i", { class: "bi bi-arrow-right muted" }),
      pos(r.residual_likelihood, r.residual_impact, "Residual"), el("i", { class: "bi bi-arrow-right muted" }), pos(r.target_likelihood, r.target_impact, "Target")),
    r.above_target ? wsNote("Residual risk is above the target: the treatment plan needs to go further.") : null,
    wsToolbar(wsAction("Risk scoring definitions", () => riskScoringDefinitions()),
      r.can_assess && r.status !== "Closed" ? wsAction("Assess", () => assessRiskForm(r), { primary: true, focus: true }) : null)));
  pane.append(wsCard("Assessment history", dataTable(r.assessments, [
    { key: "at", label: "When", render: (a) => fmtDate(a.at) }, { key: "by", label: "By" },
    { key: "inherent_score", label: "Inherent", num: true }, { key: "residual_score", label: "Residual", num: true },
    { key: "control_effectiveness", label: "Controls" }, { key: "comment", label: "Comment" },
  ], { pageSize: 10 })));
}

function riskScoringDefinitions() {
  const t = GRC.thr || { high: 15, medium: 8 };
  modal({ title: "Risk scoring definitions", width: 560, body: el("div", null,
    el("p", null, "Score = Likelihood (1-5) × Impact (1-5)."),
    el("table", { class: "ws-table" }, el("thead", null, el("tr", null, el("th", null, "Level"), el("th", null, "Score"))),
      el("tbody", null, el("tr", null, el("td", null, "High"), el("td", null, `${t.high} - 25`)), el("tr", null, el("td", null, "Medium"), el("td", null, `${t.medium} - ${t.high - 1}`)),
        el("tr", null, el("td", null, "Low"), el("td", null, `1 - ${t.medium - 1}`)))),
    el("p", { class: "ws-caption" }, "Thresholds are set by administrators (Configuration › Plan configuration).")) });
}

async function riskTreatmentPane(pane, r, reload) {
  pane.append(loadingState());
  let a;
  try { a = await API.get(`/api/grc/risks/${r.id}/assurance`); } catch (err) { clear(pane); pane.append(errorState(err)); return; }
  clear(pane);
  pane.append(el("h3", { class: "ws-h" }, "Link the strategic risk to assurance objectives"));
  const define = el("div");
  pane.append(wsToolbar(a.can_edit ? wsAction("Link Treatment", () => { define.hidden = false; define.replaceChildren(); defineTreatment(define, r, () => reload("treatment")); }, { primary: true, focus: !a.treatments.length }) : null));
  pane.append(define);
  pane.append(wsCard("Treatment areas", ...(a.treatments.length ? a.treatments.map((t) => wsRow(el("span", null, el("b", null, t.title), el("span", { class: "ws-caption" },
    `${t.type} · ${t.source || "-"}${t.type === "Framework objective" ? ` · ${t.objectives} project objective${t.objectives === 1 ? "" : "s"}` : ""}`)),
  el("span", { class: "ws-inline" }, wsTag(`${t.passing} passing · ${t.failing} failing · ${t.not_tested} not tested`),
    t.audit_id ? wsAction("View", () => openAudit(t.audit_id, "fieldwork")) : wsAction("View", () => navigate("programs")),
    a.can_edit ? wsAction("Unlink", async () => {
      try { await API.del(`/api/grc/risks/${r.id}/treatments/${t.treatment_id}`); toast("Treatment link removed"); reload("treatment"); } catch (err) { toast(err.message, "error"); }
    }) : null))) : [el("p", { class: "muted" }, "No treatment linked yet.")])));
  const tested = a.objectives.filter((o) => o.link === "Tests the risk");
  if (tested.length) pane.append(wsCard("Audit risks that test this risk", ...tested.map((o) => wsRow(`${o.ref} ${o.title}`, o.audit || "-"))));
  pane.append(wsNote("Linking framework objectives aggregates assurance across projects. Link a risk to either parent framework objectives or child project objectives, not both."));
}

async function defineTreatment(box, r, after) {
  const q = wsInput("", { type: "search", placeholder: "Search name…", "aria-label": "Find projects/frameworks" });
  const tree = el("div", { class: "ws-tree ws-list-pick" });
  const chosenFw = new Map();
  const chosenObj = new Map();
  const count = el("span");
  const go = wsAction("Link 0 Treatments", null, { primary: true, disabled: true });
  const sync = () => {
    const n = chosenFw.size + chosenObj.size;
    go.textContent = `Link ${n} Treatment${n === 1 ? "" : "s"}`; go.disabled = !n;
    count.replaceChildren(...[...chosenFw.values(), ...chosenObj.values()].map((t) => wsRow(`Selected: ${t}`, wsTag("Objective"))));
  };
  let timer = null;
  const search = async () => {
    const rows = await safeGet(`/api/grc/treatment-sources?q=${encodeURIComponent(q.value.trim())}`, []);
    tree.replaceChildren(...(rows.length ? rows.map((s) => el("details", null,
      el("summary", null, el("span", null, `${s.name} ›`), el("span", { class: "ws-caption" }, s.type === "framework" ? `Framework ${s.ref}` : `Project ${s.ref} · ${s.status}`)),
      ...s.objectives.map((o) => {
        const key = s.type === "framework" ? `${s.id}|${o.title}` : String(o.id);
        const map = s.type === "framework" ? chosenFw : chosenObj;
        const cb = el("input", { type: "checkbox", checked: map.has(key) ? "1" : null });
        cb.addEventListener("change", () => { if (cb.checked) map.set(key, o.title); else map.delete(key); sync(); });
        return el("label", null, cb, ` ${o.ref ? `${o.ref} ` : ""}${o.title}`);
      }))) : [el("p", { class: "muted small" }, "No projects or frameworks found.")]));
  };
  q.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(search, 300); });
  go.addEventListener("click", async () => {
    try {
      const res = await API.post(`/api/grc/risks/${r.id}/treatments`, {
        framework_objectives: [...chosenFw.keys()].map((k) => ({ program_id: Number(k.split("|")[0]), title: k.split("|").slice(1).join("|") })),
        objective_ids: [...chosenObj.keys()].map(Number) });
      toast(`${res.linked} treatment${res.linked === 1 ? "" : "s"} linked`); after();
    } catch (err) { toast(err.message, "error"); }
  });
  box.append(wsCard("Define Risk Treatment", wsField("Find projects/frameworks", q), tree, count,
    wsToolbar(wsAction("Cancel", () => { box.hidden = true; }), go)));
  search();
  q.focus();
}

function riskMetricsPane(pane, r, reload) {
  pane.append(el("h3", { class: "ws-h" }, "Connect ongoing indicators"));
  pane.append(wsCard("Linked metrics", ...(r.kris.length ? r.kris.map((k) => wsRow(el("span", null, el("b", null, k.name),
    el("span", { class: "ws-caption" }, `Amber ${k.higher_is_worse ? "≥" : "≤"} ${k.amber_at} · Red ${k.higher_is_worse ? "≥" : "≤"} ${k.red_at} ${k.unit} · ${k.frequency}${k.owner ? ` · ${k.owner}` : ""}`)),
  el("span", { class: "ws-inline" }, wsTag(`KRI · ${k.readings.length ? `${k.readings[0].value} ${k.unit}` : "no reading"}`, k.rag === "Red" ? "bad" : k.rag === "Amber" ? "warn" : "ok"),
    (r.can_assess || k.owner_id === state.user.id) ? wsAction("Record reading", () => kriReadingForm(k, r.id, () => reload("metrics"))) : null,
    r.can_edit ? wsAction("Edit", () => kriForm(r.id, k)) : null))) : [el("p", { class: "muted" }, "No metrics linked yet.")]),
  r.can_edit ? wsToolbar(wsAction("Link Metrics", () => kriForm(r.id, null), { primary: true, focus: !r.kris.length })) : null));
}

async function riskAssurancePane(pane, r) {
  pane.append(loadingState());
  let a;
  try { a = await API.get(`/api/grc/risks/${r.id}/assurance`); } catch (err) { clear(pane); pane.append(errorState(err)); return; }
  clear(pane);
  const c = a.controls;
  pane.append(el("h3", { class: "ws-h" }, "Review aggregated assurance and residual risk"));
  pane.append(wsGrid(
    wsCard("Overall assurance", el("p", { class: "ws-big" }, a.overall_assurance === null ? "-" : `${a.overall_assurance}%`), wsBar(a.overall_assurance || 0, "wide")),
    wsCard("Residual risk", el("p", null, el("b", null, a.residual_level), `　　Inherent: ${a.inherent_level}`))));
  pane.append(wsCard("Results across treatment areas", el("div", { class: "ws-flow" },
    el("span", null, `Passing controls　 ${c.passing}`), el("span", null, `Failing controls　 ${c.failing}`), el("span", null, `Not tested　 ${c.not_tested}`))));
  const i = a.issues;
  pane.append(wsCard("Issue trends", el("p", null, `New　${i.new_90_days}　　Remediated　${i.remediated}　　Total　${i.total}`), wsBar(i.total ? (100 * i.remediated) / i.total : 0, "wide")));
  pane.append(wsCard("Treatment areas", ...(a.treatments.length ? a.treatments.map((t) => wsRow(el("span", null, t.title, el("span", { class: "ws-caption" }, `${t.type} · ${t.source || "-"}`)),
    el("span", { class: "ws-inline" }, wsTag(`${t.passing}/${t.passing + t.failing + t.not_tested} passing`), t.audit_id ? wsAction("View", () => openAudit(t.audit_id, "fieldwork")) : null)))
    : [el("p", { class: "muted" }, "No treatment linked. Link treatments on the Treatment tab.")])));
  pane.append(wsNote(a.basis, " Issues must be created inside a linked objective and published to roll up."));
}

// ------------------------------------------------------------------ Risk Library and Planning feedback

async function renderRiskLibrary(body, industry = "") {
  body.append(loadingState());
  let lib;
  try { lib = await API.get(`/api/grc/risk-library${industry ? `?industry=${encodeURIComponent(industry)}` : ""}`); } catch (err) { clear(body); body.append(errorState(err)); return; }
  clear(body);
  const ind = wsSelect([{ value: "", label: "All industries" }, ...lib.industries], industry, { "aria-label": "Industry", class: "ws-input compact" });
  ind.addEventListener("change", () => { clear(body); renderRiskLibrary(body, ind.value); });
  const chosen = new Set();
  const go = wsAction("Import (0) Risks", null, { primary: true, disabled: true, focus: true });
  const sync = () => { go.textContent = `Import (${chosen.size}) Risks`; go.disabled = !chosen.size; };
  go.addEventListener("click", async () => {
    try { const r = await API.post("/api/grc/risk-library/import", { keys: [...chosen] }); toast(`${r.imported} risk${r.imported === 1 ? "" : "s"} imported`); renderRiskManager("register"); }
    catch (err) { toast(err.message, "error"); }
  });
  body.append(wsGrid(
    wsCard("Risk Library", wsRow(el("span", { class: "ws-caption" }, "Filter by industry and select risks relevant to your organization."), ind),
      ...lib.risks.map((x) => {
        const cb = el("input", { type: "checkbox", disabled: x.in_register ? "1" : null, onchange: (e) => { if (e.target.checked) chosen.add(x.key); else chosen.delete(x.key); sync(); } });
        return wsRow(el("label", { title: x.description }, cb, ` ${x.title}`, el("span", { class: "ws-caption" }, x.description)), x.in_register ? wsTag("In register", "ok") : wsTag(x.category || "General"));
      }), wsToolbar(go)),
    wsCard("Or create manually", el("p", null, "Add a risk with its name and description, then assess it and link its treatments."),
      wsAction("+ Add", () => riskForm(null), { primary: true }))));
  body.append(el("p", { class: "ws-caption" }, "Review industry risks first; add only risks that apply to your organization. Imported risks start at a neutral 3 × 3 score until assessed."));
}

async function renderPlanningFeedback(body) {
  body.append(loadingState());
  let s;
  try { s = await API.get("/api/assurance-plans/next-cycle-signals"); }
  catch (err) { clear(body); body.append(err.status === 403 ? wsNote("Planning feedback is for plan preparers and approvers.") : errorState(err)); return; }
  clear(body);
  body.append(el("h3", { class: "ws-h" }, "Feed risk insights into the next assurance cycle"));
  const top = s.risks.find((r) => r.signal !== "Covered");
  const action = top ? { "No linked assurance": "Define objectives and coverage for this risk in the next assurance period.", "Failing controls": "Follow up and retest the failing controls.",
    "Not yet tested": "Plan testing of the linked controls.", "Open issues": "Follow up the open issues and retest.", "Partly tested": "Complete testing of the remaining controls." }[top.signal] : null;
  body.append(wsGrid(
    wsCard("Risk requiring more coverage", el("p", null, top ? `${top.ref} ${top.title}` : "None: every high or above-target risk is covered."), top ? wsTag(`Residual risk: ${top.residual_level}`, top.residual_level === "High" ? "bad" : "warn") : null),
    wsCard("Suggested planning action", el("p", null, action || "Keep the current coverage."), wsAction("Open Assurance Plans", () => navigate("plans"), { primary: true }))));
  body.append(el("div", { class: "table-wrap" }, el("table", { class: "ws-table" },
    el("thead", null, el("tr", null, ...["Strategic risk", "Risk state", "Linked assurance", "Planning signal"].map((h) => el("th", { scope: "col" }, h)))),
    el("tbody", null, ...s.risks.map((r) => el("tr", { class: "clickable", onclick: () => openRisk(r.id, "assurance") },
      el("td", null, `${r.ref} ${r.title}`), el("td", null, wsTag(r.residual_level, r.residual_level === "High" ? "bad" : "warn")),
      el("td", null, !r.linked_objectives ? "No linked treatment" : `${r.controls.passing} passing · ${r.controls.failing} failing · ${r.controls.not_tested} not tested${r.open_issues ? ` · ${r.open_issues} open issue(s)` : ""}`),
      el("td", null, r.signal)))))));
  body.append(el("p", { class: "ws-caption" }, s.note));
}
