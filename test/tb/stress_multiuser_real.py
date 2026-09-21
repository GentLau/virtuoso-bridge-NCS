"""Multi-user routing stress against REAL Virtuoso daemons (remote mode).

Uses the committed registry in --work-dir (created by multi_virtuoso_pilot.py).
Every skill request executes ``RBDToken`` and must return the token owned by
the daemon that answered — a per-user routing check on real daemons, not
protocol fakes.  Commands/upload/download go through the same middle layer.

Usage: python test/tb/stress_multiuser_real.py --work-dir C:\\Users\\user\\vb-multi-work-2
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from common.registry import load_registry
from common.paths import registry_path, override_work_dir_for_tests
from _win import no_window


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--port", type=int, default=8127)
    parser.add_argument("--users", type=int, default=0, help="0 = every committed user")
    parser.add_argument("--concurrency", type=int, default=200)
    parser.add_argument("--cmds-per-user", type=int, default=6)
    parser.add_argument("--skills-per-user", type=int, default=4)
    parser.add_argument("--files-per-user", type=int, default=2)
    parser.add_argument("--parallel", action="store_true")
    args = parser.parse_args(argv)

    wd = Path(args.work_dir).resolve()
    override_work_dir_for_tests(wd)
    registry = load_registry(registry_path())

    entries = sorted(
        registry.entries(),
        key=lambda kv: (kv[1].roles.daemon.daemon_port or 0, kv[0]),
    )
    if args.users:
        entries = entries[: args.users]
    if not entries:
        print("no committed users in registry")
        raise SystemExit(2)

    tokens = [e.token for _, e in entries]
    roots = [e.roles.daemon.root for _, e in entries]
    users = len(tokens)
    print(
        f"real-daemon stress: users={users} "
        f"daemon_ports={[e.roles.daemon.daemon_port for _, e in entries]}"
    )

    server_log = wd / "log" / "stress_server.log"
    server_log.parent.mkdir(parents=True, exist_ok=True)
    server_log_fh = open(server_log, "wb")
    server = subprocess.Popen(
        [sys.executable, "-m", "server.stress_server", "--port", str(args.port), "--work-dir", str(wd)],
        stdout=server_log_fh,
        stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src")},
        **no_window(),
    )
    try:
        for _ in range(80):
            try:
                socket.create_connection(("127.0.0.1", args.port), timeout=0.5).close()
                break
            except OSError:
                if server.poll() is not None:
                    print("stress server exited early, rc=", server.returncode)
                    raise SystemExit(1)
                time.sleep(0.25)

        cmd = [
            sys.executable,
            str(Path(__file__).resolve().parent / "stress_client.py"),
            "--base", f"http://127.0.0.1:{args.port}",
            "--tokens", ",".join(tokens),
            "--file-roots", ",".join(roots),
            "--concurrency", str(args.concurrency),
            "--commands", str(users * args.cmds_per_user),
            "--skills", str(users * args.skills_per_user),
            "--uploads", str(users * args.files_per_user),
            "--downloads", str(users * args.files_per_user),
            "--skill-expr", "RBDToken",
            "--skill-expect", "token",
            "--remote",
        ] + (["--parallel"] if args.parallel else [])
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=1800,
            **no_window(),
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        print("client rc:", result.returncode)
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        server_log_fh.close()


if __name__ == "__main__":
    main()
