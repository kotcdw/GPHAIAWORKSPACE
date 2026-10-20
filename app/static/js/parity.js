// GPHA Audit Workspace - Diligent One (HighBond) parity screens.
//
//   Sign-offs        Preparer, Detail / General / Supplemental / Specialty Reviewer; Next Reviewer; override; remove
//   Narratives       Internal Control fieldwork: process narratives linked to controls
//   Attributes       custom attributes per audit type on objectives, narratives, risks, controls, procedures, tests
//   Progress tab     Audit Procedures Completed, Time to Deadline, fieldwork status and the progress board
//   Status Tracker   every active audit: time expired, work completed, budget, time spent
//   Audit types      terms and custom attributes per audit type
//   Plan timeline    Table / Timeline, swimlanes and milestones; Include audits; Exclude from audit plan
//   Results          collections > tables > records (priority, status, assignee), interpretations, triggers
//   Storyboards      text, charts and metrics from interpretations, shared read-only
//   Robots           tasks running catalogue analytics now or on a schedule; task runs
// Loaded after fieldwork.js and before app.js.

// Confirm, then run an action (errors become a toast).
async function confirmThen({ title, message, confirmLabel = "Confirm", onConfirm }) {
  const r = await confirmDialog({ title, text: message, confirmLabel, danger: /delete|remove|exclude/i.test(confirmLabel) });
  if (!r || !r.ok) return;
  try { await onConfirm(); } catch (err) { toast(err.message, "error"); }
}

// ------------------------------------------------------------------ sign-offs

async function signoffSection(type, id, auditId, onChange) {
  const box = el("div", { class: "so-panel" });
  async function paint() {
    clear(box);
    let st;
    try { st = await API.get(`/api/signoffs/${type}/${id}`); } catch (err) { box.append(el("p", { class: "muted small" }, err.message)); return; }
    const sign = async (override = false) => {
      let password = null;
      if (st.requires_password) {
        password = window.prompt("Enter your password to sign");
        if (!password) return;
      }
      try { await API.post(`/api/signoffs/${type}/${id}`, { password, override }); toast(override ? "Sign-off recorded (override)" : "Signed off"); await paint(); if (onChange) onChange(); }
      catch (err) { toast(err.message, "error"); }
    };
    box.append(el("table", { class: "dense so-table" },
      el("thead", null, el("tr", null, el("th", { scope: "col" }, "Sign-off"), el("th", { scope: "col" }, "Signed by"), el("th", { scope: "col" }, "Date"), el("th", { scope: "col" }, el("span", { class: "sr-only" }, "Actions")))),
      el("tbody", null, ...st.levels.map((lvl) => el("tr", { class: "no-click" },
        el("td", null, el("span", { class: `so-dot ${lvl.done ? "done" : ""}`, "aria-hidden": "true" }), ` ${lvl.label}`),
        el("td", null, lvl.done ? [lvl.by || "-", lvl.override ? el("span", { class: "muted small" }, " (override)") : null] : el("span", { class: "muted" }, lvl.level === st.next_level ? "Waiting" : "-")),
        el("td", null, lvl.at ? fmtDate(lvl.at) : "-"),
        el("td", { class: "actions-cell" }, lvl.done && (lvl.by_id === state.user.id || st.can_override) ? el("button", {
          class: "btn small secondary icon", title: `Remove sign-off (also removes later ones)`, "aria-label": `Remove ${lvl.label} sign-off`,
          onclick: () => confirmThen({ title: "Remove sign-off", message: `Remove the ${lvl.label} sign-off? Every later sign-off is removed too.`, confirmLabel: "Remove",
            onConfirm: async () => { await API.del(`/api/signoffs/${type}/${id}/${lvl.level}`); toast("Sign-off removed"); await paint(); if (onChange) onChange(); } }) },
        el("i", { class: "bi bi-x-lg" })) : null))))));
    if (st.next_reviewer) box.append(el("p", { class: "small" }, el("i", { class: "bi bi-person-check" }), ` Next Reviewer: ${st.next_reviewer.name} (${st.levels[st.next_reviewer.level - 1].label})`));
    if (st.read_only) box.append(el("p", { class: "muted small" }, el("i", { class: "bi bi-lock" }), " Signed-off pages are read-only. Remove the sign-off to change this page."));
    const actions = el("div", { class: "actions" });
    if (st.can_sign) actions.append(btn(st.next_level === 1 ? "Sign-off" : `Sign-off as ${st.next_label}`, () => sign(false)));
    if (!st.can_sign && st.can_override) actions.append(btn(`Override Sign-off (${st.next_label})`, () => sign(true), "secondary"));
    if (st.next_level && st.next_level > 1) {
      const people = await safeGet(`/api/audits/${auditId}/signoff-reviewers`, []);
      const pick = el("select", { class: "compact", "aria-label": "Next Reviewer" }, el("option", { value: "" }, "Next Reviewer…"),
        ...people.filter((p) => !st.levels.some((l) => l.by_id === p.id)).map((p) => el("option", { value: p.id, selected: st.next_reviewer && st.next_reviewer.id === p.id ? "1" : null },
          `${p.name}${p.level ? ` · ${p.level}` : ""}${p.team ? "" : " (not on team)"}`)));
      actions.append(pick, btn("Set and Notify Reviewer", async () => {
        if (!pick.value) { toast("Choose the Next Reviewer", "error"); return; }
        try { await API.put(`/api/signoffs/${type}/${id}/next-reviewer`, { reviewer_id: Number(pick.value) }); toast("Reviewer notified"); await paint(); }
        catch (err) { toast(err.message, "error"); }
      }, "secondary"));
    }
    if (!st.can_sign && st.why_not && !st.complete) box.append(el("p", { class: "muted small" }, st.why_not));
    box.append(actions);
  }
  await paint();
  return box;
}

function openSignoffs(type, id, auditId, title, onChange) {
  const body = el("div");
  const m = modal({ title: `Sign-offs · ${title}`, body, width: 640, footer: el("button", { class: "btn secondary", onclick: () => m.close() }, "Close") });
  signoffSection(type, id, auditId, onChange).then((n) => body.append(n));
}

// Sign-off dots that open the sign-off panel.
function signoffCell(type, id, dots, auditId, title, reload) {
  return el("button", { class: "so-cell", type: "button", title: "Open sign-offs", onclick: (e) => { e.stopPropagation(); openSignoffs(type, id, auditId, title, reload); } },
    signoffDots(dots || []));
}

// ------------------------------------------------------------------ custom attributes

function attributeFields(defs) {
  return defs.map((d) => {
    const base = { name: `cf_${d.key}`, label: d.label, required: d.required, help: d.help || undefined };
    if (d.field_type === "longtext") return { ...base, type: "textarea", maxLength: 5000, full: true };
    if (d.field_type === "number") return { ...base, type: "number", step: "any" };
    if (d.field_type === "date") return { ...base, type: "date" };
    if (d.field_type === "select") return { ...base, type: "select", options: d.options };
    if (d.field_type === "yesno") return { ...base, type: "select", options: [{ value: true, label: "Yes" }, { value: false, label: "No" }] };
    return { ...base, maxLength: 255, singleLine: true };
  });
}

async function editAttributes(module, id, title, onSaved, readOnly = false) {
  let data;
  try { data = await API.get(`/api/custom-values/${module}/${id}`); } catch (err) { toast(err.message, "error"); return; }
  if (!data.fields.length) {
    toast(hasPerm("system.reference") ? "No custom attributes for this page yet - add them under Platform settings > Audit types" : "No custom attributes are set up for this page");
    return;
  }
  openForm({
    title: `Attributes · ${title}`, draftable: false, width: 640,
    fields: attributeFields(data.fields).map((f) => ({ ...f, disabled: readOnly })),
    initial: Object.fromEntries(Object.entries(data.values).map(([k, v]) => [`cf_${k}`, v])),
    submitLabel: "Save attributes",
    onSubmit: (v) => {
      if (readOnly) return Promise.resolve(null);
      const values = {};
      Object.entries(v).forEach(([k, x]) => { if (k.startsWith("cf_")) values[k.slice(3)] = x === "" ? null : x; });
      return API.put(`/api/custom-values/${module}/${id}`, { values });
    },
    onDone: () => { if (!readOnly) toast("Attributes saved"); if (onSaved) onSaved(); },
  });
}

