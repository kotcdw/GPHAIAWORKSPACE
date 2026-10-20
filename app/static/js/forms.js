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
// Forms open in a right-hand panel (see formPanel below).
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
    intro, extra, onDone, actions = [], draftable = true, columns = 2, keepInTab = false,
  } = opts;
  // Forms without server drafts still keep their entries in this tab while their panel is open (survives a refresh).
  const tabKey = keepInTab && !draftable && key ? `gpha.pv.${typeof state !== "undefined" && state.user ? state.user.id : "anon"}.${key}` : null;
  const tabStore = {
    read() { try { return tabKey ? JSON.parse(sessionStorage.getItem(tabKey) || "null") : null; } catch { return null; } },
    write(v) { try { if (tabKey) sessionStorage.setItem(tabKey, JSON.stringify(v)); } catch { /* storage unavailable */ } },
    clear() { try { if (tabKey) sessionStorage.removeItem(tabKey); } catch { /* storage unavailable */ } },
  };
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
  const kept = tabStore.read();
  if (kept) fields.forEach((f) => { if (nodes[f.name] && f.type !== "password" && !f.noDraft && f.name in kept) _setValue(f, nodes[f.name], kept[f.name]); });

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
  const stamp = () => formatClock(zonedParts(new Date()));

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
    if (tabKey) tabStore.write(rawValues());
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
    const when = fmtDate(draft.updated_at);
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
      tabStore.clear();
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

  let locked = false;
  function lock(text) {
    locked = true;
    clearTimeout(serverTimer);
    grid.querySelectorAll("input, select, textarea, button").forEach((n) => { n.disabled = true; });
    footer.querySelector(".actions")?.classList.add("hidden");
    statusLine.textContent = "";
    setBanner(text, "ok");
  }

  restoreDraft();
  return {
    body, footer, submit, values, saveDraft, nodes, lock, forgetTabCopy: () => tabStore.clear(),
    get dirty() { return dirty; },
    get locked() { return locked; },
    flush: () => saveDraft(true),
  };
}

// ------------------------------------------------------------------ form panels
// Every creator / editor opens as a panel docked at the right of the workspace:
//   * clicking elsewhere in the app or pressing Esc never closes it - only its
//     x / Close buttons do, so a half-filled form is never lost by accident;
//   * the open panels are remembered in this browser tab and reopen (with the
//     typed entries, from the draft) after a page refresh or signing in again;
//   * after a successful save the panel stays open, locked, showing "Saved",
//     until the person closes it.

const FormPanels = [];

const OpenPanels = {
  _key() {
    const uid = typeof state !== "undefined" && state.user ? state.user.id : "anon";
    return `gpha.panels.${uid}`;
  },
  list() {
    try { return JSON.parse(sessionStorage.getItem(this._key()) || "[]"); } catch { return []; }
  },
  _save(list) { try { sessionStorage.setItem(this._key(), JSON.stringify(list)); } catch { /* storage unavailable */ } },
  add(entry) { this._save([...this.list().filter((e) => e.id !== entry.id), entry]); },
  remove(id) { if (id) this._save(this.list().filter((e) => e.id !== id)); },
};

// Calls to the functions that open forms are recorded (name + arguments) so a
// refresh can open the same form again. Callbacks are replaced by "reload the
// page" on restore; calls that receive page elements cannot be replayed.
const _formCalls = [];
function _encodeArgs(args) {
  const out = [];
  for (const a of args) {
    if (typeof a === "function") out.push({ __reload: 1 });
    else if (a === undefined) out.push({ __undef: 1 });
    else if ((typeof Node !== "undefined" && a instanceof Node) || (typeof Event !== "undefined" && a instanceof Event)) return null;
    else out.push(a);
  }
  try { return JSON.parse(JSON.stringify(out)); } catch { return null; }
}
function _decodeArgs(args) {
  return (args || []).map((a) => {
    if (a && typeof a === "object" && !Array.isArray(a)) {
      if (a.__reload) return reloadCurrentPage;
      if (a.__undef) return undefined;
    }
    return a;
  });
}
function reloadCurrentPage() {
  if (!(typeof restoreRoute === "function" && restoreRoute()) && typeof navigate === "function") navigate(state.view);
}

// Wrap every global function that opens a form panel (called once, after all scripts load).
function trackFormOpeners() {
  const skip = new Set(["openForm", "formPanel", "modal", "mountForm", "inlineForm", "trackFormOpeners"]);
  Object.getOwnPropertyNames(window).forEach((name) => {
    if (skip.has(name)) return;
    let fn;
    try { fn = window[name]; } catch { return; }
    if (typeof fn !== "function" || fn.__formTracked) return;
    let src = "";
    try { src = Function.prototype.toString.call(fn); } catch { return; }
    if (!src.includes("openForm(") && !src.includes("drawer: true")) return;
    const tracked = function trackedFormOpener(...args) {
      const call = { name, args };
      _formCalls.push(call);
      const done = () => { const i = _formCalls.indexOf(call); if (i >= 0) _formCalls.splice(i, 1); };
      let res;
      try { res = fn.apply(this, args); } catch (err) { done(); throw err; }
      if (res && typeof res.then === "function") res.then(done, done); else done();
      return res;
    };
    tracked.__formTracked = true;
    try { window[name] = tracked; } catch { /* read-only global */ }
  });
}

