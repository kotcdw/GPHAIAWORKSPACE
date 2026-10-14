// Platform map (architecture) and the optional AI Service helpers.

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
  const m = modal({ title, body, width: 900,
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
    const m = modal({ title: `AI suggestions for ${o.ref}`, body, width: 760,
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

// ------------------------------------------------------------------ Platform map
async function renderPlatform() {
  clear(viewRoot);
  const msg = el("div");
  viewRoot.append(viewHeader("Platform map", null, { sub: "How the workspace is built: generated from the running system, so it is always current." }), msg);
  let m;
  try { m = await API.get("/api/platform"); } catch (err) { notify(msg, err.message, "error"); return; }

  const tableChips = (tables) => tables.length
    ? el("div", { class: "pm-tables" }, ...tables.map((t) => el("code", null, t)))
    : el("span", { class: "muted small" }, "no tables of its own");
  const moduleRow = (mod) => el("tr", { class: "no-click" },
    el("td", null, el("strong", null, mod.code), el("div", { class: "muted small" }, mod.summary)),
    el("td", null, tableChips(mod.tables)),
    el("td", { class: "small" }, mod.endpoints.length ? mod.endpoints.map((e) => `/api/${e}`).join(", ") : "-"));
  const layerCard = (layer, icon) => el("div", { class: "card pm-layer" },
    el("div", { class: "card-head" }, el("h3", null, el("i", { class: `bi bi-${icon}` }), ` ${layer.name}`), el("code", { class: "muted" }, layer.package)),
    el("p", { class: "muted" }, layer.description),
    el("table", null, el("thead", null, el("tr", null, el("th", null, "Module"), el("th", null, "Tables it owns"), el("th", null, "API"))),
      el("tbody", null, ...layer.modules.map(moduleRow))));
  const arrow = () => el("div", { class: "pm-arrow" }, el("i", { class: "bi bi-arrow-down" }));

  const ai = m.services.modules.find((x) => x.code === "ai");
  const docs = m.services.modules.find((x) => x.code === "documents");
  const aiState = ai.status.enabled ? (ai.status.ready ? ["Enabled", "ok"] : ["Enabled - not ready", "warn"]) : ["Off", "muted"];

  viewRoot.append(
    el("div", { class: "pm-top" }, el("h3", null, "GPHA INTERNAL AUDIT"), el("span", { class: "muted" }, m.system)),
    arrow(),
    el("div", { class: "card pm-layer" },
      el("div", { class: "card-head" }, el("h3", null, el("i", { class: "bi bi-cpu" }), ` ${m.core.name}`), el("code", { class: "muted" }, m.core.package)),
      el("ul", null, ...m.core.components.map((c) => el("li", null, c))), tableChips(m.core.tables)),
    layerCard(m.platform, "hdd-network"),
    arrow(),
    el("div", { class: "pm-domains" }, ...m.domains.map((d) => layerCard(d, { "Audit Domain Module": "clipboard-check", "Assurance Domain Module": "calendar2-check", "Issues Domain Module": "tools" }[d.name] || "box"))),
    arrow(),
    el("div", { class: "card pm-layer pm-data" },
      el("div", { class: "card-head" }, el("h3", null, el("i", { class: "bi bi-database" }), ` ${m.shared_data.name}`)),
      el("p", null, m.shared_data.description),
      el("p", { class: "muted small" }, `${m.shared_data.engine} · database ${m.shared_data.database || "-"} · ${m.shared_data.tables} tables`)),
    arrow(),
    el("div", { class: "pm-services" },
      el("div", { class: "card pm-layer" },
        el("div", { class: "card-head" }, el("h3", null, el("i", { class: "bi bi-stars" }), " AI Service"), el("span", { class: `chip-mini ${aiState[1]}` }, aiState[0])),
        el("p", { class: "muted" }, ai.summary),
        el("p", { class: "small" }, `Provider: ${ai.status.provider} · model ${ai.status.model}`),
        ...(ai.status.problems || []).map((p) => el("div", { class: "callout warn small" }, p)),
        el("p", { class: "muted small" }, "Turn on and choose the provider under Configuration > AI. The API key stays in the server's GPHA_AI_API_KEY setting.")),
      el("div", { class: "card pm-layer" },
        el("div", { class: "card-head" }, el("h3", null, el("i", { class: "bi bi-graph-up" }), " Analytics Service"), el("span", { class: "chip-mini ok" }, "On")),
        el("p", { class: "muted" }, m.services.modules.find((x) => x.code === "analytics").summary)),
      el("div", { class: "card pm-layer" },
        el("div", { class: "card-head" }, el("h3", null, el("i", { class: "bi bi-file-earmark-word" }), " Documents Service"), el("span", { class: "chip-mini ok" }, "On")),
        el("p", { class: "muted" }, docs.summary),
        el("ul", { class: "small" }, ...docs.status.documents.map((d) => el("li", null, d.name))))));
}
