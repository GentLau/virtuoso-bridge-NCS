"""Probe: lone-surrogate request fields must not drop the HTTP connection.

``src/common/jsonutil.py`` promises that hostile JSON (non-finite numbers,
oversized ints, deep nesting) becomes a normal 4xx instead of a dropped
connection.  A lone surrogate escape (``"\\ud800"``) is valid JSON *text*
but not valid UTF-8, and it currently reaches the response builder:

    json.dumps(payload, ensure_ascii=False).encode("utf-8")
    → UnicodeEncodeError → handler dies → client sees RemoteDisconnected

Run (no real Virtuoso needed; both servers are started locally):

    python test/semi/probes/lone_surrogate_probe.py

Exit code 0 = every injection returned an HTTP status; 1 = at least one
connection was dropped (the defect).
"""
from __future__ import annotations

import http.client
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_port(port: int, timeout: float = 15.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), 0.3):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def _post(port: int, path: str, raw: bytes, label: str) -> tuple[bool, str]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=6)
    try:
        conn.request("POST", path, body=raw, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        data = resp.read()[:90]
        print(f"  {label:38s} -> {resp.status} {data!r}")
        return True, f"{resp.status}"
    except Exception as exc:  # noqa: BLE001 - the defect is exactly this path
        print(f"  {label:38s} -> DROPPED {type(exc).__name__}")
        return False, type(exc).__name__
    finally:
        conn.close()


def _start(module: str, port: int, work_dir: str) -> subprocess.Popen:
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    return subprocess.Popen(
        [sys.executable, "-m", module, "--port", str(port), "--work-dir", work_dir],
        env=env, cwd=str(ROOT),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


CASES = [
    ("server.api_server", "/api/operation",
     b'{"operation": "\\ud800", "token": "x"}', "api: surrogate in operation"),
    ("register.server", "/api/register",
     b'{"user": "\\ud800", "action": "validate"}', "reg: surrogate in user"),
    ("register.server", "/api/register",
     b'{"user": "u1", "action": "\\udfff", "token": "t"}', "reg: surrogate in action"),
]


def main() -> int:
    failures = 0
    procs: list[subprocess.Popen] = []
    try:
        for module in ("server.api_server", "register.server"):
            port = _free_port()
            work_dir = tempfile.mkdtemp(prefix=f"vb-probe-{module.split('.')[0]}-")
            proc = _start(module, port, work_dir)
            procs.append(proc)
            if not _wait_port(port):
                print(f"{module}: server did not start")
                failures += 1
                continue
            print(f"[{module}] port={port} work_dir={work_dir}")
            for mod, path, raw, label in CASES:
                if mod != module:
                    continue
                ok, _ = _post(port, path, raw, label)
                failures += 0 if ok else 1
    finally:
        for proc in procs:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    print(f"\nresult: {'PASS (all answered)' if failures == 0 else f'FAIL ({failures} dropped connection(s))'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
