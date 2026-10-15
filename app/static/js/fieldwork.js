// GPHA Audit Workspace - HighBond-style project workflows and results screens.
//
//   Fieldwork tab of an audit
//     Workplan:          Project plan (objectives > risks > procedures) | Execute procedures
//     Internal Control:  Risk control matrix | Walkthroughs | Test plan | one tab per testing round
//   Findings tab        the audit's issues with the Issue Tracker columns, publish and sign-offs
//   Issue Tracker page  every issue the user may read: List (donuts + register) and KPIs
//   Evidence requests   "Request evidence" from a procedure, test or issue; CC, reminders, "Linked to"
//   Assurance plan      Entities coverage grid, Risks
// Loaded after planning.js / roles.js (btn, heat, issueForm, testModal, evidenceDetail) and before app.js.

// ------------------------------------------------------------------ shared parts

// HighBond sign-off dots: one dot per sign-off, filled when done. Text is in the tooltip and for screen readers.
function signoffDots(list) {
  const items = list || [];
  const done = items.filter((d) => d.done).length;
  return el("span", { class: "signoffs", role: "img", "aria-label": `${done} of ${items.length} sign-offs`,
    title: items.map((d) => `${d.label}: ${d.done ? `${d.by || "signed"}${d.at ? ` · ${fmtDay(String(d.at).slice(0, 10))}` : ""}` : "pending"}`).join("\n") },
  ...items.map((d) => el("span", { class: `so-dot ${d.done ? "done" : ""}`, "aria-hidden": "true" })));
}

// Segmented sub-navigation inside a tab (keyboard: arrow keys move between options).
function subNav(items, active, onPick, label = "Views") {
  const nav = el("div", { class: "subnav", role: "tablist", "aria-label": label });
  items.forEach((it) => {
    nav.append(el("button", { type: "button", role: "tab", class: `subnav-item ${it.key === active ? "active" : ""}`,
      "aria-selected": it.key === active ? "true" : "false", tabindex: it.key === active ? "0" : "-1",
      onclick: () => onPick(it.key),
      onkeydown: (e) => {
        if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
        const all = [...nav.querySelectorAll("[role=tab]")]; const i = all.indexOf(e.currentTarget);
        const next = all[(i + (e.key === "ArrowRight" ? 1 : all.length - 1)) % all.length]; next.focus(); next.click();
      } }, it.label, it.count ? el("span", { class: "count-pill" }, String(it.count)) : null));
  });
  return nav;
}

// Donut chart with a legend; colours come from the theme tokens. items: [{label, count}]
const CHART_TONES = ["var(--accent)", "var(--danger)", "var(--warn)", "var(--ok)", "var(--purple)", "var(--muted)", "var(--bar-2)"];
const SEVERITY_TONES = { High: "var(--danger)", Medium: "var(--warn)", Low: "var(--ok)" };

function donutChart(title, items, tones = {}, unit = "issues") {
  const total = items.reduce((a, b) => a + b.count, 0);
  const r = 15.9155; // circumference 100
  let offset = 25;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 42 42"); svg.setAttribute("class", "donut"); svg.setAttribute("aria-hidden", "true");
  const ring = document.createElementNS(svg.namespaceURI, "circle");
  Object.entries({ cx: 21, cy: 21, r, fill: "none", "stroke-width": 6, class: "donut-ring" }).forEach(([k, v]) => ring.setAttribute(k, v));
  svg.append(ring);
  items.forEach((it, i) => {
    if (!it.count || !total) return;
    const pct = (100 * it.count) / total;
    const c = document.createElementNS(svg.namespaceURI, "circle");
    Object.entries({ cx: 21, cy: 21, r, fill: "none", "stroke-width": 6, "stroke-dasharray": `${pct} ${100 - pct}`, "stroke-dashoffset": offset })
      .forEach(([k, v]) => c.setAttribute(k, v));
    c.style.stroke = tones[it.label] || CHART_TONES[i % CHART_TONES.length];
    svg.append(c);
    offset -= pct;
  });
  const centre = el("div", { class: "donut-centre" }, el("div", { class: "n" }, String(total)), el("div", { class: "l" }, unit));
  return el("figure", { class: "chart-card", role: "group", "aria-label": `${title}: ${items.map((i) => `${i.label} ${i.count}`).join(", ")}` },
    el("figcaption", null, title),
    el("div", { class: "donut-wrap" }, el("div", { class: "donut-box" }, svg, centre),
      el("ul", { class: "legend" }, ...items.map((it, i) => el("li", null,
        el("span", { class: "sw", style: `background:${tones[it.label] || CHART_TONES[i % CHART_TONES.length]}` }),
        el("span", { class: "lg-l" }, it.label), el("span", { class: "lg-n" }, String(it.count)))))));
}

function progressBar(pct, tone = "") {
  const v = Math.max(0, Math.min(100, Math.round(pct || 0)));
  return el("span", { class: `pbar ${tone}`, role: "progressbar", "aria-valuenow": String(v), "aria-valuemin": "0", "aria-valuemax": "100", title: `${v}%` },
    el("span", { class: "pbar-fill", style: `width:${v}%` }), el("span", { class: "pbar-l" }, `${v}%`));
}

async function teamOptions(auditId) {
  const team = await safeGet(`/api/audits/${auditId}/assignees`, []);
  return team.map((m) => ({ value: m.id, label: `${m.name} (${m.team_role})` }));
}

function clip(text, n = 90) {
  const t = (text || "").trim();
  return t.length > n ? `${t.slice(0, n)}…` : t;
}

// ------------------------------------------------------------------ evidence requests from a record

// HighBond request form: Requester (you), Description, Owner, CC, Due date, notification (Send now + reminder).
async function requestEvidenceDialog(auditId, target, onDone) {
  const auditees = await safeGet(`/api/audits/${auditId}/auditees`, []);
  if (!auditees.length) { toast("Assign an auditee to this audit first (Engagement card on the Dashboard)", "error"); return; }
  const team = await safeGet(`/api/audits/${auditId}/assignees`, []);
  const ccOptions = [
    ...auditees.map((a) => ({ value: a.user_id, label: `${a.full_name || a.username} (auditee)` })),
    ...team.filter((m) => m.id !== state.user.id).map((m) => ({ value: m.id, label: `${m.name} (${m.team_role})` })),
  ];
  openForm({
    title: target ? `Request evidence for ${target.label}` : "Request evidence", draftable: false, width: 720,
    intro: target ? el("p", { class: "muted small" }, el("i", { class: "bi bi-link-45deg" }), ` Linked to ${target.label}. Accepted files can be filed as working papers on the same record.`) : null,
    fields: [
      { name: "title", label: "What is needed", required: true, minLength: 3, maxLength: 255, singleLine: true, full: true },
      { name: "description", label: "Description (period, format, sample)", type: "textarea", maxLength: 8000, full: true },
      { name: "assignee_id", label: "Owner (provides the evidence)", type: "select", required: true,
        options: auditees.map((a) => ({ value: a.user_id, label: a.full_name || a.username })) },
      { name: "due_date", label: "Due date", type: "date", notPast: true },
      { name: "cc_user_ids", label: "CC", type: "checklist", options: ccOptions, emptyLabel: "Nobody else to copy in.", full: true },
      { type: "heading", label: "Notification" },
      { name: "reminder", label: "Reminder", type: "select", emptyLabel: "Send now only",
        options: [{ value: "Daily", label: "Send now, then a daily reminder" }, { value: "Weekly", label: "Send now, then a weekly reminder" }],
        help: "Reminders stop when the evidence is submitted." },
      { name: "message", label: "Message", type: "textarea", maxLength: 4000, full: true, help: "Added to the notification the owner receives." },
    ],
    initial: { cc_user_ids: [] },
    submitLabel: "Send request",
    onSubmit: (v) => API.post(`/api/audits/${auditId}/evidence-requests`, {
      title: v.title, description: v.description || "", assignee_id: Number(v.assignee_id),
      due_date: v.due_date ? `${v.due_date}T23:59:00` : null, cc_user_ids: (v.cc_user_ids || []).map(Number),
      reminder: v.reminder || null, message: v.message || "",
      ...(target ? { target_type: target.type, target_id: target.id } : {}) }),
    onDone: () => { toast("Evidence requested - the owner has been notified"); if (onDone) onDone(); },
  });
}