// ------------------------------------------------------------------ terms

const TermCache = {};
async function auditTerms(auditId) {
  if (TermCache[auditId]) return TermCache[auditId];
  TermCache[auditId] = await safeGet(`/api/audits/${auditId}/terms`, {});
  return TermCache[auditId];
}
function termOf(terms, key, fallback) { return (terms && terms[key]) || fallback; }

// ------------------------------------------------------------------ narratives

async function renderNarratives(body, { audit, open, reload }) {
  body.append(loadingState());
  let rows; let rcm;
  try {
    [rows, rcm] = await Promise.all([API.get(`/api/audits/${audit.id}/narratives`), API.get(`/api/audits/${audit.id}/rcm`)]);
  } catch (err) { clear(body); body.append(errorState(err, reload)); return; }
  clear(body);
  const terms = await auditTerms(audit.id);
  const word = termOf(terms, "narrative", "Narrative");
  const objectives = rcm.objectives || [];
  const add = open ? btn(`Add new ${word.toLowerCase()}`, () => narrativeForm(audit, objectives, null, reload)) : null;
  if (!objectives.length) {
    body.append(emptyState({ icon: "journal-text", title: `No ${termOf(terms, "objective", "objective").toLowerCase()}s yet`,
      text: `Start with the engagement objectives (IIA GIAS 13.3); each ${word.toLowerCase()} describes the process behind one.`,
      action: open ? btn("Add objective", () => objectiveForm(audit.id, null, reload)) : null }));
    return;
  }
  if (!rows.length) {
    body.append(emptyState({ icon: "journal-text", title: `No ${word.toLowerCase()}s yet`, text: "Describe how each process works, then link the controls the narrative mentions.", action: add }));
    return;
  }
  body.append(el("div", { class: "card" },
    el("div", { class: "card-head" }, el("h3", null, `${word}s`), add),
    el("div", { class: "table-wrap" }, el("table", { class: "dense" },
      el("thead", null, el("tr", null, ...["Ref", "Title", termOf(terms, "objective", "Objective"), "Controls", "Updated", "Sign-offs"].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...rows.map((n) => el("tr", { tabindex: "0", onclick: () => narrativePanel(n, audit, objectives, open, reload), onkeydown: (e) => { if (e.key === "Enter") narrativePanel(n, audit, objectives, open, reload); } },
        el("td", { class: "ref", "data-label": "Ref" }, n.ref),
        el("td", { class: "col-wide", "data-label": "Title" }, el("div", { class: "cell-title" }, n.title), el("div", { class: "muted small" }, clip(n.description, 90))),
        el("td", { "data-label": "Objective" }, clip(n.objective, 40)),
        el("td", { "data-label": "Controls" }, n.controls.length ? n.controls.map((c) => c.ref).join(", ") : el("span", { class: "muted" }, "-")),
        el("td", { "data-label": "Updated" }, fmtDay(n.updated_at.slice(0, 10))),
        el("td", { "data-label": "Sign-offs" }, signoffCell("narrative", n.id, n.signoffs, audit.id, `${n.ref} ${n.title}`, reload)))))))));
}

function narrativeForm(audit, objectives, n, reload) {
  const controls = objectives.flatMap((o) => (o.controls || []).map((c) => ({ value: c.id, label: `${c.ref} ${c.title}` })));
  openForm({
    title: n ? `Edit ${n.ref}` : "Add new narrative", draftable: false, width: 760,
    fields: [
      ...(n ? [] : [{ name: "objective_id", label: "Objective", type: "select", required: true, options: objectives.map((o) => ({ value: o.id, label: `${o.ref} ${o.title}` })) }]),
      { name: "title", label: "Title", required: true, maxLength: 60, singleLine: true, full: true, help: "Up to 60 characters" },
      { name: "description", label: "Description", type: "textarea", rows: 10, maxLength: 524288, full: true },
      { name: "control_ids", label: "Controls described in this narrative", type: "checklist", full: true, options: controls, emptyLabel: "Add controls to the risk control matrix first." },
    ],
    initial: n ? { title: n.title, description: n.description, control_ids: n.controls.map((c) => c.id) } : { objective_id: objectives[0] && objectives[0].id, control_ids: [] },
    submitLabel: n ? "Save" : "Add narrative",
    onSubmit: (v) => {
      const bodyIn = { title: v.title, description: v.description || "", control_ids: (v.control_ids || []).map(Number) };
      return n ? API.patch(`/api/narratives/${n.id}`, bodyIn) : API.post(`/api/objectives/${v.objective_id}/narratives`, bodyIn);
    },
    onDone: () => { toast("Narrative saved"); reload(); },
  });
}

function narrativePanel(n, audit, objectives, open, reload) {
  const so = el("div");
  signoffSection("narrative", n.id, audit.id, () => { panel.close(); reload(); }).then((x) => so.append(x));
  const bodyNode = el("div", { class: "panel-sections" },
    el("dl", { class: "kv" }, el("dt", null, "Objective"), el("dd", null, n.objective),
      el("dt", null, "Controls"), el("dd", null, n.controls.length ? n.controls.map((c) => `${c.ref} ${c.title}`).join("; ") : "-")),
    formSection("Description", el("div", { class: "lf-value pre" }, n.description || "-")),
    formSection("Sign-offs", so));
  const footer = el("div", { class: "actions" },
    open && !n.read_only ? btn("Edit", () => { panel.close(); narrativeForm(audit, objectives, n, reload); }, "secondary") : null,
    btn("Attributes", () => editAttributes("narratives", n.id, n.ref, reload, !open || n.read_only), "secondary"),
    open && !n.read_only ? btn("Delete Narrative", () => confirmThen({ title: "Delete narrative", message: `Delete ${n.ref} ${n.title}?`, confirmLabel: "Delete",
      onConfirm: async () => { await API.del(`/api/narratives/${n.id}`); toast("Narrative deleted"); panel.close(); reload(); } }), "danger") : null);
  const panel = detailPanel({ title: `${n.ref} ${n.title}`, body: bodyNode, footer, width: 640 });
}

// ------------------------------------------------------------------ audit Progress tab

const SO_STATUS_CLASS = { Completed: "ok", "In progress": "warn", "Not started": "", "Not applicable": "muted" };

async function renderProgressTab(pane, audit) {
  const reload = () => { clear(pane); renderProgressTab(pane, audit); };
  pane.append(loadingState());
  let prog; let so;
  try { [prog, so] = await Promise.all([API.get(`/api/audits/${audit.id}/progress`), API.get(`/api/audits/${audit.id}/signoff-status`)]); }
  catch (err) { clear(pane); pane.append(errorState(err, reload)); return; }
  clear(pane);
  const work = Object.entries(prog.work).map(([label, count]) => ({ label, count }));
  const tones = { "Not Started": "var(--muted-2, #c4cad3)", "In Process": "var(--warn, #d9822b)", Completed: "var(--ok, #2f855a)" };
  pane.append(el("div", { class: "prog-grid" },
    el("div", { class: "card" }, el("h3", null, "Audit Procedures Completed"), donutChart("Procedures and tests", work, tones, "items")),
    el("div", { class: "card" }, el("h3", null, "Time to Deadline"),
      prog.target ? el("div", null,
        el("p", null, el("strong", null, prog.days_to_deadline >= 0 ? `${prog.days_to_deadline} day(s) left` : `${-prog.days_to_deadline} day(s) past target`),
          el("span", { class: "muted small" }, ` · ${fmtDay(prog.start)} to ${fmtDay(prog.target)}`)),
        el("div", { class: "small" }, "Time expired"), progressBar(prog.time_expired || 0, prog.time_expired > prog.progress + 15 ? "warn" : ""),
        el("div", { class: "small" }, "Work completed"), progressBar(prog.progress))
        : el("p", { class: "muted" }, "No planned dates: set them on the plan engagement or the Scheduler."),
      el("p", { class: "small" }, `Budget ${prog.budget_hours || 0} h · Time spent ${prog.time_spent} h`))));

  state.progressView = state.progressView || "status";
  const views = [{ key: "status", label: "Fieldwork status" }, { key: "board", label: "Progress board" }];
  const holder = el("div");
  pane.append(subNav(views, state.progressView, (k) => { state.progressView = k; reload(); }, "Progress views"), holder);
  if (!so.rows.length) { holder.append(emptyState({ icon: "kanban", title: "No fieldwork yet" })); return; }
  if (state.progressView === "status") {
    const groups = {};
    so.rows.forEach((r) => { const k = `${r.objective} › ${r.phase}`; (groups[k] = groups[k] || []).push(r); });
    holder.append(el("div", { class: "card" },
      el("div", { class: "stats" }, ...so.levels.map((l) => stat(`${so.summary[l].Completed}/${so.rows.length - so.summary[l]["Not applicable"]}`, l, "completed"))),
      el("div", { class: "table-wrap" }, el("table", { class: "dense" },
        el("thead", null, el("tr", null, el("th", { scope: "col" }, "Item"), ...so.levels.map((l, i) => el("th", { scope: "col", title: l }, `Sign-off #${i + 1}`)))),
        ...Object.entries(groups).map(([g, rows]) => el("tbody", null,
          el("tr", { class: "no-click group-row" }, el("th", { colspan: String(so.levels.length + 1) }, g)),
          ...rows.map((r) => el("tr", { class: "no-click" },
            el("td", null, signoffCell(r.type, r.id, r.signoffs, audit.id, r.title, reload), " ", clip(r.title, 70)),
            ...r.statuses.map((s) => el("td", null, el("span", { class: `so-status ${SO_STATUS_CLASS[s] || ""}` }, s)))))))))));
    return;
  }
  // Progress board: one column per stage of the sign-off flow.
  const stage = (r) => {
    const done = r.signoffs.filter((d) => d.done).length;
    if (!done) return "Not started";
    if (done === r.signoffs.length) return "Signed off";
    return done === 1 ? "Prepared" : "In review";
  };
  const cols = ["Not started", "Prepared", "In review", "Signed off"];
  holder.append(el("div", { class: "kanban" }, ...cols.map((c) => {
    const items = so.rows.filter((r) => stage(r) === c);
    return el("section", { class: "kanban-col", "aria-label": c },
      el("h4", null, c, el("span", { class: "count-pill" }, String(items.length))),
      ...items.map((r) => el("article", { class: "kanban-card" },
        el("div", { class: "muted small" }, `${r.phase}`),
        el("div", { class: "cell-title" }, clip(r.title, 80)),
        signoffCell(r.type, r.id, r.signoffs, audit.id, r.title, reload))),
      items.length ? null : el("p", { class: "muted small" }, "Nothing here"));
  })));
}

// ------------------------------------------------------------------ Status Tracker

async function renderStatusTracker() {
  clear(viewRoot);
  viewRoot.append(viewHeader("Status Tracker", null));
  const card = el("div", { class: "card" });
  viewRoot.append(card);
  card.append(loadingState());
  let rows;
  try { rows = await API.get("/api/audits/status-tracker"); } catch (err) { clear(card); card.append(errorState(err, renderStatusTracker)); return; }
  clear(card);
  const favFirst = el("input", { type: "checkbox", id: "st-fav", checked: Prefs.get("tracker.fav", true) ? "1" : null });
  const tableBox = el("div");
  card.append(el("label", { class: "check", for: "st-fav" }, favFirst, " Show favorites first"), tableBox);
  const paint = () => {
    Prefs.set("tracker.fav", favFirst.checked);
    const list = [...rows].sort((a, b) => (favFirst.checked ? (b.favorite - a.favorite) : 0) || a.name.localeCompare(b.name));
    clear(tableBox);
    if (!list.length) { tableBox.append(emptyState({ icon: "speedometer2", title: "No active audits" })); return; }
    tableBox.append(el("div", { class: "table-wrap" }, el("table", null,
      el("thead", null, el("tr", null, ...["", "Audit", "Time Expired", "Work Completed", "Budget", "Time Spent", "Status"].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...list.map((r) => el("tr", { onclick: () => openAudit(r.id) },
        el("td", null, favoriteStar(r, () => { r.favorite = !r.favorite; paint(); })),
        el("td", { class: "col-wide" }, el("div", { class: "cell-title" }, r.name), el("div", { class: "muted small" }, `${r.ref} · ${r.type || r.workflow}`)),
        el("td", null, r.time_expired === null ? el("span", { class: "muted" }, "No dates") : progressBar(r.time_expired, r.time_expired > r.work_completed + 15 ? "warn" : "")),
        el("td", null, progressBar(r.work_completed)),
        el("td", { class: "num" }, `${r.budget || 0} h`),
        el("td", { class: "num" }, el("span", { class: r.budget && r.time_spent > r.budget ? "text-danger" : null }, `${r.time_spent} h`)),
        el("td", null, statusBadge(r.status))))))));
  };
  favFirst.addEventListener("change", paint);
  paint();
}

function favoriteStar(row, onToggle) {
  return el("button", { class: "fav-star", type: "button", "aria-pressed": row.favorite ? "true" : "false",
    title: row.favorite ? "Remove from favorites" : "Add to favorites", "aria-label": row.favorite ? "Remove from favorites" : "Add to favorites",
    onclick: async (e) => {
      e.stopPropagation();
      try { if (row.favorite) await API.del(`/api/audits/${row.id}/favorite`); else await API.put(`/api/audits/${row.id}/favorite`); onToggle(); }
      catch (err) { toast(err.message, "error"); }
    } }, el("i", { class: `bi ${row.favorite ? "bi-star-fill" : "bi-star"}` }));
}

// ------------------------------------------------------------------ Audit types (terms and custom attributes)

const ATTRIBUTE_PAGES = [
  { module: "objectives", label: "Objectives" }, { module: "narratives", label: "Narratives" },
  { module: "risks", label: "Risks" }, { module: "controls", label: "Controls" },
  { module: "procedures", label: "Procedures" }, { module: "control_tests", label: "Walkthroughs and tests" },
  { module: "findings", label: "Issues" },
];
const ATTR_TYPES = [["text", "Short answer"], ["select", "Dropdown"], ["date", "Date"], ["longtext", "Paragraph"], ["number", "Number"], ["yesno", "Yes / No"]];

async function renderAuditTypes(tab = state.auditTypesTab || "terms") {
  state.auditTypesTab = tab;
  clear(viewRoot);
  viewRoot.append(viewHeader("Audit types"));
  let s;
  try { s = await API.get("/api/audit-types/settings"); } catch (err) { viewRoot.append(errorState(err, () => renderAuditTypes(tab))); return; }
  const canEdit = hasPerm("system.reference");
  viewRoot.append(tabBar([{ key: "terms", label: "Terms" }, { key: "attributes", label: "Custom attributes" }], tab, (k) => renderAuditTypes(k)));
  state.auditTypePick = state.auditTypePick && s.types.some((t) => t.name === state.auditTypePick) ? state.auditTypePick : (s.types[0] || {}).name;
  const pick = el("select", { class: "compact", "aria-label": "Audit type" }, ...s.types.map((t) => el("option", { value: t.name, selected: t.name === state.auditTypePick ? "1" : null }, `${t.name} · ${t.workflow}`)));
  pick.addEventListener("change", () => { state.auditTypePick = pick.value; renderAuditTypes(tab); });
  const type = s.types.find((t) => t.name === state.auditTypePick);
  const card = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, "Audit type"), pick));
  viewRoot.append(card);
  if (!type) { card.append(el("p", { class: "muted" }, "Add audit types under Configuration > Audit methodology first.")); return; }
  if (tab === "terms") {
    const inputs = {};
    card.append(el("div", { class: "terms-grid" }, ...Object.entries(s.defaults).map(([k, def]) => {
        inputs[k] = el("input", { value: type.terms[k] || "", placeholder: def, maxlength: "60", disabled: canEdit ? null : "1", "aria-label": `Term for ${def}` });
        return el("div", null, el("label", null, def), inputs[k]);
      })),
      canEdit ? el("div", { class: "actions" }, btn("Save terms", async () => {
        const terms = {};
        Object.entries(inputs).forEach(([k, i]) => { if (i.value.trim()) terms[k] = i.value.trim(); });
        try { await API.put(`/api/audit-types/${encodeURIComponent(type.name)}/terms`, { terms }); Object.keys(TermCache).forEach((k) => delete TermCache[k]); toast("Terms saved"); }
        catch (err) { toast(err.message, "error"); }
      })) : null);
    return;
  }
  for (const pg of ATTRIBUTE_PAGES) {
    const defs = (await safeGet(`/api/custom-fields?module=${pg.module}&include_inactive=true&audit_type=${encodeURIComponent(type.name)}`, [])).filter((d) => d.audit_type === type.name || !d.audit_type);
    const own = defs.filter((d) => d.audit_type === type.name);
    card.append(el("h4", null, `${pg.label} `, el("span", { class: "muted small" }, `${own.length}/10 for ${type.name}`)),
      defs.length ? el("table", { class: "dense" },
        el("thead", null, el("tr", null, ...["Attribute", "Type", "Choices", "Applies to", "Required", "Status"].map((h) => el("th", { scope: "col" }, h)))),
        el("tbody", null, ...defs.map((d) => el("tr", { class: "no-click" },
          el("td", null, d.label), el("td", null, (ATTR_TYPES.find((t) => t[0] === d.field_type) || [0, d.field_type])[1]),
          el("td", null, d.options.join(", ") || "-"), el("td", null, d.audit_type || "Every audit type"),
          el("td", null, d.required ? "Yes" : "No"),
          el("td", null, canEdit && d.audit_type === type.name ? el("button", { class: "btn small secondary", onclick: async () => { await API.patch(`/api/custom-fields/${d.id}`, { active: !d.active }); renderAuditTypes(tab); } }, d.active ? "Active · retire" : "Retired · restore") : (d.active ? "Active" : "Retired"))))))
        : el("p", { class: "muted small" }, "No custom attributes."),
      canEdit && own.length < 10 ? el("div", null, btn(`Add attribute to ${pg.label.toLowerCase()}`, () => auditTypeAttributeForm(pg, type, tab), "secondary")) : null);
  }
}

