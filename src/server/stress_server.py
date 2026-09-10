"""Pressure-test HTTP wrapper around the middle layer.

Exposes execute_skill / run_command over HTTP so an external script can hammer
the middle layer's per-token thread pool / channel budget / parallel path.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from transport.middle import BusinessServer


class Handler(BaseHTTPRequestHandler):
    server_version = "vb-stress/0.1"

    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read(self):
        n = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(n)
        return json.loads(raw.decode("utf-8")) if raw else {}

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            body = self._read()
        except Exception as exc:  # noqa: BLE001
            self._send(400, {"error": str(exc)})
            return
        middle: BusinessServer = self.server.middle
        try:
            if path == "/api/skill":
                r = middle.execute_skill(
                    body.get("skill", ""),
                    timeout=body.get("timeout"),
                    token=body["token"],
                )
                self._send(200, {"ok": r.ok, "output": r.output, "log": r.log, "errors": r.errors})
                return
            if path == "/api/upload":
                raw = base64.b64decode(body.get("content_b64", ""))
                tmp = Path(tempfile.mkdtemp()) / "payload.bin"
                tmp.write_bytes(raw)
                c = middle.upload_file(tmp, body.get("remote_path", ""), timeout=body.get("timeout"), token=body["token"])
                self._send(200, {"returncode": c.returncode, "stderr": c.stderr})
                return
            if path == "/api/download":
                tmp = Path(tempfile.mkdtemp()) / "out.bin"
                c = middle.download_file(body.get("remote_path", ""), tmp, timeout=body.get("timeout"), token=body["token"])
                data = tmp.read_bytes() if tmp.exists() else b""
                self._send(200, {
                    "returncode": c.returncode,
                    "stderr": c.stderr,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "size": len(data),
                })
                return
            if path == "/api/command":
                c = middle.run_command(
                    body.get("cmd", ""),
                    timeout=body.get("timeout"),
                    token=body["token"],
                    parallel=bool(body.get("parallel", False)),
                )
                self._send(200, {"returncode": c.returncode, "stdout": c.stdout, "stderr": c.stderr})
                return
            self._send(404, {"error": "not found"})
        except KeyError:
            self._send(400, {"error": "token is required"})
        except Exception as exc:  # noqa: BLE001
            self._send(500, {"error": str(exc)})

    def log_message(self, fmt, *args):
        pass


class StressServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 1024

    def __init__(self, address, middle: BusinessServer):
        super().__init__(address, Handler)
        self.middle = middle


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8125)
    parser.add_argument("--work-dir", default=None)
    args = parser.parse_args(argv)

    from transport.runtime_paths import set_working_dir
    set_working_dir(args.work_dir)
    middle = BusinessServer(args.work_dir)
    server = StressServer((args.host, args.port), middle)
    print(f"stress server: http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