async function linkedRequests(auditId, type, id, reload) {
  const box = el("div", { class: "linked" });
  const rows = await safeGet(`/api/audits/${auditId}/evidence-requests?target_type=${type}&target_id=${id}`, []);
  if (!rows.length) box.append(el("p", { class: "muted small" }, "No evidence requested for this item yet."));
  else box.append(el("ul", { class: "plain-list" }, ...rows.map((r) => el("li", null,
    el("a", { href: "#", onclick: (e) => { e.preventDefault(); evidenceDetail(r, reload); } }, el("span", { class: "ref" }, r.request_ref), ` ${r.title}`),
    " ", statusBadge(r.status), r.overdue ? el("span", { class: "text-danger small" }, " overdue") : null))));
  return box;
}

// ------------------------------------------------------------------ Fieldwork tab

async function renderFieldworkTab(pane, audit, canWrite) {
  const reload = () => { clear(pane); renderFieldworkTab(pane, audit, canWrite); };
  pane.append(loadingState());
  let fw;
  try { fw = await API.get(`/api/audits/${audit.id}/fieldwork`); } catch (err) { clear(pane); pane.append(errorState(err, reload)); return; }
  clear(pane);
  const open = canWrite && audit.status !== "Closed";
  const workplan = fw.workflow === "Workplan";
  const terms = await auditTerms(audit.id);
  state.fwSub = state.fwSub || {};
  const subs = workplan
    ? [{ key: "plan", label: "Project plan" }, { key: "exec", label: termOf(terms, "execute", "Execute procedures"), count: fw.procedures }]
    : [{ key: "narr", label: `${termOf(terms, "narrative", "Narrative")}s` }, { key: "rcm", label: termOf(terms, "rcm", "Risk control matrix") },
      { key: "walk", label: `${termOf(terms, "walkthrough", "Walkthrough")}s` }, { key: "tplan", label: termOf(terms, "test_plan", "Test plan") },
      ...fw.round_labels.map((l, i) => ({ key: `r${i + 1}`, label: fw.round_labels.length === 1 ? termOf(terms, "testing", l) : l }))];
  let sub = state.fwSub[audit.id];
  if (!subs.some((s) => s.key === sub)) sub = workplan ? subs[0].key : "rcm";

  // Workflow strip: which HighBond workflow this project uses, and its settings.
  const wfSelect = open && !fw.workflow_locked ? el("select", { class: "compact", "aria-label": "Workflow" },
    ...fw.workflows.map((w) => el("option", { value: w, selected: w === fw.workflow ? "1" : null }, w))) : null;
  if (wfSelect) wfSelect.addEventListener("change", async () => {
    try { await API.patch(`/api/audits/${audit.id}/fieldwork`, { workflow: wfSelect.value }); toast(`Workflow: ${wfSelect.value}`); reload(); }
    catch (err) { toast(err.message, "error"); wfSelect.value = fw.workflow; }
  });
  const rSelect = !workplan && open && !fw.rounds_locked ? el("select", { class: "compact", "aria-label": "Testing rounds" },
    ...fw.round_options.map((n) => el("option", { value: n, selected: n === fw.testing_rounds ? "1" : null }, `${n} round${n > 1 ? "s" : ""}`))) : null;
  if (rSelect) rSelect.addEventListener("change", async () => {
    try { await API.patch(`/api/audits/${audit.id}/fieldwork`, { testing_rounds: Number(rSelect.value) }); toast("Testing rounds updated"); reload(); }
    catch (err) { toast(err.message, "error"); }
  });
  pane.append(el("div", { class: "fw-strip" },
    el("span", { class: "fw-k" }, "Workflow"), wfSelect || el("strong", null, fw.workflow),
    fw.workflow_locked ? el("span", { class: "muted small", title: fw.workflow_locked }, el("i", { class: "bi bi-lock" }), " fixed") : null,
    workplan ? null : el("span", { class: "fw-sep" }),
    workplan ? null : el("span", { class: "fw-k" }, "Testing rounds"),
    workplan ? null : (rSelect || el("strong", null, `${fw.testing_rounds} (${fw.round_labels.join(", ")})`)),
    !workplan && fw.rounds_locked ? el("span", { class: "muted small", title: fw.rounds_locked }, el("i", { class: "bi bi-lock" }), " fixed") : null,
    el("span", { class: "grow" }),
    open && hasPerm("audit.plan", "audit.fieldwork") ? el("button", { class: "btn small secondary", type: "button",
      onclick: () => applyProgramDialog(audit, reload) }, el("i", { class: "bi bi-list-check" }), " Apply audit programme") : null));

  const body = el("div", { class: "fw-body" });
  const entBar = el("div");
  pane.append(entBar);
  auditEntitiesBar(entBar, audit, open, reload);
  pane.append(subNav(subs, sub, (k) => { state.fwSub[audit.id] = k; reload(); }, "Fieldwork views"), body);
  const ctx = { audit, open, reload };
  if (sub === "plan") renderProjectPlan(body, ctx);
  if (sub === "exec") renderExecuteProcedures(body, ctx);
  if (sub === "rcm") renderRcm(body, audit.id);
  if (sub === "narr") renderNarratives(body, ctx);
  if (sub === "walk") renderWalkthroughs(body, ctx);
  if (sub === "tplan") renderTestPlan(body, ctx);
  if (sub.startsWith("r") && sub !== "rcm") renderTestingRound(body, ctx, Number(sub.slice(1)));
}

// ---- Workplan: Project plan (objectives > risks > procedures)

async function renderProjectPlan(body, { audit, open, reload }) {
  body.append(loadingState());
  let wp;
  try { wp = await API.get(`/api/audits/${audit.id}/procedures`); } catch (err) { clear(body); body.append(errorState(err, reload)); return; }
  clear(body);
  const s = wp.summary;
  body.append(el("div", { class: "stats" },
    stat(wp.objectives.length, "Objectives"),
    stat(wp.objectives.reduce((a, o) => a + o.risks.length, 0), "Risks"),
    stat(s.procedures, "Procedures", `${s.by_status.Reviewed} reviewed · ${s.by_status.Prepared} prepared`),
    stat(s.issues_noted, "Issues noted", null, s.issues_noted ? "warn" : "")));
  if (s.risks_without_procedures.length) {
    body.append(el("div", { class: "callout warn" }, el("i", { class: "bi bi-exclamation-triangle" }),
      el("div", null, el("strong", null, "Risks not yet addressed by a procedure: "), s.risks_without_procedures.join("; "))));
  }
  const byRisk = {};
  wp.items.forEach((p) => p.risk_ids.forEach((rid) => { (byRisk[rid] = byRisk[rid] || []).push(p); }));
  if (!wp.objectives.length) {
    body.append(emptyState({ icon: "bullseye", title: "No objectives yet", text: "Start the Workplan with the audit objectives, then the risks and the procedures that address them.",
      action: open ? btn("Add objective", () => objectiveForm(audit.id, null, reload)) : null }));
    return;
  }
  wp.objectives.forEach((o) => {
    const obj = { ...o, audit_id: audit.id };
    const unlinked = wp.items.filter((p) => p.objective_id === o.id && !p.risk_ids.length);
    const procChip = (p) => el("button", { class: "proc-chip", type: "button", title: `${p.title} · ${p.status}`, onclick: () => procedurePanel(p, { audit, open, reload }) },
      el("span", { class: "ref" }, p.ref), ` ${clip(p.title, 48)} `, statusBadge(p.status));
    body.append(el("div", { class: "card" },
      el("div", { class: "card-head" }, el("h3", null, el("span", { class: "ref" }, o.ref), ` ${o.title}`),
        open ? el("div", { class: "actions" },
          btn("+ Risk", () => riskModal(obj, null, reload), "secondary"),
          btn("+ Procedure", () => procedureForm(audit.id, wp, o, null, reload), "secondary"),
          btn("Edit", () => objectiveForm(audit.id, obj, reload), "secondary")) : null),
      o.description ? el("p", { class: "muted small" }, o.description) : null,
      o.risks.length || unlinked.length ? el("div", { class: "table-wrap" }, el("table", { class: "dense plan-matrix" },
        el("thead", null, el("tr", null, el("th", { scope: "col" }, "Risk"), el("th", { scope: "col" }, "Rating"), el("th", { scope: "col" }, "Procedures"))),
        el("tbody", null,
          ...o.risks.map((r) => el("tr", { class: "no-click" },
            el("td", null, el("span", { class: "ref" }, r.ref), ` ${r.title}`),
            el("td", null, heat(r.likelihood * r.impact)),
            el("td", null, (byRisk[r.id] || []).length ? el("div", { class: "proc-chips" }, ...byRisk[r.id].map(procChip))
              : el("span", { class: "muted small" }, "No procedure yet")))),
          unlinked.length ? el("tr", { class: "no-click" }, el("td", { class: "muted" }, "Not linked to a risk"), el("td", null, "-"),
            el("td", null, el("div", { class: "proc-chips" }, ...unlinked.map(procChip)))) : null)))
        : el("p", { class: "muted small" }, "No risks or procedures under this objective yet.")));
  });
  if (open) body.append(el("div", null, btn("Add objective", () => objectiveForm(audit.id, null, reload), "secondary")));
}