function auditTypeAttributeForm(pg, type, tab) {
  return openForm({
    title: `New ${pg.label.toLowerCase()} attribute (${type.name})`, draftable: false,
    fields: [
      { name: "label", label: "Attribute", required: true, maxLength: 100, singleLine: true },
      { name: "field_type", label: "Type", type: "select", required: true, options: ATTR_TYPES.map(([v, l]) => ({ value: v, label: l })) },
      { name: "options", label: "Choices (Dropdown, one per line)", type: "textarea", maxLength: 5000 },
      { name: "required", label: "Required", type: "checkbox" },
    ],
    initial: { field_type: "text" },
    onSubmit: (v) => API.post("/api/custom-fields", { module: pg.module, audit_type: type.name, label: v.label, field_type: v.field_type,
      options: (v.options || "").split("\n").map((x) => x.trim()).filter(Boolean), required: !!v.required }),
    onDone: () => { toast("Attribute added"); renderAuditTypes(tab); },
  });
}

// ------------------------------------------------------------------ plan Timeline and Include audits

const LANE_TONES = ["#2b6cb0", "#2f855a", "#b7791f", "#805ad5", "#c53030", "#2c7a7b", "#6b46c1", "#975a16"];

async function planTimeline(container, plan, reload) {
  state.timelineGroup = state.timelineGroup || "category";
  clear(container);
  container.append(loadingState());
  let tl;
  try { tl = await API.get(`/api/assurance-plans/${plan.id}/timeline?group=${state.timelineGroup}`); } catch (err) { clear(container); container.append(errorState(err, reload)); return; }
  clear(container);
  const group = el("select", { class: "compact", "aria-label": "Swimlanes" },
    ...[["category", "Category (port / site)"], ["quarter", "Quarter"], ["lead", "Lead"], ["status", "Status"]].map(([v, l]) => el("option", { value: v, selected: v === tl.group ? "1" : null }, `Swimlanes: ${l}`)));
  group.addEventListener("change", () => { state.timelineGroup = group.value; planTimeline(container, plan, reload); });
  const start = new Date(`${tl.start}T00:00:00`); const end = new Date(`${tl.end}T00:00:00`);
  const span = Math.max(1, (end - start) / 86400000 + 1);
  const pos = (d) => `${(100 * ((new Date(`${d}T00:00:00`) - start) / 86400000)) / span}%`;
  const width = (a, b) => `${Math.max(0.8, (100 * ((new Date(`${b}T00:00:00`) - new Date(`${a}T00:00:00`)) / 86400000 + 1)) / span)}%`;
  const months = [];
  for (let d = new Date(start.getFullYear(), start.getMonth(), 1); d <= end; d = new Date(d.getFullYear(), d.getMonth() + 1, 1)) {
    const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
    months.push(el("div", { class: "tl-month", style: `left:${pos(iso < tl.start ? tl.start : iso)}` }, d.toLocaleString(undefined, { month: "short" })));
  }
  const today = new Date().toISOString().slice(0, 10);
  const marks = [
    ...(today >= tl.start && today <= tl.end ? [el("div", { class: "tl-today", style: `left:${pos(today)}`, title: "Today" })] : []),
    ...tl.milestones.map((m) => el("div", { class: `tl-milestone ${m.kind}`, style: `left:${pos(m.date)}`, title: `${m.label} · ${fmtDay(m.date)}` }, el("i", { class: "bi bi-diamond-fill", "aria-hidden": "true" }))),
  ];
  container.append(el("div", { class: "tl-tools" }, group, el("span", { class: "muted small" }, `${fmtDay(tl.start)} to ${fmtDay(tl.end)} · bars use the planned dates, or the planned quarter when no dates are set`)),
    el("div", { class: "timeline", role: "img", "aria-label": "Audit plan timeline" },
      el("div", { class: "tl-head" }, el("div", { class: "tl-lane-label" }), el("div", { class: "tl-track" }, ...months, ...marks)),
      ...tl.lanes.map((lane, i) => el("div", { class: "tl-lane" },
        el("div", { class: "tl-lane-label" }, el("span", { class: "tl-swatch", style: `background:${LANE_TONES[i % LANE_TONES.length]}` }), lane.label),
        el("div", { class: "tl-track" }, ...marks.map((m) => m.cloneNode(true)),
          ...lane.items.map((it, j) => el("button", { type: "button", class: `tl-bar ${it.dated ? "" : "undated"} ${it.status === "Cancelled" ? "cancelled" : ""}`,
            style: `left:${pos(it.start)};width:${width(it.start, it.end)};top:${4 + (j % 3) * 26}px;background:${LANE_TONES[i % LANE_TONES.length]}`,
            title: `${it.title}\n${fmtDay(it.start)} to ${fmtDay(it.end)}\n${it.status}${it.audit_status ? ` · audit ${it.audit_status}` : ""} · ${it.budget_hours} h${it.lead ? ` · ${it.lead}` : ""}`,
            onclick: () => (it.audit_id ? openAudit(it.audit_id) : null) },
          el("span", { class: "tl-fill", style: `width:${it.progress}%` }), el("span", { class: "tl-text" }, it.title))))))),
    tl.milestones.length ? el("p", { class: "muted small" }, el("i", { class: "bi bi-diamond-fill" }), " Milestones: ", tl.milestones.map((m) => `${m.label} (${fmtDay(m.date)})`).join(" · ")) : null);
}

