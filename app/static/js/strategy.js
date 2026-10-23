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
    record: { type: "erm_risk", id: r.id },
    meta: [r.category ? el("span", { class: "chip-mini" }, r.category) : null, r.review_overdue ? el("span", { class: "chip-mini warn" }, "Review overdue") : null].filter(Boolean),
    utility: [{ label: "Heatmaps", icon: "grid-3x3", onClick: () => renderRiskManager("heat") }, { label: "Assurance Plans", icon: "calendar3", onClick: () => navigate("plans") }],
    actions: [r.can_edit ? wsAction("Edit", () => riskForm(r), { icon: "pencil" }) : null].filter(Boolean),
    tabs, side: null,
    onTab: (key, pane) => {
      if (key === "details") riskDetailsPane(pane, r, reload);
      if (key === "assessment") riskAssessmentPane(pane, r, reload);
      if (key === "treatment") riskTreatmentPane(pane, r, reload);
      if (key === "metrics") riskMetricsPane(pane, r, reload);
      if (key === "assurance") riskAssurancePane(pane, r);
    },
  });
  viewRoot.append(layout.root);
  layout.select(tab || "details");
}

// Details: the risk's fields edited in place (Risk name, Description, Strategic objectives, Operating segments, Risk
// owner / attributes, causes, consequences, treatment response), saved with Save changes.
async function riskDetailsPane(pane, r, reload) {
  const v = (x) => (x ? el("span", { class: "pre" }, x) : el("span", { class: "muted" }, "-"));
  pane.append(el("h3", { class: "ws-h" }, "Describe the risk and map its context"));
  if (!r.can_edit) {
    pane.append(wsCard(null, wsFieldRows([
      { label: "Risk name", control: v(r.title) }, { label: "Description", control: v(r.description) },
      { label: "Strategic objectives", control: v(r.objective) }, { label: "Operating segments", control: v(r.entity) },
      { label: "Risk owner / attributes", control: v([r.owner, r.category, r.appetite ? `Appetite ${r.appetite}` : null].filter(Boolean).join("　/　")) },
      { label: "Causes", control: v(r.cause) }, { label: "Consequences", control: v(r.consequence) },
      { label: "Treatment response", control: v([r.treatment, r.treatment_plan].filter(Boolean).join(": ")) },
    ])));
  } else {
    const [p, ents, objs, reg] = await Promise.all([grcPeople(), grcEntities(), safeGet("/api/grc/objectives", []), safeGet("/api/grc/risks?status=__none__", { categories: [], appetites: [], treatments: [] })]);
    const opt = (list, cur, empty) => wsSelect([{ value: "", label: empty }, ...list], cur ?? "", {});
    const name = wsInput(r.title, { name: "title", maxlength: "255" });
    const desc = wsText(r.description || "", { name: "description", rows: "3", maxlength: "20000" });
    const obj = opt(objs.map((o) => ({ value: o.id, label: `${o.ref} ${o.title}` })), r.objective_id, "No strategic objective");
    const seg = opt(entityOptions(ents), r.entity_id, "All segments");
    const owner = opt(personOptions(p), r.owner_id, "Risk owner");
    const cat = opt(reg.categories.map((c) => ({ value: c, label: c })), r.category, "Risk type");
    const app = opt(reg.appetites.map((c) => ({ value: c, label: c })), r.appetite, "Appetite");
    const cause = wsText(r.cause || "", { name: "cause", rows: "2", maxlength: "10000" });
    const cons = wsText(r.consequence || "", { name: "consequence", rows: "2", maxlength: "10000" });
    const treat = opt(reg.treatments.map((c) => ({ value: c, label: c })), r.treatment, "Treatment");
    const plan = wsText(r.treatment_plan || "", { name: "treatment_plan", rows: "2", maxlength: "20000" });
    [obj, seg, owner, cat, app, treat].forEach((x, i) => x.setAttribute("aria-label", ["Strategic objectives", "Operating segments", "Risk owner", "Risk type", "Appetite", "Treatment"][i]));
    const card = wsCard(null, wsFieldRows([
      { label: "Risk name", control: name }, { label: "Description", control: desc },
      { label: "Strategic objectives", control: obj }, { label: "Operating segments", control: seg },
      { label: "Risk owner / attributes", control: el("div", { class: "ws-inline" }, owner, el("span", null, "/"), cat, el("span", null, "/"), app) },
      { label: "Causes", control: cause }, { label: "Consequences", control: cons },
      { label: "Treatment response", control: el("div", { class: "ws-inline" }, treat, plan) },
    ]), wsToolbar(wsAction("Save changes", async () => {
      const body = { title: name.value.trim(), description: desc.value, cause: cause.value, consequence: cons.value, category: cat.value,
        objective_id: numOrNull(obj.value), entity_id: numOrNull(seg.value), owner_id: numOrNull(owner.value),
        inherent_likelihood: r.inherent_likelihood, inherent_impact: r.inherent_impact, residual_likelihood: r.residual_likelihood, residual_impact: r.residual_impact,
        target_likelihood: r.target_likelihood, target_impact: r.target_impact, appetite: app.value, treatment: treat.value, treatment_plan: plan.value, status: r.status };
      try { await API.put(`/api/grc/risks/${r.id}`, body); toast("Risk saved"); reload("details"); } catch (err) { wsShowErrors(card, err); }
    }, { primary: true })));
    pane.append(card);
  }
  pane.append(linksCard("risk", r.id, r.links, ["control", "requirement", "asset", "unit", "policy"], r.can_edit, () => reload("details")));
}

