# Magpie — Build Plan

## What is Magpie

A local, Markdown-first idea & project hub. Collect, organize, and enrich
notes/links/ideas across any domain. No database — plain `.md` files with YAML
frontmatter, fully Obsidian-compatible. Python stdlib only (no pip deps at
runtime). Ships as a single `Magpie.exe` or via `pipx install magpie-hub`.

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
- Installable as `pipx install magpie-hub` or standalone `Magpie.exe`
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

#### 2. llamafile support (sidecar, zero install)
Alternative to Ollama for users who can't/won't install system software.
User drops a `.llamafile` into `~/Magpie/llamafile/`. Magpie spawns it as a
subprocess on demand, talks to it on a local port, kills it on shutdown.
No UAC, no service, no PATH — just one file.

Effort: ~100 lines in a new `llamafile_setup.py` + one new provider in `ai.py`.

#### 3. Model pull from within the app (model selector)
Currently the Ollama card only pulls `llama3.2:3b`. Should show a dropdown of
recommended models (phi4-mini, mistral:7b, llama3.2:1b) with size + quality
labels so users can choose before downloading.

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

## freeaiagent — integrated ✅

**Package:** `pip install freeaiagent` (published on PyPI by you, 2026-06-21)

**What it does:** persistent HTTP server at `localhost:7731` with Ollama and
Groq backends, SQLite conversation history, CLI (`freeaiagent start/chat/task`).

**How Magpie uses it:**

| Magpie call | freeaiagent endpoint |
|-------------|----------------------|
| AI enrichment | `POST /task` — `{task, input, system}` |
| Status check | `GET /health` — `{status, active_backend, default_model}` |
| List models | `GET /models` |
| Start from UI | `freeaiagent start` via subprocess.Popen |

Key files:
- `magpie/freeaiagent_setup.py` — all calls to localhost:7731 (stdlib urllib only)
- `magpie/ai.py` → `_call_freeaiagent()` — uses `call_task()` from setup module
- `magpie/server.py` → `POST /api/setup/agent/start` → `start_agent()`

Magpie remains pip-dependency-free. freeaiagent is optional — without it,
the other three providers (Claude, Gemini, Groq) still work.

---

## Tech constraints (don't change without discussion)

| Constraint | Reason |
|------------|--------|
| Python stdlib only at runtime | Works on Python 3.14 with no pip install |
| Markdown + YAML frontmatter | Obsidian-compatible, future-proof |
| No database | Plain files = easy backup, git, external editing |
| `~/Magpie/` data dir | Upgrades never touch user data |
| ThreadingHTTPServer | Each request (incl. SSE streams) gets its own thread |
| SSE for long-running ops | Ollama install/pull streams progress without polling |
