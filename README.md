# 💡 Idea & Project Hub

A local, Markdown-first hub for collecting ideas, projects, notes, and links —
across AI/ML, Computer Vision, IT, Pip tools, Finance, or whatever you add.

- **Your data = plain Markdown files** in `vault/<Category>/<Subcategory>/note.md`
  with YAML frontmatter. Edit them here, in VS Code, or in **Obsidian**.
- **No database, no installs.** Pure Python standard library + a single-page web UI.
- **Web capture** (articles + X/Twitter posts) and **optional AI auto-organizing**.
- **Due-soon panel + Windows toast notifications** while the app is open.

## Run it

Double-click **`run.bat`** (or run `python server.py`). Your browser opens at
`http://127.0.0.1:8765`.

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

## Enable AI (optional)

Edit `config.json` and set your Anthropic API key:

```json
"anthropic_api_key": "sk-ant-...",
"ai_model": "claude-haiku-4-5"
```

Or set the `ANTHROPIC_API_KEY` environment variable. Without a key the app is
fully functional — you just organize things by hand.

## Notifications

While the app is open, it scans your notes every `scan_interval_minutes`
(default 30) and raises a **Windows toast** for anything due today or overdue.
Adjust `due_soon_days` and `scan_interval_minutes` in `config.json`.

## Automations

See `automations/README.md`. Quick example:

```
python automations/capture_x_post.py https://x.com/user/status/123
```

## Files

| Path | What it is |
|------|------------|
| `vault/` | **Your notes** (Markdown). Back this up / put it in git. |
| `config.json` | Settings: API key, model, due window, scan interval, port. |
| `server.py` | Local server + API + background due-scan. |
| `hub.py` / `vault_io.py` | Note CRUD + frontmatter read/write. |
| `capture.py` | URL + X/Twitter capture. |
| `ai.py` | Optional Claude enrichment. |
| `notify.py` | Due-date scan + Windows toast. |
| `web/` | The single-page UI. |
| `automations/` | Your scripts. |

## Notes / limits

- The X syndication endpoint can change; if a tweet’s full text can’t be
  fetched, the URL and title are still saved.
- Toasts use Windows’ built-in notification API via PowerShell; if that fails on
  your build, the in-app **Due Soon** panel still works.