const ASSESS_ORIGIN = { manual: "Manual", kri: "Indicators", segments: "Segments" };

// Assessment (Strategy walkthrough › Assess inherent risk): strategic objectives, then a score for each operating
// segment (likelihood and impact, inherent and residual). Save records each segment and rolls the segments up to
// the risk (worst or average, a setting); with no segments the row is the whole organisation.
async function riskAssessmentPane(pane, r, reload) {
  pane.append(el("h3", { class: "ws-h" }, "Assess inherent risk across segments"));
  const can = r.can_assess && r.status !== "Closed";
  const [seg, objs, units] = await Promise.all([safeGet(`/api/grc/risks/${r.id}/segments`, { segments: [], method: "Worst", rollup: null }),
    safeGet("/api/grc/objectives", []), can ? safeGet("/api/organizations?active=true", { items: [] }) : { items: [] }]);
  const obj = wsSelect([{ value: "", label: "No strategic objective" }, ...objs.map((o) => ({ value: o.id, label: `${o.ref} ${o.title}` }))], r.objective_id ?? "",
    { "aria-label": "Strategic objectives", disabled: r.can_edit ? null : "1" });
  const sc = (v, label) => wsSelect([1, 2, 3, 4, 5], v, { "aria-label": label, class: "ws-input compact", disabled: can ? null : "1" });
  const rows = seg.segments.length ? seg.segments.map((x) => ({ org_id: x.org_id, label: x.segment, il: x.inherent_likelihood, ii: x.inherent_impact, rl: x.residual_likelihood, ri: x.residual_impact, by: x.by, at: x.at }))
    : [{ org_id: null, label: "Whole organisation", il: r.inherent_likelihood, ii: r.inherent_impact, rl: r.residual_likelihood, ri: r.residual_impact }];
  const tbody = el("tbody");
  const level = (l, i) => levelChip(GRC_band(l * i), l * i);
  const paintRow = (row) => {
    row.ctl = { il: sc(row.il, "Inherent likelihood"), ii: sc(row.ii, "Inherent impact"), rl: sc(row.rl, "Residual likelihood"), ri: sc(row.ri, "Residual impact") };
    const inh = el("td", null, level(row.il, row.ii)); const res = el("td", null, level(row.rl, row.ri));
    Object.values(row.ctl).forEach((c) => c.addEventListener("change", () => {
      row.dirty = true; inh.replaceChildren(level(Number(row.ctl.il.value), Number(row.ctl.ii.value))); res.replaceChildren(level(Number(row.ctl.rl.value), Number(row.ctl.ri.value)));
    }));
    tbody.append(el("tr", null, el("td", null, row.label, row.by ? el("span", { class: "ws-caption" }, `${row.by} · ${fmtDay(String(row.at).slice(0, 10))}`) : null),
      el("td", null, row.ctl.il), el("td", null, row.ctl.ii), inh, el("td", null, row.ctl.rl), el("td", null, row.ctl.ri), res));
  };
  rows.forEach(paintRow);
  const used = new Set(rows.map((x) => x.org_id));
  const addSel = wsSelect([{ value: "", label: "+ Add operating segment" }, ...(units.items || []).filter((o) => !used.has(o.id)).map((o) => ({ value: o.id, label: o.category ? `${o.name} (${o.category})` : o.name }))], "",
    { "aria-label": "Add operating segment", class: "ws-input compact" });
  addSel.addEventListener("change", () => {
    if (!addSel.value) return;
    const o = units.items.find((x) => String(x.id) === addSel.value);
    if (rows.length === 1 && rows[0].org_id === null) { rows.pop(); clear(tbody); }
    const row = { org_id: o.id, label: o.name, il: r.inherent_likelihood, ii: r.inherent_impact, rl: r.residual_likelihood, ri: r.residual_impact, dirty: true };
    rows.push(row); paintRow(row); addSel.querySelector(`option[value="${o.id}"]`).remove(); addSel.value = "";
  });
  const comment = wsText("", { rows: "2", maxlength: "5000", "aria-label": "What changed and why", placeholder: "What changed and why", disabled: can ? null : "1" });
  const card = wsCard(null, wsFieldRows([{ label: "Strategic objectives", control: obj }]),
    el("div", { class: "table-wrap" }, el("table", { class: "ws-table seg-table" },
      el("thead", null, el("tr", null, ...["Operating segment", "Likelihood", "Impact", "Inherent risk", "Residual likelihood", "Residual impact", "Residual risk"].map((h) => el("th", { scope: "col" }, h)))), tbody)),
    can ? el("div", { class: "ws-inline" }, addSel) : null, can ? comment : null,
    seg.segments.length > 1 ? el("p", { class: "ws-caption" }, `Segments roll up to the risk by the ${seg.method.toLowerCase()} segment (a setting).`) : null,
    wsToolbar(wsAction("Risk scoring definitions", () => riskScoringDefinitions()), can ? wsAction("Save", async () => {
      try {
        if (r.can_edit && String(obj.value) !== String(r.objective_id ?? "")) {
          await API.put(`/api/grc/risks/${r.id}`, { title: r.title, description: r.description || "", cause: r.cause || "", consequence: r.consequence || "", category: r.category || "",
            objective_id: numOrNull(obj.value), entity_id: r.entity_id, owner_id: r.owner_id, inherent_likelihood: r.inherent_likelihood, inherent_impact: r.inherent_impact,
            residual_likelihood: r.residual_likelihood, residual_impact: r.residual_impact, target_likelihood: r.target_likelihood, target_impact: r.target_impact,
            appetite: r.appetite || "", treatment: r.treatment || "", treatment_plan: r.treatment_plan || "", status: r.status });
        }
        const val = (row) => ({ inherent_likelihood: Number(row.ctl.il.value), inherent_impact: Number(row.ctl.ii.value), residual_likelihood: Number(row.ctl.rl.value), residual_impact: Number(row.ctl.ri.value) });
        const whole = rows.find((x) => x.org_id === null);
        if (whole) await API.post(`/api/grc/risks/${r.id}/assess`, { ...val(whole), comment: comment.value });
        const changed = rows.filter((x) => x.org_id !== null && x.dirty);
        for (const row of changed) await API.post(`/api/grc/risks/${r.id}/segments`, { org_id: row.org_id, ...val(row), comment: comment.value });
        if (!whole && (changed.length || seg.rollup && seg.rollup.differs)) await API.post(`/api/grc/risks/${r.id}/segments/rollup`);
        toast("Assessment saved"); reload("assessment");
      } catch (err) { wsShowErrors(card, err); }
    }, { primary: true, focus: true }) : null));
  pane.append(card);
  const pos = (lk, im, label) => el("div", { class: "score-box" }, el("div", { class: "muted small" }, label),
    lk ? levelChip(GRC_band(lk * im), lk * im) : el("span", { class: "muted" }, "-"), lk ? el("div", { class: "muted small" }, `Likelihood ${lk} × Impact ${im}`) : null);
  pane.append(wsCard("Risk scores", el("div", { class: "score-row" }, pos(r.inherent_likelihood, r.inherent_impact, "Inherent"), el("i", { class: "bi bi-arrow-right muted" }),
    pos(r.residual_likelihood, r.residual_impact, "Residual"), el("i", { class: "bi bi-arrow-right muted" }), pos(r.target_likelihood, r.target_impact, "Target")),
  r.above_target ? wsNote("Residual risk is above the target: the treatment plan needs to go further.") : null));
  pane.append(wsCard("Assessment history", dataTable(r.assessments, [
    { key: "at", label: "When", render: (a) => fmtDate(a.at) }, { key: "by", label: "By" },
    { key: "inherent_score", label: "Inherent", num: true }, { key: "residual_score", label: "Residual", num: true },
    { key: "origin", label: "Source", render: (a) => ASSESS_ORIGIN[a.origin] || a.origin },
    { key: "control_effectiveness", label: "Controls" }, { key: "comment", label: "Comment" },
  ], { pageSize: 10 })));
  const kriBox = wsCard("Indicator-driven assessment", loadingState());
  pane.append(kriBox);
  kriDrivenCard(kriBox, r, () => reload("assessment"));
}

