"use strict";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let TREE = {};
let CURRENT = null;
let FILTER = { status: "", category: "", subcategory: "", q: "", due_within: null, all: true };

const $ = (sel) => document.querySelector(sel);
const el = (id) => document.getElementById(id);

const AI_LABELS = {
  claude: "Claude",
  gemini: "Gemini Flash",
  groq: "Groq",
  ollama: "Ollama (local)",
};

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
// Minimal markdown renderer
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
    ? `✨ AI: ${AI_LABELS[data.ai] || data.ai}`
    : "AI: off — click ⚙ AI to configure";
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
  if (FILTER.q) label += `  ·  "${FILTER.q}"`;
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
  const dl = el("cat-list");
  dl.innerHTML = "";
  const cats = ["Inbox", ...Object.keys(TREE).filter((c) => c !== "Inbox")];
  for (const c of cats) {
    const o = document.createElement("option"); o.value = c; dl.appendChild(o);
  }
  if (selected !== undefined) el("e-category").value = selected;
  populateSubSelect();
}
function populateSubSelect(selected) {
  const cat = el("e-category").value;
  const dl = el("sub-list");
  dl.innerHTML = "";
  const subs = (TREE[cat] && TREE[cat].subcategories) ? Object.keys(TREE[cat].subcategories) : [];
  for (const s of subs) {
    const o = document.createElement("option"); o.value = s; dl.appendChild(o);
  }
  if (selected !== undefined) el("e-subcategory").value = selected;
}

async function createCategory() {
  const cat = el("new-cat").value.trim();
  if (!cat) return;
  const sub = el("new-sub").value.trim();
  try {
    await api("/api/category", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category: cat, subcategory: sub }),
    });
    el("new-cat").value = "";
    el("new-sub").value = "";
    el("add-cat-form").classList.add("hidden");
    await loadTree();
  } catch (e) { alert("Error: " + e.message); }
}

async function openNote(path) {
  const data = await api("/api/note?" + qs({ path }));
  CURRENT = data.note;
  showEditor(CURRENT);
  loadNotes();
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
  await api("/api/note?" + qs({ path: CURRENT.path }), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ meta, body }),
  });
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
    if (!data.suggestion) { el("ai-note").textContent = "AI unavailable — open ⚙ AI to configure."; return; }
    applySuggestion(data.suggestion);
    el("ai-note").textContent = "AI suggestion applied — review & save.";
  } catch (e) { el("ai-note").textContent = "AI error: " + e.message; }
}

function applySuggestion(s) {
  if (s.title) el("e-title").value = s.title;
  if (s.type) el("e-type").value = s.type;
  if (s.tags && s.tags.length) el("e-tags").value = s.tags.join(", ");
  if (s.category) { el("e-category").value = s.category; populateSubSelect(s.subcategory || ""); }
  if (s.subcategory) el("e-subcategory").value = s.subcategory;
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
// Feed import
// ---------------------------------------------------------------------------
let FEED_ITEMS = [];

function openFeed() {
  el("feed-modal").classList.remove("hidden");
  el("feed-url").focus();
  el("feed-list").classList.add("hidden");
  el("feed-list").innerHTML = "";
  el("feed-actions").classList.add("hidden");
  el("feed-status").textContent = "";
}

function closeFeed() {
  el("feed-modal").classList.add("hidden");
  el("feed-url").value = "";
  el("feed-status").textContent = "";
  el("feed-list").innerHTML = "";
  el("feed-list").classList.add("hidden");
  el("feed-actions").classList.add("hidden");
  FEED_ITEMS = [];
}

async function doFeedFetch() {
  const url = el("feed-url").value.trim();
  if (!url) return;
  el("feed-status").textContent = "Fetching feed…";
  el("feed-list").classList.add("hidden");
  el("feed-actions").classList.add("hidden");
  try {
    const data = await api("/api/capture/rss", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, limit: 30 }),
    });
    FEED_ITEMS = data.items || [];
    if (!FEED_ITEMS.length) { el("feed-status").textContent = "Feed is empty or unreadable."; return; }
    el("feed-status").textContent = `${FEED_ITEMS.length} item${FEED_ITEMS.length !== 1 ? "s" : ""} found — pick what to import.`;
    renderFeedList();
  } catch (e) { el("feed-status").textContent = "Error: " + e.message; }
}

function renderFeedList() {
  const list = el("feed-list");
  list.innerHTML = "";
  FEED_ITEMS.forEach((item, i) => {
    const row = document.createElement("label");
    row.className = "feed-item";
    const pub = item.published ? `<span class="feed-date">${item.published}</span>` : "";
    const src = item.author ? `<span class="feed-author">${item.author}</span>` : "";
    row.innerHTML = `<input type="checkbox" class="feed-cb" data-idx="${i}" checked />
      <span class="feed-title">${item.title}</span>${src}${pub}`;
    list.appendChild(row);
  });
  list.classList.remove("hidden");
  el("feed-actions").classList.remove("hidden");
}

