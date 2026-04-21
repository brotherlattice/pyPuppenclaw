from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def _send(self, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/health"):
            self._send({"ok": True, "sessions": 0})
            return
        self._send({"ok": True})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.startswith("/shutdown"):
            self._send({"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        self._send({"ok": True})

    def log_message(self, _format: str, *_args) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="?", default="start")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18795)
    parser.add_argument("--data-dir")
    parser.add_argument("--config")
    args = parser.parse_args()

    if args.command != "start":
        print('{"ok": true}')
        return 0

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
