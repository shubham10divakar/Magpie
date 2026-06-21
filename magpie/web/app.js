"use strict";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let TREE = {};
let CURRENT = null;          // currently open note (full object)
let FILTER = { status: "", category: "", subcategory: "", q: "", due_within: null, all: true };

const $ = (sel) => document.querySelector(sel);
const el = (id) => document.getElementById(id);

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------
async function api(path, opts) {
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}
const qs = (obj) => Object.entries(obj)
  .filter(([, v]) => v !== "" && v !== null && v !== undefined)
  .map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&");

// ---------------------------------------------------------------------------
// Minimal markdown renderer (headings, bold/italic, code, lists, links, [[wiki]])
// ---------------------------------------------------------------------------
function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function renderMarkdown(md) {
  if (!md) return "";
  const lines = escapeHtml(md).split("\n");
  let html = "", inCode = false, inList = false;
  const inline = (t) => t
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/\[\[([^\]]+)\]\]/g, '<span class="wiki">$1</span>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
    .replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank">$1</a>');
  for (let raw of lines) {
    if (raw.trim().startsWith("```")) {
      if (!inCode) { html += "<pre><code>"; inCode = true; }
      else { html += "</code></pre>"; inCode = false; }
      continue;
    }
    if (inCode) { html += raw + "\n"; continue; }
    const h = raw.match(/^(#{1,4})\s+(.*)$/);
    const li = raw.match(/^\s*[-*]\s+(.*)$/);
    if (li) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += "<li>" + inline(li[1]) + "</li>";
      continue;
    }
    if (inList) { html += "</ul>"; inList = false; }
    if (h) { const n = h[1].length; html += `<h${n}>${inline(h[2])}</h${n}>`; }
    else if (raw.trim() === "") { html += "<br/>"; }
    else { html += "<p>" + inline(raw) + "</p>"; }
  }
  if (inList) html += "</ul>";
  if (inCode) html += "</code></pre>";
  return html;
}

// ---------------------------------------------------------------------------
// Sidebar / tree
// ---------------------------------------------------------------------------
async function loadTree() {
  const data = await api("/api/tree");
  TREE = data.tree;
  const sc = data.status_counts;
  el("c-inbox").textContent = sc.inbox || 0;
  el("c-active").textContent = sc.active || 0;
  el("c-someday").textContent = sc.someday || 0;
  el("c-done").textContent = sc.done || 0;
  el("ai-status").textContent = data.ai
    ? "✨ AI suggestions: ON" : "AI suggestions: off (add an API key in config.json)";
  renderTree();
  populateCategorySelect();
  refreshDueCount();
}

function renderTree() {
  const root = el("tree");
  root.innerHTML = "";
  for (const [cat, node] of Object.entries(TREE)) {
    const c = document.createElement("div");
    c.className = "cat" + (FILTER.category === cat && !FILTER.subcategory ? " active" : "");
    c.innerHTML = `<span>${cat}</span><span class="count">${node.count}</span>`;
    c.onclick = () => setFilter({ category: cat, subcategory: "" });
    root.appendChild(c);
    for (const [sub, n] of Object.entries(node.subcategories || {})) {
      const s = document.createElement("div");
      s.className = "sub" + (FILTER.category === cat && FILTER.subcategory === sub ? " active" : "");
      s.innerHTML = `<span>${sub}</span><span class="count">${n}</span>`;
      s.onclick = (e) => { e.stopPropagation(); setFilter({ category: cat, subcategory: sub }); };
      root.appendChild(s);
    }
  }
}

async function refreshDueCount() {
  try {
    const d = await api("/api/due-soon");
    el("c-due").textContent = d.items.length;
  } catch (_) {}
}

// ---------------------------------------------------------------------------
// Filtering + list
// ---------------------------------------------------------------------------
function setFilter(patch) {
  FILTER = { status: "", category: "", subcategory: "", q: FILTER.q, due_within: null, all: false, ...patch };
  document.querySelectorAll(".filter").forEach((f) => f.classList.remove("active"));
  loadNotes();
  renderTree();
}

async function loadNotes() {
  let label = "All notes";
  if (FILTER.due_within !== null) label = "🔔 Due Soon";
  else if (FILTER.status) label = FILTER.status[0].toUpperCase() + FILTER.status.slice(1);
  else if (FILTER.category) label = FILTER.category + (FILTER.subcategory ? " › " + FILTER.subcategory : "");
  if (FILTER.q) label += `  ·  “${FILTER.q}”`;
  el("list-head").textContent = label;

  const data = await api("/api/notes?" + qs({
    status: FILTER.status, category: FILTER.category, subcategory: FILTER.subcategory,
    q: FILTER.q, due_within: FILTER.due_within,
  }));
  renderCards(data.notes);
}