async function doFeedImport() {
  const checked = [...document.querySelectorAll(".feed-cb:checked")].map((cb) => parseInt(cb.dataset.idx));
  if (!checked.length) { el("feed-status").textContent = "Nothing selected."; return; }
  el("feed-status").textContent = `Saving ${checked.length} item${checked.length !== 1 ? "s" : ""}…`;
  let saved = 0;
  for (const i of checked) {
    const f = FEED_ITEMS[i];
    try {
      await api("/api/notes", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: f.title, category: "Inbox", subcategory: "",
          type: f.type || "link", tags: f.tags || [],
          links: f.links || [], source: f.source, body: f.body || "",
        }),
      });
      saved++;
    } catch (_) {}
  }
  el("feed-status").textContent = `Saved ${saved} note${saved !== 1 ? "s" : ""} to Inbox ✓`;
  await loadTree();
  setTimeout(closeFeed, 1200);
}

// ---------------------------------------------------------------------------
// AI Settings
// ---------------------------------------------------------------------------
async function openSettings() {
  el("settings-modal").classList.remove("hidden");
  await loadAIStatus();
}

function closeSettings() {
  el("settings-modal").classList.add("hidden");
}

async function loadAIStatus() {
  try {
    const data = await api("/api/ai/status");
    // Set provider dropdown
    el("sel-ai-provider").value = data.provider || "auto";
    // Highlight selected card
    document.querySelectorAll(".ai-card").forEach((c) => c.classList.remove("selected"));
    const sel = document.getElementById(`card-${data.provider}`);
    if (sel) sel.classList.add("selected");
    // Fill key inputs (shown as dots but pre-filled)
    el("key-claude").value = data.keys.claude || "";
    el("key-gemini").value = data.keys.gemini || "";
    el("key-groq").value = data.keys.groq || "";
    // Render status for each card
    renderProviderStatus("claude", data.status.claude);
    renderProviderStatus("gemini", data.status.gemini);
    renderProviderStatus("groq", data.status.groq);
    renderOllamaStatus(data.status.ollama, data.keys);
  } catch (e) {
    console.error("Could not load AI status:", e);
  }
}

function renderProviderStatus(name, status) {
  const s = el(`status-${name}`);
  s.innerHTML = status.available
    ? `<span class="ai-ok">✅ ${status.label}</span>`
    : `<span class="ai-off">🔴 ${status.label}</span>`;
}

function renderOllamaStatus(status, keys) {
  const s = el("status-ollama");
  const ctrl = el("ollama-controls");

  s.innerHTML = status.available
    ? `<span class="ai-ok">✅ ${status.label}</span>`
    : `<span class="ai-off">🔴 ${status.label}</span>`;

  if (status.available) {
    // Running with model — show model selector
    const models = status.models || [];
    ctrl.innerHTML = `
      <select class="ai-key-input" id="ollama-model-sel">
        ${models.map((m) => `<option value="${m}">${m}</option>`).join("")}
      </select>`;
    const sel = el("ollama-model-sel");
    if (keys.ollama_model && models.includes(keys.ollama_model)) sel.value = keys.ollama_model;
  } else if (status.running) {
    // Ollama running but no model pulled yet
    ctrl.innerHTML = `
      <input class="ai-key-input" id="ollama-model-inp" value="${keys.ollama_model || 'llama3.2:3b'}" />
      <button class="primary" style="margin-top:6px;width:100%" onclick="startModelPull()">Download model</button>
      <div class="ollama-progress hidden" id="ollama-progress">
        <div class="progress-bar"><div class="progress-fill" id="ollama-pfill"></div></div>
        <div class="progress-msg" id="ollama-pmsg"></div>
      </div>`;
  } else {
    // Ollama not installed/running
    ctrl.innerHTML = `
      <button class="primary" style="margin-top:6px;width:100%" onclick="startOllamaInstall()">Install Ollama + download model</button>
      <div class="ollama-progress hidden" id="ollama-progress">
        <div class="progress-bar"><div class="progress-fill" id="ollama-pfill"></div></div>
        <div class="progress-msg" id="ollama-pmsg"></div>
      </div>`;
  }
}

function selectAIProvider(name) {
  document.querySelectorAll(".ai-card").forEach((c) => c.classList.remove("selected"));
  const card = el(`card-${name}`);
  if (card) card.classList.add("selected");
  el("sel-ai-provider").value = name;
}

async function saveAISettings() {
  const ollamaModelSel = el("ollama-model-sel");
  const ollamaModelInp = el("ollama-model-inp");
  const ollamaModel = ollamaModelSel
    ? ollamaModelSel.value
    : (ollamaModelInp ? ollamaModelInp.value.trim() : "");

  const cfg = {
    ai_provider: el("sel-ai-provider").value,
    anthropic_api_key: el("key-claude").value.trim(),
    gemini_api_key: el("key-gemini").value.trim(),
    groq_api_key: el("key-groq").value.trim(),
  };
  if (ollamaModel) cfg.ollama_model = ollamaModel;

  try {
    await api("/api/ai/config", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cfg),
    });
    await loadTree();          // refresh sidebar AI label
    await loadAIStatus();      // refresh card statuses
  } catch (e) { alert("Error saving: " + e.message); }
}

