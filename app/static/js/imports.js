// Data import: one place for every bulk import the user may run (template, check, import), and the history of
// imports carried out and uploads rejected. Each import is checked first and is all-or-nothing on the server.

const IMPORT_ICONS = { users: "people", orgunits: "diagram-3", processes: "diagram-2", universe: "bullseye", remediation: "wrench-adjustable", risks: "shield-exclamation" };

async function renderImports() {
  clear(viewRoot);
  viewRoot.append(viewHeader("Data import"));
  const grid = el("div", { class: "import-grid" }, loadingState());
  const hist = el("div", { class: "card" });
  viewRoot.append(grid, hist);
  let cat;
  try { cat = await API.get("/api/import/catalogue"); } catch (err) { clear(grid); grid.append(errorState(err, renderImports)); return; }
  clear(grid);
  if (!cat.length) grid.append(emptyState({ icon: "upload", title: "No imports available for your role" }));
  cat.forEach((c) => grid.append(el("div", { class: "import-card", title: c.where },
    el("span", { class: "import-ico" }, el("i", { class: `bi bi-${IMPORT_ICONS[c.kind] || "upload"}`, "aria-hidden": "true" })),
    el("div", { class: "import-card-text" }, el("strong", null, c.label),
      el("span", { class: "muted small" }, `${c.columns.filter((x) => x.required).length} required · ${c.columns.length} columns`)),
    el("div", { class: "import-card-actions" },
      el("a", { class: "btn small secondary", href: `/api/import/${c.kind}/template.xlsx`, title: "Download the Excel template" }, el("i", { class: "bi bi-download" }), " Template"),
      el("button", { class: "btn small", type: "button", onclick: () => importDialog({ title: `Import ${c.label.toLowerCase()}`, templateKind: c.kind, path: `/api/import/${c.kind}`,
        intro: c.where, onDone: () => renderImports() }) },
      el("i", { class: "bi bi-upload" }), " Import")))));
  paintImportHistory(hist);
}

async function paintImportHistory(card, outcome = "") {
  clear(card);
  const sel = el("select", { class: "compact", "aria-label": "Result" },
    ...[["", "All results"], ["imported", "Imported"], ["rejected", "Rejected"]].map(([v, l]) => el("option", { value: v, selected: v === outcome ? "1" : null }, l)));
  sel.addEventListener("change", () => paintImportHistory(card, sel.value));
  card.append(el("div", { class: "card-head" }, el("h3", null, "Import history"), sel));
  let d;
  try { d = await API.get(`/api/import/history?limit=200${outcome ? `&outcome=${outcome}` : ""}`); } catch (err) { card.append(errorState(err)); return; }
  if (!d.items.length) { card.append(el("p", { class: "muted" }, "No imports yet.")); return; }
  card.append(el("div", { class: "table-wrap" }, el("table", { class: "compact-table import-history" },
    el("thead", null, el("tr", null, ...["When", "Type", "File", "Result", "Rows", "By"].map((h) => el("th", null, h)))),
    el("tbody", null, ...d.items.map((r) => el("tr", { tabindex: "0", class: r.outcome === "rejected" ? "row-failure" : "", onclick: () => openImportRun(r.id),
      onkeydown: (e) => { if (e.key === "Enter") openImportRun(r.id); } },
    el("td", null, fmtDate(r.at)), el("td", null, r.label, r.context ? el("span", { class: "muted small" }, ` · ${r.context}`) : null),
    el("td", { class: "small" }, r.filename || "-"),
    el("td", null, r.outcome === "imported" ? el("span", { class: "chip-mini ok" }, el("i", { class: "bi bi-check2" }), " Imported") : el("span", { class: "chip-mini warn" }, `Rejected · ${r.problems}`)),
    el("td", { class: "num" }, r.outcome === "imported" ? `${r.created}${r.updated ? ` + ${r.updated} updated` : ""}` : String(r.rows)),
    el("td", null, r.by || "-")))))));
}

async function openImportRun(id) {
  const body = el("div", null, loadingState());
  detailPanel({ title: "Import", body, width: 620 });
  let r;
  try { r = await API.get(`/api/import/history/${id}`); } catch (err) { clear(body); body.append(errorState(err)); return; }
  clear(body);
  body.append(el("dl", { class: "log-facts" },
    ...[["When", fmtDate(r.at)], ["By", r.by || "-"], ["File", r.filename || "-"], ["Result", r.outcome === "imported" ? "Imported" : "Rejected (nothing was written)"],
      ["Rows", String(r.rows)], ...(r.outcome === "imported" ? [["Created", String(r.created)], ["Updated", String(r.updated)]] : [])]
      .map(([k, v]) => el("div", { class: "log-fact" }, el("dt", null, k), el("dd", null, v)))));
  if (r.problems.length) body.append(importProblems(r.problems, r.problem_count, r.filename));
}

// The list of problems found in a file, with a CSV download to fix them in Excel.
function importProblems(problems, total = problems.length, filename = "import") {
  const csv = () => {
    const q = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const text = ["Row,Column,Problem", ...problems.map((p) => [p.row, p.field, p.message].map(q).join(","))].join("\r\n");
    const a = el("a", { href: URL.createObjectURL(new Blob(["﻿" + text], { type: "text/csv" })), download: `${String(filename || "import").replace(/\.xlsx$/i, "")}-problems.csv` });
    document.body.append(a); a.click(); a.remove();
  };
  return el("div", { class: "import-problems" },
    el("div", { class: "card-head" }, el("h4", null, `${total} problem${total === 1 ? "" : "s"}`),
      el("button", { class: "btn small secondary", type: "button", onclick: csv }, el("i", { class: "bi bi-download" }), " Problems (CSV)")),
    el("div", { class: "table-wrap" }, el("table", { class: "compact-table" },
      el("thead", null, el("tr", null, el("th", null, "Row"), el("th", null, "Column"), el("th", null, "Problem"))),
      el("tbody", null, ...problems.slice(0, 200).map((e) => el("tr", { class: "no-click" }, el("td", null, String(e.row)), el("td", null, e.field), el("td", null, e.message)))))),
    total > problems.length ? el("p", { class: "muted small" }, `Showing the first ${problems.length}.`) : null);
}
