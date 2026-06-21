"""ai.py - optional AI enrichment via the Anthropic Messages API.

Zero-dependency: calls https://api.anthropic.com/v1/messages over urllib.
Given captured text + the existing category list, returns suggestions:
  {title, category, subcategory, tags[], summary, type}

Fully optional. If no API key is configured, enrich() returns None and the
app stays 100% functional offline.
"""
from __future__ import annotations

import json
import urllib.request

import hub

API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

SYSTEM = (
    "You organize a personal idea/project hub. Given a captured note's text "
    "(and optional source URL), return STRICT JSON only, no prose, with keys: "
    "title (short, <=80 chars), category, subcategory, tags (array of <=5 short "
    "lowercase strings), summary (1-2 sentences), type (one of idea|project|note|link). "
    "Prefer one of the EXISTING categories/subcategories when it fits; you may "
    "propose a new subcategory if clearly needed."
)


def ai_available() -> bool:
    cfg = hub.load_config()
    return bool(cfg.get("ai_enabled", True)) and bool(cfg.get("anthropic_api_key"))


def _categories_block() -> str:
    cfg = hub.load_config()
    lines = []
    for cat, subs in cfg.get("seed_categories", {}).items():
        lines.append(f"- {cat}: {', '.join(subs) if subs else '(no subcategories yet)'}")
    return "\n".join(lines)


def enrich(text: str, url: str = "") -> dict | None:
    """Return suggestion dict, or None if AI is unavailable / errored."""
    if not ai_available():
        return None
    cfg = hub.load_config()
    prompt = (
        f"EXISTING CATEGORIES:\n{_categories_block()}\n\n"
        f"SOURCE URL: {url or '(none)'}\n\n"
        f"CAPTURED TEXT:\n{text[:6000]}\n\n"
        "Return the JSON object now."
    )
    body = json.dumps({
        "model": cfg.get("ai_model", "claude-haiku-4-5"),
        "max_tokens": 1024,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "x-api-key": cfg["anthropic_api_key"],
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # network / auth / quota — degrade gracefully
        print(f"[ai] enrichment skipped: {exc}")
        return None

    # Extract the first text block and parse JSON out of it.
    text_out = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            text_out += block.get("text", "")
    text_out = text_out.strip()
    if text_out.startswith("```"):
        text_out = text_out.strip("`")
        if text_out.lstrip().lower().startswith("json"):
            text_out = text_out.split("\n", 1)[1] if "\n" in text_out else text_out
    try:
        suggestion = json.loads(text_out[text_out.find("{"): text_out.rfind("}") + 1])
    except Exception:
        return None

    # Normalize
    tags = suggestion.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    return {
        "title": (suggestion.get("title") or "").strip(),
        "category": (suggestion.get("category") or "").strip(),
        "subcategory": (suggestion.get("subcategory") or "").strip(),
        "tags": [str(t).strip() for t in tags][:5],
        "summary": (suggestion.get("summary") or "").strip(),
        "type": (suggestion.get("type") or "idea").strip(),
    }
