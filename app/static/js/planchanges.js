// GPHA Audit Workspace - plan change requests: the only way to change an approved Assurance Plan.
// Request (reason + affected items) -> impact (resources, coverage) -> independent review -> approval
// (GM Audit e-signature) -> new version, re-distributed.

const CR_ACTIONS = [{ value: "add", label: "Add an engagement" }, { value: "change", label: "Change an engagement" },
  { value: "cancel", label: "Cancel an engagement" }];

async function changeRequestEditor(plan, existing = null, onDone = null) {
  const [units, staff] = await Promise.all([
    safeGet("/api/entity-units?active_only=true", []),
    safeGet(`/api/assurance-plans/${plan.id}/cycle/recipients`, []),
  ]);
  const live = plan.engagements.filter((e) => e.status !== "Cancelled");
  const title = el("input", { maxlength: "255", value: existing ? existing.title : "", "aria-label": "Title" });
  const reason = el("textarea", { rows: "3", maxlength: "8000", "aria-label": "Reason",
    placeholder: "Why is the approved plan being changed? (Board request, new risk, resource change ...)" }, existing ? existing.reason : "");
  const items = (existing ? existing.items : [{ action: "add" }]).map((i) => ({ ...i }));
  const list = el("div", { class: "step-list" });
  const impactBox = el("div");

  const opt = (arr, v, empty) => [empty ? el("option", { value: "" }, empty) : null,
    ...arr.map((o) => el("option", { value: String(o.value), selected: String(o.value) === String(v ?? "") ? "1" : null }, o.label))];
  const unitOpts = units.sort((a, b) => b.risk_score - a.risk_score).map((u) => ({ value: u.id, label: `${u.location_name} / ${u.name} (risk ${u.risk_score})` }));
  const leadOpts = [{ value: state.user.id, label: `${state.user.full_name || state.user.username} (me)` },
    ...staff.map((s) => ({ value: s.id, label: `${s.name}${s.job_role ? ` · ${s.job_role}` : ""}` }))];
  let siteOpts = [];
  try { siteOpts = await planSites(); } catch { /* optional */ }
  const engOpts = live.map((e) => ({ value: e.id, label: `${e.title} (${e.planned_quarter}, ${e.budget_hours}h, ${e.status})` }));

  function control(it, key, node, parse = (v) => v) {
    node.addEventListener("change", () => { it[key] = node.value === "" ? null : parse(node.value); clear(impactBox); if (key === "action") paint(); });
    return node;
  }
  function paint() {
    clear(list);
    items.forEach((it, i) => {
      const num = (v) => Number(v);
      const fields = [field("Change", control(it, "action", el("select", null, ...opt(CR_ACTIONS, it.action))))];
      if (it.action !== "add") fields.push(field("Engagement", control(it, "engagement_id", el("select", null, ...opt(engOpts, it.engagement_id, "Choose...")), num)));
      if (it.action !== "cancel") {
        const t = el("input", { value: it.title || "", maxlength: "255", placeholder: it.action === "change" ? "(unchanged)" : "" });
        t.addEventListener("input", () => { it.title = t.value || null; });
        fields.push(field(it.action === "add" ? "Title" : "New title", t),
          field("Auditable unit", control(it, "entity_unit_id", el("select", null, ...opt(unitOpts, it.entity_unit_id, it.action === "add" ? "- none -" : "(unchanged)")), num)),
          field("Responsible site", control(it, "site_entity_id", el("select", null, ...opt(siteOpts, it.site_entity_id, it.action === "add" ? "- choose -" : "(unchanged)")), num)),
          field("Quarter", control(it, "planned_quarter", el("select", null, ...opt(QUARTERS.map((q) => ({ value: q, label: q })), it.planned_quarter, it.action === "add" ? null : "(unchanged)")))),
          field("Budget hours", control(it, "budget_hours", el("input", { type: "number", min: "0", max: "10000", value: it.budget_hours ?? "", placeholder: it.action === "change" ? "(unchanged)" : "0" }), num)),
          field("Lead", control(it, "lead_auditor_id", el("select", null, ...opt(leadOpts, it.lead_auditor_id, it.action === "add" ? "- not assigned -" : "(unchanged)")), num)));
      }
      if (it.action === "add" && !it.planned_quarter) it.planned_quarter = "Q1";
      list.append(el("div", { class: "step card" },
        el("div", { class: "card-head" }, el("strong", null, `Item ${i + 1}`),
          items.length > 1 ? btn("Remove", () => { items.splice(i, 1); clear(impactBox); paint(); }, "danger-ghost small") : null),
        el("div", { class: "grid-2" }, ...fields)));
    });
  }
  paint();
  const payload = () => ({ title: title.value.trim(), reason: reason.value.trim(),
    items: items.map((it) => Object.fromEntries(Object.entries(it).filter(([, v]) => v !== null && v !== undefined && v !== ""))) });
  const showImpact = async () => {
    try { clear(impactBox); impactBox.append(impactView(await API.post(`/api/assurance-plans/${plan.id}/change-requests/impact`, payload()))); }
    catch (err) { clear(impactBox); impactBox.append(el("div", { class: "msg error" }, err.message)); }
  };
  const m = modal({
    title: existing ? `Rework ${existing.cr_ref}` : "Plan change request", width: 900,
    body: el("div", null,
      el("p", { class: "muted small" }, `Approved version ${plan.current_version} is not edited directly. Describe the change; it is reviewed independently, approved by the GM Audit and becomes version ${plan.current_version + 1}.`),
      field("Title", title), field("Reason for the change", reason),
      el("h4", null, "Affected plan items"), list,
      btn("Add item", () => { items.push({ action: "add", planned_quarter: "Q1" }); paint(); }, "secondary small"),
      el("h4", null, "Impact"), impactBox),
    footer: el("div", { class: "actions" }, btn("Preview impact", showImpact, "secondary"),
      btn(existing ? "Resubmit" : "Submit for review", async () => {
        try {
          if (existing) await API.post(`/api/plan-change-requests/${existing.id}/resubmit`, payload());
          else await API.post(`/api/assurance-plans/${plan.id}/change-requests`, payload());
          toast("Change request submitted for review"); m.close(); if (onDone) onDone(); else openPlan(plan.id);
        } catch (err) { toast(err.message, "error"); }
      })),
  });
}