async function includeAuditsDialog(plan, reload) {
  const approved = plan.status === "Approved";
  const list = el("div", { class: "include-list" });
  const search = el("input", { type: "search", placeholder: "Search audits…", "aria-label": "Search audits" });
  const quarter = el("select", { class: "compact", "aria-label": "Quarter" }, ...["Q1", "Q2", "Q3", "Q4"].map((q) => el("option", { value: q }, q)));
  const reason = approved ? el("textarea", { rows: "2", maxlength: "2000", placeholder: "Reason for changing the approved plan", "aria-label": "Reason" }) : null;
  const chosen = new Set();
  let rows = [];
  const paint = () => {
    clear(list);
    const q = search.value.trim().toLowerCase();
    const shown = rows.filter((a) => !q || `${a.ref} ${a.title} ${a.audit_type || ""}`.toLowerCase().includes(q));
    if (!shown.length) { list.append(emptyState({ icon: "clipboard", title: "No audits to include" })); return; }
    list.append(el("table", { class: "dense" },
      el("thead", null, el("tr", null, ...["Select", "Ref", "Audit", "Type", "Lead", "Status"].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...shown.map((a) => {
        const box = el("input", { type: "checkbox", checked: chosen.has(a.id) ? "1" : null, "aria-label": `Include ${a.title}`,
          onchange: (e) => { if (e.target.checked) chosen.add(a.id); else chosen.delete(a.id); } });
        return el("tr", { class: "no-click" }, el("td", null, box), el("td", { class: "ref" }, a.ref), el("td", null, a.title),
          el("td", null, a.audit_type || "-"), el("td", null, a.lead || "-"), el("td", null, statusBadge(a.status)));
      }))));
  };
  search.addEventListener("input", paint);
  const body = el("div", null, el("div", { class: "tl-tools" }, search, el("label", null, "Quarter ", quarter)),
    approved ? el("div", null, el("p", { class: "muted small" }, "The plan is approved: each audit you include is recorded as a plan change."), reason) : null, list);
  const m = modal({ drawer: true, title: "Include audits", body, width: 820, footer: el("div", { class: "actions" },
    el("button", { class: "btn secondary", onclick: () => m.close() }, "Cancel"),
    el("button", { class: "btn", onclick: async () => {
      if (!chosen.size) { toast("Select at least one audit", "error"); return; }
      try {
        const r = await API.post(`/api/assurance-plans/${plan.id}/include`, { audit_ids: [...chosen], quarter: quarter.value, reason: reason ? reason.value : "" });
        toast(`${r.included} audit(s) included`); m.close(); reload();
      } catch (err) { toast(err.message, "error"); }
    } }, "Done")) });
  list.append(loadingState());
  rows = await safeGet(`/api/assurance-plans/${plan.id}/includable-audits`, []);
  paint();
}

function excludeFromPlan(plan, eng, reload) {
  const approved = plan.status === "Approved";
  if (!approved) {
    confirmThen({ title: "Exclude from audit plan", message: `Take ${eng.title} off the plan? The audit itself is kept.`, confirmLabel: "Exclude",
      onConfirm: async () => { await API.post(`/api/plan-engagements/${eng.id}/exclude`, {}); toast("Excluded from the plan"); reload(); } });
    return;
  }
  openForm({ title: "Exclude from audit plan", draftable: false, fields: [{ name: "reason", label: "Reason for changing the approved plan", type: "textarea", required: true, maxLength: 2000 }],
    submitLabel: "Exclude", onSubmit: (v) => API.post(`/api/plan-engagements/${eng.id}/exclude`, { reason: v.reason }), onDone: () => { toast("Excluded; recorded as a plan change"); reload(); } });
}

// ------------------------------------------------------------------ Results

async function renderResults(tableId = state.resultsTable || null) {
  state.resultsTable = tableId;
  clear(viewRoot);
  navCrumbs("results");
  const canBuild = hasPerm("oversight.reporting", "system.automation");
  viewRoot.append(viewHeader("Results", canBuild ? [btn("+ Add collection", () => collectionForm(tableId))] : null));
  let cols;
  try { cols = await API.get("/api/results/collections"); } catch (err) { viewRoot.append(errorState(err, () => renderResults(tableId))); return; }
  const nav = el("nav", { class: "res-nav card", "aria-label": "Collections" });
  const main = el("div", { class: "res-main" });
  viewRoot.append(el("div", { class: "res-layout" }, nav, main));
  if (!cols.length) {
    nav.append(el("p", { class: "muted small" }, "No collections yet."));
    main.append(emptyState({ icon: "table", title: "No results yet" }));
    return;
  }
  cols.forEach((c) => nav.append(el("div", { class: "res-col" },
    el("div", { class: "res-col-head" }, el("strong", null, c.name),
      canBuild ? el("button", { class: "btn small secondary icon", title: "Add table", "aria-label": `Add table to ${c.name}`, onclick: () => resultsTableForm(c, tableId) }, el("i", { class: "bi bi-plus" })) : null),
    ...c.tables.map((t) => el("button", { type: "button", class: `res-table ${t.id === tableId ? "active" : ""}`, onclick: () => renderResults(t.id) },
      el("i", { class: "bi bi-table", "aria-hidden": "true" }), ` ${t.name}`, t.open_records ? el("span", { class: "count-pill" }, String(t.open_records)) : null)),
    c.tables.length ? null : el("p", { class: "muted small" }, "No tables"))));
  if (!tableId) { main.append(emptyState({ icon: "table", title: "Choose a table" })); return; }
  main.append(loadingState());
  let t;
  try { t = await API.get(`/api/results/tables/${tableId}`); } catch (err) { clear(main); main.append(errorState(err, () => renderResults(null))); return; }
  clear(main);
  const people = await safeGet("/api/results/people", []);
  state.resultsTab = state.resultsTab || "table";
  main.append(el("div", { class: "card-head" }, el("h3", null, t.name, el("span", { class: "muted small" }, ` · ${t.collection}`))),
    t.description ? el("p", { class: "muted small" }, t.description) : null,
    tabBar([{ key: "table", label: `Table (${t.records.length})` }, { key: "interpretations", label: `Interpretations (${t.interpretations.length})` }, { key: "triggers", label: `Triggers (${t.triggers.length})` }],
      state.resultsTab, (k) => { state.resultsTab = k; renderResults(tableId); }));
  const pane = el("div", { class: "card" });
  main.append(pane);
  if (state.resultsTab === "table") {
    const fb = filterBar({ placeholder: "Search records…", filters: [{ key: "status", label: "Status", options: t.statuses }, { key: "priority", label: "Priority", options: t.priorities }], onChange: () => paint() });
    const box = el("div");
    pane.append(fb.root, box);
    const paint = () => {
      const v = fb.values();
      const rows = t.records.filter((r) => (!v.status || r.status === v.status) && (!v.priority || r.priority === v.priority)
        && (!v.q || JSON.stringify(r.data).toLowerCase().includes(v.q.toLowerCase())));
      fb.setCount(`${rows.length} of ${t.records.length}`);
      clear(box);
      if (!rows.length) { box.append(emptyState({ icon: "funnel", title: t.records.length ? "No records match" : "No records yet", text: t.records.length ? "Change or clear the filters." : "Run the robot task that publishes into this table." })); return; }
      const sel = (opts, value, onPick, label) => {
        const s = el("select", { class: "compact", "aria-label": label }, ...opts.map((o) => el("option", { value: o.value ?? o, selected: String(o.value ?? o) === String(value ?? "") ? "1" : null }, o.label ?? o)));
        s.addEventListener("change", () => onPick(s.value));
        return s;
      };
      const patch = async (r, body) => { try { Object.assign(r, await API.patch(`/api/results/records/${r.id}`, body)); toast("Record updated"); } catch (err) { toast(err.message, "error"); } };
      box.append(el("div", { class: "table-wrap" }, el("table", { class: "dense" },
        el("thead", null, el("tr", null, el("th", { scope: "col" }, "Record ID"), ...t.columns.map((c) => el("th", { scope: "col" }, c)),
          ...["Priority", "Status", "Assignee", "Published"].map((h) => el("th", { scope: "col" }, h)))),
        el("tbody", null, ...rows.map((r) => el("tr", { class: "no-click" },
          el("td", { class: "ref" }, String(r.id)),
          ...t.columns.map((c, n) => el("td", { class: n === 0 ? "col-wide" : null }, String(r.data[c] ?? ""))),
          el("td", null, sel(t.priorities, r.priority, (v) => patch(r, { priority: v }), "Priority")),
          el("td", null, sel(t.statuses, r.status, (v) => patch(r, { status: v }), "Status")),
          el("td", null, sel([{ value: "", label: "- unassigned -" }, ...people.map((p) => ({ value: p.id, label: p.name }))], r.assignee_id, (v) => patch(r, v ? { assignee_id: Number(v) } : { clear_assignee: true }), "Assignee")),
          el("td", null, fmtDay(r.published_at.slice(0, 10)))))))));
    };
    paint();
    return;
  }
  const fieldOptions = [{ value: "priority", label: "Priority" }, { value: "status", label: "Status" }, ...t.columns.map((c) => ({ value: c, label: c }))];
  if (state.resultsTab === "interpretations") {
    if (canBuild) pane.append(el("div", { class: "actions" }, btn("New interpretation", () => interpretationForm(tableId, fieldOptions))));
    if (!t.interpretations.length) { pane.append(emptyState({ icon: "bar-chart", title: "No interpretations" })); return; }
    const grid = el("div", { class: "prog-grid" });
    pane.append(grid);
    for (const i of t.interpretations) {
      const d = await safeGet(`/api/results/interpretations/${i.id}`, null);
      grid.append(el("div", { class: "card" }, el("div", { class: "card-head" }, el("h4", null, i.name),
        canBuild ? el("button", { class: "btn small secondary icon", title: "Delete", "aria-label": `Delete ${i.name}`, onclick: () => confirmThen({ title: "Delete interpretation", message: `Delete ${i.name}?`, confirmLabel: "Delete",
          onConfirm: async () => { await API.del(`/api/results/interpretations/${i.id}`); renderResults(tableId); } }) }, el("i", { class: "bi bi-trash" })) : null),
      d ? interpretationVisual(d) : el("p", { class: "muted" }, "Not available")));
    }
    return;
  }
  // triggers
  if (canBuild) pane.append(el("div", { class: "actions" }, btn("New", () => resultsTriggerForm(tableId, t, people))));
  if (!t.triggers.length) { pane.append(emptyState({ icon: "lightning", title: "No triggers" })); return; }
  pane.append(el("table", { class: "dense" },
    el("thead", null, el("tr", null, ...["Trigger", "Conditions", "Actions", "Frequency", "Last run", ""].map((h) => el("th", { scope: "col" }, h)))),
    el("tbody", null, ...t.triggers.map((g) => el("tr", { class: "no-click" },
      el("td", null, g.name),
      el("td", null, g.config.conditions.length ? `${g.config.match}: ${g.config.conditions.map((c) => `${c.field} is ${c.value}`).join(", ")}` : "Every record"),
      el("td", null, g.config.actions.map((a) => (a.type === "notify" ? `Notify ${a.user_ids.length}` : a.type === "assign" ? "Assign" : `${a.type} → ${a.value}`)).join("; ")),
      el("td", null, g.config.only_new ? "Real-time (new records)" : "Real-time"),
      el("td", null, g.last_run_at ? fmtDate(g.last_run_at) : "-"),
      el("td", { class: "actions-cell" }, canBuild ? [
        btn("Run", async () => { const r = await API.post(`/api/results/triggers/${g.id}/run`); toast(`${r.matched} record(s) matched`); renderResults(tableId); }, "secondary"),
        btn("Delete", () => confirmThen({ title: "Delete trigger", message: `Delete ${g.name}?`, confirmLabel: "Delete", onConfirm: async () => { await API.del(`/api/results/triggers/${g.id}`); renderResults(tableId); } }), "secondary")] : null))))));
}

function collectionForm(tableId) {
  return openForm({
  title: "Create collection", draftable: false,
  fields: [{ name: "name", label: "Name", required: true, maxLength: 255, singleLine: true }, { name: "description", label: "Description", type: "textarea", maxLength: 5000 }],
  onSubmit: (v) => API.post("/api/results/collections", v), onDone: () => { toast("Collection created"); renderResults(tableId); } });
}

function resultsTableForm(c, tableId) {
  return openForm({
  title: `New table in ${c.name}`, draftable: false, fields: [{ name: "name", label: "Name", required: true, maxLength: 255, singleLine: true }, { name: "description", label: "Description", type: "textarea", maxLength: 5000 }],
  onSubmit: (v) => API.post(`/api/results/collections/${c.id}/tables`, v), onDone: () => renderResults(tableId) });
}

function interpretationForm(tableId, fieldOptions) {
  return openForm({
  title: "New interpretation", draftable: false,
  fields: [{ name: "name", label: "Name", required: true, maxLength: 255, singleLine: true },
    { name: "chart", label: "Visualization", type: "select", required: true, options: [{ value: "bar", label: "Bar chart" }, { value: "donut", label: "Donut chart" }, { value: "metric", label: "Metric (count)" }, { value: "table", label: "Summary table" }] },
    { name: "group_by", label: "Group by", type: "select", required: true, options: fieldOptions },
    { name: "f_field", label: "Filter: field", type: "select", options: fieldOptions }, { name: "f_value", label: "Filter: value is", maxLength: 255, singleLine: true }],
  initial: { chart: "bar", group_by: "priority" },
  onSubmit: (v) => API.post(`/api/results/tables/${tableId}/interpretations`, { name: v.name, chart: v.chart, group_by: v.group_by,
    filters: v.f_field && v.f_value ? [{ field: v.f_field, op: "is", value: v.f_value }] : [] }),
  onDone: () => renderResults(tableId) });
}

function resultsTriggerForm(tableId, t, people) {
  return openForm({
  title: "New trigger", draftable: false, width: 720,
  fields: [{ name: "name", label: "Name", required: true, maxLength: 255, singleLine: true },
    { name: "match", label: "Conditions must match", type: "select", required: true, options: ["ALL", "ANY"] },
    { name: "c_priority", label: "When Priority is", type: "select", options: t.priorities },
    { name: "c_status", label: "When Status is", type: "select", options: t.statuses },
    { name: "a_assign", label: "Assign > Users > Assignee", type: "select", options: people.map((p) => ({ value: p.id, label: p.name })) },
    { name: "a_notify", label: "Notify", type: "checklist", full: true, options: people.map((p) => ({ value: p.id, label: p.name })) },
    { name: "a_status", label: "Set Status", type: "select", options: t.statuses },
    { name: "a_priority", label: "Set Priority", type: "select", options: t.priorities },
    { name: "only_new", label: "Real-time > Record: only for new records", type: "checkbox" }],
  initial: { match: "ALL", only_new: true },
  onSubmit: (v) => {
    const conditions = [...(v.c_priority ? [{ field: "priority", value: v.c_priority }] : []), ...(v.c_status ? [{ field: "status", value: v.c_status }] : [])];
    const actions = [...(v.a_assign ? [{ type: "assign", user_id: Number(v.a_assign) }] : []), ...((v.a_notify || []).length ? [{ type: "notify", user_ids: v.a_notify.map(Number) }] : []),
      ...(v.a_status ? [{ type: "status", value: v.a_status }] : []), ...(v.a_priority ? [{ type: "priority", value: v.a_priority }] : [])];
    return API.post(`/api/results/tables/${tableId}/triggers`, { name: v.name, match: v.match, conditions, actions, only_new: !!v.only_new });
  },
  onDone: () => renderResults(tableId) });
}

function interpretationVisual(d) {
  if (d.chart === "metric") return el("div", { class: "stat" }, el("div", { class: "l" }, d.name), el("div", { class: "n" }, String(d.total)), el("div", { class: "s" }, d.table));
  if (d.chart === "donut") return donutChart(d.name, d.series.map((s) => ({ label: s.label, count: s.count })), {}, "records");
  if (d.chart === "table") {
    return el("table", { class: "dense" }, el("thead", null, el("tr", null, el("th", { scope: "col" }, d.group_by), el("th", { scope: "col", class: "num" }, "Records"))),
      el("tbody", null, ...d.series.map((s) => el("tr", { class: "no-click" }, el("td", null, s.label), el("td", { class: "num" }, String(s.count))))));
  }
  const max = Math.max(1, ...d.series.map((s) => s.count));
  return el("div", { class: "hbars", role: "img", "aria-label": `${d.name}: ${d.series.map((s) => `${s.label} ${s.count}`).join(", ")}` },
    d.series.length ? d.series.map((s) => el("div", { class: "hbar" }, el("span", { class: "hbar-label" }, s.label),
      el("span", { class: "hbar-track" }, el("span", { class: "hbar-fill", style: `width:${Math.round((100 * s.count) / max)}%` })), el("span", { class: "hbar-n" }, String(s.count))))
      : el("p", { class: "muted small" }, "No records"));
}

// ------------------------------------------------------------------ Storyboards

async function renderStoryboards(id = null, edit = false) {
  clear(viewRoot);
  navCrumbs("storyboards");
  const canBuild = hasPerm("oversight.reporting", "system.automation");
  if (!id) {
    viewRoot.append(viewHeader("Storyboards", canBuild ? [btn("Add Storyboard", () => newStoryboardForm())] : null));
    const list = await safeGet("/api/storyboards", []);
    const card = el("div", { class: "card" });
    viewRoot.append(card);
    if (!list.length) { card.append(emptyState({ icon: "easel", title: "No storyboards" })); return; }
    card.append(el("table", null, el("thead", null, el("tr", null, ...["Storyboard", "Owner", "Shared with", "Updated"].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...list.map((s) => el("tr", { onclick: () => renderStoryboards(s.id) },
        el("td", null, s.name), el("td", null, s.owner || "-"),
        el("td", null, s.shared_with.all_staff ? "All staff" : `${(s.shared_with.user_ids || []).length} user(s)`),
        el("td", null, fmtDay(s.updated_at.slice(0, 10))))))));
    return;
  }
  let sb;
  try { sb = await API.get(`/api/storyboards/${id}`); } catch (err) { viewRoot.append(errorState(err, () => renderStoryboards())); return; }
  const blocks = sb.blocks.map((b) => ({ ...b }));
  const save = async () => { try { await API.put(`/api/storyboards/${id}`, { name: sb.name, blocks: blocks.map(({ data, ...b }) => b) }); toast("Saved"); renderStoryboards(id, true); } catch (err) { toast(err.message, "error"); } };
  const actions = sb.can_edit ? [
    el("label", { class: "check" }, el("input", { type: "checkbox", checked: edit ? "1" : null, onchange: (e) => renderStoryboards(id, e.target.checked) }), " Edit"),
    btn("Share Storyboard", () => shareStoryboard(sb), "secondary"),
    btn("Delete", () => confirmThen({ title: "Delete storyboard", message: `Delete ${sb.name}?`, confirmLabel: "Delete", onConfirm: async () => { await API.del(`/api/storyboards/${id}`); renderStoryboards(); } }), "secondary")] : null;
  viewRoot.append(viewHeader(sb.name, actions, { back: () => renderStoryboards(), sub: sb.can_edit ? `Owner: ${sb.owner || "-"}` : "Read Only" }));
  const grid = el("div", { class: "sb-grid" });
  viewRoot.append(grid);
  blocks.forEach((b, i) => {
    const tools = edit ? el("div", { class: "sb-tools" },
      iconBtn("arrow-up", "Move up", () => { if (i) { [blocks[i - 1], blocks[i]] = [blocks[i], blocks[i - 1]]; save(); } }),
      iconBtn("arrow-down", "Move down", () => { if (i < blocks.length - 1) { [blocks[i + 1], blocks[i]] = [blocks[i], blocks[i + 1]]; save(); } }),
      iconBtn("arrows-angle-expand", "Half / full width", () => { b.width = b.width === "half" ? "full" : "half"; save(); }),
      iconBtn("trash", "Remove", () => { blocks.splice(i, 1); save(); })) : null;
    let content;
    if (b.type === "text") content = el("div", null, b.title ? el("h3", null, b.title) : null, el("div", { class: "pre" }, b.body));
    else content = el("div", null, b.title ? el("h4", null, b.title) : null, b.data ? interpretationVisual(b.data.chart === "metric" || b.type === "metric" ? { ...b.data, chart: b.type === "metric" ? "metric" : b.data.chart } : b.data) : el("p", { class: "muted" }, "Interpretation not available"));
    grid.append(el("section", { class: `card sb-block ${b.width === "half" ? "half" : "full"}` }, tools, content));
  });
  if (!blocks.length) grid.append(emptyState({ icon: "easel", title: "Empty storyboard", text: edit ? "Add text, charts or metrics below." : "Nothing on this storyboard yet." }));
  if (edit) {
    const interps = await safeGet("/api/results/interpretations", []);
    const opts = interps.map((x) => ({ value: x.id, label: `${x.name} · ${x.table}` }));
    viewRoot.append(el("div", { class: "actions" },
      btn("Add Text", () => openForm({ title: "Add Text", draftable: false, fields: [{ name: "title", label: "Title", maxLength: 255, singleLine: true }, { name: "body", label: "Body", type: "textarea", rows: 6, maxLength: 20000 }],
        onSubmit: async (v) => { blocks.push({ type: "text", title: v.title || "", body: v.body || "", width: "full" }); return true; }, onDone: save }), "secondary"),
      btn("Add Chart", () => (opts.length ? openForm({ title: "Add Chart", draftable: false, fields: [{ name: "interpretation_id", label: "Interpretation", type: "select", required: true, options: opts }, { name: "title", label: "Title", maxLength: 255, singleLine: true }],
        onSubmit: async (v) => { blocks.push({ type: "chart", interpretation_id: Number(v.interpretation_id), title: v.title || "", width: "half" }); return true; }, onDone: save }) : toast("Save an interpretation in Results first", "error")), "secondary"),
      btn("Add Metric", () => (opts.length ? openForm({ title: "Add Metric", draftable: false, fields: [{ name: "interpretation_id", label: "Interpretation", type: "select", required: true, options: opts }, { name: "title", label: "Title", maxLength: 255, singleLine: true }],
        onSubmit: async (v) => { blocks.push({ type: "metric", interpretation_id: Number(v.interpretation_id), title: v.title || "", width: "half" }); return true; }, onDone: save }) : toast("Save an interpretation in Results first", "error")), "secondary")));
  }
}

function newStoryboardForm() {
  return openForm({ title: "Add Storyboard", draftable: false,
  fields: [{ name: "name", label: "Name", required: true, maxLength: 255, singleLine: true }],
  onSubmit: (v) => API.post("/api/storyboards", { name: v.name, blocks: [] }), onDone: (sb) => renderStoryboards(sb.id, true) });
}

async function shareStoryboard(sb) {
  const people = await safeGet("/api/results/people", []);
  openForm({
    title: "Share Storyboard", draftable: false, width: 640,
    fields: [{ name: "all_staff", label: "Anyone on the audit staff and committee (Read Only)", type: "checkbox" },
      { name: "user_ids", label: "Users (Read Only)", type: "checklist", full: true, options: people.map((p) => ({ value: p.id, label: `${p.name} · ${p.role}` })) }],
    initial: { all_staff: !!sb.shared_with.all_staff, user_ids: sb.shared_with.user_ids || [] },
    submitLabel: "Confirm Changes",
    onSubmit: (v) => API.put(`/api/storyboards/${sb.id}/share`, { all_staff: !!v.all_staff, user_ids: (v.user_ids || []).map(Number) }),
    onDone: () => { toast("Sharing updated"); renderStoryboards(sb.id); },
  });
}

// ------------------------------------------------------------------ Robots

async function renderRobots(tab = state.robotsTab || "robots") {
  state.robotsTab = tab;
  clear(viewRoot);
  const canRun = hasPerm("system.automation");
  viewRoot.append(viewHeader("Robots", canRun ? [btn("+ Create", () => newRobotForm())] : null));
  viewRoot.append(tabBar([{ key: "robots", label: "Robots and tasks" }, { key: "runs", label: "Task runs" }], tab, (k) => renderRobots(k)));
  const card = el("div", { class: "card" });
  viewRoot.append(card);
  if (tab === "runs") {
    const runs = await safeGet("/api/robot-runs?limit=200", []);
    if (!runs.length) { card.append(emptyState({ icon: "clock-history", title: "No task runs yet" })); return; }
    card.append(el("div", { class: "table-wrap" }, el("table", { class: "dense" },
      el("thead", null, el("tr", null, ...["Task", "Started", "Duration", "Run method", "User", "Status", "Records", "Message"].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...runs.map((r) => el("tr", { class: "no-click" },
        el("td", null, r.task || "-"), el("td", null, fmtDate(r.started_at)), el("td", null, r.duration_s === null ? "-" : `${r.duration_s} s`),
        el("td", null, r.method), el("td", null, r.user || "System"), el("td", null, statusBadge(r.status)), el("td", { class: "num" }, String(r.records)),
        el("td", { class: "small" }, r.message)))))));
    return;
  }
  const [robots, catalog] = await Promise.all([safeGet("/api/robots", []), safeGet("/api/robots/analytics", [])]);
  if (!robots.length) { card.append(emptyState({ icon: "robot", title: "No robots yet", action: null })); return; }
  robots.forEach((rb) => card.append(el("section", { class: "robot" },
    el("div", { class: "card-head" }, el("h3", null, el("i", { class: "bi bi-robot" }), ` ${rb.name}`),
      canRun ? el("div", { class: "actions" }, btn("Create task", () => robotTaskForm(rb, catalog), "secondary"),
        btn("Delete", () => confirmThen({ title: "Delete robot", message: `Delete ${rb.name} and its tasks?`, confirmLabel: "Delete", onConfirm: async () => { await API.del(`/api/robots/${rb.id}`); renderRobots(); } }), "secondary")) : null),
    rb.description ? el("p", { class: "muted small" }, rb.description) : null,
    rb.tasks.length ? el("div", { class: "table-wrap" }, el("table", { class: "dense" },
      el("thead", null, el("tr", null, ...["Task", "Analytic", "Schedule", "Next run", "Last run", "Results table", ""].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...rb.tasks.map((t) => el("tr", { class: "no-click" },
        el("td", null, t.name, t.enabled ? null : el("span", { class: "muted small" }, " (off)")),
        el("td", null, t.analytic_name),
        el("td", null, t.frequency ? `${t.frequency[0].toUpperCase()}${t.frequency.slice(1)} at ${t.starting_at}` : "Not scheduled"),
        el("td", null, t.next_run_at ? fmtDate(t.next_run_at) : "-"),
        el("td", null, t.last_run ? [statusBadge(t.last_run.status), el("span", { class: "muted small" }, ` ${fmtDate(t.last_run.started_at)} · ${t.last_run.records} rec.`)] : "-"),
        el("td", null, t.table_id ? el("a", { href: "#", onclick: (e) => { e.preventDefault(); state.resultsTab = "table"; navigate("results"); setTimeout(() => renderResults(t.table_id), 0); } }, t.table) : "-"),
        el("td", { class: "actions-cell" }, canRun ? [
          btn("Run now", async () => { try { const r = await API.post(`/api/robot-tasks/${t.id}/run`); toast(`Run ${r.status}: ${r.message}`, r.status === "Success" ? "" : "error"); renderRobots(); } catch (err) { toast(err.message, "error"); } }),
          btn(t.enabled ? "Turn off" : "Turn on", async () => { await API.patch(`/api/robot-tasks/${t.id}`, { enabled: !t.enabled }); renderRobots(); }, "secondary"),
          btn("Delete", () => confirmThen({ title: "Delete task", message: `Delete ${t.name}?`, confirmLabel: "Delete", onConfirm: async () => { await API.del(`/api/robot-tasks/${t.id}`); renderRobots(); } }), "secondary")] : null)))))) : el("p", { class: "muted small" }, "No tasks yet."))));
}

function newRobotForm() {
  return openForm({ title: "Create robot", draftable: false,
  fields: [{ name: "name", label: "Name", required: true, maxLength: 255, singleLine: true }, { name: "description", label: "Description", type: "textarea", maxLength: 5000 }],
  onSubmit: (v) => API.post("/api/robots", v), onDone: () => renderRobots("robots") });
}

function robotTaskForm(robot, catalog) {
  const params = catalog.flatMap((a) => a.params.map((p) => ({ name: `p_${a.key}_${p.key}`, label: `${a.name}: ${p.label}`, type: "number", min: p.min, max: p.max, analytic: a.key, key: p.key, def: p.default })));
  openForm({
    title: `Create task · ${robot.name}`, draftable: false, width: 760,
    fields: [
      { name: "name", label: "Task name", required: true, maxLength: 255, singleLine: true },
      { name: "analytic", label: "Analytic (selected script)", type: "select", required: true, options: catalog.map((a) => ({ value: a.key, label: `${a.name} - ${a.description}` })) },
      { type: "heading", label: "Parameters (only those of the chosen analytic are used)" },
      ...params,
      { type: "heading", label: "Put your task on a schedule" },
      { name: "frequency", label: "Frequency", type: "select", emptyLabel: "No schedule (run manually)", options: [{ value: "daily", label: "Daily" }, { value: "weekly", label: "Weekly" }, { value: "monthly", label: "Monthly" }] },
      { name: "starting_at", label: "Starting at (server time)", type: "time" },
      { name: "beginning_on", label: "Beginning on", type: "date" },
      { name: "notify_on_failure", label: "Send notifications on failure", type: "checkbox" },
    ],
    initial: { analytic: catalog[0] && catalog[0].key, starting_at: "06:00", notify_on_failure: true, ...Object.fromEntries(params.map((p) => [p.name, p.def])) },
    submitLabel: "Confirm and create task",
    onSubmit: (v) => {
      const chosen = {};
      params.filter((p) => p.analytic === v.analytic).forEach((p) => { if (v[p.name] !== null && v[p.name] !== undefined) chosen[p.key] = v[p.name]; });
      return API.post(`/api/robots/${robot.id}/tasks`, { name: v.name, analytic: v.analytic, params: chosen, frequency: v.frequency || null,
        starting_at: v.starting_at || "06:00", beginning_on: v.beginning_on || null, notify_on_failure: !!v.notify_on_failure });
    },
    onDone: () => { toast("Task created"); renderRobots("robots"); },
  });
}
