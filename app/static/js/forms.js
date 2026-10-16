// GPHA Audit Workspace - data-entry framework.
//
// Every form built with `openForm` / `mountForm`:
//   * autosaves what the user types as a DRAFT - immediately on this device
//     (localStorage) and, a moment later, on the server (/api/drafts), so
//     nothing is lost on validation errors, network/database problems, closed
//     tabs or a different computer;
//   * restores the draft next time the same form is opened (with "Discard");
//   * validates fields as the user types and before submitting (required,
//     length, numbers, e-mail, patterns, cross-field rules) and shows the
//     problem under the field;
//   * maps server validation errors (HTTP 422 `errors[]`) onto the same fields;
//   * offers "Save draft" at any time, and keeps the draft whenever submitting
//     fails - only a successful save removes it.
// Password fields are never written to drafts.
//
// Loaded after api.js and before planning.js/app.js. Uses el/modal/toast
// helpers from app.js at call time.

const EMAIL_RE = /^[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$/;
const SERVER_SAVE_DELAY = 1200;

// ------------------------------------------------------------------ draft store

const Drafts = {
  _prefix() {
    const uid = typeof state !== "undefined" && state.user ? state.user.id : "anon";
    return `gpha.draft.${uid}.`;
  },
  _localKey(key) { return this._prefix() + key; },
  readLocal(key) {
    try { return JSON.parse(localStorage.getItem(this._localKey(key)) || "null"); } catch { return null; }
  },
  writeLocal(key, record) {
    try { localStorage.setItem(this._localKey(key), JSON.stringify(record)); return true; } catch { return false; }
  },
  removeLocal(key) { try { localStorage.removeItem(this._localKey(key)); } catch { /* ignore */ } },
  listLocal() {
    const out = [];
    try {
      const prefix = this._prefix();
      for (let i = 0; i < localStorage.length; i += 1) {
        const k = localStorage.key(i);
        if (k && k.startsWith(prefix)) {
          const rec = JSON.parse(localStorage.getItem(k) || "null");
          if (rec) out.push({ form_key: k.slice(prefix.length), ...rec });
        }
      }
    } catch { /* storage unavailable */ }
    return out;
  },
  // Newest of the device copy and the server copy.
  async load(key) {
    const local = this.readLocal(key);
    let server = null;
    try { server = await API.get(`/api/drafts/${encodeURIComponent(key)}`); } catch { server = null; }
    if (server) server = { payload: server.payload, updated_at: server.updated_at.endsWith("Z") ? server.updated_at : `${server.updated_at}Z`, meta: server, synced: true };
    if (local && (!server || new Date(local.updated_at) > new Date(server.updated_at))) return { ...local, source: "device" };
    if (server) return { ...server, source: "server" };
    return null;
  },
  async pushServer(key, meta, payload) {
    await API.put(`/api/drafts/${encodeURIComponent(key)}`, {
      title: (meta.title || "").slice(0, 255), record_type: meta.record_type || null,
      record_id: meta.record_id ?? null, payload,
    });
  },
  async discard(key) {
    this.removeLocal(key);
    try { await API.del(`/api/drafts/${encodeURIComponent(key)}`); } catch { /* offline: local copy already gone */ }
  },
};

// ------------------------------------------------------------------ field widgets

function _options(f) {
  return (f.options || []).map((o) => (typeof o === "object" ? o : { value: o, label: String(o) }));
}

function _makeInput(f) {
  const attrs = { name: f.name, id: `ff-${f.name}-${Math.random().toString(36).slice(2, 7)}` };
  if (f.placeholder) attrs.placeholder = f.placeholder;
  if (f.disabled) attrs.disabled = "1";
  let node;
  switch (f.type) {
    case "textarea":
      node = el("textarea", { ...attrs, rows: f.rows || 3 });
      break;
    case "select":
      node = el("select", attrs,
        ...(f.required ? [] : [el("option", { value: "" }, f.emptyLabel || "- none -")]),
        ..._options(f).map((o) => el("option", { value: String(o.value) }, o.label)));
      break;
    case "checkbox":
      node = el("input", { ...attrs, type: "checkbox" });
      break;
    case "checklist":
      node = el("div", { class: "checklist", "data-name": f.name },
        ..._options(f).map((o) => el("label", { class: "check" },
          el("input", { type: "checkbox", value: String(o.value), disabled: f.disabled ? "1" : null }), ` ${o.label}`)));
      if (!_options(f).length) node.append(el("span", { class: "muted" }, f.emptyLabel || "Nothing to choose yet."));
      break;
    case "whys":
      node = el("div", { class: "whys", "data-name": f.name },
        ...[1, 2, 3, 4, 5].map((i) => el("input", { placeholder: `Why ${i}?`, maxlength: "1000", disabled: f.disabled ? "1" : null })));
      break;
    default:
      node = el("input", { ...attrs, type: f.type === "email" ? "email" : f.type || "text" });
      if (f.type === "number") {
        if (f.min !== undefined) node.min = f.min;
        if (f.max !== undefined) node.max = f.max;
        node.step = f.step || "1";
      }
      if (f.maxLength) node.maxLength = f.maxLength;
  }
  return node;
}

function _getValue(f, node) {
  switch (f.type) {
    case "checkbox": return node.checked;
    case "checklist": return [...node.querySelectorAll("input:checked")].map((b) => (/^\d+$/.test(b.value) ? Number(b.value) : b.value));
    case "whys": return [...node.querySelectorAll("input")].map((i) => i.value.trim()).filter(Boolean);
    case "number": return node.value === "" ? null : Number(node.value);
    case "select": {
      if (node.value === "") return null;
      const opt = _options(f).find((o) => String(o.value) === node.value);
      return opt ? opt.value : node.value;
    }
    case "textarea": return node.value;
    default: return node.value.trim() === "" ? (f.type === "date" ? null : "") : node.value.trim();
  }
}

function _rawValue(f, node) {
  // What goes into a draft: exactly what the user typed (no trimming/coercion).
  switch (f.type) {
    case "checkbox": return node.checked;
    case "checklist": return [...node.querySelectorAll("input:checked")].map((b) => b.value);
    case "whys": return [...node.querySelectorAll("input")].map((i) => i.value);
    default: return node.value;
  }
}

function _setValue(f, node, value) {
  if (value === undefined) return;
  switch (f.type) {
    case "checkbox": node.checked = !!value; break;
    case "checklist": {
      const wanted = new Set((value || []).map(String));
      node.querySelectorAll("input").forEach((b) => { b.checked = wanted.has(b.value); });
      break;
    }
    case "whys": {
      const items = Array.isArray(value) ? value : [];
      node.querySelectorAll("input").forEach((i, idx) => { i.value = items[idx] || ""; });
      break;
    }
    case "date": node.value = value ? String(value).slice(0, 10) : ""; break;
    default: node.value = value === null || value === undefined ? "" : String(value);
  }
}

// ------------------------------------------------------------------ validation

function _validateField(f, value) {
  const empty = value === null || value === "" || (Array.isArray(value) && !value.length);
  if (f.required && empty) return `${f.label} is required`;
  if (empty) return null;
  if (typeof value === "string") {
    if (f.maxLength && value.length > f.maxLength) return `${f.label} must be at most ${f.maxLength} characters`;
    if (f.minLength && value.length < f.minLength) return `${f.label} must be at least ${f.minLength} characters`;
    if (f.singleLine && /[\r\n]/.test(value)) return `${f.label} must be a single line`;
  }
  if (f.type === "email" && !EMAIL_RE.test(value)) return `${f.label} must be a valid e-mail address (e.g. name@gpha.gov.gh)`;
  if (f.type === "number") {
    if (Number.isNaN(value)) return `${f.label} must be a number`;
    if ((f.step || "1") === "1" && !Number.isInteger(value)) return `${f.label} must be a whole number`;
    if (f.min !== undefined && value < f.min) return `${f.label} must be at least ${f.min}`;
    if (f.max !== undefined && value > f.max) return `${f.label} must be at most ${f.max}`;
  }
  if (f.type === "date") {
    const d = new Date(`${value}T00:00:00`);
    if (Number.isNaN(d.getTime())) return `${f.label} must be a valid date`;
    if (f.notPast) {
      const today = new Date(); today.setHours(0, 0, 0, 0);
      if (d < today) return `${f.label} must be today or later`;
    }
    if (f.notFuture) {
      const today = new Date(); today.setHours(0, 0, 0, 0);
      if (d > today) return `${f.label} cannot be in the future`;
    }
  }
  if (f.pattern && !new RegExp(f.pattern).test(value)) return f.patternMessage || `${f.label} has an invalid format`;
  if (f.validate) return f.validate(value) || null;
  return null;
}

// ------------------------------------------------------------------ the form

function mountForm(container, opts) {
  const {
    key, meta = {}, fields, initial = {}, submitLabel = "Save", onSubmit, validate,
    intro, extra, onDone, actions = [], draftable = true, columns = 2,
  } = opts;
  const nodes = {};
  const errs = {};
  const banner = el("div", { class: "form-banner hidden" });
  const statusLine = el("span", { class: "draft-status muted" }, draftable ? "" : "");
  const grid = el("div", { class: `grid cols-${columns} form-fields` });

  fields.forEach((f) => {
    if (f.type === "heading") { grid.append(el("h4", { class: "full" }, f.label)); return; }
    const node = _makeInput(f);
    nodes[f.name] = node;
    const err = el("div", { class: "field-error" });
    errs[f.name] = err;
    const label = el("label", { for: node.id || null }, f.label, f.required ? el("span", { class: "req" }, " *") : null);
    grid.append(el("div", { class: `form-field ${f.full || ["textarea", "checklist", "whys"].includes(f.type) ? "full" : ""}` },
      label, node, f.help ? el("div", { class: "help muted" }, f.help) : null, err));
  });

  // Initial values, then (if any) the saved draft on top.
  fields.forEach((f) => { if (nodes[f.name]) _setValue(f, nodes[f.name], initial[f.name]); });

  const values = () => Object.fromEntries(fields.filter((f) => nodes[f.name]).map((f) => [f.name, _getValue(f, nodes[f.name])]));
  const rawValues = () => Object.fromEntries(fields
    .filter((f) => nodes[f.name] && f.type !== "password" && !f.noDraft)
    .map((f) => [f.name, _rawValue(f, nodes[f.name])]));
  const baseline = JSON.stringify(rawValues());

  function showError(name, message) {
    const node = nodes[name];
    if (!errs[name]) return false;
    errs[name].textContent = message || "";
    if (node) node.classList.toggle("invalid", !!message);
    return true;
  }
  function clearErrors() { Object.keys(errs).forEach((n) => showError(n, "")); }
  function setBanner(text, kind = "info", extraNode = null) {
    banner.className = `form-banner ${kind}`;
    banner.replaceChildren(el("span", null, text), extraNode || "");
    if (!text) banner.classList.add("hidden");
    else if (kind === "error" && banner.scrollIntoView) banner.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function runValidation() {
    clearErrors();
    const v = values();
    const problems = {};
    fields.forEach((f) => {
      if (!nodes[f.name] || f.disabled) return;
      const msg = _validateField(f, v[f.name]);
      if (msg) problems[f.name] = msg;
    });
    if (validate) Object.assign(problems, validate(v) || {});
    Object.entries(problems).forEach(([n, m]) => { if (!showError(n, m)) problems[n] = m; });
    return problems;
  }

  // ---------------- drafts
  let dirty = false;
  let serverTimer = null;
  let saving = Promise.resolve();
  const stamp = () => new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  function saveDraft(now = false) {
    if (!draftable || !key) return Promise.resolve();
    const payload = rawValues();
    const changed = JSON.stringify(payload) !== baseline;
    if (!changed) { Drafts.removeLocal(key); statusLine.textContent = ""; return Promise.resolve(); }
    dirty = true;
    Drafts.writeLocal(key, { payload, updated_at: new Date().toISOString(), meta });
    statusLine.textContent = `Draft saved on this device ${stamp()}`;
    clearTimeout(serverTimer);
    const push = () => {
      saving = Drafts.pushServer(key, meta, payload)
        .then(() => { statusLine.textContent = `Draft saved ${stamp()}`; refreshDraftCount(); })
        .catch(() => { statusLine.textContent = `Draft kept on this device ${stamp()} (server unreachable - it will sync later)`; });
      return saving;
    };
    if (now) return push();
    serverTimer = setTimeout(push, SERVER_SAVE_DELAY);
    return Promise.resolve();
  }

  const onInput = (e) => {
    const name = e.target.name || e.target.closest("[data-name]")?.dataset.name;
    const f = fields.find((x) => x.name === name);
    if (f && errs[name] && errs[name].textContent) showError(name, _validateField(f, _getValue(f, nodes[name])) || "");
    saveDraft();
  };
  grid.addEventListener("input", onInput);
  grid.addEventListener("change", onInput);
  grid.addEventListener("focusout", (e) => {
    const name = e.target.name;
    const f = fields.find((x) => x.name === name);
    // Delay so a click that caused the blur (e.g. on Save) is not lost to the
    // layout shift of a newly shown error message.
    if (f && nodes[name]) {
      setTimeout(() => {
        const msg = _validateField(f, _getValue(f, nodes[name]));
        if (msg) showError(name, msg); // never clears form-level (cross-field) errors
      }, 250);
    }
  });

  async function restoreDraft() {
    if (!draftable || !key) return;
    const draft = await Drafts.load(key);
    // The user started typing before the draft arrived: their input wins.
    if (dirty || JSON.stringify(rawValues()) !== baseline) return;
    if (!draft || !draft.payload) return;
    if (JSON.stringify(draft.payload) === baseline) return;
    fields.forEach((f) => { if (nodes[f.name] && f.type !== "password" && !f.noDraft && f.name in draft.payload) _setValue(f, nodes[f.name], draft.payload[f.name]); });
    dirty = true;
    const when = new Date(draft.updated_at).toLocaleString();
    setBanner(`Restored your unsaved entries from ${when}.`, "info",
      el("button", { class: "btn small secondary", type: "button", onclick: async () => {
        await Drafts.discard(key);
        fields.forEach((f) => { if (nodes[f.name]) _setValue(f, nodes[f.name], initial[f.name] ?? (f.type === "checkbox" ? false : "")); });
        dirty = false; clearErrors(); setBanner(""); statusLine.textContent = "Draft discarded";
      } }, "Discard draft"));
    if (draft.source === "device") saveDraft(true); // sync the device copy to the server
  }

  async function submit(btnNode) {
    const problems = runValidation();
    if (Object.keys(problems).length) {
      await saveDraft(true);
      const loose = Object.entries(problems).filter(([n]) => !nodes[n]).map(([, m]) => m);
      setBanner(`Please correct ${Object.keys(problems).length} field(s) highlighted below. ${loose.join(" ")}${draftable && key ? " Your entries are saved as a draft." : ""}`, "error");
      const first = Object.keys(problems).find((n) => nodes[n]);
      if (first && nodes[first].focus) nodes[first].focus();
      return false;
    }
    if (btnNode) btnNode.disabled = true;
    try {
      const result = await onSubmit(values(), { nodes });
      clearTimeout(serverTimer);
      await saving.catch(() => {});
      if (draftable && key) await Drafts.discard(key);
      dirty = false;
      refreshDraftCount();
      statusLine.textContent = "";
      if (onDone) onDone(result);
      return true;
    } catch (err) {
      await saveDraft(true);
      const fieldErrs = (err && err.errors) || [];
      const unmapped = [];
      fieldErrs.forEach((e) => { if (!showError(e.field, e.message)) unmapped.push(`${e.field}: ${e.message}`); });
      const offline = err && (err.status === 0 || err.status >= 500);
      const msg = fieldErrs.length
        ? `Please correct the highlighted fields. ${unmapped.join("; ")}`
        : (offline ? `The server could not save this right now (${err.message}).` : err.message);
      setBanner(`${msg} Your entries are kept as a draft - nothing is lost; you can retry.`, "error");
      return false;
    } finally {
      if (btnNode) btnNode.disabled = false;
    }
  }

  const submitBtn = el("button", { class: "btn", type: "button" }, submitLabel);
  submitBtn.addEventListener("click", () => submit(submitBtn));
  const draftBtn = draftable && key ? el("button", { class: "btn secondary", type: "button", onclick: async () => {
    await saveDraft(true);
    toast(dirty ? "Draft saved - you can finish it later" : "Nothing to save yet");
  } }, "Save draft") : null;

  const body = el("div", { class: "form-body" }, intro ? (intro instanceof Node ? el("div", { class: "form-intro" }, intro) : el("p", { class: "muted" }, intro)) : null, banner, grid, extra || null);
  const footer = el("div", { class: "form-foot" }, statusLine,
    el("div", { class: "actions" }, ...actions, draftBtn, submitBtn));
  container.append(body);

  restoreDraft();
  return {
    body, footer, submit, values, saveDraft, nodes,
    get dirty() { return dirty; },
    flush: () => saveDraft(true),
  };
}

// Modal form.
function openForm(opts) {
  let handle;
  const holder = el("div");
  let instance;
  handle = mountForm(holder, {
    ...opts,
    onDone: (result) => { instance.close(true); if (opts.onDone) opts.onDone(result); },
  });
  instance = modal({
    title: opts.title,
    body: handle.body,
    footer: el("div", { class: "form-foot-wrap" },
      el("button", { class: "btn secondary", type: "button", onclick: () => instance.close() }, "Close"), handle.footer),
    width: opts.width || 760,
    onClose: (submitted) => {
      if (!submitted && handle.dirty) {
        handle.flush();
        toast("Draft kept - reopen this form to continue where you left off");
      }
    },
  });
  return handle;
}

// Inline (card) form - e.g. the profile page.
function inlineForm(card, opts) {
  const handle = mountForm(card, opts);
  card.append(handle.footer);
  return handle;
}

// ------------------------------------------------------------------ resume registry + My Drafts

const FormOpeners = {};
function registerFormOpener(prefix, fn) { FormOpeners[prefix] = fn; }

async function renderDrafts() {
  clear(viewRoot);
  const msg = el("div");
  viewRoot.append(viewHeader("My drafts"), msg,
    el("p", { class: "muted" }, "Everything you type into a form is saved here automatically until you submit it. Open a draft to continue, or discard it."));
  let server = [];
  try { server = await API.get("/api/drafts"); } catch (err) { notify(msg, `Server drafts unavailable: ${err.message}. Showing drafts on this device.`, "error"); }
  const byKey = new Map(server.map((d) => [d.form_key, { ...d, where: "server" }]));
  Drafts.listLocal().forEach((d) => {
    const s = byKey.get(d.form_key);
    if (!s) byKey.set(d.form_key, { form_key: d.form_key, title: d.meta?.title || d.form_key, record_type: d.meta?.record_type, record_id: d.meta?.record_id, updated_at: d.updated_at, where: "this device only" });
  });
  refreshDraftCount();
  const items = [...byKey.values()].sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));
  const card = el("div", { class: "card" });
  if (!items.length) card.append(el("div", { class: "empty" }, "No drafts - all your entries have been saved."));
  else card.append(el("table", null,
    el("thead", null, el("tr", null, el("th", null, "Form"), el("th", null, "Record"), el("th", null, "Last saved"), el("th", null, "Stored"), el("th", null, ""))),
    el("tbody", null, ...items.map((d) => el("tr", { class: "no-click" },
      el("td", null, d.title || d.form_key),
      el("td", { class: "muted" }, d.record_type ? `${d.record_type} #${d.record_id ?? "new"}` : "new record"),
      el("td", { class: "muted" }, fmtDate(d.updated_at && !String(d.updated_at).endsWith("Z") && !String(d.updated_at).includes("+") ? `${d.updated_at}Z` : d.updated_at)),
      el("td", { class: "muted" }, d.where),
      el("td", null, el("div", { class: "actions" },
        btnResume(d),
        el("button", { class: "btn small secondary", onclick: async () => { await Drafts.discard(d.form_key); toast("Draft discarded"); renderDrafts(); } }, "Discard"))))))));
  viewRoot.append(card);
}

