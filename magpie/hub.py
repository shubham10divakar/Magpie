"""hub.py - domain operations over the Markdown vault.

The vault layout is:  vault/<Category>/<Subcategory>/<note>.md
Category/subcategory are derived from the folder path (single source of truth).
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta

from . import vault_io

# --------------------------------------------------------------------------- #
# Paths & config
# --------------------------------------------------------------------------- #
# Code (web/, default config) lives in the installed package; the user's data
# (config.json + vault/) lives in their home dir so upgrades never touch it.
PKG_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG_PATH = os.path.join(PKG_DIR, "default_config.json")

HOME = os.environ.get("MAGPIE_HOME") or os.path.join(
    os.path.expanduser("~"), "Magpie"
)
CONFIG_PATH = os.path.join(HOME, "config.json")


def _read_config_file() -> dict:
    path = CONFIG_PATH if os.path.exists(CONFIG_PATH) else DEFAULT_CONFIG_PATH
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_config() -> dict:
    cfg = _read_config_file()
    # allow env var to override / supply the API key
    cfg["anthropic_api_key"] = (
        os.environ.get("ANTHROPIC_API_KEY") or cfg.get("anthropic_api_key", "")
    )
    return cfg


def ensure_home() -> str:
    """Create ~/Magpie with config + seeded category folders on first run."""
    os.makedirs(HOME, exist_ok=True)
    if not os.path.exists(CONFIG_PATH):
        with open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as fh:
            default = json.load(fh)
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump(default, fh, indent=2)
    cfg = load_config()
    root = vault_root()
    os.makedirs(os.path.join(root, "Inbox"), exist_ok=True)
    for cat, subs in cfg.get("seed_categories", {}).items():
        if subs:
            for sub in subs:
                os.makedirs(os.path.join(root, cat, sub), exist_ok=True)
        else:
            os.makedirs(os.path.join(root, cat), exist_ok=True)
    return HOME


def vault_root() -> str:
    cfg = _read_config_file()
    vp = cfg.get("vault_path", "vault")
    return vp if os.path.isabs(vp) else os.path.join(HOME, vp)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def slugify(title: str) -> str:
    s = re.sub(r"[^\w\s-]", "", (title or "untitled")).strip().lower()
    s = re.sub(r"[\s_]+", "-", s)
    return s[:60] or "untitled"


def _rel(path: str) -> str:
    return os.path.relpath(path, vault_root()).replace("\\", "/")


def _abs(rel_path: str) -> str:
    # prevent path escape
    full = os.path.normpath(os.path.join(vault_root(), rel_path))
    if not full.startswith(os.path.normpath(vault_root())):
        raise ValueError("path escapes vault")
    return full


def _split_category(rel_path: str):
    parts = rel_path.split("/")
    category = parts[0] if len(parts) >= 2 else ""
    subcategory = parts[1] if len(parts) >= 3 else ""
    return category, subcategory


def _today() -> date:
    return date.today()


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Listing / searching
# --------------------------------------------------------------------------- #
def _iter_note_paths():
    root = vault_root()
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if name.lower().endswith(".md"):
                yield os.path.join(dirpath, name)


def _summary(meta: dict, rel_path: str) -> dict:
    category, subcategory = _split_category(rel_path)
    return {
        "path": rel_path,
        "title": meta.get("title") or os.path.basename(rel_path)[:-3],
        "type": meta.get("type", "idea"),
        "status": meta.get("status", "inbox"),
        "category": category,
        "subcategory": subcategory,
        "tags": meta.get("tags") or [],
        "due": meta.get("due"),
        "remind": meta.get("remind"),
        "source": meta.get("source", "manual"),
        "updated": meta.get("updated"),
    }


def list_notes(category="", subcategory="", status="", q="", due_within=None):
    results = []
    q_low = (q or "").lower()
    for path in _iter_note_paths():
        rel = _rel(path)
        meta = vault_io.read_frontmatter_only(path)
        item = _summary(meta, rel)
        if category and item["category"] != category:
            continue
        if subcategory and item["subcategory"] != subcategory:
            continue
        if status and item["status"] != status:
            continue
        if due_within is not None:
            d = _parse_date(item["due"]) or _parse_date(item["remind"])
            if d is None or (d - _today()).days > int(due_within):
                continue
        if q_low:
            hay = " ".join([
                str(item["title"]),
                " ".join(str(t) for t in item["tags"]),
                rel,
            ]).lower()
            # fall back to body search if not matched in metadata
            if q_low not in hay:
                _m, body = vault_io.read_note(path)
                if q_low not in body.lower():
                    continue
        results.append(item)
    results.sort(key=lambda x: (str(x.get("updated") or ""), x["title"]), reverse=True)
    return results


def get_note(rel_path: str) -> dict:
    path = _abs(rel_path)
    meta, body = vault_io.read_note(path)
    item = _summary(meta, rel_path)
    item["body"] = body
    item["links"] = meta.get("links") or []
    item["ai_summary"] = meta.get("ai_summary", "")
    item["created"] = meta.get("created")
    return item


def build_tree():
    """Return category -> {count, subcategories: {name: count}}.

    Scans the vault filesystem first so manually-created folders (empty or
    otherwise) always show up in the sidebar without needing a note in them.
    """
    root = vault_root()
    tree = {}
    if os.path.isdir(root):
        for name in sorted(os.listdir(root)):
            full = os.path.join(root, name)
            if not os.path.isdir(full) or name.startswith("."):
                continue
            subs = {}
            for sub in sorted(os.listdir(full)):
                if os.path.isdir(os.path.join(full, sub)) and not sub.startswith("."):
                    subs[sub] = 0
            tree[name] = {"count": 0, "subcategories": subs}
    for path in _iter_note_paths():
        rel = _rel(path)
        cat, sub = _split_category(rel)
        if not cat:
            continue
        node = tree.setdefault(cat, {"count": 0, "subcategories": {}})
        node["count"] += 1
        if sub:
            node["subcategories"][sub] = node["subcategories"].get(sub, 0) + 1
    return tree


def create_category(category: str, subcategory: str = "") -> None:
    rel = category if not subcategory else f"{category}/{subcategory}"
    os.makedirs(_abs(rel), exist_ok=True)


def status_counts():
    counts = {"inbox": 0, "active": 0, "someday": 0, "done": 0, "archived": 0}
    for path in _iter_note_paths():
        meta = vault_io.read_frontmatter_only(path)
        st = meta.get("status", "inbox")
        counts[st] = counts.get(st, 0) + 1
    return counts


def due_soon(days=None):
    cfg = load_config()
    window = int(days if days is not None else cfg.get("due_soon_days", 7))
    today = _today()
    out = []
    for path in _iter_note_paths():
        rel = _rel(path)
        meta = vault_io.read_frontmatter_only(path)
        if meta.get("status") in ("done", "archived"):
            continue
        for field in ("due", "remind"):
            d = _parse_date(meta.get(field))
            if d is not None and (d - today).days <= window:
                item = _summary(meta, rel)
                item["date_kind"] = field
                item["date"] = d.isoformat()
                item["days_left"] = (d - today).days
                out.append(item)
                break
    out.sort(key=lambda x: x["days_left"])
    return out


# --------------------------------------------------------------------------- #
# Create / update / move / delete
# --------------------------------------------------------------------------- #
def _unique_path(folder_abs: str, slug: str) -> str:
    candidate = os.path.join(folder_abs, slug + ".md")
    n = 2
    while os.path.exists(candidate):
        candidate = os.path.join(folder_abs, f"{slug}-{n}.md")
        n += 1
    return candidate


def create_note(category="Inbox", subcategory="", title="Untitled", body="", **meta):
    rel_dir = category if not subcategory else f"{category}/{subcategory}"
    folder_abs = _abs(rel_dir)
    os.makedirs(folder_abs, exist_ok=True)
    path = _unique_path(folder_abs, slugify(title))
    today = _today().isoformat()
    full_meta = {
        "title": title,
        "type": meta.get("type", "idea"),
        "status": meta.get("status", "inbox"),
        "tags": meta.get("tags") or [],
        "due": meta.get("due"),
        "remind": meta.get("remind"),
        "links": meta.get("links") or [],
        "source": meta.get("source", "manual"),
        "ai_summary": meta.get("ai_summary", ""),
        "created": today,
        "updated": today,
    }
    vault_io.write_note(path, full_meta, body or "")
    return _rel(path)


def update_note(rel_path: str, meta_updates: dict, body=None):
    path = _abs(rel_path)
    meta, old_body = vault_io.read_note(path)
    for key, value in (meta_updates or {}).items():
        meta[key] = value
    meta["updated"] = _today().isoformat()
    vault_io.write_note(path, meta, old_body if body is None else body)
    return _rel(path)


def move_note(rel_path: str, category: str, subcategory=""):
    src = _abs(rel_path)
    meta, body = vault_io.read_note(src)
    rel_dir = category if not subcategory else f"{category}/{subcategory}"
    folder_abs = _abs(rel_dir)
    os.makedirs(folder_abs, exist_ok=True)
    slug = os.path.basename(src)[:-3]
    dest = _unique_path(folder_abs, slug)
    vault_io.write_note(dest, meta, body)
    # Only remove the source after verifying the destination was written.
    if not os.path.exists(dest) or os.path.getsize(dest) == 0:
        raise RuntimeError(f"Move aborted: destination not written correctly ({dest})")
    os.remove(src)
    return _rel(dest)


def archive_note(rel_path: str):
    return update_note(rel_path, {"status": "archived"})