async function procedureForm(auditId, wp, objective, p, reload) {
  const team = await teamOptions(auditId);
  const objectives = wp.objectives;
  const obj = objective || objectives.find((o) => o.id === p.objective_id);
  openForm({
    title: p ? `Edit ${p.ref}` : `New procedure under ${obj.ref}`, draftable: false, width: 720,
    fields: [
      { name: "title", label: "Procedure", required: true, maxLength: 255, singleLine: true, full: true, placeholder: "e.g. Vouch toll receipts to bank deposits" },
      { name: "steps", label: "Steps", type: "textarea", maxLength: 20000, full: true, help: "What the auditor does, the sample and the evidence to keep." },
      { name: "risk_ids", label: "Risks addressed", type: "checklist", full: true, emptyLabel: "Add risks to this objective first.",
        options: obj.risks.map((r) => ({ value: r.id, label: `${r.ref} ${r.title}` })) },
      { name: "assigned_to", label: "Assigned to", type: "select", emptyLabel: "- not assigned -", options: team,
        help: team.length ? "Members of the engagement team" : "Add people to the engagement team first" },
      { name: "due_date", label: "Due date", type: "date" },
    ],
    initial: p ? { ...p, risk_ids: p.risk_ids } : { risk_ids: [] },
    submitLabel: p ? "Save" : "Add procedure",
    onSubmit: (v) => {
      const bodyIn = { title: v.title, steps: v.steps || "", risk_ids: (v.risk_ids || []).map(Number),
        assigned_to: v.assigned_to ? Number(v.assigned_to) : (p ? 0 : null), due_date: v.due_date || null };
      return p ? API.patch(`/api/procedures/${p.id}`, bodyIn) : API.post(`/api/objectives/${obj.id}/procedures`, bodyIn);
    },
    onDone: () => { toast("Procedure saved"); reload(); },
  });
}

// ---- Workplan: Execute procedures

