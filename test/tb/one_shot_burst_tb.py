"""One-shot channel burst TB (real host): session-channel opens must retry.

``run_gui_command`` / ``run_spectre_command`` open a fresh SSH session channel
per call (one-shot by design).  When more calls run at once than the server's
per-connection ``MaxSessions`` allows, sshd answers CHANNEL_OPEN_FAILURE
(``ChannelException(2, "Connect failed")``).  Opening a channel has no side
effect, so the spec's "retry only pre-side-effect transport phases" rule applies
and every call must still return its own answer.

Run with::

    PYTHONPATH=src python test/tb/one_shot_burst_tb.py --work-dir ... \
        --token vb-vblog --out test/tb/artifacts/one-shot-burst.json
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from transport.middle import BusinessServer  # noqa: E402
from transport.registry import UserEntry, load_registry  # noqa: E402
from transport.runtime_paths import set_working_dir  # noqa: E402


class ProbeFailure(AssertionError):
    pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--user", default="vblog")
    parser.add_argument("--host", default="wsl-gent")
    parser.add_argument("--ssh-user", default="Gent")
    parser.add_argument("--root", default="/home/Gent/.virtuoso-bridge/vblog")
    parser.add_argument("--daemon-port", type=int, default=65121)
    parser.add_argument("--local-port", type=int, default=65201)
    parser.add_argument("--workers", type=int, default=24,
                        help="concurrent one-shot calls (must exceed server MaxSessions)")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    set_working_dir(work_dir)
    registry = load_registry()
    if registry.get(args.user) is None:
        entry = UserEntry(token=args.token, mode="remote")
        entry.ssh.default.host = args.host
        entry.ssh.default.user = args.ssh_user
        for name in ("gui", "daemon", "command", "file", "spectre"):
            role = getattr(entry.roles, name)
            role.host = args.host
            role.user = args.ssh_user
            role.root = args.root
            role.max_sessions = 32
        entry.roles.daemon.daemon_port = args.daemon_port
        entry.roles.daemon.local_port = args.local_port
        entry.runtime.thread_pool_size = 64
        entry.runtime.channel_budget = 64
        entry.cdslog.log_level = "off"
        registry.register(args.user, entry)
    else:
        entry = registry.get(args.user)
        entry.runtime.thread_pool_size = 64
        entry.runtime.channel_budget = 64
        for name in ("gui", "daemon", "command", "file", "spectre"):
            getattr(entry.roles, name).max_sessions = 32
        # persist: BusinessServer re-reads registry.json, so an in-memory-only
        # budget bump would be lost
        registry.register(args.user, entry, overwrite=True)

    server = BusinessServer(work_dir)
    results: list[dict] = []
    lock = threading.Lock()
    started_workers = 0

    def one(index: int, kind: str) -> None:
        marker = f"OSB-{kind}-{uuid.uuid4().hex[:10]}"
        cmd = f"echo {marker}"
        started = time.monotonic()
        if kind == "gui":
            result = server.run_gui_command(cmd, timeout=60, token=args.token)
        else:
            result = server.run_spectre_command(cmd, timeout=60, token=args.token)
        with lock:
            results.append({
                "kind": kind,
                "marker": marker,
                "returncode": result.returncode,
                "kind_field": result.kind,
                "stdout": (result.stdout or "")[:120],
                "stderr": (result.stderr or "")[:200],
                "ok": result.returncode == 0 and marker in (result.stdout or ""),
                "elapsed_s": round(time.monotonic() - started, 3),
            })

    alive: list[threading.Thread] = []
    try:
        for _round in range(args.rounds):
            threads = []
            for index in range(args.workers):
                kind = "gui" if index % 2 == 0 else "spectre"
                threads.append(threading.Thread(target=one, args=(index, kind)))
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=300)
            alive.extend(thread for thread in threads if thread.is_alive())
    finally:
        server.close()

    planned_calls = args.workers * args.rounds
    failed = [item for item in results if not item["ok"]]
    transport_failures = [item for item in failed if item["kind_field"] == "transport"]
    if alive:
        failed.append({"kind": "worker-timeout", "ok": False,
                       "detail": f"{len(alive)} one-shot workers still running"})
    if len(results) != planned_calls:
        failed.append({"kind": "request-count", "ok": False,
                       "detail": f"{len(results)} answers for {planned_calls} planned calls"})
    evidence = {
        "ok": not failed,
        "workers": args.workers,
        "rounds": args.rounds,
        "requests": len(results),
        "planned_requests": planned_calls,
        "failed": len(failed),
        "transport_failures": len(transport_failures),
        "by_kind": {
            kind: {
                "total": sum(1 for r in results if r["kind"] == kind),
                "ok": sum(1 for r in results if r["kind"] == kind and r["ok"]),
            }
            for kind in ("gui", "spectre")
        },
        "failures": failed[:8],
    }
    text = json.dumps(evidence, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
