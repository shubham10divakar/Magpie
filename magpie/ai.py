"""ai.py – multi-provider AI enrichment (Claude, Gemini, Groq, Ollama).

Priority in auto mode: Claude → Gemini Flash → Groq → Ollama → off.
All providers use the same prompt and return the same JSON shape.
Zero pip dependencies: every call is a plain urllib.request.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error

from . import hub

SYSTEM = (
    "You organize a personal idea/project hub. Given a captured note's text "
    "(and optional source URL), return STRICT JSON only, no prose, with keys: "
    "title (short, <=80 chars), category, subcategory, tags (array of <=5 short "
    "lowercase strings), summary (1-2 sentences), type (one of idea|project|note|link). "
    "Prefer one of the EXISTING categories/subcategories when it fits; you may "
    "propose a new subcategory if clearly needed."
)


def _categories_block() -> str:
    """Return live vault categories so the AI sees what actually exists."""
    try:
        tree = hub.build_tree()
        lines = []
        for cat, node in tree.items():
            subs = list((node.get("subcategories") or {}).keys())
            lines.append(f"- {cat}: {', '.join(subs) if subs else '(none yet)'}")
        return "\n".join(lines) or "(none yet)"
    except Exception:
        cfg = hub.load_config()
        return "\n".join(
            f"- {c}: {', '.join(s) if s else ''}"
            for c, s in cfg.get("seed_categories", {}).items()
        )


def _build_prompt(text: str, url: str) -> str:
    return (
        f"EXISTING CATEGORIES:\n{_categories_block()}\n\n"
        f"SOURCE URL: {url or '(none)'}\n\n"
        f"CAPTURED TEXT:\n{text[:6000]}\n\n"
        "Return the JSON object now."
    )


def _parse(raw: str) -> dict | None:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lstrip().lower().startswith("json"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw
    try:
        obj = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
    except Exception:
        return None
    tags = obj.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    return {
        "title": (obj.get("title") or "").strip(),
        "category": (obj.get("category") or "").strip(),
        "subcategory": (obj.get("subcategory") or "").strip(),
        "tags": [str(t).strip() for t in tags][:5],
        "summary": (obj.get("summary") or "").strip(),
        "type": (obj.get("type") or "idea").strip(),
    }


# --------------------------------------------------------------------------- #
# Provider call functions
# --------------------------------------------------------------------------- #
def _call_claude(cfg: dict, prompt: str) -> str | None:
    key = cfg.get("anthropic_api_key", "")
    if not key:
        return None
    body = json.dumps({
        "model": cfg.get("ai_model", "claude-haiku-4-5"),
        "max_tokens": 1024,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return "".join(
        b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
    )


def _call_gemini(cfg: dict, prompt: str) -> str | None:
    key = cfg.get("gemini_api_key", "")
    if not key:
        return None
    model = cfg.get("gemini_model", "gemini-1.5-flash")
    body = json.dumps({
        "system_instruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1024},
    }).encode()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models"
        f"/{model}:generateContent?key={key}"
    )
    req = urllib.request.Request(
        url, data=body, headers={"content-type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _call_groq(cfg: dict, prompt: str) -> str | None:
    key = cfg.get("groq_api_key", "")
    if not key:
        return None
    body = json.dumps({
        "model": cfg.get("groq_model", "llama-3.1-8b-instant"),
        "max_tokens": 1024,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
    }).encode()
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


def _call_ollama(cfg: dict, prompt: str) -> str | None:
    url = cfg.get("ollama_url", "http://localhost:11434")
    model = cfg.get("ollama_model", "llama3.2:3b")
    body = json.dumps({
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
    }).encode()
    req = urllib.request.Request(
        f"{url}/api/chat",
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    return data["message"]["content"]


_PROVIDERS: list[tuple[str, object]] = [
    ("claude", _call_claude),
    ("gemini", _call_gemini),
    ("groq", _call_groq),
    ("ollama", _call_ollama),
]


# --------------------------------------------------------------------------- #
# Status & routing
# --------------------------------------------------------------------------- #
def provider_status(cfg: dict | None = None) -> dict:
    """Return availability info for every provider (used by the Settings UI)."""
    if cfg is None:
        cfg = hub.load_config()

    from . import ollama_setup
    ollama_url = cfg.get("ollama_url", "http://localhost:11434")
    ollama_running = ollama_setup.is_running(ollama_url)
    ollama_models = ollama_setup.list_local_models(ollama_url) if ollama_running else []

    return {
        "claude": {
            "available": bool(cfg.get("anthropic_api_key")),
            "label": "Key set" if cfg.get("anthropic_api_key") else "No key",
        },
        "gemini": {
            "available": bool(cfg.get("gemini_api_key")),
            "label": "Key set" if cfg.get("gemini_api_key") else "No key",
        },
        "groq": {
            "available": bool(cfg.get("groq_api_key")),
            "label": "Key set" if cfg.get("groq_api_key") else "No key",
        },
        "ollama": {
            "available": ollama_running and bool(ollama_models),
            "running": ollama_running,
            "installed": ollama_setup.is_installed(),
            "models": ollama_models,
            "label": (
                f"Running · {cfg.get('ollama_model','llama3.2:3b')}"
                if ollama_running and ollama_models
                else ("Running — no model yet" if ollama_running else "Not detected")
            ),
        },
    }


def ai_available() -> str | bool:
    """Return the active provider name (truthy), or False if none available."""
    cfg = hub.load_config()
    if not cfg.get("ai_enabled", True):
        return False
    chosen = cfg.get("ai_provider", "auto")
    status = provider_status(cfg)
    candidates = [chosen] if chosen != "auto" else [p[0] for p in _PROVIDERS]
    for name in candidates:
        if status.get(name, {}).get("available"):
            return name
    return False


def enrich(text: str, url: str = "") -> dict | None:
    """Run enrichment with the configured/available provider. Returns None on failure."""
    cfg = hub.load_config()
    if not cfg.get("ai_enabled", True):
        return None
    prompt = _build_prompt(text, url)
    chosen = cfg.get("ai_provider", "auto")
    order = [p for p in _PROVIDERS] if chosen == "auto" else [(n, f) for n, f in _PROVIDERS if n == chosen]
    for name, call in order:
        try:
            raw = call(cfg, prompt)
            if raw:
                result = _parse(raw)
                if result:
                    return result
        except Exception as exc:
            print(f"[ai] {name}: {exc}")
    return None