async function kriDrivenCard(card, r, reload) {
  let p;
  try { p = await API.get(`/api/grc/risks/${r.id}/kri-assessment`); } catch (err) { card.replaceChildren(errorState(err)); return; }
  const score = (x) => `${x.residual_likelihood} × ${x.residual_impact} = ${x.residual_score}`;
  card.replaceChildren(el("b", { class: "ws-card-t" }, "Indicator-driven assessment"));
  if (!p.drivers.length) { card.append(el("span", { class: "ws-caption" }, "No indicator drives this risk (Metrics › Automate…).")); return; }
  card.append(el("table", { class: "ws-table" },
    el("thead", null, el("tr", null, ...["Indicator", "Drives", "Status", "Step"].map((h) => el("th", { scope: "col" }, h)))),
    el("tbody", null, ...p.drivers.map((d) => el("tr", null, el("td", null, d.name), el("td", null, d.drives),
      el("td", null, wsTag(d.rag, d.rag === "Red" ? "bad" : d.rag === "Amber" ? "warn" : d.rag === "Green" ? "ok" : "")),
      el("td", { class: "num" }, d.step ? `+${d.step}` : "-"))))));
  card.append(wsFieldRows([
    { label: `Residual (${p.base.from})`, control: el("span", null, score(p.base)) },
    { label: "Indicator-driven residual", control: el("span", null, score(p.proposed), " ", levelChip(p.proposed.residual_level, p.proposed.residual_score)) },
  ]), wsToolbar(p.auto ? wsTag("Applied automatically on each reading") : null,
    p.can_apply && p.changes ? wsAction("Apply indicator scores", async () => {
      try { await API.post(`/api/grc/risks/${r.id}/kri-assessment`); toast("Risk reassessed from its indicators"); reload(); } catch (err) { toast(err.message, "error"); }
    }, { primary: true }) : null));
}

