"""Remote-mode stress TB: Windows client -> WSL fake daemons."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import tempfile
import time
from pathlib import Path

from transport.middle import BusinessServer
from transport.registry import UserEntry, load_registry
from transport.runtime_paths import set_working_dir


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=100)
    ap.add_argument("--max-workers", type=int, default=30)
    ap.add_argument("--base-port", type=int, default=6801)
    ap.add_argument("--local-port-base", type=int, default=7000)
    ap.add_argument("--token-prefix", default="fake")
    ap.add_argument("--host", default="wsl-gent")
    ap.add_argument("--ssh-user", default="Gent")
    ap.add_argument("--remote-root-base", default="/home/Gent/.virtuoso-bridge-stress")
    ap.add_argument("--work-dir", default=None)
    args = ap.parse_args()
    wd = Path(args.work_dir) if args.work_dir else Path(tempfile.mkdtemp(prefix="vb-remote-stress-"))
    set_working_dir(wd)
    reg = load_registry(); users = []
    for i in range(args.users):
        user = f"fr{i:03d}"; token = f"{args.token_prefix}-{i:02d}"
        e = UserEntry(token=token, mode="remote")
        e.ssh.default.host = args.host; e.ssh.default.user = args.ssh_user; e.ssh.backend = "paramiko"; e.runtime.thread_pool_size = 8
        for name in ("gui", "daemon", "command", "file", "spectre"):
            r = getattr(e.roles, name); r.host = args.host; r.user = args.ssh_user; r.root = f"{args.remote_root_base.rstrip('/')}/{user}/{name}"
        e.roles.daemon.daemon_port = args.base_port + i; e.roles.daemon.local_port = args.local_port_base + i; e.roles.daemon.python = "/usr/bin/python3"; e.cdslog.log_level = "off"
        reg.register(user, e)
        p = wd / f"in-{i}.bin"; p.write_bytes(token.encode() * 512); users.append((user, token, p))
    server = BusinessServer(wd); stats = {"ok": 0, "retries": 0, "errors": []}; lock = __import__("threading").Lock()

    def run_user(i: int):
        user, token, payload = users[i]
        time.sleep((i % args.max_workers) * 0.04)
        try:
            def upload():
                for attempt in range(100):
                    r = server.upload_file(payload, f"roundtrip/{user}.bin", timeout=60, token=token)
                    if r.returncode == 0 or r.kind != "rejected": return r
                    with lock: stats["retries"] += 1
                    time.sleep(0.05 + attempt * 0.01)
                return r
            up = upload()
            if up.returncode != 0: return f"{user} upload {up.kind} {up.stderr}"
            out = wd / f"out-{i}.bin"; dn = server.download_file(f"roundtrip/{user}.bin", out, timeout=60, token=token)
            if dn.returncode != 0: return f"{user} download {dn.kind} {dn.stderr}"
            if hashlib.sha256(out.read_bytes()).digest() != hashlib.sha256(payload.read_bytes()).digest(): return f"{user} checksum"
            sk = server.execute_skill("1+1", timeout=60, token=token)
            if not sk.ok or sk.output.strip() != "2": return f"{user} skill {sk.errors}"
            cm = server.run_command(f"echo {user}", timeout=60, token=token)
            if cm.returncode != 0 or user not in cm.stdout: return f"{user} command {cm.kind}"
            gui = server.run_gui_command(f"echo gui-{user}", timeout=60, token=token)
            if gui.returncode != 0: return f"{user} gui {gui.kind}"
            sp = server.run_spectre_command(f"echo spec-{user}", timeout=60, token=token)
            if sp.returncode != 0: return f"{user} spectre {sp.kind}"
            return None
        except Exception as exc:
            return f"{user} exception {type(exc).__name__}: {exc}"

    start = time.time()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as pool:
            for err in pool.map(run_user, range(args.users)):
                if err:
                    with lock: stats["errors"].append(err)
                else:
                    with lock: stats["ok"] += 1
    finally:
        server.close()
    result = {"users": args.users, "max_workers": args.max_workers, "ok": stats["ok"], "retries": stats["retries"], "errors": stats["errors"][:10], "error_count": len(stats["errors"]), "elapsed_s": time.time() - start, "workdir": str(wd)}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not stats["errors"] and stats["ok"] == args.users else 2


if __name__ == "__main__":
    raise SystemExit(main())
