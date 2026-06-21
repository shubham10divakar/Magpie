"""capture.py – fetch a URL and turn it into note fields.

Handlers (all degrade gracefully on fetch failure):
  • X/Twitter status URLs    – tweet text + author; unrolls reply-chains
  • YouTube watch/short URLs – title, channel, duration, auto-captions
  • Generic pages            – <p>/heading/li extraction + density fallback
  • RSS/Atom feeds           – capture_feed() returns list of item dicts
"""
from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
import urllib.request
from html.parser import HTMLParser

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

X_STATUS_RE = re.compile(
    r"https?://(?:www\.)?(?:x|twitter)\.com/[^/]+/status/(\d+)", re.I
)
YT_RE = re.compile(
    r"https?://(?:www\.)?(?:youtube\.com/watch\?[^#\s]*v=|youtu\.be/)"
    r"([a-zA-Z0-9_-]{11})",
    re.I,
)


def _get(url: str, headers=None, timeout=15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


# --------------------------------------------------------------------------- #
# X / Twitter
# --------------------------------------------------------------------------- #
def _syndication_token(tweet_id: str) -> str:
    """Mirror Twitter's JS: ((id/1e15)*pi) base36, strip '0' and '.'."""
    num = (int(tweet_id) / 1e15) * math.pi
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    int_part = int(num)
    frac = num - int_part
    s = ""
    n = int_part
    if n == 0:
        s = "0"
    while n > 0:
        s = digits[n % 36] + s
        n //= 36
    s += "."
    count = 0
    while frac > 0 and count < 18:
        frac *= 36
        d = int(frac)
        s += digits[d]
        frac -= d
        count += 1
    return s.replace("0", "").replace(".", "")


def _fetch_tweet(tweet_id: str) -> dict | None:
    """Fetch a single tweet from the syndication API. Returns None on failure."""
    token = _syndication_token(tweet_id)
    for url in [
        f"https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}&token={token}&lang=en",
        f"https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}&token=a",
    ]:
        try:
            return json.loads(_get(url, timeout=8))
        except Exception:
            continue
    return None


def _capture_tweet(url: str, tweet_id: str) -> dict:
    data = _fetch_tweet(tweet_id)
    if not data:
        return {
            "title": f"Tweet {tweet_id}",
            "body": f"(Could not fetch tweet text automatically.)\n\nSource: {url}",
            "links": [url],
            "source": "x",
            "type": "link",
            "tags": [],
            "_partial": True,
        }

    author_handle = ((data.get("user") or {}).get("screen_name") or "").lower()

    # Walk backward via in_reply_to_status_id_str to unroll threads.
    chain = [data]
    seen = {tweet_id}
    cur = data
    for _ in range(9):  # max 10 tweets total
        parent_id = cur.get("in_reply_to_status_id_str") or ""
        if not parent_id or parent_id in seen:
            break
        parent = _fetch_tweet(parent_id)
        if not parent:
            break
        if ((parent.get("user") or {}).get("screen_name") or "").lower() != author_handle:
            break  # different author — not a self-thread
        seen.add(parent_id)
        chain.append(parent)
        cur = parent

    chain.reverse()  # oldest first
    is_thread = len(chain) > 1

    first = chain[0]
    author = (first.get("user") or {})
    name = author.get("name", "")
    handle = author.get("screen_name", "")
    created = (first.get("created_at") or "")[:10]

    first_text = first.get("text", "")
    title = ""
    for line in first_text.strip().split("\n"):
        cleaned = re.sub(r"https?://\S+", "", line).strip()
        if cleaned:
            title = cleaned[:80]
            break
    if not title:
        title = f"Tweet by @{handle}" if handle else f"Tweet {tweet_id}"

    byline = f"**{name}** (@{handle})" + (f" — {created}" if created else "")

    if is_thread:
        title = f"[Thread] {title}"
        parts = [f"{i}. {t.get('text', '')}" for i, t in enumerate(chain, 1)]
        body = f"{byline}\n\n" + "\n\n".join(parts) + f"\n\nSource: {url}"
    else:
        body = f"{byline}\n\n{first_text}\n\nSource: {url}"

    return {
        "title": title,
        "body": body,
        "links": [url],
        "source": "x",
        "type": "idea",
        "tags": ["thread"] if is_thread else [],
        "author": name or handle,
        "published": created,
    }


# --------------------------------------------------------------------------- #
# HTML parsers
# --------------------------------------------------------------------------- #
class _MetaParser(HTMLParser):
    """Extract <title> and key <meta> fields: author, description, publish date."""

    def __init__(self):
        super().__init__()
        self.title = ""
        self.description = ""
        self.author = ""
        self.published = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            a = dict(attrs)
            prop = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            content = (a.get("content") or "").strip()
            if prop == "og:title" and not self.title:
                self.title = content
            elif prop in ("description", "og:description") and not self.description:
                self.description = content
            elif prop in ("author", "og:author", "article:author", "byl") and not self.author:
                self.author = content
            elif prop in (
                "article:published_time", "og:published_time",
                "pubdate", "date", "datepublished",
            ) and not self.published:
                self.published = content[:10]

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title and not self.title:
            self.title = data.strip()


class _ArticleExtractor(HTMLParser):
    """Extract readable text from <p>, headings, <li>, <blockquote>. Skips boilerplate."""

    SKIP = {
        "script", "style", "nav", "header", "footer", "aside",
        "noscript", "iframe", "form", "button", "figure", "figcaption",
        "menu", "dialog", "template",
    }
    HEADING_PREFIX = {"h1": "# ", "h2": "## ", "h3": "### ", "h4": "#### "}

    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self._tag = None
        self._buf: list[str] = []
        self._paras: list[str] = []

    def _flush(self, min_len=0):
        text = " ".join(self._buf).strip()
        if text and len(text) >= min_len:
            self._paras.append(text)
        self._buf = []
        self._tag = None

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t in self.SKIP:
            self._skip_depth += 1
        if self._skip_depth:
            return
        if t in ("p", "li", "blockquote") or t in self.HEADING_PREFIX:
            if self._tag:
                self._flush(40 if self._tag == "p" else 0)
            self._tag = t
            self._buf = []
            if t in self.HEADING_PREFIX:
                self._buf.append(self.HEADING_PREFIX[t])

    def handle_endtag(self, tag):
        t = tag.lower()
        if t in self.SKIP and self._skip_depth:
            self._skip_depth -= 1
        if t == self._tag:
            self._flush(40 if t == "p" else 0)

    def handle_data(self, data):
        if self._tag and not self._skip_depth:
            chunk = data.strip()
            if chunk:
                self._buf.append(chunk)

    def result(self) -> str:
        return "\n\n".join(self._paras)


class _DensityExtractor(HTMLParser):
    """Fallback for React/JS-heavy pages: find the <div> block with the highest
    text-to-markup density.  Score = text_len² / tag_count (semantic blocks get 2×).
    Each block's text is propagated upward so parents are always scored too."""

    SKIP = {
        "script", "style", "nav", "header", "footer", "aside",
        "noscript", "iframe", "form", "button", "template",
    }
    BLOCKS = {"div", "article", "main", "section", "body", "blockquote"}
    SEMANTIC = {"article", "main"}

    def __init__(self):
        super().__init__()
        self._stack: list[dict] = []
        self._skip = 0
        self._best_text = ""
        self._best_score = 0

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t in self.SKIP:
            self._skip += 1
            return
        if self._skip:
            return
        if t in self.BLOCKS:
            self._stack.append({"tag": t, "chunks": [], "tags": 0})
        elif self._stack:
            self._stack[-1]["tags"] += 1

    def handle_endtag(self, tag):
        t = tag.lower()
        if t in self.SKIP:
            if self._skip:
                self._skip -= 1
            return
        if self._skip:
            return
        if t in self.BLOCKS and self._stack:
            frame = self._stack.pop()
            text = "\n\n".join(c for c in frame["chunks"] if c)
            n_text = len(text)
            n_tags = max(1, frame["tags"])
            bonus = 2.0 if frame["tag"] in self.SEMANTIC else 1.0
            score = bonus * n_text * n_text / n_tags
            if score > self._best_score:
                self._best_score = score
                self._best_text = text
            if self._stack:
                self._stack[-1]["chunks"].extend(frame["chunks"])
                self._stack[-1]["tags"] += frame["tags"] + 1

    def handle_data(self, data):
        if self._skip or not self._stack:
            return
        chunk = data.strip()
        if chunk:
            self._stack[-1]["chunks"].append(chunk)

    def result(self) -> str:
        return self._best_text[:10_000]


# --------------------------------------------------------------------------- #
# YouTube
# --------------------------------------------------------------------------- #
def _yt_captions(video_id: str) -> str:
    """Fetch auto-captions as plain text via the public timedtext API."""
    try:
        xml_text = _get(
            f"https://www.youtube.com/api/timedtext?lang=en&v={video_id}&fmt=srv3",
            timeout=10,
        )
        root = ET.fromstring(xml_text)
        parts = []
        prev = ""
        for p in root.iter("p"):
            text = ET.tostring(p, encoding="unicode", method="text").strip()
            if text and text != prev:
                parts.append(text)
                prev = text
        return " ".join(parts)
    except Exception:
        return ""


def _capture_youtube(url: str, video_id: str) -> dict:
    try:
        html = _get(url)
    except Exception:
        return {
            "title": "YouTube video",
            "body": f"(Could not fetch video info.)\n\nSource: {url}",
            "links": [url],
            "source": "youtube",
            "type": "link",
            "tags": ["video"],
            "_partial": True,
        }

    meta = _MetaParser()
    meta.feed(html)

    title = (meta.title or f"YouTube {video_id}").strip()
    title = re.sub(r"\s*[-–]\s*YouTube\s*$", "", title).strip()

    channel = ""
    for pat in [r'"ownerChannelName"\s*:\s*"([^"\\]+)"',
                r'"channelName"\s*:\s*"([^"\\]+)"']:
        m = re.search(pat, html)
        if m:
            channel = m.group(1)
            break

    duration = ""
    m = re.search(r'"approxDurationMs"\s*:\s*"(\d+)"', html)
    if m:
        secs = int(m.group(1)) // 1000
        h, rem = divmod(secs, 3600)
        mi, s = divmod(rem, 60)
        duration = (f"{h}h " if h else "") + (f"{mi}m " if mi else "") + f"{s}s"
        duration = duration.strip()

    published = meta.published or ""
    if not published:
        m = re.search(r'"publishDate"\s*:\s*"(\d{4}-\d{2}-\d{2})"', html)
        if m:
            published = m.group(1)

    meta_parts = [p for p in [channel, duration, published[:10] if published else ""] if p]
    parts = []
    if meta_parts:
        parts.append(f"*{' · '.join(meta_parts)}*")
    if meta.description:
        parts.append(meta.description.strip()[:2000])

    captions = _yt_captions(video_id)
    if captions:
        parts.append(f"**Transcript:**\n\n{captions[:8000]}")

    parts.append(f"\nSource: {url}")

    return {
        "title": title,
        "body": "\n\n".join(parts),
        "links": [url],
        "source": "youtube",
        "type": "link",
        "tags": ["video"],
        "author": channel or meta.author,
        "published": published[:10] if published else "",
    }


# --------------------------------------------------------------------------- #
# RSS / Atom feed
# --------------------------------------------------------------------------- #
def _strip_html(s: str) -> str:
    class _S(HTMLParser):
        def __init__(self): super().__init__(); self.out = []
        def handle_data(self, d): self.out.append(d)
    p = _S()
    p.feed(s or "")
    return " ".join("".join(p.out).split())


_ATOM_NS = "http://www.w3.org/2005/Atom"
_DC_NS = "http://purl.org/dc/elements/1.1/"
_CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"


def capture_feed(url: str, limit: int = 30) -> list[dict]:
    """Fetch an RSS 2.0 or Atom feed; return a list of note-field dicts."""
    try:
        xml_text = _get(url)
    except Exception as exc:
        raise RuntimeError(f"Could not fetch feed: {exc}") from exc

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise RuntimeError(f"Feed is not valid XML: {exc}") from exc

    is_atom = _ATOM_NS in (root.tag or "")
    items: list[dict] = []

    if is_atom:
        for e in root.findall(f"{{{_ATOM_NS}}}entry")[:limit]:
            def _at(tag): return (e.findtext(f"{{{_ATOM_NS}}}{tag}") or "").strip()
            link_el = e.find(f"{{{_ATOM_NS}}}link[@rel='alternate']")
            if link_el is None:
                link_el = e.find(f"{{{_ATOM_NS}}}link")
            link = (link_el.get("href") if link_el is not None else "") or ""
            name_el = e.find(f".//{{{_ATOM_NS}}}name")
            author = (name_el.text if name_el is not None else "") or ""
            content_el = e.find(f"{{{_ATOM_NS}}}content")
            summary_el = e.find(f"{{{_ATOM_NS}}}summary")
            raw = ((content_el.text if content_el is not None else "")
                   or (summary_el.text if summary_el is not None else ""))
            items.append({
                "title": _at("title") or link or "Untitled",
                "body": _strip_html(raw) or _at("summary"),
                "links": [link] if link else [],
                "source": "rss",
                "type": "link",
                "tags": [],
                "author": author,
                "published": (_at("published") or _at("updated"))[:10],
            })
    else:
        channel = root.find("channel") or root
        for item in channel.findall("item")[:limit]:
            def _t(tag): return (item.findtext(tag) or "").strip()
            desc = (_t("description")
                    or _t(f"{{{_CONTENT_NS}}}encoded")
                    or "")
            link = _t("link")
            author = _t("author") or _t(f"{{{_DC_NS}}}creator")
            pub = _t("pubDate") or _t(f"{{{_DC_NS}}}date")
            items.append({
                "title": _t("title") or link or "Untitled",
                "body": _strip_html(desc),
                "links": [link] if link else [],
                "source": "rss",
                "type": "link",
                "tags": [],
                "author": author,
                "published": pub[:10] if pub else "",
            })

    return items


# --------------------------------------------------------------------------- #
# Generic pages
# --------------------------------------------------------------------------- #
def _capture_page(url: str) -> dict:
    try:
        html = _get(url)

        meta = _MetaParser()
        meta.feed(html)

        extractor = _ArticleExtractor()
        extractor.feed(html)
        full_text = extractor.result()

        # Fallback: density extractor for React/JS-heavy pages with few <p> tags.
        if len(full_text) < 200:
            density = _DensityExtractor()
            density.feed(html)
            density_text = density.result()
            if len(density_text) > len(full_text):
                full_text = density_text

        title = (meta.title or url).strip()[:120]

        parts = []
        if meta.author or meta.published:
            byline = " | ".join(filter(None, [meta.author, meta.published]))
            parts.append(f"*{byline}*")
        if full_text:
            parts.append(full_text[:10_000])
        elif meta.description:
            parts.append(meta.description.strip())
        parts.append(f"\nSource: {url}")

        return {
            "title": title,
            "body": "\n\n".join(parts),
            "links": [url],
            "source": "web",
            "type": "link",
            "tags": [],
            "author": meta.author,
            "published": meta.published,
            "_full_text": full_text,
        }
    except Exception:
        return {
            "title": url,
            "body": f"(Could not fetch page automatically.)\n\nSource: {url}",
            "links": [url],
            "source": "web",
            "type": "link",
            "tags": [],
            "_partial": True,
        }


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def capture(url: str) -> dict:
    """Return note fields for a URL (X, YouTube, and generic-page aware).
    Never raises for fetch failures."""
    url = (url or "").strip()
    m = X_STATUS_RE.match(url)
    if m:
        return _capture_tweet(url, m.group(1))
    m = YT_RE.search(url)
    if m:
        return _capture_youtube(url, m.group(1))
    return _capture_page(url)


if __name__ == "__main__":
    import sys
    result = capture(sys.argv[1] if len(sys.argv) > 1 else "")
    result.pop("_full_text", None)
    print(json.dumps(result, indent=2))