function kriDriverForm(kris, after) {
  const pick = wsSelect(kris.map((k) => ({ value: k.id, label: k.name })), (kris.find((k) => k.drives) || kris[0]).id, { "aria-label": "Metric" });
  const drives = wsSelect([{ value: "", label: "Not a driver" }, { value: "likelihood", label: "Residual likelihood" }, { value: "impact", label: "Residual impact" }], "", { "aria-label": "Drives" });
  const steps = [0, 1, 2, 3, 4];
  const amber = wsSelect(steps, 1, { "aria-label": "Amber step" });
  const red = wsSelect(steps, 2, { "aria-label": "Red step" });
  const cond = el("span", { class: "ws-caption" });
  const load = () => {
    const k = kris.find((x) => String(x.id) === pick.value);
    drives.value = k.drives || ""; amber.value = String(k.amber_step ?? 1); red.value = String(k.red_step ?? 2);
    const op = k.higher_is_worse ? "≥" : "≤";
    cond.textContent = `Amber at ${op} ${k.amber_at} ${k.unit}, Red at ${op} ${k.red_at} ${k.unit}`;
  };
  pick.addEventListener("change", load);
  load();
  const dlg = modal({ title: "Automated assessment driver", width: 580,
    body: wsFieldRows([{ label: "Metric", control: pick, help: null }, { label: "Thresholds", control: cond }, { label: "Drives", control: drives },
      { label: "When Amber, raise by", control: amber }, { label: "When Red, raise by", control: red }]),
    footer: wsToolbar(wsAction("Cancel", () => dlg.close()), wsAction("Save", async () => {
      try { await API.put(`/api/grc/kris/${pick.value}/driver`, { drives: drives.value, amber_step: Number(amber.value), red_step: Number(red.value) }); toast("Driver saved"); dlg.close(); after(); }
      catch (err) { toast(err.message, "error"); }
    }, { primary: true })) });
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

function kriCondition(k) {
  if (!k.drives) return "Not automated";
  const op = k.higher_is_worse ? "≥" : "≤";
  return `Amber (${op} ${k.amber_at} ${k.unit}) → ${k.drives} +${k.amber_step}; Red (${op} ${k.red_at} ${k.unit}) → ${k.drives} +${k.red_step}`;
}

function riskMetricsPane(pane, r, reload) {
  pane.append(el("h3", { class: "ws-h" }, "Connect ongoing indicators (optional)"));
  pane.append(wsCard("Linked metrics", ...(r.kris.length ? r.kris.map((k) => wsRow(el("span", null, el("b", null, k.name),
    el("span", { class: "ws-caption" }, `Amber ${k.higher_is_worse ? "≥" : "≤"} ${k.amber_at} · Red ${k.higher_is_worse ? "≥" : "≤"} ${k.red_at} ${k.unit} · ${k.frequency}${k.owner ? ` · ${k.owner}` : ""}`)),
  el("span", { class: "ws-inline" }, wsTag(`KRI · ${k.readings.length ? `${k.readings[0].value} ${k.unit}` : "no reading"}`, k.rag === "Red" ? "bad" : k.rag === "Amber" ? "warn" : "ok"),
    (r.can_assess || k.owner_id === state.user.id) ? wsAction("Record reading", () => kriReadingForm(k, r.id, () => reload("metrics"))) : null,
    r.can_edit ? wsAction("Edit", () => kriForm(r.id, k)) : null))) : [el("p", { class: "muted" }, "No metrics linked yet.")]),
  r.can_edit ? wsToolbar(wsAction("Link Metrics", () => kriForm(r.id, null), { primary: true, focus: !r.kris.length })) : null));
  // Automated assessment driver: a metric's Amber or Red reading raises the residual likelihood or impact.
  const drivers = r.kris.filter((k) => k.drives);
  pane.append(wsCard("Automated assessment driver",
    ...(drivers.length ? drivers.map((k) => wsFieldRows([{ label: "Metric", control: el("span", null, k.name) }, { label: "Condition", control: el("span", null, kriCondition(k)) }]))
      : [wsFieldRows([{ label: "Metric", control: el("span", { class: "muted" }, r.kris.length ? "Choose a metric" : "Link a metric first") }, { label: "Condition", control: el("span", { class: "muted" }, "Not automated") }])]),
    r.can_edit && r.kris.length ? wsToolbar(wsAction("Automate…", () => kriDriverForm(r.kris, () => reload("metrics")))) : null));
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
    manualRiskCard()));
  body.append(el("p", { class: "ws-caption" }, "Review industry risks first; add only risks that apply to your organization. Imported risks start at a neutral 3 × 3 score until assessed."));
}

// Or create manually: risk name and description; the risk starts at a neutral 3 x 3 score until it is assessed.
function manualRiskCard() {
  const name = wsInput("", { name: "title", maxlength: "255", placeholder: "Failure of key third-party vendors" });
  const desc = wsText("", { name: "description", rows: "3", maxlength: "20000", placeholder: "Describe uncertainty and potential impact…" });
  const card = wsCard("Or create manually", wsFieldRows([{ label: "Risk name", control: name }, { label: "Description", control: desc }]),
    wsToolbar(wsAction("Save", async () => {
      try {
        const r = await API.post("/api/grc/risks", { title: name.value.trim(), description: desc.value, inherent_likelihood: 3, inherent_impact: 3,
          residual_likelihood: 3, residual_impact: 3, status: "Active" });
        toast(`${r.ref} added to the risk profile`); openRisk(r.id, "details");
      } catch (err) { wsShowErrors(card, err); }
    }, { primary: true })));
  return card;
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
