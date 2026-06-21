"""freeaiagent_setup.py – thin interface to the user's local freeaiagent service.

freeaiagent (https://pypi.org/project/freeaiagent/) is a separate pip package
that runs a persistent HTTP server on localhost:7731. It owns Ollama/Groq
backend management, model selection, and conversation context so Magpie
doesn't have to.

Install:  pip install freeaiagent
Start:    freeaiagent start
Docs:     http://localhost:7731/docs  (when running)
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
import urllib.request

DEFAULT_URL = "http://localhost:7731"


def is_running(url: str = DEFAULT_URL) -> bool:
    try:
        urllib.request.urlopen(f"{url}/health", timeout=2)
        return True
    except Exception:
        return False


def is_installed() -> bool:
    return shutil.which("freeaiagent") is not None


def get_health(url: str = DEFAULT_URL) -> dict:
    """Return /health payload, or {"status": "offline"} on failure."""
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=3) as resp:
            return json.loads(resp.read())
    except Exception:
        return {"status": "offline"}


def list_models(url: str = DEFAULT_URL) -> list[str]:
    try:
        with urllib.request.urlopen(f"{url}/models", timeout=3) as resp:
            return json.loads(resp.read()).get("models", [])
    except Exception:
        return []


def start_agent(url: str = DEFAULT_URL) -> dict:
    """Launch `freeaiagent start` in the background. Returns {ok, msg}."""
    if is_running(url):
        h = get_health(url)
        return {
            "ok": True,
            "msg": f"Already running · {h.get('active_backend','?')} · {h.get('default_model','?')}",
        }
    if not is_installed():
        return {
            "ok": False,
            "msg": "freeaiagent not installed. Run:  pip install freeaiagent",
        }
    try:
        subprocess.Popen(
            ["freeaiagent", "start"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        return {"ok": False, "msg": f"Could not launch agent: {exc}"}

    for _ in range(15):
        time.sleep(1)
        if is_running(url):
            h = get_health(url)
            return {
                "ok": True,
                "msg": f"Agent started · {h.get('active_backend','?')} · {h.get('default_model','?')}",
            }
    return {
        "ok": False,
        "msg": "Agent launched but did not respond — try `freeaiagent start` in a terminal.",
    }


def call_task(task: str, input_text: str = "", system: str = "",
              url: str = DEFAULT_URL, timeout: int = 120) -> str:
    """POST /task and return the result string. Raises on failure."""
    payload: dict = {"task": task}
    if input_text:
        payload["input"] = input_text
    if system:
        payload["system"] = system
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{url}/task",
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    return data["result"]
