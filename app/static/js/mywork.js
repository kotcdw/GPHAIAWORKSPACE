// My work: one inbox of everything waiting for the signed-in person, across every audit.
// Items come from the workflow engine (prepare, review, respond, validate...) plus the person's to-dos.

const MYWORK_TABS = [
  { key: "", label: "All" },
  { key: "prepare", label: "To prepare" },
  { key: "review", label: "To review" },
  { key: "respond", label: "To respond" },
  { key: "action", label: "Actions" },
  { key: "task", label: "To-dos" },
];

function slaChip(item) {
  const st = item.sla_state;
  if (!item.due_at) return el("span", { class: "sla-chip sla-none" }, "No due date");
  const due = new Date(item.due_at);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const day = new Date(due); day.setHours(0, 0, 0, 0);
  const days = Math.round((day - today) / 86400000);
  let text;
  if (st === "breached") text = days < 0 ? `Overdue ${-days} day${days === -1 ? "" : "s"}` : "Overdue";
  else if (days === 0) text = "Due today";
  else if (days === 1) text = "Due tomorrow";
  else if (days < 8) text = `Due in ${days} days`;
  else text = `Due ${fmtDay(due)}`;
  const icon = st === "breached" ? "exclamation-octagon" : st === "warning" ? "hourglass-split" : "calendar-event";
  return el("span", { class: `sla-chip sla-${st}`, title: `Due ${fmtDate(due)}` },
    el("i", { class: `bi bi-${icon}`, "aria-hidden": "true" }), ` ${text}`);
}

function openWorkItem(item) {
  const l = item.link || {};
  if (l.type === "audit" && l.id) return openAudit(l.id, l.tab || null);
  if (l.type === "task") return navigate("tasks");
  return openLink(l.type, l.id);
}

async function refreshMyWorkCount() {
  const node = document.querySelector("#myWorkCount");
  if (!node) return;
  const c = await safeGet("/api/my-work/counts", { total: 0, overdue: 0 });
  node.textContent = c.total ? String(c.total) : "";
  node.classList.toggle("hidden", !c.total);
  node.classList.toggle("alert", !!c.overdue);
  node.title = c.overdue ? `${c.overdue} overdue` : "";
}

async function renderMyWork() {
  clear(viewRoot);
  const f = state.myWork || (state.myWork = { group: "", due: "", audit: "", q: "" });
  const msg = el("div");
  const refresh = el("button", { class: "btn small secondary", type: "button", onclick: () => renderMyWork() },
    el("i", { class: "bi bi-arrow-clockwise" }), " Refresh");
  viewRoot.append(viewHeader("My work", refresh,
    { sub: "Everything waiting for you across all audits, oldest due date first. Items close by themselves when the work moves on." }), msg);
  viewRoot.append(loadingState("Loading your work…"));
  let data;
  try { data = await API.get("/api/my-work"); }
  catch (err) { viewRoot.lastChild.remove(); notify(msg, err.message, "error"); return; }
  viewRoot.lastChild.remove();
  refreshMyWorkCount();
  const all = data.items;
  const c = data.counts;

  viewRoot.append(el("div", { class: "stats" },
    stat(c.total, "Open", "waiting for you"),
    stat(c.overdue, "Overdue", c.overdue ? "past their due date" : "nothing late", c.overdue ? "danger" : "ok"),
    stat(c.due_soon, "Due soon", "inside the warning window", c.due_soon ? "warn" : ""),
    stat(c.due_week, "Due in 7 days", "including overdue")));

  const audits = [...new Map(all.filter((i) => i.audit_id).map((i) => [i.audit_id, i])).values()]
    .sort((a, b) => (a.audit_ref || "").localeCompare(b.audit_ref || ""));
  const tabs = el("div", { class: "tabs mywork-tabs", role: "tablist" }, ...MYWORK_TABS.map((t) => {
    const n = t.key ? (c.by_group[t.key] || 0) : c.total;
    return el("button", { class: `tab ${f.group === t.key ? "active" : ""}`, type: "button", role: "tab",
      "aria-selected": f.group === t.key ? "true" : "false", onclick: () => { f.group = t.key; renderMyWork(); } },
    t.label, el("span", { class: "tab-count" }, String(n)));
  }));
  const auditSel = el("select", { class: "compact", "aria-label": "Audit" },
    el("option", { value: "" }, "All audits"),
    ...audits.map((a) => el("option", { value: String(a.audit_id), selected: String(a.audit_id) === f.audit ? "1" : null },
      `${a.audit_ref} · ${a.audit_title || ""}`.slice(0, 70))));
  auditSel.addEventListener("change", () => { f.audit = auditSel.value; paint(); });
  const dueSel = el("select", { class: "compact", "aria-label": "Due date" },
    ...[["", "Any due date"], ["overdue", "Overdue"], ["week", "Due in 7 days"]].map(([v, l]) =>
      el("option", { value: v, selected: f.due === v ? "1" : null }, l)));
  dueSel.addEventListener("change", () => { f.due = dueSel.value; paint(); });
  const search = el("input", { type: "search", class: "compact", placeholder: "Search", "aria-label": "Search my work", value: f.q });
  search.addEventListener("input", () => { f.q = search.value; paint(); });
  viewRoot.append(tabs, el("div", { class: "toolbar mywork-toolbar" }, auditSel, dueSel, search));

  const host = el("div");
  viewRoot.append(el("div", { class: "card" }, host));

  function paint() {
    clear(host);
    const week = Date.now() + 7 * 86400000;
    const q = f.q.trim().toLowerCase();
    const rows = all.filter((i) => (!f.group || i.group === f.group)
      && (!f.audit || String(i.audit_id) === f.audit)
      && (!f.due || (f.due === "overdue" ? i.sla_state === "breached" : (i.due_at && new Date(i.due_at).getTime() <= week)))
      && (!q || `${i.title} ${i.label} ${i.audit_ref || ""} ${i.audit_title || ""}`.toLowerCase().includes(q)));
    if (window.matchMedia("(max-width: 760px)").matches) { host.append(myWorkCards(rows, all.length)); return; }
    host.append(dataTable(rows, [
      { key: "due_at", label: "Due", render: slaChip, sortValue: (i) => i.due_at || "9999" },
      { key: "label", label: "What to do", render: (i) => el("span", { class: "mywork-kind" },
        el("i", { class: `bi bi-${MYWORK_ICONS[i.kind] || "circle"}`, "aria-hidden": "true" }), ` ${i.label}`) },
      { key: "title", label: "Item", render: (i) => el("span", { class: i.priority === "high" ? "strong" : null }, i.title) },
      { key: "audit_ref", label: "Audit", render: (i) => (i.audit_ref
        ? el("span", null, el("span", { class: "ref" }, i.audit_ref), " ", el("span", { class: "muted small" }, (i.audit_title || "").slice(0, 40)))
        : el("span", { class: "muted" }, "-")) },
      { key: "opened_at", label: "Waiting since", render: (i) => fmtDate(i.opened_at).split(",")[0] },
    ], { onRow: openWorkItem, pageSize: 25, exportName: "my-work.csv",
      emptyText: all.length ? "Nothing matches these filters." : "Nothing is waiting for you. New work appears here as soon as it is assigned or handed to you." }));
  }
  paint();
}

