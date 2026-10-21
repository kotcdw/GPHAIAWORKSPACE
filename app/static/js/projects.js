// Projects (audits) - Project Execution walkthrough:
//   Fieldwork › objective list (Add Objective, Import Objective, My work status, Go To ▾), objective Overview with
//   Clone Objective, Import Objective, Project settings (workflow), Results (project results, fieldwork reports,
//   Reports app) and the Issues side panel (+ Add Issue) from the title bar.
// Loaded after fieldwork.js / planning.js / walk.js.

function goFieldwork(auditId, sub) {
  state.fwSub = state.fwSub || {};
  state.fwSub[auditId] = sub;
  openAudit(auditId, "fieldwork");
}

function objectiveImportButton(auditId) {
  return btn("Import Objective", () => goFieldwork(auditId, "objimport"), "secondary");
}

async function renderObjectiveList(body, ctx, fw) {
  const { audit, open, reload } = ctx;
  body.append(loadingState());
  let rows;
  try { rows = await API.get(`/api/audits/${audit.id}/objective-list`); } catch (err) { clear(body); body.append(errorState(err, reload)); return; }
  clear(body);
  const workplan = fw.workflow === "Workplan";
  body.append(wsToolbar(
    open ? wsAction("Add Objective", () => objectiveForm(audit.id, null, reload), { primary: !rows.length, focus: !rows.length }) : null,
    open ? wsAction("Import Objective", () => goFieldwork(audit.id, "objimport")) : null,
    wsAction("My work status", () => navigate("mywork"))));
  if (!rows.length) {
    body.append(emptyState({ icon: "bullseye", title: "No objectives yet", text: "Add an objective, or import objectives from another project or a framework." }));
    return;
  }
  const rounds = fw.round_labels || ["Testing"];
  const goto = (o) => wsMenu("Go To", [
    ["Overview", () => goFieldwork(audit.id, `objview:${o.id}`)],
    ...(workplan ? [["Work programme", () => goFieldwork(audit.id, "plan")], ["Execute procedures", () => goFieldwork(audit.id, "exec")]]
      : [["Narratives", () => goFieldwork(audit.id, "narr")], ["Risk & control matrix", () => goFieldwork(audit.id, "rcm")],
        ["Walkthroughs", () => goFieldwork(audit.id, "walk")], ["Test plan", () => goFieldwork(audit.id, "tplan")],
        ...rounds.map((label, i) => [rounds.length > 1 ? `${label} Testing` : "Testing", () => {
          state.fwRound = state.fwRound || {}; state.fwRound[audit.id] = i + 1; goFieldwork(audit.id, "test");
        }])]),
  ]);
  const tone = { "Not Started": "", "In Process": "warn", Completed: "ok" };
  body.append(el("div", { class: "table-wrap" }, el("table", { class: "ws-table obj-list" },
    el("thead", null, el("tr", null, ...["Objective", "Assigned user", "Progress", "Go To"].map((h) => el("th", { scope: "col" }, h)))),
    el("tbody", null, ...rows.map((o) => el("tr", null,
      el("td", null, el("span", { class: "ref" }, o.ref), ` ${o.title}`,
        el("div", { class: "ws-caption" }, workplan ? `${o.risks} risks · ${o.procedures} procedures` : `${o.risks} risks · ${o.controls} controls · ${o.narratives} narratives`)),
      el("td", null, o.assigned.length ? o.assigned.join(", ") : el("span", { class: "muted" }, "-")),
      el("td", null, wsTag(o.progress, tone[o.progress])),
      el("td", null, goto(o))))))));
}

