"""capture.py - fetch a URL and turn it into note fields.

Generic pages: extracts <title>, meta tags, AND full article body text via a
paragraph extractor that skips nav/header/footer/ads.

X/Twitter status URLs: use the public syndication endpoint (works server-side;
browsers get HTTP 402).

Always degrades gracefully — if rich content can't be fetched we still return
the URL and whatever title we found so capture never hard-fails.
"""
from __future__ import annotations

import json
import math
import re
import urllib.request
from html.parser import HTMLParser

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

X_STATUS_RE = re.compile(
    r"https?://(?:www\.)?(?:x|twitter)\.com/[^/]+/status/(\d+)", re.I
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


def _capture_tweet(url: str, tweet_id: str) -> dict:
    token = _syndication_token(tweet_id)
    api = (
        f"https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}"
        f"&token={token}&lang=en"
    )
    try:
        data = json.loads(_get(api))
    except Exception:
        try:
            data = json.loads(_get(
                f"https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}&token=a"
            ))
        except Exception:
            return {
                "title": f"Tweet {tweet_id}",
                "body": f"(Could not fetch tweet text automatically.)\n\nSource: {url}",
                "links": [url],
                "source": "x",
                "type": "link",
                "tags": [],
                "_partial": True,
            }
    text = data.get("text", "")
    author = data.get("user", {}) or {}
    name = author.get("name", "")
    handle = author.get("screen_name", "")
    created = (data.get("created_at") or "")[:10]  # date only

    title = ""
    for line in text.strip().split("\n"):
        cleaned = re.sub(r"https?://\S+", "", line).strip()
        if cleaned:
            title = cleaned[:80]
            break
    if not title:
        title = f"Tweet by @{handle}" if handle else f"Tweet {tweet_id}"

    byline = f"**{name}** (@{handle})" + (f" — {created}" if created else "")
    body = f"{byline}\n\n{text}\n\nSource: {url}"

    return {
        "title": title,
        "body": body,
        "links": [url],
        "source": "x",
        "type": "idea",
        "tags": [],
        "author": name or handle,
        "published": created,
    }


# --------------------------------------------------------------------------- #
# Generic pages
# --------------------------------------------------------------------------- #
class _MetaParser(HTMLParser):
    """Extract <title> and key <meta> fields including author and publish date."""

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
            prop = (a.get("property") or a.get("name") or "").lower()
            content = (a.get("content") or "").strip()
            if prop in ("og:title",) and not self.title:
                self.title = content
            elif prop in ("description", "og:description") and not self.description:
                self.description = content
            elif prop in ("author", "og:author", "article:author", "byl") and not self.author:
                self.author = content
            elif prop in ("article:published_time", "og:published_time", "pubdate", "date") and not self.published:
                self.published = content[:10]

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title and not self.title:
            self.title = data.strip()


class _ArticleExtractor(HTMLParser):
    """Pull readable paragraph text, skipping boilerplate regions."""

    # Tags whose subtree we skip entirely.
    SKIP = {
        "script", "style", "nav", "header", "footer", "aside",
        "noscript", "iframe", "form", "button", "figure", "figcaption",
        "menu", "dialog", "template",
    }

    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self._in_p = False
        self._buf: list[str] = []
        self._paras: list[str] = []

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t in self.SKIP:
            self._skip_depth += 1
        if t == "p" and not self._skip_depth:
            self._in_p = True
            self._buf = []

    def handle_endtag(self, tag):
        t = tag.lower()
        if t in self.SKIP and self._skip_depth:
            self._skip_depth -= 1
        if t == "p" and self._in_p:
            text = " ".join(self._buf).strip()
            # keep paragraphs that are long enough to be real content
            if len(text) > 40:
                self._paras.append(text)
            self._in_p = False

    def handle_data(self, data):
        if self._in_p and not self._skip_depth:
            chunk = data.strip()
            if chunk:
                self._buf.append(chunk)

    def result(self) -> str:
        return "\n\n".join(self._paras)


def _capture_page(url: str) -> dict:
    try:
        html = _get(url)

        meta = _MetaParser()
        meta.feed(html)

        extractor = _ArticleExtractor()
        extractor.feed(html)
        full_text = extractor.result()

        title = (meta.title or url).strip()[:120]

        # Build structured note body
        parts = []
        if meta.author or meta.published:
            byline = " | ".join(filter(None, [meta.author, meta.published]))
            parts.append(f"*{byline}*")
        if full_text:
            # cap at ~10 000 chars to keep notes manageable
            parts.append(full_text[:10_000])
        elif meta.description:
            parts.append(meta.description.strip())
        parts.append(f"\nSource: {url}")

        body = "\n\n".join(parts)

        return {
            "title": title,
            "body": body,
            "links": [url],
            "source": "web",
            "type": "link",
            "tags": [],
            "author": meta.author,
            "published": meta.published,
            # Full raw text forwarded to AI for richer enrichment (not stored in note).
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


def capture(url: str) -> dict:
    """Return note fields for a URL (X-aware). Never raises for fetch failures."""
    url = (url or "").strip()
    m = X_STATUS_RE.match(url)
    if m:
        return _capture_tweet(url, m.group(1))
    return _capture_page(url)


if __name__ == "__main__":
    import sys
    result = capture(sys.argv[1] if len(sys.argv) > 1 else "")
    result.pop("_full_text", None)
    print(json.dumps(result, indent=2))