function dueBadge(item) {
  const d = item.due || item.remind;
  if (!d) return "";
  const days = Math.round((new Date(d) - new Date()) / 86400000);
  let cls = "grey";
  if (days < 0) cls = "red";
  else if (days <= 3) cls = "amber";
  else if (days <= 7) cls = "grey";
  else return "";
  const txt = days < 0 ? `overdue ${d}` : `⏰ ${d}`;
  return `<span class="badge ${cls}">${txt}</span>`;
}

function renderCards(notes) {
  const root = el("cards");
  root.innerHTML = "";
  if (!notes.length) { root.innerHTML = '<div class="empty">No notes here yet.</div>'; return; }
  for (const n of notes) {
    const card = document.createElement("div");
    card.className = "card" + (CURRENT && CURRENT.path === n.path ? " active" : "");
    const tags = (n.tags || []).map((t) => `<span class="tag">#${t}</span>`).join(" ");
    card.innerHTML = `
      <div class="card-title">${n.title}</div>
      <div class="card-meta">
        <span class="chip">${n.category || "Inbox"}${n.subcategory ? " › " + n.subcategory : ""}</span>
        <span class="status-dot">● ${n.status}</span>
        ${dueBadge(n)} ${tags}
      </div>`;
    card.onclick = () => openNote(n.path);
    root.appendChild(card);
  }
}

// ---------------------------------------------------------------------------
// Editor
// ---------------------------------------------------------------------------
function populateCategorySelect(selected) {
  const sel = el("e-category");
  sel.innerHTML = "";
  const cats = Object.keys(TREE);
  if (!cats.includes("Inbox")) cats.unshift("Inbox");
  for (const c of cats) {
    const o = document.createElement("option");
    o.value = c; o.textContent = c;
    if (c === selected) o.selected = true;
    sel.appendChild(o);
  }
  populateSubSelect();
}
function populateSubSelect(selected) {
  const cat = el("e-category").value;
  const sel = el("e-subcategory");
  sel.innerHTML = '<option value="">(none)</option>';
  const subs = (TREE[cat] && TREE[cat].subcategories) ? Object.keys(TREE[cat].subcategories) : [];
  for (const s of subs) {
    const o = document.createElement("option");
    o.value = s; o.textContent = s;
    if (s === selected) o.selected = true;
    sel.appendChild(o);
  }
}

async function openNote(path) {
  const data = await api("/api/note?" + qs({ path }));
  CURRENT = data.note;
  showEditor(CURRENT);
  loadNotes(); // refresh active highlight
}

function showEditor(n) {
  el("editor-empty").classList.add("hidden");
  el("editor-body").classList.remove("hidden");
  el("e-title").value = n.title || "";
  el("e-type").value = n.type || "idea";
  el("e-status").value = n.status || "inbox";
  populateCategorySelect(n.category || "Inbox");
  populateSubSelect(n.subcategory || "");
  el("e-due").value = n.due || "";
  el("e-remind").value = n.remind || "";
  el("e-tags").value = (n.tags || []).join(", ");
  el("e-links").value = (n.links || []).join("\n");
  el("e-body").value = n.body || "";
  el("ai-note").textContent = n.ai_summary ? "AI: " + n.ai_summary : "";
  el("save-note").textContent = "";
  updatePreview();
}

function updatePreview() { el("preview").innerHTML = renderMarkdown(el("e-body").value); }

function collectMeta() {
  return {
    type: el("e-type").value,
    status: el("e-status").value,
    tags: el("e-tags").value.split(",").map((t) => t.trim()).filter(Boolean),
    due: el("e-due").value || null,
    remind: el("e-remind").value || null,
    links: el("e-links").value.split("\n").map((l) => l.trim()).filter(Boolean),
    title: el("e-title").value || "Untitled",
    ai_summary: el("ai-note").dataset.summary || (CURRENT && CURRENT.ai_summary) || "",
  };
}

async function saveNote() {
  if (!CURRENT) return;
  const meta = collectMeta();
  const body = el("e-body").value;
  const wantCat = el("e-category").value;
  const wantSub = el("e-subcategory").value;
  // Save fields first
  await api("/api/note?" + qs({ path: CURRENT.path }), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ meta, body }),
  });
  // Move if category/subcategory changed
  if (wantCat !== CURRENT.category || wantSub !== (CURRENT.subcategory || "")) {
    const moved = await api("/api/note/move?" + qs({ path: CURRENT.path }), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category: wantCat, subcategory: wantSub }),
    });
    CURRENT.path = moved.path;
  }
  el("save-note").textContent = "Saved ✓";
  await loadTree();
  await openNote(CURRENT.path);
}

