"""100-user local-mode stress TB (run on WSL with fake daemons)."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from transport.middle import BusinessServer
from common.registry import UserEntry, load_registry
from common.paths import registry_path, override_work_dir_for_tests  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=100)
    ap.add_argument("--ops-per-user", type=int, default=8)
    ap.add_argument("--base-port", type=int, default=6801)
    ap.add_argument("--token-prefix", default="fake")
    ap.add_argument("--thread-pool-size", type=int, default=8)
    ap.add_argument("--work-dir", default=None)
    args = ap.parse_args()
    wd = Path(args.work_dir) if args.work_dir else Path(tempfile.mkdtemp(prefix="vb-local-stress-"))
    override_work_dir_for_tests(wd)
    reg = load_registry(registry_path())
    users = []
    for i in range(args.users):
        user = f"fu{i:03d}"
        token = f"{args.token_prefix}-{i:02d}"
        e = UserEntry(token=token, mode="local")
        e.runtime.thread_pool_size = args.thread_pool_size
        for name in ("gui", "daemon", "command", "file", "spectre"):
            getattr(e.roles, name).root = str((wd / user / name).resolve())
        e.roles.daemon.daemon_port = args.base_port + i
        e.roles.daemon.local_port = args.base_port + i
        e.roles.daemon.python = sys.executable
        e.cdslog.log_level = "off"
        reg.register(user, e)
        payload = wd / user / "payload.bin"
        payload.parent.mkdir(parents=True, exist_ok=True)
        payload.write_bytes(token.encode() * 512)
        users.append((user, token, payload))
    server = BusinessServer(wd)
    lock = threading.Lock(); stats = {"ok": 0, "retries": 0, "errors": []}

    def one(i: int, j: int):
        user, token, payload = users[i]
        op = (i + j) % 5
        for attempt in range(200):
            if op == 0:
                r = server.execute_skill("1+1", timeout=10, token=token)
                good = r.ok and r.output.strip() == "2"
                rejected = any("thread pool exceeded" in e for e in r.errors)
            elif op == 1:
                r = server.run_command(f"echo op-{i}-{j}", timeout=10, token=token)
                good = r.returncode == 0 and f"op-{i}-{j}" in r.stdout
                rejected = r.kind == "rejected"
            elif op == 2:
                r = server.upload_file(payload, f"up-{i}-{j}.bin", timeout=10, token=token)
                good = r.returncode == 0; rejected = r.kind == "rejected"
            elif op == 3:
                remote = f"down-{i}-{j}.bin"
                up = server.upload_file(payload, remote, timeout=10, token=token)
                r = up if up.returncode != 0 else server.download_file(remote, wd / user / f"got-{i}-{j}.bin", timeout=10, token=token)
                good = r.returncode == 0; rejected = r.kind == "rejected"
            else:
                r = server.run_gui_command(f"echo gui-{i}-{j}", timeout=10, token=token)
                good = r.returncode == 0 and f"gui-{i}-{j}" in r.stdout
                rejected = r.kind == "rejected"
            if good:
                with lock: stats["ok"] += 1
                return None
            if rejected:
                with lock: stats["retries"] += 1
                time.sleep(0.002 * (attempt + 1)); continue
            return f"{user} op={op}: {getattr(r, 'errors', None) or getattr(r, 'stderr', r)}"
        return f"{user} op={op}: retry limit"

    start = time.time()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.users * 2) as pool:
            for err in pool.map(lambda pair: one(*pair), ((i, j) for i in range(args.users) for j in range(args.ops_per_user))):
                if err:
                    with lock: stats["errors"].append(err)
    finally:
        server.close()
    result = {"users": args.users, "ops": args.users * args.ops_per_user, "ok": stats["ok"], "retries": stats["retries"], "errors": stats["errors"][:10], "error_count": len(stats["errors"]), "elapsed_s": time.time() - start, "workdir": str(wd)}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not stats["errors"] and stats["ok"] == args.users * args.ops_per_user else 2


if __name__ == "__main__":
    raise SystemExit(main())
