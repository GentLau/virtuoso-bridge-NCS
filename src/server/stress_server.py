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
            if path == "/api/shutdown":
                # graceful stop: release per-token clients (tunnels + shells)
                # before the harness terminates this process (TerminateProcess
                # would skip atexit and leave orphan ``ssh -N -L`` behind)
                middle.close()
                self._send(200, {"ok": True})
                import threading as _threading
                _threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
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
            if path == "/api/composite":
                token = body["token"]
                seq = str(body.get("seq", "0"))
                delay_ms = float(body.get("delay_ms", 0))
                token_owner = middle.registry.user_of(token) or token
                entry = middle.registry.by_token(token)
                if entry is None:
                    self._send(400, {"error": "unknown token"})
                    return
                import time as _time
                payload = (token + seq).encode() * 2048
                src = Path(tempfile.mkdtemp()) / "p.bin"
                src.write_bytes(payload)
                from transport.remote_roles import resolve as _resolve
                remote = f"{_resolve(entry, token_owner).file.root}/composite-{token_owner}-{seq}.bin"
                up = middle.upload_file(src, remote, token=token)
                _time.sleep(delay_ms / 1000.0)
                sk = middle.execute_skill("RBDToken", token=token)
                _time.sleep(delay_ms / 1000.0)
                cmd = f"echo composite-{seq}; sleep {0.1 + (float(seq[-2:]) % 40) / 100.0}"
                cm = middle.run_command(cmd, token=token)
                back = Path(tempfile.mkdtemp()) / "out.bin"
                dn = middle.download_file(remote, back, token=token)
                sha_ok = back.exists() and hashlib.sha256(back.read_bytes()).hexdigest() == hashlib.sha256(payload).hexdigest()
                stages = (up, cm, dn)
                rejected = any(
                    getattr(stage, "kind", "") == "rejected" for stage in stages
                )
                self._send(200, {
                    "upload_rc": up.returncode,
                    "upload_stderr": up.stderr,
                    "upload_kind": up.kind,
                    "skill_ok": sk.ok,
                    "skill_out": sk.output,
                    "skill_log": sk.log,
                    "skill_errors": sk.errors,
                    "command_rc": cm.returncode,
                    "command_out": cm.stdout,
                    "command_stderr": cm.stderr,
                    "command_kind": cm.kind,
                    "download_rc": dn.returncode,
                    "download_stderr": dn.stderr,
                    "download_kind": dn.kind,
                    "sha_ok": sha_ok,
                    "rejected": rejected,
                    "ok": up.returncode == 0 and sk.ok and cm.returncode == 0 and dn.returncode == 0 and sha_ok,
                })
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
