# Magpie — Build Plan

## What is Magpie

A local, Markdown-first idea & project hub. Collect, organize, and enrich
notes/links/ideas across any domain. No database — plain `.md` files with YAML
frontmatter, fully Obsidian-compatible. Core app is stdlib-only; the local-AI
feature depends on `freeaiagent`. Ships via `pipx install magpie-hub`
(the single-`Magpie.exe` target was dropped — see #3 / Tech constraints).

---

## ✅ Built (shipped)

### Core vault & UI
- Markdown vault: `~/Magpie/vault/<Category>/<Subcategory>/note.md`
- YAML frontmatter (title, type, status, tags, due, remind, links, source, ai_summary)
- Three-panel web UI: sidebar → card list → editor with live markdown preview
- `[[wiki-link]]` support in editor
- Status filters: Inbox / Active / Someday / Done / Due Soon / All
- Full-text search across title, tags, and body
- Category management: create from UI (+), free-text input in editor, filesystem scan
- Safe note move: write → verify → delete source (never loses data)
- Due-soon panel + Windows toast notifications (background scanner thread)
- Installable as `pipx install magpie-hub`
- Per-user data dir `~/Magpie/` — upgrades never touch notes

### URL capture (`capture.py`)
- **Generic pages**: `_ArticleExtractor` — pulls `<p>`, `h1–h4`, `<li>`, `<blockquote>`
- **Density fallback** (`_DensityExtractor`): scores `<div>` blocks by `text²/tag_count`
  so React/Next.js pages with no `<p>` tags still produce real body text
- **X/Twitter**: syndication API (works server-side; browser gets 402)
- **Twitter thread unrolling**: walks `in_reply_to_status_id_str` backward up to
  10 hops (same author only), stitches into one chronological note
- **YouTube**: title, channel, duration, description, publish date from page JSON;
  optional auto-captions via public `timedtext` API (srv3 XML)
- **RSS/Atom feed import**: modal with checkbox list, bulk save to Inbox;
  handles RSS 2.0 + Atom 1.0, `content:encoded`, `dc:creator` namespaces
- Graceful fallback on any fetch failure — URL + title always saved

### AI enrichment (`ai.py`)
- **Multi-provider routing** — tries in order, first success wins:
  1. Claude (Anthropic) — paid, best quality
  2. Gemini Flash (Google) — free tier, 1500 req/day, no credit card
  3. Groq — free tier, 14 400 req/day, llama-3.1
  4. Ollama — local, no key, no internet, completely free
- All providers: same prompt → same JSON output (title, category, subcategory,
  tags, summary, type)
- `ai_provider: auto` (default) or pin to a specific provider
- Active provider name shown in sidebar ("✨ AI: Gemini Flash")

### Local AI Agent (`freeaiagent_setup.py`) — replaces ollama_setup.py
- Thin adapter to **freeaiagent** (`pip install freeaiagent`) at `localhost:7731`
- `is_running()` / `is_installed()` / `get_health()` / `list_models()` — all stdlib urllib
- `start_agent()` — spawns `freeaiagent start` as a background subprocess, polls up to 15s
- `call_task()` — POSTs to `/task` with `{task, input, system}`, returns result string
- freeaiagent owns Ollama/Groq routing; Magpie doesn't touch Ollama directly at all

### ⚙ AI Settings modal
- Four provider cards: Claude / Gemini Flash / Groq / Local AI Agent
- Live status per card (✅ Key set / 🔴 No key / ✅ Running · ollama · llama3.2:3b / 🔴 …)
- Key inputs (password) pre-filled from config; blank submission keeps existing key
- Local AI card: **Start Agent** button (POST `/api/setup/agent/start`) if installed but not running;
  install instructions if not installed; model list if running
- Provider dropdown: Auto / Claude / Gemini / Groq / Local AI Agent
- Saves to `~/Magpie/config.json`

---

## 🔲 Pending / Next up

### High priority

#### ✅ 1. freeaiagent integration — DONE
`ollama_setup.py` replaced by `freeaiagent_setup.py`. Magpie now calls
`localhost:7731/task` via stdlib urllib. freeaiagent (published on PyPI as
`freeaiagent`) owns Ollama/Groq routing, model management, and context.
Settings card shows live backend + model from `/health`.

#### ~~2. llamafile support (sidecar, zero install)~~ — SUBSUMED by freeaiagent 1.2.0
**No longer a Magpie-side task.** freeaiagent 1.2.0 ships a built-in
zero-install local backend (llamafile + GGUF, 1B–14B, no Ollama, no key,
fully offline). Magpie does **not** need its own `llamafile_setup.py` — it
just surfaces freeaiagent's local backend through the new catalog/pull UI
described in #3 below.

#### 🔲 3. Model catalog + download + progress, in the UI  ← NEXT UP
**Now unblocked by freeaiagent 1.2.0.** Previously the Local AI card could only
*list* installed model names — it could not browse a catalog, start a download,
or show progress. freeaiagent 1.2.0 now exposes the endpoints to do all three:

| freeaiagent endpoint | Gives us |
|----------------------|----------|
| `GET /models/catalog` | curated models with `installed` flag, size, RAM, tier |
| `GET /models/installed` | what's actually on disk |
| `POST /pull/stream` | SSE download with live progress (`phase`, `pct`, `downloaded_mb`, `total_mb`, `speed_mbps`) |
| `POST /config/set` | set `default_model` (dotted-key config) |

**Decision:** use the **`freeaiagent.Client` SDK** (not raw urllib). This makes
`freeaiagent` a declared dependency of `magpie-hub` and **drops the single
`Magpie.exe` target** — distribution is now pipx-only, since a frozen exe can't
import a package living in the user's separate environment. The SDK buys us
`client.pull()` progress iteration, `client.models.catalog()`, port
auto-discovery (`~/.freeaiagent/server.json`), and typed errors
(`ServerNotRunning`, `DownloadInProgress`).

##### Implementation plan

**A. `magpie/freeaiagent_setup.py`** — replace urllib internals with a lazily
constructed `Client(name="magpie", auto_start=False)`. Keep the existing public
function names so callers don't churn; add four helpers:
- `get_catalog()` → `client.models.catalog()` (each entry flagged `installed`).
  `[]` on failure.
- `get_installed()` → `client.models.installed()`. `[]` on failure.
- `set_default_model(model)` → `client.config.set("default_model", model)`.
  Returns `{ok, msg}`.
- `pull_model(model)` → **generator** wrapping `client.pull(model)`, yielding
  each progress object (`p.type`, `p.phase`, `p.pct`, `p.downloaded_mb`,
  `p.total_mb`) as a plain dict for the server's SSE passthrough.

Import `freeaiagent` lazily (inside functions / behind a module-level
try-import) so that if it's somehow absent, the cloud providers still load and
the Local AI card degrades to an "install freeaiagent" message rather than
crashing app startup.

**B. `magpie/server.py`** — three new routes:
- `GET /api/setup/agent/catalog` → merges `get_catalog()` + `get_installed()`,
  returns `{models: [...]}` for the dropdown.
- `POST /api/setup/agent/config` → body `{model}` → `set_default_model()`.
- `POST /api/setup/agent/pull` → **SSE passthrough**. Iterate
  `freeaiagent_setup.pull_model()` and re-emit each event as
  `data: {…}\n\n` on Magpie's own response, so the browser gets one clean
  progress stream. Reuse the existing ThreadingHTTPServer + SSE plumbing.

**C. `magpie/web/index.html` + `app.js`** — extend the Local AI card
(`#local-ai-controls`, currently `app.js:475-507`):
- When the agent is running, render a **model `<select>`** populated from
  `/api/setup/agent/catalog`. Installed models show a ✓; others show size +
  tier (e.g. `qwen2.5-7b · 4.7 GB · high`).
- **Set as default** button → `POST /api/setup/agent/config`.
- **Download** button for not-yet-installed models → opens an `EventSource`
  /reads the SSE stream from `/api/setup/agent/pull`, drives a `<progress>`
  bar + MB/speed text (reuse the existing `.progress-msg` styling), and
  refreshes the card + `loadAIStatus()` on `[DONE]`.

**D. Acceptance:** from the AI Settings modal a user can, with no terminal:
pick a model from the catalog, click Download, watch a real progress bar to
completion, set it as default, and have enrichment use it.

**E. Packaging:** add `freeaiagent>=1.2.0` to `pyproject.toml`; remove any
PyInstaller `.exe` build target/spec and update README install docs to
pipx-only.

Effort: ~80 lines in `freeaiagent_setup.py`, ~40 in `server.py`, ~70 in the UI,
plus the packaging cleanup.

#### 4. Bulk note operations
- Multi-select cards (shift-click / checkbox)
- Bulk move to category
- Bulk tag
- Bulk archive

#### 5. Note templates
Pre-defined frontmatter for common note types (project brief, reading note,
meeting note). Shown when clicking `+ New` with a type selector.

### Medium priority

#### 6. Export / backup
- Export vault as `.zip`
- One-click "Open vault in Explorer"
- Optional auto-backup to a user-specified folder on save

#### 7. Better search
- Faceted filters (tag picker, date range, source filter)
- Highlight matched terms in cards
- Saved searches / pinned filters

#### 8. Dark mode
Toggle in settings. CSS variables already set up — just needs a `[data-theme=dark]`
override block and a toggle button.

#### 9. Responsive / mobile UI
Current layout breaks below ~900px. Low priority for a desktop-first app but
useful for tablet use.

#### 10. Mac/Linux Ollama install
`ollama_setup.py` currently only handles Windows (`OllamaSetup.exe`).
Mac: download `Ollama-darwin.zip`, unzip, move to Applications.
Linux: `curl -fsSL https://ollama.com/install.sh | sh` via subprocess.

### Low priority / future ideas

- Image/file attachments stored next to `.md` files
- Sharing: export a single note as HTML or PDF
- Browser extension to one-click capture the current tab
- Webhook / API key for external tools to POST notes directly
- Plugin system for custom capture handlers
- Keyboard shortcut cheatsheet modal

---

## freeaiagent — integrated ✅ (tracking 1.2.0)

**Package:** `pip install freeaiagent` (published on PyPI by you; 1.2.0 released
2026-06-23)

**What it does:** persistent HTTP server at `localhost:7731`. As of 1.2.0:
built-in **zero-install local backend** (llamafile + GGUF, 1B–14B, no Ollama,
no key, offline), plus Ollama, Groq, and OpenAI-compatible cloud presets
(Gemini, OpenRouter, Together, Cerebras). SQLite history, streaming, tool use,
a model catalog, server-side streaming downloads, and a Python `Client` SDK.

**How Magpie uses it (via the `freeaiagent.Client` SDK — a declared dependency):**

| Magpie call | SDK / endpoint | Status |
|-------------|----------------|--------|
| AI enrichment | `client.task(...)` → `POST /task` | ✅ wired (migrate to SDK in #3) |
| Status check | `client.is_running()` / `GET /health` | ✅ wired |
| List models | `client.models.list()` / `GET /models` | ✅ wired |
| Start from UI | `freeaiagent start` via subprocess (or `auto_start=True`) | ✅ wired |
| Model catalog | `client.models.catalog()` / `client.models.installed()` | 🔲 planned (#3) |
| Download model | `client.pull(model)` (progress iterator) | 🔲 planned (#3) |
| Set default model | `client.config.set("default_model", …)` | 🔲 planned (#3) |

Key files:
- `magpie/freeaiagent_setup.py` — lazily constructs `Client(name="magpie")`; all freeaiagent access goes through here
- `magpie/ai.py` → `_call_freeaiagent()` — uses `call_task()` from setup module
- `magpie/server.py` → `POST /api/setup/agent/start` → `start_agent()`

freeaiagent is now a real dependency of the local-AI feature (declared in
`pyproject.toml`). The other three providers (Claude, Gemini, Groq) still work
without it — the import is lazy, so its absence degrades the Local AI card to an
install prompt rather than breaking the app.

---

## Tech constraints (don't change without discussion)

| Constraint | Reason |
|------------|--------|
| Core app is stdlib-only | Vault, capture, server need no pip deps |
| `freeaiagent` is the one allowed dependency | Local-AI feature uses the `Client` SDK (catalog/pull/progress) |
| pipx-only distribution (no `Magpie.exe`) | SDK import requires Magpie + freeaiagent in the same env; a frozen exe can't import the user's separate install |
| Markdown + YAML frontmatter | Obsidian-compatible, future-proof |
| No database | Plain files = easy backup, git, external editing |
| `~/Magpie/` data dir | Upgrades never touch user data |
| ThreadingHTTPServer | Each request (incl. SSE streams) gets its own thread |
| SSE for long-running ops | Model pull streams progress to the UI without polling |