async function renderExecuteProcedures(body, ctx) {
  const { audit, open, reload } = ctx;
  body.append(loadingState());
  let wp;
  try { wp = await API.get(`/api/audits/${audit.id}/procedures`); } catch (err) { clear(body); body.append(errorState(err, reload)); return; }
  clear(body);
  const people = [...new Map(wp.items.filter((p) => p.assigned_to).map((p) => [p.assigned_to, p.assigned_name])).entries()];
  const tableBox = el("div");
  const fb = filterBar({ placeholder: "Search procedures…",
    filters: [
      { key: "status", label: "Status", options: ["Not Started", "In Progress", "Prepared", "Reviewed"] },
      { key: "outcome", label: "Issues", options: ["No Issues", "Issue(s) noted", { value: "none", label: "Not answered" }] },
      { key: "assigned", label: "Assigned", options: [{ value: String(state.user.id), label: "Me" }, ...people.filter(([id]) => id !== state.user.id).map(([id, n]) => ({ value: String(id), label: n }))] },
    ],
    onChange: () => paint() });
  body.append(el("div", { class: "card" }, fb.root, tableBox));
  function paint() {
    const v = fb.values();
    const rows = wp.items.filter((p) => (!v.status || p.status === v.status)
      && (!v.outcome || (v.outcome === "none" ? !p.outcome : p.outcome === v.outcome))
      && (!v.assigned || String(p.assigned_to) === v.assigned)
      && (!v.q || [p.ref, p.title, p.objective, p.assigned_name, ...p.risks.map((r) => r.ref)].join(" ").toLowerCase().includes(v.q.toLowerCase())));
    fb.setCount(`${rows.length} of ${wp.items.length}`);
    clear(tableBox);
    if (!wp.items.length) {
      tableBox.append(emptyState({ icon: "list-task", title: "No procedures yet", text: "Add procedures from the Project plan, or apply an audit programme." }));
      return;
    }
    if (!rows.length) { tableBox.append(emptyState({ icon: "funnel", title: "No procedures match", text: "Change or clear the filters." })); return; }
    tableBox.append(el("div", { class: "table-wrap" }, el("table", { class: "dense" },
      el("thead", null, el("tr", null, ...["Ref", "Procedure", "Risks", "Assigned", "Due", "Status", "Issues identified", "Sign-offs", "Evidence"].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...rows.map((p) => el("tr", { tabindex: "0", onclick: () => procedurePanel(p, ctx), onkeydown: (e) => { if (e.key === "Enter") procedurePanel(p, ctx); } },
        el("td", { class: "ref", "data-label": "Ref" }, p.ref),
        el("td", { class: "col-wide", "data-label": "Procedure" }, el("div", { class: "cell-title" }, p.title), el("div", { class: "muted small" }, `${p.objective_ref} ${clip(p.objective, 40)}`)),
        el("td", { "data-label": "Risks" }, p.risks.length ? p.risks.map((r) => r.ref).join(", ") : el("span", { class: "muted" }, "-")),
        el("td", { "data-label": "Assigned" }, p.assigned_name || el("span", { class: "muted" }, "-")),
        el("td", { "data-label": "Due" }, p.due_date ? el("span", { class: p.overdue ? "text-danger" : null }, fmtDay(p.due_date), p.overdue ? " · overdue" : "") : "-"),
        el("td", { "data-label": "Status" }, statusBadge(p.status)),
        el("td", { "data-label": "Issues identified" }, p.outcome ? el("span", { class: `outcome ${p.outcome === "No Issues" ? "ok" : "bad"}` },
          el("i", { class: `bi ${p.outcome === "No Issues" ? "bi-check-circle" : "bi-exclamation-circle"}`, "aria-hidden": "true" }), ` ${p.outcome}`) : el("span", { class: "muted" }, "-"),
          p.issue_ids.length ? el("div", { class: "muted small" }, p.issue_ids.map((i) => `Issue #${i}`).join(", ")) : null),
        el("td", { "data-label": "Sign-offs" }, signoffCell("procedure", p.id, p.signoffs, audit.id, `${p.ref} ${p.title}`, reload)),
        el("td", { class: "num", "data-label": "Evidence" }, p.evidence_requests ? String(p.evidence_requests) : "-")))))));
  }
  paint();
}

// Execute a procedure in the side panel: results, "Were issues identified?", sign-offs, issue, evidence.
async function procedurePanel(p, { audit, open, reload }) {
  const signed = (p.signoffs || []).some((d) => d.done);
  const editable = open && !signed && !["Prepared", "Reviewed"].includes(p.status);
  const soBox = el("div");
  signoffSection("procedure", p.id, audit.id, () => { panel.close(); reload(); }).then((n) => soBox.append(n));
  const results = el("textarea", { rows: "7", maxlength: "50000", "aria-label": "Procedure results", disabled: editable ? null : "1" }, p.results || "");
  const radios = ["No Issues", "Issue(s) noted"].map((o) => {
    const id = `out-${p.id}-${o.replace(/\W/g, "")}`;
    const r = el("input", { type: "radio", name: `out-${p.id}`, id, value: o, checked: p.outcome === o ? "1" : null, disabled: editable ? null : "1" });
    return { r, node: el("label", { class: "check", for: id }, r, ` ${o}`) };
  });
  const outcome = () => (radios.find((x) => x.r.checked) || {}).r?.value || null;
  const evBox = el("div");
  linkedRequests(audit.id, "procedure", p.id, reload).then((n) => evBox.append(n));
  const bodyNode = el("div", { class: "panel-sections" },
    el("dl", { class: "kv" },
      el("dt", null, "Objective"), el("dd", null, `${p.objective_ref} ${p.objective}`),
      el("dt", null, "Risks"), el("dd", null, p.risks.length ? p.risks.map((r) => `${r.ref} ${r.title} (${r.rating})`).join("; ") : "-"),
      el("dt", null, "Assigned"), el("dd", null, p.assigned_name || "-"),
      el("dt", null, "Due"), el("dd", null, p.due_date ? fmtDay(p.due_date) : "-"),
      el("dt", null, "Status"), el("dd", null, statusBadge(p.status))),
    p.steps ? formSection("Steps", el("div", { class: "lf-value pre" }, p.steps)) : null,
    formSection("Procedure results", results),
    formSection("Were issues identified?", el("div", { class: "radio-row" }, ...radios.map((x) => x.node))),
    p.review_comment ? el("div", { class: "callout warn" }, el("i", { class: "bi bi-chat-left-text" }), el("div", null, el("strong", null, "Reviewer: "), p.review_comment)) : null,
    formSection("Sign-offs", el("div", null, editable ? el("p", { class: "muted small" }, "Save the results and answer 'Were issues identified?' before the preparer signs off.") : null, soBox)),
    formSection("Issues", p.issue_ids.length ? el("ul", { class: "plain-list" }, ...p.issue_ids.map((i) => el("li", null,
      el("a", { href: "#", onclick: async (e) => { e.preventDefault(); panel.close(); const f = await API.get(`/api/findings/${i}`); issueForm(f, audit.id, open, reload); } }, `Issue #${i}`))))
      : el("p", { class: "muted small" }, "No issue raised from this procedure.")),
    formSection("Evidence requests", evBox));
  const save = async (extra = {}) => API.patch(`/api/procedures/${p.id}`, { results: results.value, outcome: outcome(), ...extra });
  const act = (label, fn, kind = "") => el("button", { class: `btn ${kind}`, type: "button", onclick: async () => {
    try { await fn(); } catch (err) { toast(err.message, "error"); }
  } }, label);
  const footer = el("div", { class: "actions" },
    editable ? act("Save", async () => { await save(); toast("Saved"); panel.close(); reload(); }, "secondary") : null,
    editable ? act("Save and sign-off", async () => { await save(); await API.post(`/api/signoffs/procedure/${p.id}`, {}); toast("Signed off as Preparer"); panel.close(); reload(); }) : null,
    act("Attributes", async () => editAttributes("procedures", p.id, p.ref, reload, !editable), "secondary"),
    open && p.outcome === "Issue(s) noted" && !p.issue_ids.length ? act("Raise issue", async () => {
      const f = await API.post(`/api/procedures/${p.id}/raise-issue`); toast(`Issue #${f.id} raised - complete it under Findings`); panel.close(); reload();
    }) : null,
    open && hasPerm("audit.evidence") ? act("Request evidence", async () => {
      requestEvidenceDialog(audit.id, { type: "procedure", id: p.id, label: `${p.ref} ${p.title}` }, reload);
    }, "secondary") : null,
    open && p.status === "Not Started" ? act("Edit plan", async () => {
      panel.close(); procedureForm(audit.id, await API.get(`/api/audits/${audit.id}/procedures`), null, p, reload);
    }, "secondary") : null);
  const panel = detailPanel({ title: `${p.ref} ${p.title}`, body: bodyNode, footer, width: 620 });
}

// ---- Internal Control: walkthroughs, test plan, testing rounds

async function openControlTest(auditId, controlRow, testId, open, reload) {
  try {
    const t = await API.get(`/api/control-tests/${testId}`);
    testModal({ id: controlRow.control_id, ref: controlRow.control_ref, audit_id: auditId }, t, open, reload);
  } catch (err) { toast(err.message, "error"); }
}

async function renderWalkthroughs(body, { audit, open, reload }) {
  body.append(loadingState());
  let w;
  try { w = await API.get(`/api/audits/${audit.id}/walkthroughs`); } catch (err) { clear(body); body.append(errorState(err, reload)); return; }
  clear(body);
  const s = w.summary;
  body.append(el("div", { class: "stats" },
    stat(s.controls, "Controls"), stat(s.designed_appropriately, "Designed appropriately", null, "ok"),
    stat(s.design_failure, "Design failure", null, s.design_failure ? "danger" : ""), stat(s.not_walked_through, "Not walked through", null, s.not_walked_through ? "warn" : "")));
  if (!w.rows.length) { body.append(emptyState({ icon: "diagram-3", title: "No controls yet", text: "Document the controls in the Risk control matrix first." })); return; }
  const designTone = { "Designed appropriately": "ok", "Design failure": "bad" };
  body.append(el("div", { class: "card" }, el("p", { class: "muted small" }, "Walk one transaction through each control and answer: is the control designed appropriately?"),
    el("div", { class: "table-wrap" }, el("table", { class: "dense" },
      el("thead", null, el("tr", null, ...["Control", "Key", "Owner", "Walkthrough", "Status", "Is the control designed appropriately?", "Sign-offs", ""].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...w.rows.map((r) => el("tr", { class: "no-click" },
        el("td", { class: "col-wide", "data-label": "Control" }, el("span", { class: "ref" }, r.control_ref), ` ${r.control}`, el("div", { class: "muted small" }, `${r.control_type} · ${r.nature} · ${r.frequency}`)),
        el("td", { "data-label": "Key" }, r.is_key ? statusBadge("Key") : "-"),
        el("td", { class: "muted small", "data-label": "Owner" }, r.owner_email || "-"),
        el("td", { class: "ref", "data-label": "Walkthrough" }, r.test ? r.test.ref : "-"),
        el("td", { "data-label": "Status" }, r.test ? statusBadge(r.test.status) : el("span", { class: "muted" }, "-")),
        el("td", { "data-label": "Designed appropriately?" }, el("span", { class: `outcome ${designTone[r.design] || ""}` }, r.design)),
        el("td", { "data-label": "Sign-offs" }, r.test ? signoffCell("test", r.test.id, r.test.signoffs, audit.id, `${r.test.ref} ${r.control}`, reload) : "-"),
        el("td", null, el("div", { class: "actions" },
          r.test ? btn("Open", () => openControlTest(audit.id, r, r.test.id, open, reload), "secondary") : null,
          !r.test && open ? btn("Start walkthrough", async () => {
            try { const t = await API.post(`/api/controls/${r.control_id}/tests`, { test_type: "Walkthrough", procedure: r.test_steps || "" }); openControlTest(audit.id, r, t.id, open, reload); }
            catch (err) { toast(err.message, "error"); }
          }) : null,
          r.test ? btn("Attributes", () => editAttributes("control_tests", r.test.id, r.test.ref, reload, !open), "secondary") : null)))))))));
}

async function renderTestPlan(body, { audit, open, reload }) {
  body.append(loadingState());
  let rcm;
  try { rcm = await API.get(`/api/audits/${audit.id}/rcm`); } catch (err) { clear(body); body.append(errorState(err, reload)); return; }
  clear(body);
  const controls = rcm.objectives.flatMap((o) => o.controls);
  if (!controls.length) { body.append(emptyState({ icon: "clipboard-check", title: "No controls yet", text: "The test plan lists each control from the Risk control matrix." })); return; }
  body.append(el("div", { class: "card" }, el("p", { class: "muted small" }, "How each control will be tested. The testing method, total sample size and test steps carry into every testing round."),
    el("div", { class: "table-wrap" }, el("table", { class: "dense" },
      el("thead", null, el("tr", null, ...["Control", "Key", "Frequency", "Nature", "Testing method", "Total sample size", "Test steps", "Sign-offs", ""].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...controls.map((c) => el("tr", { class: "no-click" },
        el("td", { class: "col-wide", "data-label": "Control" }, el("span", { class: "ref" }, c.ref), ` ${c.title}`),
        el("td", { "data-label": "Key" }, c.is_key ? statusBadge("Key") : "-"),
        el("td", { "data-label": "Frequency" }, c.frequency), el("td", { "data-label": "Nature" }, c.nature),
        el("td", { "data-label": "Testing method" }, c.test_method || el("span", { class: "muted" }, "Not set")),
        el("td", { class: "num", "data-label": "Total sample size" }, c.total_sample_size != null ? String(c.total_sample_size) : el("span", { class: "muted" }, "Default")),
        el("td", { class: "small", "data-label": "Test steps" }, c.test_steps ? clip(c.test_steps, 120) : el("span", { class: "muted" }, "-")),
        el("td", { "data-label": "Sign-offs" }, signoffCell("test_plan", c.id, c.plan_signoffs, audit.id, `Test plan ${c.ref}`, reload)),
        el("td", null, el("div", { class: "actions" }, open ? btn("Edit", () => testPlanForm(c, reload), "secondary") : null,
          btn("Attributes", () => editAttributes("controls", c.id, c.ref, reload, !open), "secondary"))))))))));
}

const TEST_METHODS = ["Inquiry", "Observation", "Inspection", "Re-performance", "Data analytics"];

function testPlanForm(c, reload) {
  openForm({
    title: `Test plan: ${c.ref} ${c.title}`, draftable: false, width: 680,
    fields: [
      { name: "test_method", label: "Testing method", type: "select", emptyLabel: "- choose -", options: TEST_METHODS },
      { name: "total_sample_size", label: "Total sample size", type: "number", min: 0, max: 100000,
        help: "Leave empty to use the default for the control frequency (Configuration > Audit methodology)." },
      { name: "test_steps", label: "Test steps / attributes", type: "textarea", maxLength: 20000, full: true },
    ],
    initial: c,
    submitLabel: "Save",
    onSubmit: (v) => API.patch(`/api/controls/${c.id}`, { test_method: v.test_method || null, total_sample_size: v.total_sample_size ?? null, test_steps: v.test_steps || null }),
    onDone: () => { toast("Test plan saved"); reload(); },
  });
}

async function renderTestingRound(body, { audit, open, reload }, roundNo) {
  body.append(loadingState());
  let rd; let team;
  try { [rd, team] = await Promise.all([API.get(`/api/audits/${audit.id}/testing/${roundNo}`), teamOptions(audit.id)]); }
  catch (err) { clear(body); body.append(errorState(err, reload)); return; }
  clear(body);
  const s = rd.summary;
  body.append(el("div", { class: "stats" },
    stat(s.key_controls, "Key controls"), stat(s.in_scope, "Tested this round"),
    stat(`${s.by_status.Completed + s.by_status.Reviewed}/${s.in_scope}`, "Completed", `${s.by_status.Reviewed} reviewed`),
    stat(s.effective, "Effective", null, "ok"), stat(s.ineffective, "Ineffective", null, s.ineffective ? "danger" : "")));
  if (s.not_prepared && open) {
    body.append(el("div", { class: "callout" }, el("i", { class: "bi bi-info-circle" }),
      el("div", { style: "flex:1" }, `${s.not_prepared} key control(s) have no test in the ${rd.round_label} round yet.`),
      btn(`Prepare ${rd.round_label} round`, async () => {
        try { const r = await API.post(`/api/audits/${audit.id}/testing/${roundNo}/prepare`); toast(`${r.created} test(s) prepared`); reload(); }
        catch (err) { toast(err.message, "error"); }
      })));
  }
  if (!rd.rows.length) { body.append(emptyState({ icon: "clipboard-data", title: "No controls yet", text: "Document the controls in the Risk control matrix first." })); return; }
  const assignSel = (t) => {
    const sel = el("select", { class: "compact", "aria-label": "Assigned to", disabled: open && t.status !== "Reviewed" ? null : "1" },
      el("option", { value: "" }, "- not assigned -"), ...team.map((o) => el("option", { value: o.value, selected: o.value === t.assigned_to ? "1" : null }, o.label)));
    sel.addEventListener("change", async () => {
      try { await API.patch(`/api/control-tests/${t.id}`, { assigned_to: sel.value ? Number(sel.value) : 0 }); toast("Assigned"); }
      catch (err) { toast(err.message, "error"); reload(); }
    });
    return sel;
  };
  const scopeBox = (t) => {
    const cb = el("input", { type: "checkbox", checked: t.in_scope ? "1" : null, "aria-label": "Testing this key control this round?",
      disabled: open && t.status === "Not Started" ? null : "1" });
    cb.addEventListener("change", async () => {
      try { await API.patch(`/api/control-tests/${t.id}`, { in_scope: cb.checked }); toast(cb.checked ? "In scope this round" : "Not tested this round"); reload(); }
      catch (err) { toast(err.message, "error"); cb.checked = !cb.checked; }
    });
    return el("label", { class: "check" }, cb, cb.checked ? " Yes" : " No");
  };
  body.append(el("div", { class: "card" },
    el("div", { class: "table-wrap" }, el("table", { class: "dense" },
      el("thead", null, el("tr", null, ...["Control", "Tested this round?", "Assigned", "Sample", "Exceptions", "Status", "Conclusion", "Sign-offs", "Evidence", ""].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...rd.rows.map((r) => {
        const t = r.test;
        return el("tr", { class: `no-click ${t && !t.in_scope ? "row-muted" : ""}` },
          el("td", { class: "col-wide", "data-label": "Control" }, el("span", { class: "ref" }, r.control_ref), ` ${r.control} `, r.is_key ? statusBadge("Key") : null,
            el("div", { class: "muted small" }, `${r.frequency} · ${r.test_method || "method not set"}`)),
          el("td", { "data-label": "Testing this round?" }, t ? scopeBox(t) : el("span", { class: "muted small" }, r.is_key ? "Not prepared" : "Not a key control")),
          el("td", { "data-label": "Assigned" }, t ? assignSel(t) : "-"),
          el("td", { class: "num", "data-label": "Sample" }, t ? (t.population_size ? `${t.sample_size ?? "-"} of ${t.population_size}` : String(t.sample_size ?? r.suggested_sample)) : String(r.suggested_sample)),
          el("td", { class: "num", "data-label": "Exceptions" }, t ? String(t.exceptions_found) : "-"),
          el("td", { "data-label": "Status" }, t ? statusBadge(t.status) : "-"),
          el("td", { "data-label": "Conclusion" }, t ? statusBadge(t.conclusion) : "-"),
          el("td", { "data-label": "Sign-offs" }, t ? signoffCell("test", t.id, t.signoffs, audit.id, `${t.ref} ${r.control}`, reload) : "-"),
          el("td", { class: "num", "data-label": "Evidence" }, t && t.evidence_requests ? String(t.evidence_requests) : "-"),
          el("td", null, t ? el("div", { class: "actions" },
            btn("Open", () => openControlTest(audit.id, r, t.id, open, reload), "secondary"),
            open && t.conclusion === "Ineffective" && ["Completed", "Reviewed"].includes(t.status) && !t.issue_id ? btn("Raise issue", async () => {
              try { await API.post(`/api/control-tests/${t.id}/raise-issue`); toast("Issue raised - see Findings"); reload(); } catch (err) { toast(err.message, "error"); }
            }) : null,
            open && hasPerm("audit.evidence") ? iconBtn("paperclip", "Request evidence", () => requestEvidenceDialog(audit.id, { type: "control_test", id: t.id, label: `${t.ref} (${r.control_ref})` }, reload)) : null) : null));
      }))))));
}

// ------------------------------------------------------------------ Findings tab (the audit's issues)

async function renderAuditIssues(panel, audit, canWrite) {
  const id = audit.id;
  const reload = () => openAudit(id, "findings");
  panel.append(loadingState());
  let findings;
  try { findings = await API.get(`/api/audits/${id}/findings`); } catch (err) { clear(panel); panel.append(errorState(err)); return; }
  clear(panel);
  const open = canWrite && audit.status !== "Closed";
  const unpublished = findings.filter((f) => !f.published);
  const head = el("div", { class: "card-head" }, el("h3", null, "Issues"),
    el("div", { class: "actions" },
      open && unpublished.length ? btn(`Publish ${unpublished.length} to the auditee`, async () => {
        const ok = await confirmDialog({ title: "Publish issues", text: `${unpublished.length} unpublished issue(s) become visible to the auditee and each owner is notified to respond.`, confirmLabel: "Publish" });
        if (!ok.ok) return;
        let n = 0;
        for (const f of unpublished) { try { await API.post(`/api/findings/${f.id}/publish`); n += 1; } catch (err) { toast(`#${f.id}: ${err.message}`, "error"); } }
        toast(`${n} issue(s) published`); reload();
      }, "secondary") : null,
      canWrite ? btn("Import from Excel", () => importDialog({
        title: "Import findings from Excel", templateKind: "findings", path: `/api/audits/${id}/import/findings`,
        intro: "Add many findings at once. Required columns: Title and Risk rating (High, Medium or Low). The file is checked first; nothing is added if any row has a problem.",
        onDone: reload }), "secondary") : null,
      open ? btn("Add issue", () => issueForm(null, id, true, reload)) : null));
  const card = el("div", { class: "card" }, head);
  panel.append(card);
  if (!findings.length) { card.append(emptyState({ icon: "flag", title: "No issues recorded", text: "Issues are raised from procedures and control tests, or added here." })); return; }
  card.append(el("div", { class: "table-wrap" }, el("table", { class: "dense" },
    el("thead", null, el("tr", null, ...["Issue", "Status", "Severity", "Owner", "Remediation deadline", "Issue type", "Published", "Sign-offs", "Remediation", "Responses"].map((h) => el("th", { scope: "col" }, h)))),
    el("tbody", null, ...findings.map((f) => el("tr", { tabindex: "0", title: "Open issue", onclick: () => issueForm(f, id, canWrite, reload), onkeydown: (e) => { if (e.key === "Enter") issueForm(f, id, canWrite, reload); } },
      el("td", { class: "col-wide", "data-label": "Issue" }, el("span", { class: "ref" }, `#${f.id}`), " ", el("span", { class: "cell-title" }, f.title),
        el("div", { class: "muted small" }, f.procedure_id ? "From a procedure" : f.test_id ? "From a control test" : "")),
      el("td", { "data-label": "Status" }, statusBadge(f.status)),
      el("td", { "data-label": "Severity" }, statusBadge(f.risk_rating)),
      el("td", { class: "small", "data-label": "Owner" }, f.assigned_owner_email || el("span", { class: "muted" }, "-")),
      el("td", { "data-label": "Remediation deadline" }, f.target_date ? fmtDay(f.target_date.slice(0, 10)) : el("span", { class: "muted" }, "-")),
      el("td", { "data-label": "Issue type" }, f.issue_type || el("span", { class: "muted" }, "-")),
      el("td", { "data-label": "Published" }, f.published ? el("span", { class: "outcome ok" }, el("i", { class: "bi bi-eye" }), " Yes") : el("span", { class: "outcome" }, el("i", { class: "bi bi-eye-slash" }), " No")),
      el("td", { "data-label": "Sign-offs" }, signoffCell("finding", f.id, f.signoffs, id, `Issue #${f.id}`, reload)),
      el("td", { class: "small", "data-label": "Remediation" }, f.remediation ? f.remediation.state : "-"),
      el("td", { "data-label": "Responses" }, el("span", { class: "chips" },
        el("span", { class: `chip-mini ${f.client_response ? "ok" : ""}`, title: "Audit client response" }, el("i", { class: `bi ${f.client_response ? "bi-check2" : "bi-hourglass"}` }), " Client"),
        el("span", { class: `chip-mini ${f.management_response ? "ok" : ""}`, title: "Management response" }, el("i", { class: `bi ${f.management_response ? "bi-check2" : "bi-hourglass"}` }), " Management")))))))));
}

// Extra actions on the issue form: publish, review sign-off, request evidence.
function issueExtraActions(f, auditId, canWrite, onSaved) {
  if (!f || !canWrite) return [];
  const closeForm = () => document.querySelector(".modal-backdrop")?.remove();
  return [
    !f.published ? el("button", { class: "btn secondary", type: "button", title: "Make the issue visible to the auditee and notify its owner", onclick: async () => {
      try { await API.post(`/api/findings/${f.id}/publish`); toast("Published - the owner has been notified"); closeForm(); onSaved(); } catch (err) { toast(err.message, "error"); }
    } }, el("i", { class: "bi bi-send" }), " Publish") : null,
    el("button", { class: "btn secondary", type: "button", onclick: () => { closeForm(); openSignoffs("finding", f.id, auditId, `Issue #${f.id}`, onSaved); } },
      el("i", { class: "bi bi-pen" }), " Sign-offs"),
    hasPerm("audit.evidence") ? el("button", { class: "btn secondary", type: "button", onclick: () => requestEvidenceDialog(auditId, { type: "finding", id: f.id, label: `Issue #${f.id}` }, onSaved) },
      el("i", { class: "bi bi-paperclip" }), " Request evidence") : null,
  ].filter(Boolean);
}

// ------------------------------------------------------------------ Issue Tracker page

async function renderIssueTracker(tab = state.issueTab || "list") {
  state.issueTab = tab;
  clear(viewRoot);
  viewRoot.append(viewHeader("Issue Tracker", null, { sub: "Every issue across the audits you can see - status, severity, owner, remediation deadline and sign-offs" }));
  viewRoot.append(tabBar([{ key: "list", label: "List" }, { key: "kpis", label: "KPIs" }], tab, (k) => renderIssueTracker(k)));
  const body = el("div");
  viewRoot.append(body);
  let types = [];
  let owners = [];
  let entities = [];
  try {
    const [s, u] = await Promise.all([API.get("/api/findings/register/summary"), safeGet("/api/audit-universe", { entities: [] })]);
    types = s.issue_types; owners = s.owners; entities = u.entities.filter((e) => e.status === "Active");
  }
  catch (err) { body.append(errorState(err, () => renderIssueTracker(tab))); return; }
  if (tab === "kpis") { renderIssueKpis(body); return; }

  const charts = el("div", { class: "chart-row" });
  body.append(charts);
  const paintCharts = async (values = {}) => {
    const sp = new URLSearchParams(Object.entries(values).filter(([, v]) => v !== "" && v != null));
    try {
      const s = await API.get(`/api/findings/register/summary?${sp.toString()}`);
      clear(charts);
      charts.append(donutChart("By Issue Type", s.by_issue_type.map((x) => ({ ...x, label: x.label === "(none)" ? "Not set" : x.label }))), donutChart("By Severity", s.by_severity, SEVERITY_TONES),
        el("div", { class: "chart-card kpi-mini" }, el("figcaption", null, "At a glance"),
          el("dl", { class: "kv compact" }, el("dt", null, "Open"), el("dd", null, String(s.open)), el("dt", null, "Overdue"), el("dd", { class: s.overdue ? "text-danger" : null }, String(s.overdue)),
            el("dt", null, "Unpublished"), el("dd", null, String(s.unpublished)))));
    } catch { /* charts are optional */ }
  };
  paintCharts();
  const table = serverTable({
    url: "/api/findings/register", storageKey: "issues", defaultSort: "-updated_at", exportName: "issue-tracker",
    onFilter: (v) => paintCharts(v),
    filters: [
      { key: "status", label: "Status", options: ["Open", "Remediating", "Closed"] },
      { key: "severity", label: "Severity", options: ["High", "Medium", "Low"] },
      { key: "owner", label: "Owner", options: owners.map((o) => ({ value: o.email, label: o.name })) },
      { key: "issue_type", label: "Issue type", options: [...types, { value: "(none)", label: "Not set" }] },
      { key: "published", label: "Published", options: [{ value: "true", label: "Yes" }, { value: "false", label: "No" }] },
      { key: "overdue", label: "Deadline", options: [{ value: "true", label: "Overdue" }] },
      ...(entities.length ? [{ key: "entity_id", label: "Entity", options: entities.map((e) => ({ value: e.id, label: e.name })) }] : []),
    ],
    columns: [
      { key: "title", label: "Issue", sort: true, render: (r) => el("span", null, el("span", { class: "ref" }, r.ref), " ", el("span", { class: "cell-title" }, r.title)), csv: (r) => `${r.ref} ${r.title}` },
      { key: "status", label: "Status", sort: true, render: (r) => statusBadge(r.status), csv: (r) => r.status },
      { key: "severity", label: "Severity", sort: true, render: (r) => statusBadge(r.severity), csv: (r) => r.severity },
      { key: "owner", label: "Owner", sort: true },
      { key: "remediation_deadline", label: "Remediation deadline", sort: true,
        render: (r) => (r.remediation_deadline ? el("span", { class: r.overdue ? "text-danger" : null }, fmtDay(r.remediation_deadline), r.overdue ? " · overdue" : "") : "-"),
        csv: (r) => r.remediation_deadline || "" },
      { key: "issue_type", label: "Issue type", sort: true },
      { key: "published", label: "Published", sort: true, render: (r) => (r.published ? "Yes" : "No") },
      { key: "signoffs", label: "Sign-offs", render: (r) => signoffDots(r.signoffs), csv: (r) => `${r.signoffs.filter((d) => d.done).length}/${r.signoffs.length}` },
      { key: "audit", label: "Project", sort: true },
      { key: "remediation", label: "Remediation", hidden: true },
      { key: "source", label: "Source", hidden: true },
    ],
    onRow: async (r) => {
      try { const f = await API.get(`/api/findings/${r.id}`); issueForm(f, r.audit_id, canWriteModule("audits"), () => table.reload()); }
      catch (err) { toast(err.message, "error"); }
    },
    emptyTitle: "No issues yet", emptyText: "Issues raised in audits appear here.",
  });
  body.append(el("div", { class: "card" }, table.root));
}

async function renderIssueKpis(body) {
  let s;
  try { s = await API.get("/api/findings/register/summary"); } catch (err) { body.append(errorState(err)); return; }
  const bars = (title, items) => {
    const max = Math.max(1, ...items.map((i) => i.count));
    return el("div", { class: "card" }, el("h3", null, title), items.length ? el("div", { class: "hbars" }, ...items.map((i) => el("div", { class: "hbar" },
      el("span", { class: "hbar-label" }, i.label), el("span", { class: "hbar-track" }, el("span", { class: "hbar-fill", style: `width:${Math.round((100 * i.count) / max)}%` })),
      el("span", { class: "hbar-val" }, String(i.count))))) : emptyState({ icon: "bar-chart", title: "No issues" }));
  };
  body.append(el("div", { class: "stats" }, stat(s.total, "Issues"), stat(s.open, "Open"), stat(s.overdue, "Overdue", null, s.overdue ? "danger" : ""),
    stat(s.unpublished, "Unpublished", null, s.unpublished ? "warn" : "")),
  el("div", { class: "two-cols" }, bars("Issue count by project", s.by_project), bars("Issue count by issue type", s.by_issue_type.map((x) => ({ ...x, label: x.label === "(none)" ? "Not set" : x.label })))),
  el("div", { class: "two-cols" }, bars("Issue count by severity", s.by_severity), bars("Issue count by status", s.by_status)));
}

// ------------------------------------------------------------------ Assurance plan: Entities coverage and Risks

async function renderPlanCoverage(pane, plan, mode = "entities") {
  const values = state.covFilter && state.covFilter.plan === plan.id ? state.covFilter : { plan: plan.id, category: "", not_covered: false };
  state.covFilter = values;
  const reload = () => { clear(pane); renderPlanCoverage(pane, plan, mode); };
  pane.append(loadingState());
  const sp = new URLSearchParams();
  if (values.category && mode === "entities") sp.set("category", values.category);
  if (values.not_covered && mode === "entities") sp.set("not_covered", "true");
  let cov;
  try { cov = await API.get(`/api/assurance-plans/${plan.id}/coverage?${sp.toString()}`); } catch (err) { clear(pane); pane.append(errorState(err, reload)); return; }
  clear(pane);
  if (mode === "risks") { renderPlanRisks(pane, cov); return; }
  const over = cov.hours.available && cov.hours.planned > cov.hours.available;
  const hoursPct = cov.hours.available ? Math.min(100, (100 * cov.hours.planned) / cov.hours.available) : 0;
  pane.append(el("div", { class: "cov-summary" },
    el("div", { class: "cov-box" }, el("div", { class: "l" }, "Overall progress"), progressBar(cov.overall_progress)),
    el("div", { class: "cov-box" }, el("div", { class: "l" }, "Hours planned / available"),
      el("span", { class: `pbar ${over ? "bad" : "ok"}`, title: `${cov.hours.planned}h of ${cov.hours.available || "-"}h` },
        el("span", { class: "pbar-fill", style: `width:${cov.hours.available ? hoursPct : 0}%` }),
        el("span", { class: "pbar-l" }, `${cov.hours.planned}h / ${cov.hours.available ? `${cov.hours.available}h` : "no budget"}${over ? ` (+${cov.hours.over}h)` : ""}`))),
    el("div", { class: "cov-box" }, el("div", { class: "l" }, "Actual hours charged"), el("strong", null, `${cov.hours.actual}h`))));

  const cat = el("select", { class: "fb-select", "aria-label": "Entity category" }, el("option", { value: "" }, "Entity category: All"),
    ...cov.categories.map((c) => el("option", { value: c.id, selected: String(c.id) === String(values.category) ? "1" : null }, `Entity category: ${c.name}`)));
  cat.addEventListener("change", () => { values.category = cat.value; reload(); });
  const nc = el("input", { type: "checkbox", id: "covNc", checked: values.not_covered ? "1" : null });
  nc.addEventListener("change", () => { values.not_covered = nc.checked; reload(); });
  pane.append(el("div", { class: "filter-bar" }, cat, el("label", { class: "check", for: "covNc" }, nc, ` Entities not covered (${cov.not_covered})`),
    cov.not_covered_high ? el("span", { class: "text-danger small" }, `${cov.not_covered_high} high-risk not covered`) : null,
    el("button", { class: "link-btn", type: "button", onclick: () => { values.category = ""; values.not_covered = false; reload(); } }, "Clear")));

  if (!cov.engagements.length && !cov.entities.length) { pane.append(emptyState({ icon: "grid-3x3", title: "Nothing to show", text: "Add entities to the Audit Universe and engagements to the plan." })); return; }
  const ents = cov.entities;
  pane.append(el("div", { class: "card" }, el("div", { class: "table-wrap cov-wrap" }, el("table", { class: "dense cov-grid" },
    el("thead", null, el("tr", null, el("th", { scope: "col", class: "sticky" }, "Project"), el("th", { scope: "col" }, "Status"), el("th", { scope: "col", class: "num" }, "Hours"),
      el("th", { scope: "col" }, "Progress"),
      ...ents.map((u) => el("th", { scope: "col", class: "ent", title: `${u.location} / ${u.name} · risk ${u.risk_score} (${u.risk})` },
        el("span", { class: "ent-l" }, u.name), el("span", { class: `ent-risk ${u.risk.toLowerCase()}` }, u.risk))))),
    el("tbody", null, ...cov.engagements.map((e) => el("tr", { class: `no-click ${e.cancelled ? "row-muted" : ""}` },
      el("td", { class: "sticky" }, e.audit_id ? el("a", { href: "#", onclick: (ev) => { ev.preventDefault(); openAudit(e.audit_id); } }, e.title) : e.title,
        el("div", { class: "muted small" }, [e.quarter, e.lead].filter(Boolean).join(" · "))),
      el("td", null, statusBadge(e.status)),
      el("td", { class: "num" }, `${e.hours}h`, e.actual_hours ? el("div", { class: "muted small" }, `${e.actual_hours}h charged`) : null),
      el("td", null, progressBar(e.progress)),
      ...ents.map((u) => el("td", { class: "ent-cell" }, e.entity_unit_id === u.id ? el("i", { class: "bi bi-check-lg cov-tick", "aria-label": "Covered", title: `${e.title} covers ${u.name}` }) : null)))),
      ents.length ? el("tr", { class: "no-click cov-foot" }, el("td", { class: "sticky muted small" }, "Coverage"), el("td"), el("td"), el("td"),
        ...ents.map((u) => el("td", { class: "ent-cell" }, u.covered ? el("span", { class: "outcome ok small" }, "Covered") : el("span", { class: "outcome bad small" }, "Not covered")))) : null)))));
}

function renderPlanRisks(pane, cov) {
  const ents = [...cov.entities].sort((a, b) => b.risk_score - a.risk_score);
  pane.append(el("div", { class: "card" }, el("h3", null, "Entities by risk"),
    el("p", { class: "muted small" }, "Risk score from the Audit Universe (likelihood × impact) and whether the plan covers each entity."),
    ents.length ? el("div", { class: "table-wrap" }, el("table", { class: "dense" },
      el("thead", null, el("tr", null, ...["Entity", "Category", "Risk score", "Rating", "Covered by the plan"].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...ents.map((u) => el("tr", { class: "no-click" },
        el("td", null, el("span", { class: "ref" }, u.code), ` ${u.name}`), el("td", null, u.location), el("td", null, heat(u.risk_score)),
        el("td", null, statusBadge(u.risk)),
        el("td", null, u.covered ? el("span", { class: "outcome ok" }, el("i", { class: "bi bi-check-circle" }), " Yes")
          : el("span", { class: `outcome ${u.risk === "High" ? "bad" : ""}` }, el("i", { class: "bi bi-dash-circle" }), " No")))))))
      : emptyState({ icon: "diagram-2", title: "No entities in the Audit Universe" })));
}


// ---- auditable entities covered by the audit, and detailed scoping from them

async function auditEntitiesBar(box, audit, open, reload) {
  const ents = await safeGet(`/api/audits/${audit.id}/entities`, []);
  clear(box);
  box.append(el("div", { class: "fw-strip ent-strip" },
    el("span", { class: "fw-k" }, "Auditable entities"),
    ents.length ? el("span", { class: "chips" }, ...ents.map((e) => el("button", { class: "chip-link", type: "button", title: "Open the entity", onclick: () => openEntity(e.id) },
      el("span", { class: "ref" }, e.code), ` ${e.name}`))) : el("span", { class: "muted small" }, "None - choose the entities this audit covers"),
    el("span", { class: "grow" }),
    open ? btn("Choose entities", () => chooseAuditEntities(audit, ents, reload), "secondary") : null,
    open && ents.length && hasPerm("audit.plan", "audit.fieldwork") ? btn("Scope from entities", () => scopingDialog(audit, reload)) : null));
}

async function chooseAuditEntities(audit, current, reload) {
  const uni = await safeGet("/api/audit-universe", { entities: [] });
  openForm({
    title: "Auditable entities covered by this audit", draftable: false, width: 680,
    intro: "The audit's issues inherit these entities. The first one is the primary entity (from the plan).",
    fields: [{ name: "entity_ids", label: "Auditable entities", type: "checklist", full: true, emptyLabel: "Define the audit universe first.",
      options: uni.entities.filter((e) => e.status === "Active" || current.some((c) => c.id === e.id)).map((e) => ({ value: e.id, label: `${e.code} ${e.name}` })) }],
    initial: { entity_ids: current.map((e) => e.id) }, submitLabel: "Save",
    onSubmit: (v) => API.put(`/api/audits/${audit.id}/entities`, { entity_ids: (v.entity_ids || []).map(Number) }),
    onDone: () => { toast("Auditable entities saved"); reload(); },
  });
}

async function scopingDialog(audit, reload) {
  let pre;
  try { pre = await API.get(`/api/audits/${audit.id}/scoping`); } catch (err) { toast(err.message, "error"); return; }
  const wp = pre.workflow === "Workplan";
  const fresh = pre.groups.reduce((n, g) => n + g.risks.filter((r) => !r.in_audit).length + g.controls.filter((c) => !c.in_audit).length, 0);
  const body = el("div", null,
    el("p", { class: "muted small" }, wp ? "Each objective gets the entity's risks, and a procedure for each standard control (from its test steps)."
      : "Each objective gets the entity's risks (linked to the enterprise risk) and the standard controls, mapped to the risks, with their test steps as the test plan."),
    pre.groups.length ? el("div", null, ...pre.groups.map((g) => el("div", { class: "scope-group" },
      el("h4", null, g.objective),
      el("div", { class: "table-wrap" }, el("table", { class: "dense" },
        el("thead", null, el("tr", null, el("th", { scope: "col" }, "Item"), el("th", { scope: "col" }, "Type"), el("th", { scope: "col" }, "In the audit"))),
        el("tbody", null,
          ...g.risks.map((r) => el("tr", { class: "no-click" }, el("td", null, el("span", { class: "ref" }, r.ref), ` ${r.title}`), el("td", null, "Risk ", heat(r.likelihood * r.impact)),
            el("td", null, r.in_audit ? el("span", { class: "outcome ok" }, "Already in") : el("span", { class: "outcome" }, "Will be added")))),
          ...g.controls.map((c) => el("tr", { class: "no-click" }, el("td", null, el("span", { class: "ref" }, c.ref), ` ${c.title}`), el("td", null, wp ? "Procedure" : "Control"),
            el("td", null, c.in_audit ? el("span", { class: "outcome ok" }, "Already in") : el("span", { class: "outcome" }, "Will be added"))))))))))
      : emptyState({ icon: "link-45deg", title: "Nothing linked yet", text: "Link enterprise risks and standard controls to the entity or its processes (Process library > Risks & controls)." }));
  const m = modal({ title: "Detailed scoping from the auditable entities", width: 820, body,
    footer: el("div", { class: "form-foot-wrap" }, el("button", { class: "btn secondary", type: "button", onclick: () => m.close() }, "Cancel"),
      el("button", { class: "btn", type: "button", disabled: fresh ? null : "1", onclick: async () => {
        try {
          const r = await API.post(`/api/audits/${audit.id}/scoping`);
          m.close(true);
          toast(`Scoped: ${r.objectives} objective(s), ${r.risks} risk(s), ${wp ? `${r.procedures} procedure(s)` : `${r.controls} control(s)`}`);
          reload();
        } catch (err) { toast(err.message, "error"); }
      } }, fresh ? `Add ${fresh} item(s)` : "Nothing new to add")) });
}
