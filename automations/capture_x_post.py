"""Capture an X/Twitter post (or any URL) into the Inbox.

Usage:
    python automations/capture_x_post.py https://x.com/user/status/123
"""
import sys

from _helpers import capture_url

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python automations/capture_x_post.py <url>")
        raise SystemExit(1)
    path = capture_url(sys.argv[1])
    print(f"Captured -> vault/{path}")
