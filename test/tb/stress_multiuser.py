"""100-user middle-layer routing stress harness.

Simulates the registry with N users, one protocol-accurate daemon endpoint per
user (skills), plus per-user command/file traffic.  Every instruction must
receive a response; the skill response must come from the daemon owning that
token (automatic routing check).

Usage: python test/tb/stress_multiuser.py --users 100
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from common.registry import UserEntry, load_registry
from common.paths import registry_path, override_work_dir_for_tests
from _win import no_window


class FakeDaemon:
    """Protocol-accurate bottom endpoint whose skill output is its token."""

    def __init__(self, token):
        self.token = token
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(5)
        self.port = self._sock.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            try:
                data = b""
                while True:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    data += chunk
                req = json.loads(data.decode("utf-8"))
                if req.get("token") != self.token:
                    conn.sendall(b"\x15" + json.dumps({"error": "invalid token", "log": ""}).encode() + b"\x1e")
                else:
                    value = self.token if "1+1" in req.get("skill", "") else "3"
                    conn.sendall(b"\x02" + json.dumps({"value": value, "log": ""}).encode() + b"\x1e")
                conn.close()
            except Exception:
                try:
                    conn.close()
                except OSError:
                    pass

    def close(self):
        self._sock.close()


def build_registry(users, wd):
    registry = load_registry(registry_path())
    daemons = []
    tokens = []
    roots = []
    for i in range(users):
        token = f"tok-{i:03d}"
        daemon = FakeDaemon(token)
        daemons.append(daemon)
        entry = UserEntry(token=token, mode="local")
        entry.roles.daemon.daemon_port = daemon.port
        entry.roles.daemon.local_port = daemon.port
        entry.roles.daemon.root = str((Path(wd) / "users" / f"u{i}").resolve())
        registry.register(f"u{i}", entry)
        tokens.append(token)
        roots.append(entry.roles.daemon.root)
    return registry, daemons, tokens, roots


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=300)
    args = parser.parse_args(argv)

    wd = Path(tempfile.mkdtemp())
    override_work_dir_for_tests(wd)
    registry, daemons, tokens, roots = build_registry(args.users, wd)
    server_port = free_port()

    server = subprocess.Popen(
        [sys.executable, "-m", "server.stress_server",
         "--port", str(server_port), "--work-dir", str(wd)],
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
        env={**__import__("os").environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src")},
        **no_window(),
    )
    try:
        for _ in range(40):
            try:
                socket.create_connection(("127.0.0.1", server_port), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.25)
        cmd = [
            sys.executable, str(Path(__file__).resolve().parent / "stress_client.py"),
            "--base", f"http://127.0.0.1:{server_port}",
            "--tokens", ",".join(tokens),
            "--file-roots", ",".join(roots),
            "--concurrency", str(args.concurrency),
            "--commands", str(args.users * 6),
            "--skills", str(args.users * 4),
            "--uploads", str(args.users * 2),
            "--downloads", str(args.users * 2),
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=1200,
            **no_window(),
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        print("client rc:", result.returncode)
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
        for d in daemons:
            d.close()


if __name__ == "__main__":
    main()
