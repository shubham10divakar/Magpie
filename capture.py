"""capture.py - fetch a URL and turn it into note fields.

Generic pages: extract <title>, meta description, og: tags via stdlib html.parser.
X/Twitter status URLs: use the public syndication endpoint (works server-side,
which is exactly what a browser fetch gets blocked on with HTTP 402).

Always degrades gracefully: if rich content can't be fetched, we still return the
URL and whatever title we found so capture never hard-fails.
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
        # token can drift; retry with a trivial token before giving up
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
    created = data.get("created_at", "")
    # title = first meaningful (non-URL) line of text, else fall back to author
    title = ""
    for line in text.strip().split("\n"):
        cleaned = re.sub(r"https?://\S+", "", line).strip()
        if cleaned:
            title = cleaned[:80]
            break
    if not title:
        title = f"Tweet by @{handle}" if handle else f"Tweet {tweet_id}"
    body = (
        f"**{name}** (@{handle}) — {created}\n\n"
        f"{text}\n\n"
        f"Source: {url}"
    )
    return {
        "title": title,
        "body": body,
        "links": [url],
        "source": "x",
        "type": "idea",
        "tags": [],
    }


# --------------------------------------------------------------------------- #
# Generic pages
# --------------------------------------------------------------------------- #
class _MetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.description = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            a = dict(attrs)
            prop = (a.get("property") or a.get("name") or "").lower()
            content = a.get("content") or ""
            if prop in ("og:title",) and not self.title:
                self.title = content
            elif prop in ("description", "og:description") and not self.description:
                self.description = content

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title and not self.title:
            self.title = data.strip()


def _capture_page(url: str) -> dict:
    try:
        html = _get(url)
        parser = _MetaParser()
        parser.feed(html)
        title = (parser.title or url).strip()[:120]
        desc = parser.description.strip()
        body = f"{desc}\n\nSource: {url}" if desc else f"Source: {url}"
        return {
            "title": title,
            "body": body,
            "links": [url],
            "source": "web",
            "type": "link",
            "tags": [],
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
    print(json.dumps(capture(sys.argv[1] if len(sys.argv) > 1 else ""), indent=2))