function impactView(im) {
  const r = im.resource; const c = im.coverage;
  const sign = (n) => (n > 0 ? `+${n}` : String(n));
  return el("div", { class: "impact" },
    el("ul", { class: "small" }, ...im.changes.map((x) => el("li", null, x))),
    el("div", { class: "stats" },
      stat(`${sign(r.hours_delta)}h`, "Hours", `${r.hours_before}h → ${r.hours_after}h of ${r.budget_hours || "no"} budget`, r.over_budget ? "danger" : ""),
      stat(`${r.engagements_before} → ${r.engagements_after}`, "Engagements"),
      stat(`${c.coverage_before}% → ${c.coverage_after}%`, "Universe coverage", `${c.covered_before} → ${c.covered_after} units`,
        c.coverage_after < c.coverage_before ? "warn" : ""),
      stat(c.high_risk_uncovered_after, "High-risk units not covered after", null, c.high_risk_newly_uncovered.length ? "danger" : "")),
    r.over_budget ? el("div", { class: "callout warn" }, el("i", { class: "bi bi-exclamation-triangle" }), el("div", null, "Planned hours would exceed the plan's budget.")) : null,
    c.high_risk_newly_uncovered.length ? el("div", { class: "callout warn" }, el("i", { class: "bi bi-shield-exclamation" }),
      el("div", null, el("strong", null, "High-risk units losing coverage: "), c.high_risk_newly_uncovered.join(", "))) : null,
    c.high_risk_newly_covered.length ? el("div", { class: "muted small" }, `Newly covered high-risk units: ${c.high_risk_newly_covered.join(", ")}`) : null,
    Object.keys(r.lead_hours_delta).length ? el("div", { class: "muted small" },
      `Hours by lead: ${Object.entries(r.lead_hours_delta).map(([k, v]) => `${k} ${sign(v)}h`).join(" · ")}`) : null,
    el("div", { class: "muted small" }, `Hours by quarter after: ${Object.entries(r.by_quarter_after).map(([q, h]) => `${q} ${h}h`).join(" · ")}`));
}

