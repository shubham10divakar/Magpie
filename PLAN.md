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

### Ollama in-app setup (`ollama_setup.py`)
- Detects if Ollama is running at `localhost:11434`
- **Install flow** (Windows, from inside the app):
  1. Downloads `OllamaSetup.exe` from GitHub releases with progress bar
  2. Runs it silently (`/S` flag) — one UAC prompt, then done
  3. Polls until Ollama service is up
  4. Pulls `llama3.2:3b` (~2 GB) via Ollama API with streaming progress
- All steps stream to the UI via SSE (`EventSource`) — live progress bars
- After setup: Ollama auto-starts on every Windows boot, zero user involvement

### ⚙ AI Settings modal
- Four provider cards: Claude / Gemini Flash / Groq / Ollama
- Live status per card (✅ Key set / 🔴 No key / ✅ Running / 🔴 Not detected)
- Key inputs (password) pre-filled from config; blank submission keeps existing key
- Ollama card: Install button → progress bar, or model selector if already running
- Provider dropdown: Auto / Claude / Gemini / Groq / Ollama
- Saves to `~/Magpie/config.json`

---

## 🔲 Pending / Next up

### High priority

#### 1. Pip agent integration (YOUR project — see below)
You are building a separate pip package / agent that manages local LLM models
(Ollama and similar). Once that ships, replace `ollama_setup.py` with a thin
adapter that calls your agent instead of driving the Ollama installer directly.
This makes Magpie's local-AI story much cleaner and removes the fragile
`subprocess + OllamaSetup.exe` approach.

**Integration point:** `ai.py → _call_ollama()` and `ollama_setup.py` are the
two files to touch. The agent should expose a simple interface:
- `agent.is_running()` → bool
- `agent.pull(model)` → progress generator
- `agent.chat(model, messages)` → str

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

## Your pip agent (future integration)

**What you're building:** a pip-installable agent/tool that manages local LLM
models (Ollama and similar runtimes) — install, pull, run, query.

**How it fits into Magpie:**

Right now Magpie has hand-rolled Ollama management (`ollama_setup.py`).
When your agent ships, the plan is:

```
pip install <your-agent>   # user installs once
```

Then in `magpie/ai.py`:
```python
# Replace _call_ollama() with:
import your_agent
def _call_ollama(cfg, prompt):
    return your_agent.chat(
        model=cfg.get("ollama_model", "llama3.2:3b"),
        messages=[{"role": "system", "content": SYSTEM},
                  {"role": "user",   "content": prompt}]
    )
```

And in `ollama_setup.py` → delegate to `your_agent.pull()` / `your_agent.is_running()`.

The Settings modal Ollama card would show your agent's status rather than
probing `localhost:11434` directly.

**What your agent should expose (minimal interface Magpie needs):**
```python
your_agent.is_running() -> bool
your_agent.list_models() -> list[str]
your_agent.pull(model: str) -> Generator[dict, None, None]  # progress events
your_agent.chat(model: str, messages: list[dict], **kwargs) -> str
```

This keeps Magpie's core stdlib-only (your agent is an optional dep, only needed
for local AI), and means Magpie automatically benefits from any runtime your
agent supports beyond Ollama (llama.cpp, llamafile, etc.).

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
