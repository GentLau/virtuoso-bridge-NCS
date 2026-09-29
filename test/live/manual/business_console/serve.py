"""Manual same-origin harness for the business-face console.

The production business server intentionally exposes only ``POST /api/operation``
plus ``GET /health`` and ``GET /help``.  It neither serves static files nor sends
CORS headers.  This small, test-only process therefore serves the console HTML
and proxies those business endpoints so the browser can read structured JSON.

It never imports the production server and never writes business state.

Run::

    python test/live/manual/business_console/serve.py \
        --business-base http://127.0.0.1:8127 --port 8130
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
PAGE = ROOT / "index.html"
PROXY_PATHS = {"/health", "/help", "/api/operation"}


class ConsoleHandler(BaseHTTPRequestHandler):
    server_version = "vb-business-console/0.1"
    protocol_version = "HTTP/1.1"

    @property
    def business_base(self) -> str:
        return self.server.business_base  # type: ignore[attr-defined]

    def _cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _send_bytes(
        self,
        status: int,
        body: bytes,
        content_type: str,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors_headers()
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(
        self,
        status: int,
        payload: object,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(
            200 if status == 204 else status,
            body,
            "application/json; charset=utf-8",
            extra_headers=extra_headers,
        )

    def _upstream_url(self, path: str) -> str:
        return self.business_base.rstrip("/") + path

    def _proxy(self, method: str) -> None:
        path = urlsplit(self.path).path
        if path not in PROXY_PATHS:
            self._send_json(404, {"ok": False, "data": None, "error": "not found"})
            return

        body: bytes | None = None
        if method == "POST":
            raw_length = self.headers.get("Content-Length", "0") or "0"
            try:
                length = max(0, int(raw_length))
            except ValueError:
                self._send_json(
                    400, {"ok": False, "data": None, "error": "invalid Content-Length"}
                )
                return
            body = self.rfile.read(length) if length else b""

        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = (
                self.headers.get("Content-Type") or "application/json"
            )
        request = urllib.request.Request(
            self._upstream_url(path),
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=3600) as upstream:
                payload = upstream.read()
                content_type = upstream.headers.get(
                    "Content-Type", "application/json; charset=utf-8"
                )
                self._send_bytes(upstream.status, payload, content_type)
        except urllib.error.HTTPError as error:
            payload = error.read()
            content_type = error.headers.get(
                "Content-Type", "application/json; charset=utf-8"
            )
            self._send_bytes(error.code, payload, content_type)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            self._send_json(
                502,
                {
                    "ok": False,
                    "data": None,
                    "error": f"business proxy unavailable: {error}",
                },
            )

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self._cors_headers()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/":
            body = PAGE.read_bytes()
            self._send_bytes(200, body, "text/html; charset=utf-8")
            return
        if path == "/__console__/config":
            self._send_json(
                200,
                {
                    "ok": True,
                    "data": {
                        "business_base": self.business_base,
                        "proxy": self.server.server_address,
                    },
                    "error": None,
                },
            )
            return
        self._proxy("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._proxy("POST")

    def log_message(self, fmt: str, *args) -> None:  # noqa: A002
        print(f"[business-console] {self.address_string()} - {fmt % args}")


class ConsoleServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, business_base: str) -> None:
        super().__init__(address, ConsoleHandler)
        self.business_base = business_base.rstrip("/")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Manual business-face console (serves HTML + proxies the business API)"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8130)
    parser.add_argument(
        "--business-base",
        default="http://127.0.0.1:8127",
        help="existing business API base URL; no business server is modified",
    )
    args = parser.parse_args(argv)

    if not PAGE.is_file():
        raise SystemExit(f"console page not found: {PAGE}")

    server = ConsoleServer((args.host, args.port), args.business_base)
    print("=" * 72)
    print("Virtuoso Bridge manual business console")
    print(f"console:  http://{args.host}:{args.port}/")
    print(f"business: {server.business_base}")
    print("mode:     test-only static host + same-origin API proxy")
    print("Press Ctrl+C to stop.")
    print("=" * 72)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

