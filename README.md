# 🐦 Magpie

*Your idea & project hub — collect shiny things from everywhere.*

A local, Markdown-first hub for collecting ideas, projects, notes, and links —
across AI/ML, Computer Vision, IT, Pip tools, Finance, or whatever you add.

- **Your data = plain Markdown files** in `vault/<Category>/<Subcategory>/note.md`
  with YAML frontmatter. Edit them here, in VS Code, or in **Obsidian**.
- **No database.** Plain files + a single-page web UI. The core app is
  stdlib-only; the optional local-AI feature uses the `freeaiagent` package.
- **Web capture** (articles + X/Twitter posts) and **optional AI auto-organizing**.
- **Due-soon panel + Windows toast notifications** while the app is open.

## Install & run

**From source (this repo):** double-click **`run.bat`** (or run `python -m magpie`).
Your browser opens at `http://127.0.0.1:8765`.

**As a pip tool (for other people):**

```bash
pipx install magpie-hub      # or: pip install magpie-hub  (Python 3.10+)
magpie                       # launches the hub
```

This pulls in `freeaiagent` (the local-AI backend). Magpie is distributed via
pipx/pip only — there's no standalone `.exe`, because a frozen build can't
import `freeaiagent` from the user's separate environment.

Your notes are created in **`~/Magpie/`** (config + `vault/`) on first run, so
upgrades and reinstalls never touch your data. Point `MAGPIE_HOME` at another
folder to override.

## Using it

- **Sidebar** — filter by status (Inbox / Active / Someday / Done / Due Soon) or
  click a category/subcategory.
- **+ New** — create a note in the current folder.
- **🔗 Capture** — paste a URL; it’s fetched, optionally AI-organized, and saved to
  Inbox. (X/Twitter posts use the public syndication API server-side — the thing
  a browser can’t fetch directly.)
- **Editor** — edit frontmatter fields + Markdown body with live preview. Supports
  `[[wiki-links]]`. **Ctrl+S** saves. Changing category/subcategory moves the file.
- **✨ Suggest with AI** — fills in title/category/tags/summary (needs an API key).

## Managing categories

Categories and subcategories are just **folders** inside `~/Magpie/vault/`. Magpie
scans the filesystem on every refresh, so any folder you create — empty or not —
shows up in the sidebar automatically.

### Adding a category or subcategory

Three ways, all safe (nothing is ever overwritten):

| Method | How |
|--------|-----|
| **UI button** | Click `+` next to "Categories" in the sidebar. Type the category name and an optional subcategory, press Enter or click Create. |
| **Type in editor** | The Category and Subcategory fields accept free text. Type any new name while editing a note and save — the folder is created automatically. |
| **File manager / terminal** | `mkdir` the folder inside `~/Magpie/vault/`. Magpie picks it up on next refresh even if the folder is empty. |

### Renaming or deleting a category

**Do this in your file manager (Explorer), not in Magpie.** The UI intentionally
has no rename or delete buttons for categories because:

- Renaming a category = moving every file inside it — risky to automate silently.
- Deleting a category with notes in it = permanent data loss.

In Explorer, rename or delete the folder under `C:\Users\<you>\Magpie\vault\` as
you would any normal folder. The OS warns you before deleting non-empty folders.
Magpie reflects the change on next refresh.

> **Tip:** back up `~/Magpie/vault/` (or put it in git) before bulk reorganising.

## AI providers (all optional)

Click **⚙ AI** in the top bar to open the Settings panel. Magpie supports four
providers — pick whichever fits your setup. Without any provider the app is
fully functional; you just organise things by hand.

Priority in **Auto** mode: Claude → Gemini Flash → Groq → Local AI Agent.

### 🤖 Claude (Anthropic) — paid, best quality
1. Go to **[console.anthropic.com](https://console.anthropic.com/)**
2. Sign up → **API Keys** → **Create Key**
3. In Magpie → **⚙ AI** → paste key under Claude → **Save**

### ✨ Gemini Flash (Google) — free tier, no credit card
1,500 requests / day free with a Google account.
1. Go to **[aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)**
2. Sign in with your Google account → **Create API key**
3. In Magpie → **⚙ AI** → paste key under Gemini Flash → **Save**

### ⚡ Groq — free tier, very fast
14,400 requests / day free (llama-3.1 model).
1. Go to **[console.groq.com/keys](https://console.groq.com/keys)**
2. Sign up → **Create API key**
3. In Magpie → **⚙ AI** → paste key under Groq → **Save**

### 🤖 Local AI Agent — local, no key, works offline
Uses [freeaiagent](https://pypi.org/project/freeaiagent/) (installed with Magpie)
— a persistent local LLM server with a built-in zero-install backend
(llamafile/GGUF, no Ollama, no key). Completely free, data never leaves your
machine.

Everything is in the UI now — no terminal needed:

1. Magpie → **⚙ AI** → **Local AI Agent** card → **Start Agent**
2. Pick a model from the catalog dropdown (size + quality tier shown)
3. **Download** — watch the live progress bar
4. **Set as default** — enrichment now runs on your local model

See `freeaiagent --help` or [pypi.org/project/freeaiagent](https://pypi.org/project/freeaiagent/)
for advanced backend/model configuration.

## Notifications

While the app is open, it scans your notes every `scan_interval_minutes`
(default 30) and raises a **Windows toast** for anything due today or overdue.
Adjust `due_soon_days` and `scan_interval_minutes` in `config.json`.

## Automations

See `automations/README.md`. Quick example:

```
python automations/capture_x_post.py https://x.com/user/status/123
```

## Layout

Your **data** (created at first run, never touched by upgrades):

| Path | What it is |
|------|------------|
| `~/Magpie/vault/` | **Your notes** (Markdown). Back this up / put it in git. |
| `~/Magpie/config.json` | Settings: API key, model, due window, scan interval, port. |

The **code** (this repo / the installed package):

| Path | What it is |
|------|------------|
| `magpie/server.py` | Local server + API + background due-scan. |
| `magpie/hub.py` / `vault_io.py` | Note CRUD + frontmatter read/write. |
| `magpie/capture.py` | URL + X/Twitter capture. |
| `magpie/ai.py` | Multi-provider AI enrichment (Claude, Gemini, Groq, freeaiagent). |
| `magpie/freeaiagent_setup.py` | Adapter to freeaiagent via its `Client` SDK (health, task, catalog, pull, config). |
| `magpie/notify.py` | Due-date scan + Windows toast. |
| `magpie/web/` | The single-page UI. |
| `magpie/default_config.json` | Template copied to `~/Magpie/config.json` on first run. |
| `automations/` | Example scripts (`capture_x_post.py`). |
| `pyproject.toml` | pip/pipx packaging (depends on `freeaiagent`). |

## Data safety

Magpie follows a strict **add-only** rule — it never silently removes or overwrites
your files:

| Action | What actually happens |
|--------|----------------------|
| Create category | `mkdir` with `exist_ok=True` — harmless if the folder already exists. |
| Move note to new category | Writes the destination file first, verifies it is non-empty, then removes the source. If the write fails the source is untouched. |
| Archive note | Changes `status: archived` in frontmatter only — the file stays on disk. |
| Rename / delete category | **Not in the UI** — do it in your file manager where the OS handles it safely. |

Your vault is plain Markdown files. Back it up with git, Dropbox, or any tool you
like — Magpie never touches files it doesn’t own.

## Notes / limits

- The X syndication endpoint can change; if a tweet’s full text can’t be
  fetched, the URL and title are still saved.
- Toasts use Windows’ built-in notification API via PowerShell; if that fails on
  your build, the in-app **Due Soon** panel still works.
