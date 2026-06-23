"""freeaiagent_setup.py – Magpie's interface to the local freeaiagent service.

freeaiagent (https://pypi.org/project/freeaiagent/) is a separate pip package
that runs a persistent HTTP server (default localhost:7731). It owns the local
LLM (llamafile/GGUF), Ollama/Groq routing, the model catalog, downloads, and
conversation context, so Magpie doesn't have to.

As of freeaiagent 1.2.0 this module talks to it through the bundled
``freeaiagent.Client`` SDK (catalog/pull-with-progress/config). The import is
guarded: if freeaiagent isn't importable, every function degrades gracefully so
the cloud providers (Claude/Gemini/Groq) keep working.

Install:  pip install freeaiagent
Start:    freeaiagent start
Docs:     http://localhost:7731/docs  (when running)
"""
from __future__ import annotations

from urllib.parse import urlparse

DEFAULT_URL = "http://localhost:7731"

# Guarded import — freeaiagent is a declared dependency, but its absence must
# not crash app startup (server.py imports this module at top level).
try:
    from freeaiagent import Client
    _IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - exercised only without the dep
    Client = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc

_clients: dict[str, object] = {}


def _client(url: str = DEFAULT_URL):
    """Return a cached Client pinned to ``url``'s port, or None if unavailable."""
    if Client is None:
        return None
    c = _clients.get(url)
    if c is None:
        port = urlparse(url).port or 7731
        c = Client(name="magpie", port=port)
        _clients[url] = c
    return c


def is_installed() -> bool:
    """True if the freeaiagent package is importable in this environment."""
    return Client is not None


def is_running(url: str = DEFAULT_URL) -> bool:
    c = _client(url)
    return bool(c and c.is_running())


def get_health(url: str = DEFAULT_URL) -> dict:
    """Return /health payload, or {"status": "offline"} on failure."""
    c = _client(url)
    if not c:
        return {"status": "offline"}
    try:
        return c.health()
    except Exception:
        return {"status": "offline"}


def list_models(url: str = DEFAULT_URL) -> list[str]:
    """Models available on the active backend right now."""
    c = _client(url)
    if not c:
        return []
    try:
        return c.models.list()
    except Exception:
        return []


def get_catalog(url: str = DEFAULT_URL) -> list[dict]:
    """Curated downloadable catalog; each entry flagged ``installed``.

    Entry keys: name, display, kind, size_gb, min_ram_gb, tier, description,
    installed.
    """
    c = _client(url)
    if not c:
        return []
    try:
        return c.models.catalog()
    except Exception:
        return []


def get_installed(url: str = DEFAULT_URL) -> list[dict]:
    """Local model files on disk (name, size_mb, kind, path)."""
    c = _client(url)
    if not c:
        return []
    try:
        return c.models.installed()
    except Exception:
        return []


def set_default_model(model: str, url: str = DEFAULT_URL) -> dict:
    """Set the agent's default model. Returns {ok, msg}."""
    c = _client(url)
    if not c:
        return {"ok": False, "msg": "freeaiagent not installed. Run:  pip install freeaiagent"}
    try:
        c.config.set("default_model", model)
        return {"ok": True, "msg": f"Default model set to {model}"}
    except Exception as exc:
        return {"ok": False, "msg": f"Could not set model: {exc}"}


def pull_model(model: str, url: str = DEFAULT_URL):
    """Yield progress dicts while downloading ``model`` server-side.

    Each dict mirrors a freeaiagent PullProgress event:
    {type, phase, label, pct, downloaded_mb, total_mb, speed_mbps, path, error}
    where type is one of start | progress | done | error. Raises if the SDK is
    unavailable.
    """
    c = _client(url)
    if not c:
        raise RuntimeError("freeaiagent not installed. Run:  pip install freeaiagent")
    for p in c.pull(model):
        yield {
            "type": p.type,
            "phase": p.phase,
            "label": p.label,
            "pct": p.pct,
            "downloaded_mb": p.downloaded_mb,
            "total_mb": p.total_mb,
            "speed_mbps": p.speed_mbps,
            "path": p.path,
            "error": p.error,
        }


def start_agent(url: str = DEFAULT_URL) -> dict:
    """Launch the freeaiagent server in the background. Returns {ok, msg}."""
    c = _client(url)
    if c and c.is_running():
        h = get_health(url)
        return {
            "ok": True,
            "msg": f"Already running · {h.get('active_backend','?')} · {h.get('default_model','?')}",
        }
    if not c:
        return {
            "ok": False,
            "msg": "freeaiagent not installed. Run:  pip install freeaiagent",
        }
    try:
        c.start(wait=20.0)
    except Exception as exc:
        return {
            "ok": False,
            "msg": f"Agent did not start: {exc} — try `freeaiagent start` in a terminal.",
        }
    h = get_health(url)
    return {
        "ok": True,
        "msg": f"Agent started · {h.get('active_backend','?')} · {h.get('default_model','?')}",
    }


def call_task(task: str, input_text: str = "", system: str = "",
              url: str = DEFAULT_URL, timeout: int = 120) -> str:
    """Run a one-shot /task and return the result string. Raises on failure."""
    c = _client(url)
    if not c:
        raise RuntimeError("freeaiagent not installed. Run:  pip install freeaiagent")
    return c.task(task, input=input_text or None, system=system or None)
