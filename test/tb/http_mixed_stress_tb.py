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
import os
import random
import socket
import subprocess
import sys
import tempfile
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
                # echo the requested expression so the caller can verify that
                # this answer really belongs to this request
                skill = str(request.get("skill", ""))
                value = "2" if skill.strip() in ("1+1", "") else skill
                conn.sendall(b"\x02" + json.dumps({"value": value, "log": ""}).encode() + b"\x1e")
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


def _ssh_process_count() -> int:
    """Client-side ssh process count (the 2026-09 process-storm regression guard)."""
    try:
        if os.name == "nt":
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq ssh.exe", "/NH"],
                capture_output=True, text=True, timeout=30,
            )
            return sum(
                1 for line in out.stdout.splitlines()
                if line.strip().lower().startswith("ssh.exe")
            )
        out = subprocess.run(["pgrep", "-c", "ssh"], capture_output=True, text=True,
                             timeout=30)
        return int((out.stdout or "0").strip() or 0)
    except Exception:  # noqa: BLE001 - diagnostics only
        return -1


def _staging_leftovers() -> list[str]:
    """Temp dirs that hold only staging payloads (the stress server's signature).

    Matched by content, never by name alone, so unrelated ``/tmp/tmpXXXX`` dirs
    from other tools are ignored.
    """
    root = Path(tempfile.gettempdir())
    hits: list[str] = []
    try:
        candidates = list(root.glob("tmp*"))
    except OSError:
        return hits
    for path in candidates:
        if not path.is_dir():
            continue
        try:
            names = {item.name for item in path.iterdir()}
        except OSError:
            continue
        if names and names <= {"out.bin", "payload.bin"}:
            hits.append(path.name)
    return hits


def is_rejected(response: dict) -> bool:
    """True only when the bridge actually refused for capacity reasons.

    (The composite response carries a boolean ``rejected`` field, so a plain
    substring search over the JSON would treat every composite as a refusal.)
    """
    if response.get("rejected") is True:
        return True
    if response.get("kind") == "rejected":
        return True
    errors = response.get("errors")
    if isinstance(errors, list) and any(
        "exceeded" in str(item) or "max_sessions" in str(item) for item in errors
    ):
        return True
    return False


def verify(kind: str, marker: str, response: dict) -> tuple[bool, str]:
    """One-to-one check: did this response belong to this request?"""
    if kind == "skill":
        if response.get("ok") and marker in (response.get("output") or ""):
            return True, ""
        if response.get("post_error"):
            return False, f"skill transport error: {response['post_error']}"
        return False, f"skill answer did not belong to this request: {response}"
    if kind in ("command", "gui", "spectre"):
        out = response.get("stdout") or ""
        if response.get("returncode") == 0 and marker in out:
            return True, ""
        return False, f"{kind} failed: {response}"
    if kind == "upload":
        # an upload only counts when the payload comes back byte-identical
        declared = response.get("declared_sha256")
        if (
            response.get("returncode") == 0
            and declared
            and declared == response.get("expected_sha256") == response.get("verified_sha256")
        ):
            return True, ""
        return False, f"upload failed or not verified: {response}"
    if kind == "download":
        if response.get("returncode") == 0 and response.get("sha256") == hashlib.sha256(
            json.dumps({"m": marker}).encode()
        ).hexdigest():
            return True, ""
        return False, f"download mismatch: {response}"
    if kind == "composite":
        # one business-shaped call: upload -> skill -> command -> download,
        # with the sha256 round-trip checked inside the server
        if response.get("ok") and response.get("sha_ok"):
            return True, ""
        return False, f"composite failed: {response}"
    return False, f"unknown kind {kind}"


