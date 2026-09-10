"""Live middle-layer pressure test against wsl-gent.

Registers a dedicated user, loads the daemon into the running CIW, then
starts the stress HTTP server and hammers it with mixed command/skill calls.

Usage: python scripts/stress_live.py
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from transport.register import RegistrationFlow, RegistrationRequest
from transport.registry import load_registry
from transport.runtime_paths import registry_path, set_working_dir

HOST = "wsl-gent"
USER = "Gent"


def discover_daemon():
    try:
        out = subprocess.run(
            ["ssh", HOST, 'pgrep -fa "ramic_bridge_daemon_(3|27)\\.py"'],
            capture_output=True, text=True, timeout=20,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    found = []
    for line in out.splitlines():
        if "bash -c" in line or "pgrep" in line:
            continue
        parts = line.split()
        py_idx = next((i for i, p in enumerate(parts) if p.endswith(".py")), None)
        if py_idx is None:
            continue
        tail = parts[py_idx + 1:]
        if len(tail) < 2:
            continue
        try:
            port = int(tail[1])
        except ValueError:
            continue
        token = tail[2] if len(tail) >= 3 else None
        found.append((token, port))
    for token, port in found:
        if token:
            return token, port
    return (found[0] if found else (None, None))


def send_load(setup, token, port):
    proc = subprocess.Popen(
        ["ssh", "-N", "-L", "16599:127.0.0.1:%d" % port, HOST],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(1.5)
        s = socket.create_connection(("127.0.0.1", 16599), timeout=25)
        try:
            payload = {
                "skill": 'progn(RBStop() load("%s"))' % setup,
                "timeout": 25,
                "token": token,
                "log_level": "all",
                "log_max_bytes": 65536,
            }
            s.sendall(json.dumps(payload).encode())
            s.shutdown(socket.SHUT_WR)
            try:
                while s.recv(65536):
                    pass
            except OSError:
                pass
        finally:
            s.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


def main():
    token = "stress-" + uuid.uuid4().hex[:8]
    wd = Path(tempfile.mkdtemp())
    set_working_dir(wd)
    registry = load_registry(registry_path())

    flow = RegistrationFlow(registry)
    state = flow.apply(RegistrationRequest(user="stress", token=token, host=HOST, ssh_user=USER))
    if state.stage != "deployed":
        print("deploy failed:", state.errors)
        sys.exit(1)
    print("deployed:", state.setup_path)

    cur_token, cur_port = discover_daemon()
    if cur_port is None:
        print("no running daemon to bootstrap from")
        sys.exit(1)
    send_load(state.setup_path, cur_token, cur_port)
    time.sleep(2)

    state = flow.verify()
    if state.stage != "committed":
        print("verify failed:", state.errors, state.report)
        sys.exit(1)
    print("committed:", token)

    import os
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    server_proc = subprocess.Popen(
        [sys.executable, "-m", "server.stress_server", "--port", "8126", "--work-dir", str(wd)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env,
    )
    try:
        for _ in range(20):
            if server_proc.poll() is not None:
                print("stress server exited early:", server_proc.stdout.read())
                sys.exit(1)
            try:
                socket.create_connection(("127.0.0.1", 8126), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.5)
        else:
            print("stress server did not bind:", server_proc.stdout.read())
            sys.exit(1)
        client = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent / "stress_client.py"),
             "--base", "http://127.0.0.1:8126", "--token", token,
             "--concurrency", "100", "--commands", "100", "--skills", "30",
             "--uploads", "20", "--downloads", "20", "--parallel"],
            capture_output=True, text=True, timeout=300,
        )
        print(client.stdout)
        if client.stderr:
            print(client.stderr)
        print("client rc:", client.returncode)
    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()


if __name__ == "__main__":
    main()
