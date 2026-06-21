"""server.py - local HTTP server for Magpie (idea & project hub).

Serves the web/ UI and a JSON API at /api/*. Runs a background thread that
periodically scans the vault for due dates and raises Windows toasts while the
app is open. Standard library only.
"""
from __future__ import annotations

import json
import os
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from . import ai
from . import capture
from . import hub
from . import notify

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(PKG_DIR, "web")

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
}


class Handler(BaseHTTPRequestHandler):
    # ----- helpers -------------------------------------------------------- #
    def _send_json(self, obj, status=200):
        payload = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def _query(self) -> dict:
        return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

    def log_message(self, fmt, *args):  # quieter console
        pass

    # ----- routing -------------------------------------------------------- #
    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            return self._handle_api_get(path)
        return self._serve_static(path)

    def do_POST(self):
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            return self._handle_api_post(path)
        self._send_json({"error": "not found"}, 404)

    def do_PUT(self):
        path = urlparse(self.path).path
        if path == "/api/note":
            q = self._query()
            body = self._read_body()
            try:
                new_path = hub.update_note(q["path"], body.get("meta", {}), body.get("body"))
                return self._send_json({"path": new_path})
            except Exception as exc:
                return self._send_json({"error": str(exc)}, 400)
        self._send_json({"error": "not found"}, 404)

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path == "/api/note":
            q = self._query()
            try:
                hub.archive_note(q["path"])
                return self._send_json({"ok": True})
            except Exception as exc:
                return self._send_json({"error": str(exc)}, 400)
        self._send_json({"error": "not found"}, 404)

    # ----- API: GET ------------------------------------------------------- #
    def _handle_api_get(self, path):
        q = self._query()
        try:
            if path == "/api/tree":
                return self._send_json({
                    "tree": hub.build_tree(),
                    "status_counts": hub.status_counts(),
                    "ai": ai.ai_available(),
                })
            if path == "/api/notes":
                due = q.get("due_within")
                return self._send_json({"notes": hub.list_notes(
                    category=q.get("category", ""),
                    subcategory=q.get("subcategory", ""),
                    status=q.get("status", ""),
                    q=q.get("q", ""),
                    due_within=int(due) if due not in (None, "") else None,
                )})
            if path == "/api/note":
                return self._send_json({"note": hub.get_note(q["path"])})
            if path == "/api/due-soon":
                days = q.get("days")
                return self._send_json({"items": hub.due_soon(int(days) if days else None)})
        except Exception as exc:
            return self._send_json({"error": str(exc)}, 400)
        self._send_json({"error": "not found"}, 404)

    # ----- API: POST ------------------------------------------------------ #
    def _handle_api_post(self, path):
        q = self._query()
        body = self._read_body()
        try:
            if path == "/api/notes":
                meta = {k: body.get(k) for k in (
                    "type", "status", "tags", "due", "remind", "links",
                    "source", "ai_summary",
                ) if k in body}
                new_path = hub.create_note(
                    category=body.get("category", "Inbox"),
                    subcategory=body.get("subcategory", ""),
                    title=body.get("title", "Untitled"),
                    body=body.get("body", ""),
                    **meta,
                )
                return self._send_json({"path": new_path})

            if path == "/api/note/move":
                new_path = hub.move_note(
                    q.get("path") or body.get("path"),
                    body.get("category", "Inbox"),
                    body.get("subcategory", ""),
                )
                return self._send_json({"path": new_path})

            if path == "/api/capture":
                fields = capture.capture(body.get("url", ""))
                suggestion = None
                if body.get("enrich", True):
                    suggestion = ai.enrich(fields.get("body", ""), fields.get("links", [""])[0] if fields.get("links") else "")
                return self._send_json({"fields": fields, "suggestion": suggestion})

            if path == "/api/note/ai-enrich":
                note = hub.get_note(q["path"])
                suggestion = ai.enrich(note.get("body", ""), (note.get("links") or [""])[0] if note.get("links") else "")
                return self._send_json({"suggestion": suggestion})
        except Exception as exc:
            return self._send_json({"error": str(exc)}, 400)
        self._send_json({"error": "not found"}, 404)

    # ----- static --------------------------------------------------------- #
    def _serve_static(self, path):
        if path == "/" or path == "":
            path = "/index.html"
        rel = path.lstrip("/")
        full = os.path.normpath(os.path.join(WEB_DIR, rel))
        if not full.startswith(WEB_DIR) or not os.path.isfile(full):
            self.send_response(404)
            self.end_headers()
            return
        ext = os.path.splitext(full)[1]
        ctype = CONTENT_TYPES.get(ext, "application/octet-stream")
        with open(full, "rb") as fh:
            data = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _scanner_loop(interval_minutes: int):
    while True:
        try:
            notify.scan_and_notify()
        except Exception as exc:
            print(f"[scanner] {exc}")
        time.sleep(max(60, interval_minutes * 60))


def main():
    home = hub.ensure_home()
    cfg = hub.load_config()
    host = cfg.get("host", "127.0.0.1")
    port = int(cfg.get("port", 8765))

    t = threading.Thread(
        target=_scanner_loop,
        args=(int(cfg.get("scan_interval_minutes", 30)),),
        daemon=True,
    )
    t.start()

    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}/"
    print(f"Magpie running at {url}")
    print(f"   Your notes live in: {home}")
    print("Press Ctrl+C to stop.")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