def worker(base: str, token: str, index: int, rounds: int, results: list,
           lock: threading.Lock, max_attempts: int) -> None:
    rng = random.Random(f"{token}-{index}")
    kinds = ["skill", "command", "upload", "download", "gui", "spectre", "composite"]
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
            body["sha256"] = hashlib.sha256(payload).hexdigest()
        elif kind == "download":
            body["remote_path"] = remote
            body["content_b64"] = base64.b64encode(payload).decode()
        elif kind == "composite":
            # the composite handler derives a sleep from the last two digits,
            # so the sequence must be numeric (zero padded)
            body["seq"] = f"{rng.randint(0, 9999):04d}"
            body["delay_ms"] = rng.choice([0, 5, 20, 50])

        time.sleep(rng.random() * 0.15)
        attempts = 0
        rejections = 0
        started = time.monotonic()
        ok = False
        detail = ""
        first_error = ""
        while attempts < max_attempts:
            attempts += 1
            if kind == "download":
                up = post(base, "/api/upload", {
                    "token": token, "content_b64": body["content_b64"],
                    "remote_path": remote, "timeout": 60,
                })
                if up.get("returncode") != 0:
                    detail = f"prepare upload failed: {up}"
                    rejections += 1
                    time.sleep(min(0.05 * attempts, 0.5))
                    continue
            response = post(base, path, body)
            if is_rejected(response):
                # admission control said "too much at once": back off and try
                # again — the contract is that a request is eventually
                # answered, not that it is never refused
                rejections += 1
                time.sleep(min(0.05 * attempts, 0.5))
                continue
            ok, detail = verify(kind, marker, response)
            if ok:
                break
            if not first_error:
                first_error = f"kind={response.get('kind')} detail={detail}"[:300]
            time.sleep(min(0.05 * attempts, 0.5))
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
                "first_error": first_error,
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
    parser.add_argument("--local-pool", type=int, default=32,
                        help="local token thread pool (lower it to force rejections)")
    parser.add_argument("--max-attempts", type=int, default=12,
                        help="retry cap per request (raise it for saturation runs)")
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
    entry.runtime.thread_pool_size = args.local_pool
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
    staging_before = _staging_leftovers()
    ssh_before = _ssh_process_count()
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
    expected = len(tokens) * args.workers * args.rounds
    try:
        for token in tokens:
            for index in range(args.workers):
                threads.append(threading.Thread(
                    target=worker,
                    args=(base, token, index, args.rounds, results, lock,
                          args.max_attempts),
                ))
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=600)
        alive = [t for t in threads if t.is_alive()]
    finally:
        server.shutdown()
        server.server_close()
        middle.close()
        stub.stop()

    elapsed = time.monotonic() - started
    # staging hygiene: the HTTP server must not leave per-request temp dirs
    staging_root = work_dir / "stress-tmp"
    leftover = sorted(item.name for item in staging_root.iterdir()) if staging_root.is_dir() else []
    new_staging_dirs = sorted(set(_staging_leftovers()) - set(staging_before))
    ssh_after = _ssh_process_count()
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
    if alive:
        failed.append({"kind": "worker-timeout", "ok": False,
                       "detail": f"{len(alive)} worker threads still running"})
    if len(results) != expected:
        failed.append({"kind": "request-count", "ok": False,
                       "detail": f"{len(results)} results for {expected} planned requests"})
    ssh_budget = len(tokens) + 4  # one tunnel per token plus slack; a storm blows past this
    if ssh_before >= 0 and ssh_after > ssh_before + ssh_budget:
        failed.append({"kind": "ssh-process-storm", "ok": False,
                       "detail": f"ssh processes {ssh_before} -> {ssh_after}"})
    if (leftover or new_staging_dirs) and not failed:
        failed = [{"kind": "temp-dir-hygiene", "ok": False,
                   "detail": (f"{len(leftover)} staging dirs in {staging_root}; "
                              f"{len(new_staging_dirs)} new system temp dirs")}]
    first_errors: dict[str, int] = {}
    for item in results:
        if item.get("first_error"):
            key = f"{item['kind']}: {item['first_error'][:120]}"
            first_errors[key] = first_errors.get(key, 0) + 1
    evidence = {
        "ok": not failed,
        "tokens": tokens,
        "workers_per_token": args.workers,
        "rounds_per_worker": args.rounds,
        "max_attempts": args.max_attempts,
        "requests": len(results),
        "planned_requests": expected,
        "failed": len(failed),
        "elapsed_s": round(elapsed, 3),
        "per_kind": per_kind,
        "failures": failed[:10],
        "ssh_processes_before": ssh_before,
        "ssh_processes_after": ssh_after,
        "staging_root": str(staging_root),
        "staging_leftovers": leftover[:10],
        "new_system_temp_dirs": new_staging_dirs[:10],
        "first_errors": dict(sorted(first_errors.items(), key=lambda kv: -kv[1])[:10]),
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