async function renderChangeRequests(panelEl, plan) {
  const reload = () => openPlan(plan.id);
  let rows;
  try { rows = await API.get(`/api/assurance-plans/${plan.id}/change-requests`); }
  catch (err) { panelEl.append(el("div", { class: "empty" }, err.message)); return; }
  const canRequest = plan.status === "Approved" && plan.current_version > 0 && hasPerm("plan.prepare", "oversight.port", "audit.memo_approve");
  const card = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, "Change requests"),
    canRequest ? btn("New change request", () => changeRequestEditor(plan)) : null));
  panelEl.append(card);
  if (!rows.length) { card.append(el("div", { class: "empty" }, plan.current_version ? "No change requests yet." : "Change requests start once the plan has an approved version.")); return; }
  rows.forEach((cr) => {
    const acts = [];
    if (cr.can_review) {
      acts.push(btn("Endorse", () => crReview(cr, "Endorse", reload)), btn("Return", () => crReview(cr, "Return", reload), "secondary"));
    }
    if (cr.can_approve) acts.push(btn("Approve / reject (e-sign)", () => eSignModal({ title: `Approve ${cr.cr_ref}`,
      pathOverride: `/api/plan-change-requests/${cr.id}/approve`, actionLabel: "Sign", allowReject: true, onDone: reload })));
    if (cr.can_resubmit) {
      acts.push(btn("Rework & resubmit", () => changeRequestEditor(plan, cr, reload), "secondary"));
    }
    if (cr.can_record_committee) acts.push(btn("Record Audit Committee decision", () => crCommittee(cr, reload)));
    if (cr.can_withdraw) acts.push(btn("Withdraw", async () => {
      try { await API.post(`/api/plan-change-requests/${cr.id}/withdraw`); toast("Withdrawn"); reload(); } catch (err) { toast(err.message, "error"); }
    }, "danger-ghost"));
    card.append(el("details", { class: "table-toggle cr", open: ["Submitted", "Endorsed", "Returned", "Awaiting Committee"].includes(cr.status) ? "1" : null },
      el("summary", null, el("span", { class: "ref" }, cr.cr_ref), " ", el("strong", null, cr.title), " ", badge(cr.status),
        cr.significant ? el("span", { class: "chip-mini warn-chip", title: "Needs Audit Committee approval (IIA GIAS 9.4)" }, " Significant") : el("span", { class: "chip-mini" }, " Minor"),
        el("span", { class: "muted small" }, ` · against v${cr.base_version}${cr.new_version ? ` → v${cr.new_version}` : ""}`)),
      el("dl", { class: "kv two-col" },
        el("dt", null, "Requested by"), el("dd", null, `${cr.requested_by || "-"} · ${fmtDate(cr.requested_at)}`),
        el("dt", null, "Reviewer"), el("dd", null, cr.reviewer ? `${cr.reviewer} · ${fmtDate(cr.reviewed_at)}${cr.review_comment ? ` — ${cr.review_comment}` : ""}` : "Awaiting review"),
        el("dt", null, "Approval"), el("dd", null, cr.approver ? `${cr.approver} · ${fmtDate(cr.decided_at)}${cr.decision_comment ? ` — ${cr.decision_comment}` : ""}` : "Pending"),
        el("dt", null, "Audit Committee"), el("dd", null, cr.significant
          ? (cr.committee_decision ? `${cr.committee_decision} · ${fmtDate(cr.committee_meeting_date).split(",")[0]} · ref ${cr.committee_reference}${cr.committee_notes ? ` — ${cr.committee_notes}` : ""}` : "Required (significant change) - after the CAE's approval")
          : "Not required (minor change); reported in the Committee pack"),
        el("dt", null, "New version"), el("dd", null, cr.new_version ? `v${cr.new_version}` : "-")),
      cr.significant && (cr.impact.significance || []).length ? el("div", { class: "callout warn" }, el("i", { class: "bi bi-bank" }),
        el("div", null, el("strong", null, "Significant change - Audit Committee approval required (IIA GIAS 9.4): "), cr.impact.significance.join("; "))) : null,
      el("div", { class: "long-field" }, el("div", { class: "lf-label" }, "Reason"), el("div", { class: "lf-value" }, cr.reason)),
      impactView(cr.impact),
      acts.length ? el("div", { class: "actions", style: "margin-top:8px" }, ...acts) : null));
  });
}

