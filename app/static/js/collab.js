// Collaboration on records: the "Came from / Feeds into" strip (the record's place in the data flow of the
// assurance cycle) and the comments panel with @mentions. Mentioned people are notified and see the comment in
// Projects until they reply on the record or mark it done.

const COLLAB_OPENABLE = new Set(["audit", "finding", "capa", "assurance_plan", "audit_report", "erm_risk", "entity_unit", "risk_assessment"]);

function openLineageNode(n) {
  if (n.tab && n.audit_id) return openAudit(n.audit_id, n.tab);
  if (COLLAB_OPENABLE.has(n.type)) return openLink(n.type, n.id);
  return null;
}

function lineageChip(n) {
  const clickable = (n.tab && n.audit_id) || COLLAB_OPENABLE.has(n.type);
  const inner = [el("span", { class: "ln-kind" }, n.kind), el("span", { class: "ln-ref" }, n.ref),
    el("span", { class: "ln-title" }, clip(n.title || "", 48)), n.status ? el("span", { class: "ln-status" }, n.status) : null,
    n.note ? el("span", { class: "ln-note" }, n.note) : null];
  return clickable
    ? el("button", { class: "ln-chip", type: "button", title: `${n.kind} ${n.ref}: ${n.title}`, onclick: () => openLineageNode(n) }, ...inner)
    : el("span", { class: "ln-chip static", title: `${n.kind} ${n.ref}: ${n.title}` }, ...inner);
}

// The strip under a record's header. Empty sides say so, so a missing link is visible too.
function lineageStrip(d) {
  const side = (label, icon, nodes, empty) => el("div", { class: "ln-side" },
    el("span", { class: "ln-label" }, el("i", { class: `bi bi-${icon}`, "aria-hidden": "true" }), ` ${label}`),
    nodes.length ? el("div", { class: "ln-chips" }, ...nodes.slice(0, 12).map(lineageChip),
      nodes.length > 12 ? el("span", { class: "muted small" }, `+${nodes.length - 12} more`) : null)
      : el("span", { class: "muted small" }, empty));
  return el("div", { class: "lineage", "aria-label": "Data flow" },
    side("Came from", "box-arrow-in-right", d.came_from, "Nothing upstream"),
    side("Feeds into", "box-arrow-right", d.feeds_into, "Nothing downstream yet"));
}

// Wire a record page: strip + "Comments (n)" link. Returns a function that reloads both.
function attachCollab(layout, record) {
  const host = el("div", { class: "lineage-host" });
  const band = layout.root.querySelector(".rec-grid");
  if (band) band.before(host);
  const util = layout.root.querySelector(".rec-util");
  const btn = el("button", { class: "link-btn", type: "button", onclick: () => openComments(record.type, record.id, load) },
    el("i", { class: "bi bi-chat-left-text", "aria-hidden": "true" }), " Comments", el("span", { class: "count-pill hidden" }, ""));
  if (util) util.prepend(btn);
  async function load() {
    let d;
    try { d = await API.get(`/api/records/${record.type}/${record.id}/collab`); } catch { host.remove(); btn.remove(); return null; }
    clear(host);
    host.append(lineageStrip(d));
    const n = d.comments.filter((c) => !c.withdrawn).length;
    const pill = btn.querySelector(".count-pill");
    pill.textContent = String(n);
    pill.classList.toggle("hidden", !n);
    return d;
  }
  load();
  return load;
}

