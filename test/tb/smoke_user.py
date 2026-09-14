"""Per-user smoke test: the five middle interfaces with per-stage timings.

Builds a throw-away registry (no registration flow, no HTTP server) and runs
skill / command / upload / download for one user, printing how long each stage
took and what it returned.  Use it to isolate one user or one role when a
multi-user run reports a slow or failing stage.

Usage::

    python test/tb/smoke_user.py --user vb03 --mode remote --host wsl-gent \
        --ssh-user Gent --daemon-port 65103 [--repeat 3]
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
import time
from pathlib import Path

_src = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_src))

from transport.registry import UserEntry, load_registry  # noqa: E402
from transport.register.probe import allocate_local_port  # noqa: E402
from transport.middle import BusinessServer  # noqa: E402
from transport.runtime_paths import registry_path, set_working_dir  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", required=True)
    ap.add_argument("--token", default=None)
    ap.add_argument("--mode", choices=["remote", "local"], default="remote")
    ap.add_argument("--host", default="wsl-gent")
    ap.add_argument("--ssh-user", default="Gent")
    ap.add_argument("--daemon-port", type=int, required=True)
    ap.add_argument("--daemon-root", default=None)
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--keep-workdir", action="store_true")
    args = ap.parse_args()

    token = args.token or f"smoke-{args.user}"
    wd = set_working_dir(Path(tempfile.mkdtemp(prefix="vb-smoke-")))
    reg = load_registry(registry_path())
    entry = UserEntry(token=token, mode=args.mode)
    entry.roles.daemon.daemon_port = args.daemon_port
    entry.roles.daemon.local_port = allocate_local_port(tries=200)
    entry.roles.daemon.root = args.daemon_root or f"/home/{args.ssh_user}/.virtuoso-bridge/{args.user}"
    if args.mode == "remote":
        for role in ("daemon", "command", "file"):
            getattr(entry.roles, role).host = args.host
            getattr(entry.roles, role).user = args.ssh_user
        entry.roles.daemon.expected_user = args.ssh_user
    reg.register(args.user, entry)

    print(f"workdir={wd} token={token} local_port={entry.roles.daemon.local_port}")
    server = BusinessServer(wd)
    failures = 0
    for round_no in range(1, args.repeat + 1):
        stages = []
        t0 = time.time()
        sk = server.execute_skill("RBDToken", token=token)
        stages.append(("skill", time.time() - t0, sk.ok, sk.output if sk.ok else sk.errors))
        t0 = time.time()
        cm = server.run_command("echo smoke-ok", token=token)
        stages.append(("command", time.time() - t0, cm.returncode == 0, f"{cm.kind} rc={cm.returncode} {cm.stdout.strip()}{cm.stderr.strip()[:80]}"))
        payload = f"{token}-{round_no}".encode() * 256
        src = Path(tempfile.mkdtemp()) / "smoke.bin"
        src.write_bytes(payload)
        t0 = time.time()
        up = server.upload_file(src, f"smoke-{round_no}.bin", token=token)
        stages.append(("upload", time.time() - t0, up.returncode == 0, f"{up.kind} {up.stderr[:80]}"))
        dst = Path(tempfile.mkdtemp()) / "back.bin"
        t0 = time.time()
        dn = server.download_file(f"smoke-{round_no}.bin", dst, token=token)
        digest_ok = dst.exists() and hashlib.sha256(dst.read_bytes()).hexdigest() == hashlib.sha256(payload).hexdigest()
        stages.append(("download", time.time() - t0, dn.returncode == 0 and digest_ok, f"{dn.kind} sha_ok={digest_ok} {dn.stderr[:80]}"))
        for name, dt, ok, detail in stages:
            if not ok:
                failures += 1
            print(f"round{round_no} {name:9s} {dt:7.2f}s ok={ok} {detail}")
    print("FAILURES:", failures)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
