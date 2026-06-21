"""Helpers for automation scripts.

Import these in any script under automations/ to write into the same vault the
app uses. Example:

    from _helpers import add_note, capture_url
    add_note(title="An idea", category="AI-ML", subcategory="LLM agents",
             body="...", tags=["agents"])
    capture_url("https://x.com/user/status/123")
"""
from __future__ import annotations

import os
import sys

# Make the magpie package importable when running these scripts straight from
# the repo (no install needed). If Magpie is pip-installed, this is harmless.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from magpie import ai       # noqa: E402
from magpie import capture  # noqa: E402
from magpie import hub      # noqa: E402


def add_note(title="Untitled", category="Inbox", subcategory="", body="", **meta):
    """Create a note in the vault. Returns its relative path."""
    hub.ensure_home()
    meta.setdefault("source", "automation")
    return hub.create_note(category=category, subcategory=subcategory,
                           title=title, body=body, **meta)


def capture_url(url, enrich=True, category="Inbox"):
    """Fetch a URL (X/Twitter-aware) and file it. Returns the note path."""
    fields = capture.capture(url)
    suggestion = ai.enrich(fields.get("body", ""),
                           fields.get("links", [""])[0] if fields.get("links") else "") if enrich else None
    s = suggestion or {}
    return add_note(
        title=s.get("title") or fields["title"],
        category=s.get("category") or category,
        subcategory=s.get("subcategory") or "",
        body=fields["body"],
        type=s.get("type") or fields.get("type", "idea"),
        tags=s.get("tags") or fields.get("tags", []),
        links=fields.get("links", []),
        source=fields.get("source", "automation"),
        ai_summary=s.get("summary", ""),
    )
