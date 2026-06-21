"""vault_io.py - read/write Markdown notes with YAML frontmatter.

Dependency-free. Targets the subset of YAML we use:
  - scalars (strings, ints, ISO dates, booleans, null)
  - quoted strings ('...' / "...")
  - inline lists: [a, b, c]
  - block lists:
        key:
          - a
          - b

Frontmatter is delimited by a leading '---' line and a closing '---' line.
Round-trips cleanly so files stay git-friendly and Obsidian-compatible.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime

# Stable key order so serialized frontmatter is deterministic / clean.
KEY_ORDER = [
    "title", "type", "status", "tags", "due", "remind",
    "links", "source", "ai_summary", "created", "updated",
]


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def _coerce_scalar(value: str):
    """Turn a raw YAML scalar string into a Python value."""
    v = value.strip()
    if v == "" or v in ("~", "null", "Null", "NULL"):
        return None
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    if v in ("true", "True", "TRUE"):
        return True
    if v in ("false", "False", "FALSE"):
        return False
    # ISO date -> keep as plain string (we treat dates as strings everywhere)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return v
    if re.fullmatch(r"-?\d+", v):
        try:
            return int(v)
        except ValueError:
            return v
    return v


def _parse_inline_list(value: str):
    inner = value.strip()[1:-1].strip()
    if not inner:
        return []
    # naive split on commas (our values don't contain commas)
    return [_coerce_scalar(part) for part in inner.split(",") if part.strip() != ""]


def parse_frontmatter(text: str):
    """Return (meta: dict, body: str)."""
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    # find closing '---'
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, text

    fm_lines = lines[1:end]
    body = "\n".join(lines[end + 1:])
    if body.startswith("\n"):
        body = body[1:]

    meta: dict = {}
    i = 0
    while i < len(fm_lines):
        line = fm_lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        m = re.match(r"^([A-Za-z0-9_\-]+):\s*(.*)$", line)
        if not m:
            i += 1
            continue
        key, rest = m.group(1), m.group(2)
        rest = rest.strip()
        if rest.startswith("[") and rest.endswith("]"):
            meta[key] = _parse_inline_list(rest)
        elif rest == "":
            # could be a block list or just an empty scalar
            block = []
            j = i + 1
            while j < len(fm_lines) and re.match(r"^\s*-\s+", fm_lines[j]):
                item = re.sub(r"^\s*-\s+", "", fm_lines[j]).strip()
                block.append(_coerce_scalar(item))
                j += 1
            if block:
                meta[key] = block
                i = j
                continue
            meta[key] = None
        else:
            meta[key] = _coerce_scalar(rest)
        i += 1
    return meta, body


# --------------------------------------------------------------------------- #
# Serializing
# --------------------------------------------------------------------------- #
def _needs_quote(s: str) -> bool:
    if s == "":
        return True
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return False
    # quote if it contains yaml-significant characters
    return bool(re.search(r"[:#\[\]{}\n]|^\s|\s$", s)) or s in (
        "true", "false", "null", "True", "False", "Null"
    )


def _dump_scalar(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    s = str(value)
    if _needs_quote(s):
        s = s.replace('"', '\\"')
        return f'"{s}"'
    return s


def dump_frontmatter(meta: dict, body: str) -> str:
    keys = [k for k in KEY_ORDER if k in meta] + [
        k for k in meta if k not in KEY_ORDER
    ]
    out = ["---"]
    for key in keys:
        value = meta[key]
        if isinstance(value, list):
            if not value:
                out.append(f"{key}: []")
            else:
                rendered = ", ".join(_dump_scalar(v) for v in value)
                out.append(f"{key}: [{rendered}]")
        else:
            out.append(f"{key}: {_dump_scalar(value)}".rstrip())
    out.append("---")
    out.append("")
    out.append(body.rstrip("\n"))
    out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# File helpers
# --------------------------------------------------------------------------- #
def read_note(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    meta, body = parse_frontmatter(text)
    return meta, body


def write_note(path: str, meta: dict, body: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(dump_frontmatter(meta, body))


def read_frontmatter_only(path: str):
    """Fast path for scans: read just enough to parse frontmatter."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            head = fh.read(8192)
    except OSError:
        return {}
    meta, _ = parse_frontmatter(head)
    return meta