async function renderObjectiveOverview(body, ctx, objectiveId) {
  const { audit, open, reload } = ctx;
  body.append(loadingState());
  let rcm; let list;
  try { [rcm, list] = await Promise.all([API.get(`/api/audits/${audit.id}/rcm`), API.get(`/api/audits/${audit.id}/objective-list`)]); }
  catch (err) { clear(body); body.append(errorState(err, reload)); return; }
  clear(body);
  const o = rcm.objectives.find((x) => x.id === objectiveId);
  const meta = list.find((x) => x.id === objectiveId);
  if (!o) { body.append(emptyState({ icon: "bullseye", title: "Objective not found" })); return; }
  body.append(wsToolbar(wsAction("Back to objective list", () => goFieldwork(audit.id, "objs")),
    open ? wsAction("Edit objective", () => objectiveForm(audit.id, o, reload)) : null));
  body.append(el("h3", { class: "ws-h" }, `${o.ref} · ${o.title}`));
  body.append(wsCard(null, wsFieldRows([
    { label: "Description", control: el("span", { class: "pre" }, o.description || "-") },
    { label: "Progress", control: el("span", null, meta ? meta.progress : "-") },
    { label: "Assigned users", control: el("span", null, meta && meta.assigned.length ? meta.assigned.join(", ") : "-") },
    { label: "Risks", control: el("span", null, o.risks.length ? o.risks.map((r) => `${r.ref} ${r.title}`).join("; ") : "None") },
    { label: "Controls", control: el("span", null, o.controls.length ? o.controls.map((c) => `${c.ref} ${c.title}`).join("; ") : "None") },
  ])));
  // Clone Objective: one objective at a time to one target project.
  const audits = (await safeGet("/api/audits", [])).filter((a) => a.id !== audit.id && a.status !== "Closed");
  const target = wsSelect([{ value: "", label: "- choose a project -" }, ...audits.map((a) => ({ value: a.id, label: `AUD-${String(a.id).padStart(4, "0")} ${a.title}` }))], "", { name: "target_audit_id" });
  const results = el("input", { type: "checkbox" });
  const card = wsCard("Clone Objective", el("p", { class: "ws-caption" }, "Copies this objective with its risks, controls, test plan, narratives and procedures into another project. Sign-offs and reviews are not copied."),
    wsFieldRows([{ label: "Target project", control: target }, { label: "Include results", control: el("label", null, results, " Tests and procedure results") }]),
    wsToolbar(wsAction("Clone", async () => {
      if (!target.value) { toast("Choose the target project", "error"); return; }
      try { const r = await API.post(`/api/objectives/${o.id}/clone`, { target_audit_id: Number(target.value), include_results: results.checked }); toast(`Cloned as ${r.ref}`); }
      catch (err) { toast(err.message, "error"); }
    }, { primary: true })));
  body.append(card);
}

async function renderObjectiveImport(body, ctx) {
  const { audit } = ctx;
  let src;
  try { src = await API.get(`/api/audits/${audit.id}/objective-sources`); } catch (err) { body.append(errorState(err)); return; }
  body.append(wsToolbar(wsAction("Back to objective list", () => goFieldwork(audit.id, "objs"))));
  body.append(el("h3", { class: "ws-h" }, "Import Objective"));
  const pick = el("select", { class: "ws-input", "aria-label": "Import from" }, el("option", { value: "" }, "- choose a source -"),
    src.audits.length ? el("optgroup", { label: "Projects" }, ...src.audits.map((a) => el("option", { value: `audit:${a.id}` }, `${a.ref} ${a.title} (${a.objectives})`))) : null,
    src.programmes.length ? el("optgroup", { label: "Frameworks (Project Library)" }, ...src.programmes.map((p) => el("option", { value: `programme:${p.id}` }, `${p.ref} ${p.name}`))) : null);
  const list = el("div", { class: "ws-list-pick" });
  const results = el("input", { type: "checkbox" });
  const resultsRow = el("label", { hidden: "1" }, results, " Include project results (tests, procedure results)");
  const go = wsAction("Import", null, { primary: true, disabled: true });
  const sync = () => { go.disabled = !list.querySelector("input:checked"); };
  pick.addEventListener("change", async () => {
    clear(list);
    const [kind, id] = pick.value.split(":");
    resultsRow.hidden = kind !== "audit";
    results.checked = false;
    if (!kind) { sync(); return; }
    let items;
    if (kind === "audit") {
      try { items = (await API.get(`/api/audits/${audit.id}/objective-sources/${id}`)).map((o) => ({ value: String(o.id), label: `${o.ref} ${o.title}`, note: `${o.risks} risks · ${o.controls} controls` })); }
      catch (err) { toast(err.message, "error"); return; }
    } else {
      items = src.programmes.find((p) => String(p.id) === id).objectives.map((t) => ({ value: t, label: t, note: "Framework objective" }));
    }
    list.replaceChildren(...items.map((o) => wsRow(el("label", null, el("input", { type: "checkbox", value: o.value, onchange: sync }), ` ${o.label}`), wsTag(o.note))));
    sync();
  });
  go.addEventListener("click", async () => {
    const [kind, id] = pick.value.split(":");
    const chosen = [...list.querySelectorAll("input:checked")].map((b) => b.value);
    const payload = kind === "audit"
      ? { source: "audit", source_id: Number(id), objective_ids: chosen.map(Number), include_results: results.checked }
      : { source: "programme", source_id: Number(id), objective_titles: chosen };
    go.disabled = true;
    try { const r = await API.post(`/api/audits/${audit.id}/objectives/import`, payload); toast(`${r.imported} objective${r.imported === 1 ? "" : "s"} imported from ${r.source}`); goFieldwork(audit.id, "objs"); }
    catch (err) { toast(err.message, "error"); sync(); }
  });
  body.append(wsCard(null, wsFieldRows([{ label: "Source project / framework", control: pick }]), list, resultsRow,
    wsToolbar(wsAction("Cancel", () => goFieldwork(audit.id, "objs")), go)));
  body.append(el("p", { class: "ws-caption" }, "Import copies several objectives at once; Clone (Go To › Overview) copies one objective to one project."));
}