function _layoutPanels() {
  const top = FormPanels[FormPanels.length - 1];
  document.body.classList.toggle("has-form-panel", !!top);
  if (top) document.body.style.setProperty("--dock-w", `${top.width}px`);
  else document.body.style.removeProperty("--dock-w");
  FormPanels.forEach((p, i) => p.root.classList.toggle("is-covered", i < FormPanels.length - 1));
}

// A panel docked at the right. Same call shape as modal(); returns { close, root, forget }.
function formPanel({ title, body, footer, width = 760, onClose, persistId = null }) {
  const host = qs("#drawerRoot") || document.body;
  // A form replaces an open (centred) dialog, as before; confirmations opened later stack on top.
  document.querySelectorAll("#modalRoot .modal-backdrop").forEach((n) => n.remove());
  const opener = document.activeElement;
  const titleId = `pnl-${Math.random().toString(36).slice(2, 8)}`;
  const w = Math.max(420, Math.min(Number(width) || 760, 980));
  let closed = false;
  const call = _formCalls[_formCalls.length - 1];
  const id = persistId || title;
  const inst = { width: w, id };
  const close = (submitted = false) => {
    if (closed) return;
    closed = true;
    inst.root.remove();
    const i = FormPanels.indexOf(inst);
    if (i >= 0) FormPanels.splice(i, 1);
    OpenPanels.remove(id);
    _layoutPanels();
    const next = FormPanels[FormPanels.length - 1];
    if (opener && opener.focus && document.contains(opener)) opener.focus({ preventScroll: true });
    else if (next) next.root.focus({ preventScroll: true });
    if (onClose) onClose(submitted === true);
  };
  inst.root = el("section", { class: "modal form-panel", role: "dialog", "aria-labelledby": titleId, tabindex: "-1", style: `--drawer-w:${w}px` },
    el("div", { class: "modal-head" }, el("h3", { id: titleId }, title),
      el("button", { class: "modal-close", type: "button", onclick: () => close(), title: "Close", "aria-label": "Close panel" }, "\u00d7")),
    el("div", { class: "modal-body" }, body),
    footer ? el("div", { class: "modal-foot" }, footer) : null);
  inst.close = close;
  inst.forget = () => OpenPanels.remove(id);
  host.append(inst.root);
  FormPanels.push(inst);
  _layoutPanels();
  const args = call ? _encodeArgs(call.args) : null;
  OpenPanels.add({ id, title, route: window.location.hash, call: call && args ? { name: call.name, args } : null });
  setTimeout(() => {
    const target = inst.root.querySelector(".modal-body input:not([disabled]), .modal-body select:not([disabled]), .modal-body textarea:not([disabled])")
      || inst.root.querySelector(".modal-close");
    if (target) target.focus({ preventScroll: true });
  }, 0);
  return inst;
}

function closeFormPanels() {
  [...FormPanels].reverse().forEach((p) => { p.root.remove(); });
  FormPanels.length = 0;
  _layoutPanels();
}

// The panel holding `node` (or the top one) - for actions inside a form that finish the job another way.
function closeFormPanel(node = null) {
  const p = (node && FormPanels.find((x) => x.root.contains(node))) || FormPanels[FormPanels.length - 1];
  if (p) p.close(true);
}

// After a refresh / sign-in: open again the panels that were open in this tab.
async function restoreFormPanels() {
  const list = OpenPanels.list();
  if (!list.length) return;
  for (const entry of list) {
    if (FormPanels.some((p) => p.id === entry.id)) continue;
    OpenPanels.remove(entry.id);
    try {
      if (entry.call && typeof window[entry.call.name] === "function") {
        await window[entry.call.name](..._decodeArgs(entry.call.args));
      } else {
        const prefix = Object.keys(FormOpeners).sort((a, b) => b.length - a.length).find((p) => entry.id.startsWith(p));
        if (prefix) await FormOpeners[prefix](entry.id, { form_key: entry.id, ...((Drafts.readLocal(entry.id) || {}).meta || {}) });
      }
    } catch { /* the record is gone or no longer allowed: leave it closed */ }
  }
}

// Form in a right-hand panel.
function openForm(opts) {
  const id = opts.key || opts.title;
  const existing = FormPanels.find((p) => p.id === id && p.handle);
  if (existing) { existing.root.focus({ preventScroll: true }); return existing.handle; }
  const holder = el("div");
  let instance;
  const handle = mountForm(holder, {
    ...opts,
    keepInTab: true,
    onDone: (result) => {
      instance.forget();
      handle.lock(`Saved ${formatClock(zonedParts(new Date()))}. Close this panel when you have finished.`);
      if (opts.onDone) opts.onDone(result);
    },
  });
  instance = formPanel({
    title: opts.title,
    body: handle.body,
    footer: el("div", { class: "form-foot-wrap" },
      el("button", { class: "btn secondary", type: "button", onclick: () => instance.close() }, "Close"), handle.footer),
    width: opts.width || 760,
    persistId: id,
    onClose: (submitted) => {
      handle.forgetTabCopy();
      if (!submitted && handle.dirty && !handle.locked) {
        handle.flush();
        toast("Draft kept - reopen this form to continue where you left off");
      }
    },
  });
  instance.handle = handle;
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
  viewRoot.append(viewHeader("My drafts"), msg);
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