function btnResume(d) {
  const prefix = Object.keys(FormOpeners).sort((a, b) => b.length - a.length).find((p) => d.form_key.startsWith(p));
  if (!prefix) return el("span", { class: "muted" }, "-");
  return el("button", { class: "btn small", onclick: () => FormOpeners[prefix](d.form_key, d) }, "Continue");
}

async function refreshDraftCount() {
  const badgeNode = document.querySelector("#draftCount");
  if (!badgeNode) return;
  let n = 0;
  try { n = (await API.get("/api/drafts")).length; } catch { n = 0; }
  const localOnly = Drafts.listLocal().length;
  const total = Math.max(n, localOnly);
  badgeNode.textContent = total ? String(total) : "";
  badgeNode.classList.toggle("hidden", !total);
}

// ------------------------------------------------------------------ health banner

async function checkHealth() {
  const bar = document.querySelector("#healthBar");
  if (!bar) return;
  try {
    const res = await fetch("/health", { credentials: "same-origin" });
    const h = await res.json();
    if (h.can_save) { bar.classList.add("hidden"); return; }
    bar.textContent = `Saving is not possible right now - ${h.database.error || "the database schema is out of date"}. ` +
      "You can keep typing: your entries are kept as drafts on this device and can be submitted once this is fixed.";
    bar.classList.remove("hidden");
  } catch {
    bar.textContent = "The server is not reachable. Your entries are kept as drafts on this device until it is back.";
    bar.classList.remove("hidden");
  }
}