// Comments panel: the thread, then the composer with @mentions of people who can open the record.
async function openComments(type, id, onChange = null) {
  const body = el("div", { class: "cm-panel" }, loadingState());
  const panel = detailPanel({ title: "Comments", body, width: 520 });
  let d;
  try { d = await API.get(`/api/records/${type}/${id}/collab`); } catch (err) { clear(body); body.append(errorState(err)); return panel; }
  const thread = el("div", { class: "cm-thread", "aria-live": "polite" });
  const paint = (comments) => {
    clear(thread);
    if (!comments.length) { thread.append(el("p", { class: "muted" }, "No comments yet. Use @ to bring someone in.")); return; }
    comments.forEach((c) => thread.append(el("div", { class: `cm ${c.author_id === state.user.id ? "mine" : ""}` },
      el("div", { class: "cm-head" }, el("strong", null, c.author), el("span", { class: "muted small" }, fmtDate(c.created_at)),
        c.can_withdraw ? el("button", { class: "linkish small", type: "button", onclick: async () => {
          try { const r = await API.post(`/api/comments/${c.id}/withdraw`); paint(r.comments); if (onChange) onChange(); } catch (err) { toast(err.message, "error"); }
        } }, "Withdraw") : null),
      c.withdrawn ? el("p", { class: "muted small" }, "Comment withdrawn by its author.") : el("p", { class: "cm-body" }, ...highlightMentions(c.body)),
      c.mentions.length ? el("div", { class: "muted small" }, "Mentioned: ", c.mentions.map((m) => `${m.name}${m.done ? " ✓" : ""}`).join(", ")) : null,
      c.my_open_mention ? el("button", { class: "btn small secondary", type: "button", onclick: async () => {
        try { await API.post(`/api/mentions/${c.my_open_mention}/done`); toast("Marked as done"); c.my_open_mention = null; paint(comments); refreshMyWorkCount(); } catch (err) { toast(err.message, "error"); }
      } }, "Mark as done") : null)));
    thread.scrollTop = thread.scrollHeight;
  };
  paint(d.comments);
  const box = el("textarea", { class: "cm-input", rows: "3", maxlength: "5000", placeholder: "Write a comment. Type @ to mention someone.", "aria-label": "Comment" });
  const picks = el("div", { class: "cm-picks hidden", role: "listbox", "aria-label": "People" });
  const chosen = new Map();  // name -> id
  const people = d.mentionable.filter((p) => p.id !== state.user.id);
  const query = () => { const m = /@([^\s@]{0,40})$/.exec(box.value.slice(0, box.selectionStart)); return m ? m[1].toLowerCase() : null; };
  const showPicks = () => {
    const q = query();
    clear(picks);
    if (q === null) { picks.classList.add("hidden"); return; }
    const hits = people.filter((p) => `${p.name} ${p.username}`.toLowerCase().includes(q)).slice(0, 6);
    if (!hits.length) { picks.classList.add("hidden"); return; }
    hits.forEach((p) => picks.append(el("button", { type: "button", role: "option", onclick: () => {
      const pos = box.selectionStart;
      const before = box.value.slice(0, pos).replace(/@([^\s@]{0,40})$/, `@${p.name} `);
      box.value = before + box.value.slice(pos);
      chosen.set(p.name, p.id);
      picks.classList.add("hidden");
      box.focus(); box.selectionStart = box.selectionEnd = before.length;
    } }, p.name, el("span", { class: "muted small" }, ` ${p.username}`))));
    picks.classList.remove("hidden");
  };
  box.addEventListener("input", showPicks);
  box.addEventListener("keydown", (e) => {
    if (e.key === "Escape") picks.classList.add("hidden");
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); send(); }
  });
  const sendBtn = el("button", { class: "btn", type: "button" }, "Post");
  async function send() {
    const text = box.value.trim();
    if (!text) return;
    const ids = [...chosen.entries()].filter(([n]) => text.includes(`@${n}`)).map(([, i]) => i);
    sendBtn.disabled = true;
    try {
      const r = await API.post(`/api/records/${type}/${id}/comments`, { body: text, mention_ids: ids });
      box.value = ""; chosen.clear(); paint(r.comments);
      if (onChange) onChange();
      refreshMyWorkCount();
    } catch (err) { toast(err.message, "error"); }
    sendBtn.disabled = false;
  }
  sendBtn.addEventListener("click", send);
  clear(body);
  body.append(el("div", { class: "muted small" }, `${d.record.kind} ${d.record.ref} · ${d.record.title}`), thread,
    el("div", { class: "cm-compose" }, el("div", { class: "cm-wrap" }, box, picks), el("div", { class: "actions" }, el("span", { class: "muted small" }, "Ctrl+Enter to post"), sendBtn)));
  box.focus();
  return panel;
}

// Show "@Name" in a comment as a highlighted mention (text only, never HTML).
function highlightMentions(text) {
  const parts = String(text).split(/(@[A-Z][\w.'-]*(?: [A-Z][\w.'-]*)*)/);
  return parts.filter((p) => p !== "").map((p) => (p.startsWith("@") ? el("span", { class: "cm-at" }, p) : p));
}