// ------------------------------------------------------------------ Project settings and Results

async function renderProjectSettings(pane, audit, canWrite) {
  const reload = () => { clear(pane); renderProjectSettings(pane, audit, canWrite); };
  let fw;
  try { fw = await API.get(`/api/audits/${audit.id}/fieldwork`); } catch (err) { pane.append(errorState(err, reload)); return; }
  pane.append(el("h3", { class: "ws-h" }, "Confirm the project workflow"));
  const current = fw.workflow;
  const started = Object.values(fw.steps || {}).some((v) => Number(v) > 0);
  const card = (name, text, tag) => wsCard(name, el("p", null, text), wsRow(wsTag(tag), current === name ? wsTag("Current workflow", "ok")
    : canWrite && audit.status !== "Closed" ? wsAction(`Use ${name}`, async () => {
      try { await API.patch(`/api/audits/${audit.id}/fieldwork`, { workflow: name }); toast(`Workflow set to ${name}`); openAudit(audit.id, "settings"); }
      catch (err) { toast(err.message, "error"); }
    }, { disabled: started, title: started ? "Fieldwork has started; the workflow can no longer change" : null }) : null));
  pane.append(wsGrid(card("Workplan", "Document objectives and execute procedures.", "Execute procedures"),
    card("Internal Control", "Assess control design and operating effectiveness.", "Walkthroughs and tests")));
  pane.append(wsNote("The workflow determines which project components appear. Your organization may customize tab names and fields (Configuration › Audit types)."));
  pane.append(wsCard("Project details", wsFieldRows([
    { label: "Project name", control: el("span", null, audit.title) }, { label: "Audit type", control: el("span", null, audit.audit_type || "-") },
    { label: "Status", control: el("span", null, audit.status) }, { label: "Scope", control: el("span", { class: "pre" }, audit.scope || "-") }]),
  canWrite && audit.status !== "Closed" ? wsToolbar(wsAction("Edit project", () => editAuditModal(audit))) : null));
}

function resultsCards(audit, goTab) {
  return el("div", null, el("h3", { class: "ws-h" }, "Review results and prepare reporting"),
    wsGrid(wsCard("Project results", el("p", null, "Review findings, outcomes, and supporting documentation."), wsAction("Results", () => goTab("findings"), { focus: true })),
      wsCard("Fieldwork reports", el("p", null, "Open the project report, its approvals and the Word output."),
        wsAction("Fieldwork Reports", () => { const n = document.querySelector(".rec-pane .report-section, .rec-pane .card"); if (n) n.scrollIntoView({ behavior: "smooth" }); }))),
    wsCard("Need a reusable report or dashboard?", el("p", null, "Open the Reports app. Choose a template or create a report, select a data view, arrange fields, format it, and publish or save as a draft."),
      wsAction("Open Reports", () => navigate("reports"), { primary: true })));
}

// ------------------------------------------------------------------ Issues side panel (utility bar)

async function issuesSidePanel(audit, canWrite) {
  const body = el("div", null, loadingState());
  const reloadList = async () => {
    const rows = await safeGet(`/api/audits/${audit.id}/findings`, []);
    clear(body);
    body.append(wsCard("Issues", ...(rows.length ? rows.map((f) => wsRow(el("button", { class: "ws-crumb-link", type: "button", onclick: () => { p.close(); openIssue(f.id); } }, f.title),
      wsTag(f.status, f.status === "Closed" ? "ok" : ""))) : [el("p", { class: "muted small" }, "No issues yet.")]),
    canWrite && audit.status !== "Closed" ? wsAction("+ Add Issue", () => { p.close(); issueForm(null, audit.id, true, () => openAudit(audit.id, "findings")); }, { primary: true, focus: true }) : null));
  };
  const p = detailPanel({ title: "Issues", body, width: 460 });
  reloadList();
}