function crReview(cr, decision, reload) {
  openForm({
    title: `${decision === "Endorse" ? "Endorse" : "Return"} ${cr.cr_ref}`, draftable: false, width: 560,
    fields: [{ name: "comment", label: decision === "Return" ? "What needs to change" : "Review comment (optional)", type: "textarea",
      required: decision === "Return", minLength: decision === "Return" ? 5 : undefined, maxLength: 4000, full: true },
    ...(decision === "Endorse" && !cr.significant ? [{ name: "mark_significant", label: "Treat as significant (send to the Audit Committee)", type: "checkbox" }] : [])],
    submitLabel: decision,
    onSubmit: (v) => API.post(`/api/plan-change-requests/${cr.id}/review`, { decision, comment: v.comment || "", mark_significant: !!v.mark_significant }),
    onDone: () => { toast(decision === "Endorse" ? "Endorsed - sent for approval" : "Returned to the requester"); reload(); },
  });
}

function revisePlanDialog(plan) {
  openForm({
    title: "Full revision of the approved plan", draftable: false, width: 600,
    intro: "The plan returns to draft and goes back through internal review and the Audit Committee; re-approval creates the next version. For targeted changes use a change request instead.",
    fields: [{ name: "reason", label: "Reason for the revision", type: "textarea", required: true, minLength: 10, maxLength: 2000, full: true }],
    submitLabel: "Reopen for revision",
    onSubmit: (v) => API.post(`/api/assurance-plans/${plan.id}/reopen`, v),
    onDone: () => { toast("Plan reopened for revision"); openPlan(plan.id); },
  });
}

function crCommittee(cr, reload) {
  openForm({
    title: `Audit Committee decision on ${cr.cr_ref}`, draftable: false, width: 600,
    intro: "IIA GIAS 9.4: significant changes to the internal audit plan are approved by the board (Audit Committee). Approval applies the change and freezes a new version.",
    fields: [
      { name: "decision", label: "Decision", type: "select", required: true, options: ["Approved", "Rejected", "Deferred"] },
      { name: "meeting_date", label: "Meeting date", type: "date", required: true, notFuture: true },
      { name: "reference", label: "Minute / resolution reference", required: true, maxLength: 100, singleLine: true },
      { name: "notes", label: "Committee comments", type: "textarea", maxLength: 8000, full: true },
    ],
    submitLabel: "Record decision",
    onSubmit: (v) => API.post(`/api/plan-change-requests/${cr.id}/committee-decision`, { ...v, meeting_date: `${v.meeting_date}T09:00:00` }),
    onDone: (r) => { toast(r.new_version ? `Approved - version ${r.new_version} frozen` : `Decision recorded: ${r.committee_decision}`); reload(); },
  });
}