// Ollama install (download + silent installer + model pull) via SSE
function startOllamaInstall() {
  const progress = el("ollama-progress");
  const fill = el("ollama-pfill");
  const msg = el("ollama-pmsg");
  if (!progress) return;
  progress.classList.remove("hidden");

  const es = new EventSource("/api/setup/ollama/install");
  es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.stage === "download") {
      fill.style.width = (data.pct || 0) + "%";
      msg.textContent = data.msg || `Downloading… ${data.pct || 0}%`;
    } else if (data.stage === "install") {
      fill.style.width = "70%";
      msg.textContent = data.msg || "Installing…";
      if (data.done) {
        es.close();
        // Ollama is running — now pull the model
        startModelPull();
      }
    } else if (data.stage === "error") {
      es.close();
      fill.style.background = "var(--red)";
      msg.textContent = "Error: " + data.msg;
    }
  };
  es.onerror = () => { es.close(); if (msg) msg.textContent = "Connection lost — check console."; };
}

function startModelPull() {
  const progress = el("ollama-progress");
  const fill = el("ollama-pfill");
  const msg = el("ollama-pmsg");
  if (!progress) return;
  progress.classList.remove("hidden");

  const modelInp = el("ollama-model-inp");
  const model = modelInp ? modelInp.value.trim() || "llama3.2:3b" : "llama3.2:3b";
  fill.style.width = "0%";
  fill.style.background = "";
  msg.textContent = `Downloading ${model}…`;

  const es = new EventSource(`/api/setup/ollama/pull?model=${encodeURIComponent(model)}`);
  es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.pct !== undefined) {
      fill.style.width = data.pct + "%";
      msg.textContent = data.msg || `${data.status} … ${data.pct}%`;
    } else {
      msg.textContent = data.msg || data.status || "";
    }
    if (data.done) {
      es.close();
      fill.style.width = "100%";
      msg.textContent = `✅ ${model} ready!`;
      setTimeout(loadAIStatus, 1000);
    }
    if (data.stage === "error") {
      es.close();
      fill.style.background = "var(--red)";
      msg.textContent = "Error: " + data.msg;
    }
  };
  es.onerror = () => { es.close(); };
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

  // Capture
  el("btn-capture").onclick = openCapture;
  el("capture-go").onclick = doCapture;
  el("capture-cancel").onclick = closeCapture;
  el("capture-url").addEventListener("keydown", (e) => { if (e.key === "Enter") doCapture(); });

  // Feed
  el("btn-feed").onclick = openFeed;
  el("feed-fetch").onclick = doFeedFetch;
  el("feed-url").addEventListener("keydown", (e) => { if (e.key === "Enter") doFeedFetch(); });
  el("feed-import").onclick = doFeedImport;
  el("feed-cancel").onclick = closeFeed;
  el("feed-close").onclick = closeFeed;
  el("feed-check-all").onclick = () => {
    const cbs = [...document.querySelectorAll(".feed-cb")];
    const allChecked = cbs.every((cb) => cb.checked);
    cbs.forEach((cb) => { cb.checked = !allChecked; });
    el("feed-check-all").textContent = allChecked ? "Select all" : "Deselect all";
  };

  // Settings
  el("btn-settings").onclick = openSettings;
  el("btn-settings-save").onclick = saveAISettings;
  el("btn-settings-close").onclick = closeSettings;
  el("sel-ai-provider").onchange = () => {
    const v = el("sel-ai-provider").value;
    document.querySelectorAll(".ai-card").forEach((c) => c.classList.remove("selected"));
    const card = el(`card-${v}`);
    if (card) card.classList.add("selected");
  };

  // Editor
  el("e-category").oninput = () => populateSubSelect();
  el("e-body").oninput = updatePreview;
  el("btn-save").onclick = saveNote;
  el("btn-archive").onclick = archiveNote;
  el("btn-ai").onclick = aiSuggest;

  // Add-category form
  el("btn-add-cat").onclick = () => {
    el("add-cat-form").classList.toggle("hidden");
    if (!el("add-cat-form").classList.contains("hidden")) el("new-cat").focus();
  };
  el("add-cat-go").onclick = createCategory;
  el("add-cat-cancel").onclick = () => {
    el("add-cat-form").classList.add("hidden");
    el("new-cat").value = ""; el("new-sub").value = "";
  };
  el("new-cat").addEventListener("keydown", (e) => { if (e.key === "Enter") createCategory(); });
  el("new-sub").addEventListener("keydown", (e) => { if (e.key === "Enter") createCategory(); });

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
