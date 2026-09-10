"""Live end-to-end middle+bottom test against the real Virtuoso (wsl-gent).

Run with:  python -m unittest test.e2e.test_e2e_live -v
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from transport.middle import BusinessServer
from transport.register import RegistrationFlow, RegistrationRequest
from transport.runtime_paths import set_working_dir
from transport.ssh import SSHRunner

HOST = "wsl-gent"
USER = "Gent"
SCRATCH = "/home/Gent/.virtuoso-bridge"


def _discover_current_daemon() -> tuple[str, int] | None:
    """Find a running new-protocol daemon: (token, port)."""
    try:
        out = subprocess.run(
            ["ssh", HOST, 'pgrep -fa "ramic_bridge_daemon_(3|27)\\.py"'],
            capture_output=True, text=True, timeout=20,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    found: list[tuple] = []
    for line in out.splitlines():
        if "bash -c" in line or "pgrep" in line:
            continue
        parts = line.split()
        py_idx = next((i for i, part in enumerate(parts) if part.endswith(".py")), None)
        if py_idx is None:
            continue
        tail = parts[py_idx + 1:]
        if len(tail) < 2:
            continue
        try:
            port = int(tail[1])
        except ValueError:
            continue
        # legacy daemons predate the token argument and accept any token
        token = tail[2] if len(tail) >= 3 else None
        found.append((token, port))
    # prefer a token-bearing daemon: RBStop + load must survive in one request
    for token, port in found:
        if token:
            return token, port
    return found[0] if found else None


def _free_local_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _send_load(setup: str, token: str, port: int) -> None:
    """Load setup into CIW through an existing daemon (RBStop + load)."""
    proc = subprocess.Popen(
        ["ssh", "-N", "-L", f"16599:127.0.0.1:{port}", HOST],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(1.5)
        s = socket.create_connection(("127.0.0.1", 16599), timeout=25)
        try:
            skill = f'progn(RBStop() load("{setup}"))'
            payload = {"skill": skill, "timeout": 25, "token": token, "log_level": "all", "log_max_bytes": 65536}
            if token is None:
                payload.pop("token", None)
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


class TestLiveE2E(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("VB_E2E") == "1", "set VB_E2E=1 to run live tests")
    def test_full_flow(self):
        token = "e2e-" + uuid.uuid4().hex[:8]
        wd = set_working_dir(Path(tempfile.mkdtemp()))
        server = BusinessServer(wd)

        # 1-4. six-step registration: apply (validate + probe + deploy)
        flow = RegistrationFlow(server.registry)
        local_port = _free_local_port()  # avoid stale detached tunnels
        state = flow.apply(RegistrationRequest(
            user="e2e", token=token, host=HOST, ssh_user=USER,
            scratch_root=SCRATCH, local_port=local_port,
        ))
        self.assertEqual(state.stage, "deployed", str(state.errors))
        self.assertTrue(state.setup_path.startswith(SCRATCH))

        # load into CIW (through whichever new daemon is running)
        current = _discover_current_daemon()
        self.assertIsNotNone(current, "no running bridge daemon to bootstrap from")
        cur_token, cur_port = current
        _send_load(state.setup_path, cur_token, cur_port)
        time.sleep(2)

        # 5-6. verify (connectivity smoke + registry commit)
        state = flow.verify()
        self.assertEqual(state.stage, "committed", str(state.errors) + str(state.report))

        # 5. skill returns value + log
        r = server.execute_skill("1+1", token=token)
        self.assertTrue(r.ok, str(r))
        self.assertEqual(r.output.strip().strip('"'), "2")
        self.assertTrue(r.log)

        # 6. command
        c = server.run_command("echo vb-ok", token=token)
        self.assertEqual((c.returncode, c.stdout.strip()), (0, "vb-ok"))

        # 7. upload/download roundtrip with digest verify
        local = Path(wd) / "payload.bin"
        local.write_bytes(b"hello-vb-" * 2000)
        remote = f"{SCRATCH}/{token}/status/payload.bin"
        u = server.upload_file(local, remote, token=token)
        self.assertEqual(u.returncode, 0, str(u))
        back = Path(wd) / "back.bin"
        d = server.download_file(remote, back, token=token)
        self.assertEqual(d.returncode, 0, str(d))
        self.assertEqual(back.read_bytes(), local.read_bytes())

        # 8. parallel: two remote commands must overlap in wall-clock time
        # (interval overlap is robust against slow cold SSH handshakes)
        results: dict[int, tuple[float, float]] = {}
        def run(i: int) -> None:
            cmd = (
                "s=$(date +%s.%N); sleep 2; e=$(date +%s.%N); "
                "printf '%s %s' \"$s\" \"$e\""
            )
            r = server.run_command(cmd, token=token, parallel=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            parts = r.stdout.strip().split()
            results[i] = (float(parts[0]), float(parts[1]))
        ts = [threading.Thread(target=run, args=(i,)) for i in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        (s0, e0), (s1, e1) = results[0], results[1]
        overlap = min(e0, e1) - max(s0, s1)
        self.assertGreater(overlap, 0.5)  # serial execution would give ~0


    @unittest.skipUnless(os.environ.get("VB_E2E") == "1", "set VB_E2E=1 to run live tests")
    def test_paramiko_backend_live(self):
        runner = SSHRunner(HOST, user=USER, backend="paramiko", connect_timeout=20)
        try:
            res = runner.run_command("echo vb-ok-paramiko")
            self.assertEqual(res.returncode, 0)
            self.assertEqual(res.stdout.strip(), "vb-ok-paramiko")
            remote = f"{SCRATCH}/_paramiko_probe.txt"
            up = runner.upload_text("paramiko-text-probe", remote)
            self.assertEqual(up.returncode, 0)
            check = runner.run_command(f"cat {remote}")
            self.assertEqual(check.stdout.strip(), "paramiko-text-probe")
        finally:
            runner.close()


if __name__ == "__main__":
    unittest.main()