async function archiveNote() {
  if (!CURRENT) return;
  if (!confirm("Archive this note?")) return;
  await api("/api/note?" + qs({ path: CURRENT.path }), { method: "DELETE" });
  CURRENT = null;
  el("editor-body").classList.add("hidden");
  el("editor-empty").classList.remove("hidden");
  await loadTree();
  loadNotes();
}

async function newNote() {
  const cat = FILTER.category || "Inbox";
  const data = await api("/api/notes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: "Untitled idea", category: cat, subcategory: FILTER.subcategory || "", body: "" }),
  });
  await loadTree();
  await openNote(data.path);
  el("e-title").focus();
  el("e-title").select();
}

async function aiSuggest() {
  if (!CURRENT) return;
  el("ai-note").textContent = "Thinking…";
  try {
    const data = await api("/api/note/ai-enrich?" + qs({ path: CURRENT.path }), { method: "POST" });
    if (!data.suggestion) { el("ai-note").textContent = "AI unavailable (check API key)."; return; }
    applySuggestion(data.suggestion);
    el("ai-note").textContent = "AI suggestion applied — review & save.";
  } catch (e) { el("ai-note").textContent = "AI error: " + e.message; }
}

function applySuggestion(s) {
  if (s.title) el("e-title").value = s.title;
  if (s.type) el("e-type").value = s.type;
  if (s.tags && s.tags.length) el("e-tags").value = s.tags.join(", ");
  if (s.category) {
    if (![...el("e-category").options].some((o) => o.value === s.category)) {
      const o = document.createElement("option"); o.value = o.textContent = s.category; el("e-category").appendChild(o);
    }
    el("e-category").value = s.category;
    populateSubSelect(s.subcategory || "");
  }
  if (s.subcategory && ![...el("e-subcategory").options].some((o) => o.value === s.subcategory)) {
    const o = document.createElement("option"); o.value = o.textContent = s.subcategory; el("e-subcategory").appendChild(o);
    el("e-subcategory").value = s.subcategory;
  }
  if (s.summary) el("ai-note").dataset.summary = s.summary;
}

// ---------------------------------------------------------------------------
// Capture
// ---------------------------------------------------------------------------
function openCapture() { el("capture-modal").classList.remove("hidden"); el("capture-url").focus(); }
function closeCapture() { el("capture-modal").classList.add("hidden"); el("capture-url").value = ""; el("capture-status").textContent = ""; }

async function doCapture() {
  const url = el("capture-url").value.trim();
  if (!url) return;
  el("capture-status").textContent = "Fetching…";
  try {
    const data = await api("/api/capture", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, enrich: true }),
    });
    const f = data.fields, s = data.suggestion || {};
    const created = await api("/api/notes", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: s.title || f.title, category: s.category || "Inbox", subcategory: s.subcategory || "",
        type: s.type || f.type, tags: s.tags || f.tags, links: f.links, source: f.source,
        ai_summary: s.summary || "", body: f.body,
      }),
    });
    el("capture-status").textContent = "Saved to Inbox ✓";
    await loadTree();
    setTimeout(() => { closeCapture(); openNote(created.path); }, 500);
  } catch (e) { el("capture-status").textContent = "Error: " + e.message; }
}

// ---------------------------------------------------------------------------
// Wiring
// ---------------------------------------------------------------------------
function wire() {
  document.querySelectorAll(".filter").forEach((f) => {
    f.onclick = () => {
      document.querySelectorAll(".filter").forEach((x) => x.classList.remove("active"));
      f.classList.add("active");
      if (f.dataset.status) FILTER = { status: f.dataset.status, category: "", subcategory: "", q: FILTER.q, due_within: null, all: false };
      else if (f.dataset.due) FILTER = { status: "", category: "", subcategory: "", q: FILTER.q, due_within: parseInt(f.dataset.due), all: false };
      else FILTER = { status: "", category: "", subcategory: "", q: FILTER.q, due_within: null, all: true };
      renderTree();
      loadNotes();
    };
  });
  el("search").oninput = debounce(() => { FILTER.q = el("search").value.trim(); loadNotes(); }, 250);
  el("btn-new").onclick = newNote;
  el("btn-refresh").onclick = () => { loadTree(); loadNotes(); };
  el("btn-capture").onclick = openCapture;
  el("capture-go").onclick = doCapture;
  el("capture-cancel").onclick = closeCapture;
  el("e-category").onchange = () => populateSubSelect();
  el("e-body").oninput = updatePreview;
  el("btn-save").onclick = saveNote;
  el("btn-archive").onclick = archiveNote;
  el("btn-ai").onclick = aiSuggest;
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); saveNote(); }
  });
}
function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

// ---------------------------------------------------------------------------
window.addEventListener("DOMContentLoaded", async () => {
  wire();
  await loadTree();
  await loadNotes();
});