// Phone layout: one card per item instead of a wide table.
function myWorkCards(rows, total) {
  if (!rows.length) {
    return el("div", { class: "empty" }, total ? "Nothing matches these filters."
      : "Nothing is waiting for you. New work appears here as soon as it is assigned or handed to you.");
  }
  return el("div", { class: "mywork-cards" }, ...rows.map((i) => el("button", { class: `mywork-card ${i.priority === "high" ? "high" : ""}`, type: "button", onclick: () => openWorkItem(i) },
    el("div", { class: "mywork-card-top" }, slaChip(i), el("span", { class: "mywork-kind" },
      el("i", { class: `bi bi-${MYWORK_ICONS[i.kind] || "circle"}`, "aria-hidden": "true" }), ` ${i.label}`)),
    el("div", { class: "mywork-card-title" }, i.title),
    i.audit_ref ? el("div", { class: "muted small" }, `${i.audit_ref} · ${i.audit_title || ""}`) : null)));
}

const MYWORK_ICONS = {
  prepare: "pencil-square", review: "check2-circle", review_paper: "file-earmark-check", answer_note: "chat-left-text",
  clear_note: "chat-left-dots", provide_evidence: "upload", accept_evidence: "inbox", review_report: "file-earmark-text",
  approve_report: "patch-check", respond_finding: "reply", implement_action: "tools", validate_action: "shield-check",
  task: "check2-square",
};

// ------------------------------------------------------------------ Configuration > SLA time limits

async function renderSlaPoliciesCard(container) {
  const card = el("div", { class: "card" });
  container.append(card);
  const canEdit = hasPerm("system.workflow");
  card.append(el("div", { class: "card-head" }, el("h3", null, el("i", { class: "bi bi-stopwatch" }), " SLA time limits")),
    );
  let rows;
  try { rows = await API.get("/api/sla-policies"); } catch (err) { card.append(el("div", { class: "muted" }, err.message)); return; }
  const table = el("table", { class: "sla-table" },
    el("thead", null, el("tr", null, el("th", null, "Task"), el("th", { class: "num" }, "Working days"), el("th", { class: "num" }, "Warn before"),
      el("th", null, "Escalate"), el("th", null, "Active"), canEdit ? el("th", null, "") : null)),
    el("tbody", null, ...rows.map((p) => {
      const days = el("input", { type: "number", min: "1", max: "365", value: p.working_days, class: "cfg-num", disabled: canEdit ? null : "1", "aria-label": `${p.label}: working days` });
      const warn = el("input", { type: "number", min: "0", max: "60", value: p.warn_before_days, class: "cfg-num", disabled: canEdit ? null : "1", "aria-label": `${p.label}: warn before` });
      const esc = el("input", { type: "checkbox", disabled: canEdit ? null : "1", "aria-label": `${p.label}: escalate` }); esc.checked = p.escalate_on_breach;
      const act = el("input", { type: "checkbox", disabled: canEdit ? null : "1", "aria-label": `${p.label}: active` }); act.checked = p.active;
      const save = canEdit ? el("button", { class: "btn small", type: "button", onclick: async () => {
        try {
          await API.put(`/api/sla-policies/${p.key}`, { working_days: Number(days.value), warn_before_days: Number(warn.value),
            escalate_on_breach: esc.checked, active: act.checked });
          toast(`${p.label}: saved`);
        } catch (err) { toast(err.message, "error"); }
      } }, "Save") : null;
      return el("tr", { class: "no-click" }, el("td", null, p.label), el("td", { class: "num" }, days), el("td", { class: "num" }, warn),
        el("td", null, el("label", { class: "switch" }, esc, el("span", { class: "slider" }))),
        el("td", null, el("label", { class: "switch" }, act, el("span", { class: "slider" }))), canEdit ? el("td", null, save) : null);
    })));
  card.append(el("div", { class: "table-wrap" }, table));
}
