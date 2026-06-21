"""ollama_setup.py – detect, download, install, and manage Ollama locally.

All functions are safe to call even when Ollama is not present; they either
return sensible defaults or yield {"stage": "error", ...} events.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
import urllib.error

INSTALLER_URL = (
    "https://github.com/ollama/ollama/releases/latest/download/OllamaSetup.exe"
)
DEFAULT_MODEL = "llama3.2:3b"


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #
def is_running(url: str = "http://localhost:11434") -> bool:
    try:
        urllib.request.urlopen(f"{url}/api/tags", timeout=2)
        return True
    except Exception:
        return False


def is_installed() -> bool:
    return shutil.which("ollama") is not None


def list_local_models(url: str = "http://localhost:11434") -> list[str]:
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=5) as resp:
            data = json.loads(resp.read())
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# Download installer (Windows)
# --------------------------------------------------------------------------- #
def _installer_dest() -> str:
    return os.path.join(tempfile.gettempdir(), "OllamaSetup.exe")


def download_installer_stream(url: str = INSTALLER_URL):
    """Yield download-progress dicts while saving OllamaSetup.exe to temp."""
    dest = _installer_dest()
    req = urllib.request.Request(url, headers={"User-Agent": "Magpie/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            downloaded = 0
            with open(dest, "wb") as fh:
                while True:
                    block = resp.read(65536)
                    if not block:
                        break
                    fh.write(block)
                    downloaded += len(block)
                    pct = int(downloaded * 100 / total) if total else 0
                    yield {
                        "stage": "download",
                        "pct": pct,
                        "downloaded": downloaded,
                        "total": total,
                        "msg": f"Downloading Ollama… {pct}%",
                    }
    except Exception as exc:
        yield {"stage": "error", "msg": f"Download failed: {exc}"}
        return
    yield {"stage": "download", "pct": 100, "done": True, "msg": "Download complete."}


# --------------------------------------------------------------------------- #
# Install
# --------------------------------------------------------------------------- #
def run_installer_stream():
    """Launch OllamaSetup.exe /S, poll until the service is up, yield events."""
    dest = _installer_dest()
    if not os.path.exists(dest):
        yield {"stage": "error", "msg": "Installer not found — download it first."}
        return

    yield {"stage": "install", "msg": "Running installer (a UAC prompt may appear)…"}
    try:
        subprocess.Popen([dest, "/S"])
    except Exception as exc:
        yield {"stage": "error", "msg": f"Could not launch installer: {exc}"}
        return

    for i in range(60):
        time.sleep(1)
        if is_running():
            yield {
                "stage": "install",
                "done": True,
                "msg": "Ollama installed and running.",
            }
            return
        yield {"stage": "install", "msg": f"Waiting for Ollama service… ({i + 1}s)"}

    yield {
        "stage": "error",
        "msg": "Ollama installed but did not start. Try restarting your PC.",
    }


# --------------------------------------------------------------------------- #
# Model pull (streams Ollama's own progress)
# --------------------------------------------------------------------------- #
def pull_model_stream(model: str, url: str = "http://localhost:11434"):
    """Yield normalised progress dicts while pulling a model from Ollama."""
    body = json.dumps({"model": model}).encode()
    req = urllib.request.Request(
        f"{url}/api/pull",
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            for line in resp:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                out: dict = {"stage": "pull", "status": data.get("status", "")}
                if "total" in data and "completed" in data and data["total"]:
                    out["pct"] = int(data["completed"] * 100 / data["total"])
                    out["total"] = data["total"]
                    out["completed"] = data["completed"]
                    out["msg"] = f"{data.get('status','')} … {out['pct']}%"
                else:
                    out["msg"] = data.get("status", "")
                if data.get("status") == "success":
                    out["done"] = True
                yield out
    except Exception as exc:
        yield {"stage": "error", "msg": str(exc)}
