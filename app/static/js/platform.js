// Optional AI Service helpers (drafting help on findings, report summaries and risks).

// ------------------------------------------------------------------ AI Service (pluggable, off by default)
let _aiStatus = null;
function aiStatus(refresh = false) {
  if (!_aiStatus || refresh) _aiStatus = safeGet("/api/ai/status", { enabled: false, can_use: false });
  return _aiStatus;
}

// A button that only appears when AI is enabled and the user's role may use it.
function aiButton(label, onclick) {
  const holder = el("span", { class: "ai-slot" });
  aiStatus().then((s) => {
    if (!s.can_use) return;
    holder.append(el("button", { class: "btn secondary ai-btn", type: "button", title: "Produces a draft for you to review; nothing is saved until you accept it and save",
      onclick: async (e) => {
        const b = e.currentTarget;
        b.disabled = true;
        const old = b.textContent;
        b.textContent = "Drafting…";
        try { await onclick(); } catch (err) { toast(err.message, "error"); }
        finally { b.disabled = false; b.textContent = old; }
      } }, el("i", { class: "bi bi-stars" }), ` ${label}`));
  });
  return holder;
}

function _fillField(handle, fields, name, value) {
  const node = handle.nodes[name];
  const f = fields.find((x) => x.name === name);
  if (!node || !f) return;
  _setValue(f, node, value);
  node.dispatchEvent(new Event("input", { bubbles: true }));
}

// Show AI drafts side by side with the current text; the user ticks which ones to copy into the form.
function aiReview(title, rows, onAccept) {
  const checks = {};
  const body = el("div", null,
    el("div", { class: "callout" }, el("i", { class: "bi bi-info-circle" }),
      " AI draft. Check every statement against your evidence before using it; you remain responsible for the content. Nothing is saved until you save the form."),
    ...rows.map((r) => {
      checks[r.name] = el("input", { type: "checkbox", checked: !r.current });
      return el("div", { class: "ai-row" },
        el("label", { class: "ai-row-head" }, checks[r.name], ` ${r.label}`),
        el("div", { class: "ai-cols" },
          el("div", null, el("div", { class: "muted small" }, "Current"), el("div", { class: "ai-text" }, r.current || el("span", { class: "muted" }, "(empty)"))),
          el("div", null, el("div", { class: "muted small" }, "AI draft"), el("div", { class: "ai-text ai-draft" }, r.draft))));
    }));
  const m = modal({ drawer: true, title, body, width: 900,
    footer: el("div", { class: "form-foot-wrap" },
      el("button", { class: "btn secondary", type: "button", onclick: () => m.close() }, "Discard"),
      el("button", { class: "btn", type: "button", onclick: () => {
        const chosen = rows.filter((r) => checks[r.name].checked);
        onAccept(chosen);
        m.close();
        toast(chosen.length ? "Draft copied into the form - review and save" : "Nothing copied");
      } }, "Use ticked drafts")) });
}

const AI_FINDING_LABELS = { condition: "Condition", criteria: "Criteria", cause: "Cause", effect: "Effect", recommendation: "Recommendation" };

function aiFindingAction(findingId, getHandle, fields) {
  return aiButton("Draft with AI", async () => {
    const handle = getHandle();
    const v = handle.values ? handle.values() : {};
    const notes = [v.description, v.condition].filter(Boolean).join("\n");
    const out = await API.post(`/api/ai/findings/${findingId}/draft`, { notes });
    aiReview("AI draft of the finding (5C)", Object.entries(AI_FINDING_LABELS).map(([name, label]) => ({ name, label, current: v[name] || "", draft: out.draft[name] || "" })),
      (chosen) => chosen.forEach((r) => _fillField(handle, fields, r.name, r.draft)));
  });
}

function aiSummaryAction(reportId, getHandle, fields) {
  return aiButton("Draft summary with AI", async () => {
    const handle = getHandle();
    const v = handle.values ? handle.values() : {};
    const out = await API.post(`/api/ai/reports/${reportId}/executive-summary`);
    aiReview("AI draft of the executive summary", [{ name: "executive_summary", label: "Executive summary", current: v.executive_summary || "", draft: out.draft.executive_summary }],
      (chosen) => chosen.forEach((r) => _fillField(handle, fields, r.name, r.draft)));
  });
}

function aiRiskAction(o, reload) {
  return aiButton("Suggest risks", async () => {
    const out = await API.post(`/api/ai/objectives/${o.id}/risks`);
    const checks = [];
    const body = el("div", null,
      el("div", { class: "callout" }, el("i", { class: "bi bi-info-circle" }),
        " AI suggestions. Tick the risks that apply to this objective; they are added with their controls and you can edit them afterwards."),
      ...out.draft.risks.map((r) => {
        const c = el("input", { type: "checkbox" });
        checks.push([c, r]);
        return el("div", { class: "ai-row" },
          el("label", { class: "ai-row-head" }, c, ` ${r.risk} `, el("span", { class: "muted small" }, `(L${r.likelihood} × I${r.impact})`)),
          r.description ? el("div", { class: "muted small" }, r.description) : null,
          r.controls.length ? el("ul", { class: "small" }, ...r.controls.map((x) => el("li", null, x))) : null);
      }));
    const m = modal({ drawer: true, title: `AI suggestions for ${o.ref}`, body, width: 760,
      footer: el("div", { class: "form-foot-wrap" },
        el("button", { class: "btn secondary", type: "button", onclick: () => m.close() }, "Discard"),
        el("button", { class: "btn", type: "button", onclick: async () => {
          const chosen = checks.filter(([c]) => c.checked).map(([, r]) => r);
          try {
            for (const r of chosen) {
              const risk = await API.post(`/api/objectives/${o.id}/risks`, { title: r.risk, likelihood: r.likelihood, impact: r.impact, description: r.description || "" });
              for (const c of r.controls) {
                await API.post(`/api/objectives/${o.id}/controls`, { title: c, control_type: "Preventive", nature: "Manual", frequency: "Monthly", is_key: false, description: "", owner_email: null, risk_ids: [risk.id] });
              }
            }
            m.close();
            toast(chosen.length ? `${chosen.length} risk(s) added - review type, nature and frequency of the controls` : "Nothing added");
            reload();
          } catch (err) { toast(err.message, "error"); }
        } }, "Add ticked risks")) });
  });
}
