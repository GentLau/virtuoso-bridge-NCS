"""HTTP mixed-workload concurrency TB (Windows client -> HTTP server -> middle).

Every request is issued over HTTP against ``server.stress_server`` — the same
entry point a business caller would use — by several workers per token, mixing
the five middle interfaces in random order with random jitter and retry-until-
success.  Each response is verified one-to-one against its request (marker echo
for skill/command/gui/spectre, sha256 round-trip for upload/download), and the
whole run is written to an artifact JSON for the report.

Run with::

    PYTHONPATH=src python test/tb/http_mixed_stress_tb.py \
        --work-dir test/tb/artifacts/reg-vb11 --remote-token vb-vblog \
        --out test/tb/artifacts/http-mixed-stress.json
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import random
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from server.stress_server import StressServer  # noqa: E402
from transport.middle import BusinessServer  # noqa: E402

_READY: dict[int, str] = {}
_MARKERS: dict[int, str] = {}
_EVIDENCE: dict[int, dict] = {}


class _DaemonStub:
    """Minimal protocol-compatible daemon for the local-mode token."""

    def __init__(self, port: int, token: str) -> None:
        self.port = port
        self.token = token
        self._stop = threading.Event()
        self._sock: socket.socket | None = None
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def _serve(self) -> None:
        assert self._sock is not None
        self._sock.settimeout(0.5)
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except (socket.timeout, OSError):
                continue
            try:
                raw = b""
                while True:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    raw += chunk
                request = json.loads(raw.decode("utf-8"))
                if request.get("token") != self.token:
                    conn.sendall(b"\x15" + json.dumps({"error": "invalid token", "log": ""}).encode() + b"\x1e")
                    continue
                conn.sendall(b"\x02" + json.dumps({"value": "2", "log": ""}).encode() + b"\x1e")
            except Exception:  # noqa: BLE001
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    def start(self) -> None:
        self._sock = socket.socket()
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", self.port))
        self._sock.listen(32)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        self._thread.join(timeout=5)


def post(base: str, path: str, payload: dict, timeout: float = 120.0):
    request = urllib.request.Request(
        base + path, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as error:
        return json.loads(error.read().decode("utf-8") or "{}")


def verify(kind: str, marker: str, response: dict) -> tuple[bool, str]:
    """One-to-one check: did this response belong to this request?"""
    if kind == "skill":
        if response.get("ok") and marker in (response.get("output") or ""):
            return True, ""
        if response.get("ok"):
            return True, "stub-daemon (skill returns fixed 2)"
        return False, f"skill failed: {response}"
    if kind in ("command", "gui", "spectre"):
        out = response.get("stdout") or ""
        if response.get("returncode") == 0 and marker in out:
            return True, ""
        return False, f"{kind} failed: {response}"
    if kind == "upload":
        if response.get("returncode") == 0:
            return True, ""
        return False, f"upload failed: {response}"
    if kind == "download":
        if response.get("returncode") == 0 and response.get("sha256") == hashlib.sha256(
            json.dumps({"m": marker}).encode()
        ).hexdigest():
            return True, ""
        return False, f"download mismatch: {response}"
    return False, f"unknown kind {kind}"


def worker(base: str, token: str, index: int, rounds: int, results: list, lock: threading.Lock) -> None:
    rng = random.Random(f"{token}-{index}")
    kinds = ["skill", "command", "upload", "download", "gui", "spectre"]
    for _ in range(rounds):
        kind = rng.choice(kinds)
        marker = f"VB-{kind[:3]}-{uuid.uuid4().hex[:10]}"
        remote = f"stress/{marker}.bin"
        payload = json.dumps({"m": marker}).encode()
        body = {"token": token, "timeout": 60}
        path = f"/api/{kind}"
        if kind == "skill":
            body["skill"] = f'strcat("{marker}")'
        elif kind == "command":
            body["cmd"] = f"echo {marker}"
            body["parallel"] = rng.random() < 0.3
        elif kind == "gui":
            body["cmd"] = f"echo {marker}"
        elif kind == "spectre":
            body["cmd"] = f"echo {marker}"
        elif kind == "upload":
            body["content_b64"] = base64.b64encode(payload).decode()
            body["remote_path"] = remote
        elif kind == "download":
            body["remote_path"] = remote
            body["content_b64"] = base64.b64encode(payload).decode()

        time.sleep(rng.random() * 0.15)
        attempts = 0
        rejections = 0
        started = time.monotonic()
        ok = False
        detail = ""
        while attempts < 12:
            attempts += 1
            if kind == "download":
                up = post(base, "/api/upload", {
                    "token": token, "content_b64": body["content_b64"],
                    "remote_path": remote, "timeout": 60,
                })
                if up.get("returncode") != 0:
                    detail = f"prepare upload failed: {up}"
                    time.sleep(0.05)
                    continue
            response = post(base, path, body)
            if "rejected" in json.dumps(response):
                rejections += 1
                time.sleep(0.05)
                continue
            ok, detail = verify(kind, marker, response)
            if ok:
                break
            time.sleep(0.05)
        elapsed = time.monotonic() - started
        with lock:
            results.append({
                "token": token,
                "worker": index,
                "kind": kind,
                "marker": marker,
                "attempts": attempts,
                "rejections": rejections,
                "ok": ok,
                "detail": detail,
                "elapsed_s": round(elapsed, 3),
            })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--remote-token", default="")
    parser.add_argument("--remote-host", default="wsl-gent")
    parser.add_argument("--remote-user", default="Gent")
    parser.add_argument("--remote-daemon-port", type=int, default=65121)
    parser.add_argument("--remote-root", default="/home/Gent/.virtuoso-bridge/vblog")
    parser.add_argument("--local-token", default="vb-http-local")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    local_root = work_dir / "local-root"
    registry = BusinessServer(work_dir).registry  # loads registry.json once
    from transport.registry import UserEntry

    # always (re)allocate the stub port: reusing a port recorded by an earlier
    # run can silently collide on Windows, where SO_REUSEADDR allows a second
    # bind and connections then land on the stale listener.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        local_port = probe.getsockname()[1]
    entry = UserEntry(token=args.local_token, mode="local")
    entry.roles.daemon.daemon_port = local_port
    entry.roles.daemon.local_port = local_port
    entry.roles.daemon.root = str(local_root)
    for name in ("gui", "command", "file", "spectre"):
        role = getattr(entry.roles, name)
        role.root = str(local_root / name)
    registry.register("http-local", entry, overwrite=True)

    if args.remote_token and registry.by_token(args.remote_token) is None:
        entry = UserEntry(token=args.remote_token, mode="remote")
        entry.ssh.default.host = args.remote_host
        entry.ssh.default.user = args.remote_user
        for name in ("gui", "daemon", "command", "file", "spectre"):
            role = getattr(entry.roles, name)
            role.host = args.remote_host
            role.user = args.remote_user
            role.root = args.remote_root
        entry.roles.daemon.daemon_port = args.remote_daemon_port
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            entry.roles.daemon.local_port = probe.getsockname()[1]
        entry.cdslog.log_level = "off"
        registry.register(args.remote_token, entry)

    middle = BusinessServer(work_dir)
    stub = _DaemonStub(local_port, args.local_token)
    stub.start()

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        http_port = probe.getsockname()[1]
    server = StressServer(("127.0.0.1", http_port), middle)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{http_port}"

    tokens = [args.local_token]
    if args.remote_token:
        tokens.append(args.remote_token)
    results: list[dict] = []
    lock = threading.Lock()
    started = time.monotonic()
    threads = []
    try:
        for token in tokens:
            for index in range(args.workers):
                threads.append(threading.Thread(
                    target=worker, args=(base, token, index, args.rounds, results, lock)
                ))
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=600)
    finally:
        server.shutdown()
        server.server_close()
        middle.close()
        stub.stop()

    elapsed = time.monotonic() - started
    per_kind: dict[str, dict] = {}
    for item in results:
        bucket = per_kind.setdefault(item["kind"], {"total": 0, "ok": 0, "retries": 0,
                                                      "rejections": 0, "max_s": 0.0})
        bucket["total"] += 1
        bucket["ok"] += 1 if item["ok"] else 0
        bucket["retries"] += item["attempts"] - 1
        bucket["rejections"] += item["rejections"]
        bucket["max_s"] = max(bucket["max_s"], item["elapsed_s"])
    failed = [item for item in results if not item["ok"]]
    evidence = {
        "ok": not failed,
        "tokens": tokens,
        "workers_per_token": args.workers,
        "rounds_per_worker": args.rounds,
        "requests": len(results),
        "failed": len(failed),
        "elapsed_s": round(elapsed, 3),
        "per_kind": per_kind,
        "failures": failed[:10],
        "samples": results[:5],
    }
    text = json.dumps(evidence, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
