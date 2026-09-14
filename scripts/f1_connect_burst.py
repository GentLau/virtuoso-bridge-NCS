"""F1 live: cold first-connect burst to the weak vps sshd (MaxStartups).

30 fresh tokens each open their first SSH tunnel concurrently.  Transient
mid-banner drops must be absorbed by the <=3 attempt connect retry; the
instruction must still get a structured reply.  Run from Windows.
"""
from __future__ import annotations
import argparse
import json
import socket
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from transport.middle import BusinessServer
from transport.registry import UserEntry, load_registry
from transport.register.probe import allocate_local_port
from transport.runtime_paths import set_working_dir, registry_path

VPS = "vps"

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=30)
    ap.add_argument("--concurrency", type=int, default=30)
    args = ap.parse_args()

    wd = set_working_dir(Path(tempfile.mkdtemp(prefix="vb-f1-")))
    reg = load_registry(registry_path())
    reserved = set()
    users = []
    for n in range(args.users):
        if n < 30:
            user, token, port = f"burst{n:02d}", f"burst-{n:02d}", 6780 + n
        else:
            user, token, port = f"burst{n:02d}", f"burst2-{n-30:02d}", 6810 + (n - 30)
        lp = allocate_local_port(reserved=reserved, tries=500)
        assert lp is not None
        reserved.add(lp)
        e = UserEntry(token=token, mode="remote")
        e.route.daemon.host = VPS
        e.route.daemon.daemon_port = port
        e.route.daemon.local_port = lp
        e.route.command.host = VPS
        e.route.command.user = "root"
        e.route.file.host = VPS
        e.deploy.scratch_root = "/root/vbtest"
        e.expected.daemon_user = "root"
        e.ssh.backend = "openssh"
        reg.register(user, e)
        users.append((user, token))

    middle = BusinessServer(wd)
    errors = []
    lock = threading.Lock()

    def one(i):
        user, tok = users[i]
        r = middle.execute_skill("RBDToken", token=tok, timeout=90)
        got = (r.output or "").strip().strip('"')
        if not r.ok or got != tok:
            with lock:
                errors.append(f"{user}: status={r.status} got={got!r} err={r.errors}")

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        list(pool.map(one, range(args.users)))
    elapsed = time.time() - t0
    for c in list(middle._clients.values()):
        try:
            c.close()
        except Exception:
            pass

    # verify no leaked tunnel processes for our ports
    leak = 0
    try:
        out = __import__("subprocess").run(
            ["ssh", VPS, "pgrep -c -f 'ssh.*-N.*-L'"], capture_output=True, text=True, timeout=15
        ).stdout.strip()
    except Exception:
        out = ""
    print(json.dumps({
        "case": "F1", "client": "windows", "users": args.users,
        "concurrency": args.concurrency, "errors": len(errors),
        "elapsed": round(elapsed, 1),
        "samples": errors[:5], "remote_ssh_tunnel_procs": out,
    }, ensure_ascii=False))
    return 1 if errors else 0

if __name__ == "__main__":
    raise SystemExit(main())
