# === TB 注释头（规范见 test/docs/写TB规范.md §0）=====================
# 作者: 设计/Codex
# 最后改动: 2026-09-28 12:04
# 依赖: 无
# =====================================================================
# 六步流程（按 test/docs/写TB规范.md §1–§6）：
# §1 环境检查：VB_E2E 门禁 + 发现真实 daemon；不满足则 skip。
# §2 构建：六步注册测试账号、绑定 work_root、建立 server。
# §3 最终检查：确认注册/runtime/隧道就绪。
# §4 执行：注册 + skill/command/file 全链路。
# §5 比对：阶段、marker、文件字节和下载结果与期望一致。
# §6 重复/收尾：单链一次完整执行；保留证据，不清理真实持久对象。
"""Live end-to-end middle+bottom test against the real Virtuoso (wsl-gent).

Run with:  python -m unittest test.e2e.test_e2e_live -v
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from transport.middle import BusinessServer
from register import RegistrationFlow, RegistrationRequest
from common.paths import work_root
from common.ssh import SSHRunner

HOST = "wsl-gent"
USER = "Gent"
SCRATCH = "/home/Gent/.virtuoso-bridge"


def _discover_current_daemon() -> tuple[str, int] | None:
    """Find a running new-protocol daemon to bootstrap from: (token, port).

    Only *real* daemons qualify: a fake Virtuoso (``fakevirt``) answers skill
    requests but cannot run ``ipcBeginProcess``, so bootstrapping through one
    fails later with "SKILL execution timed out" while looking like a bridge
    defect.  ``VB_E2E_BOOTSTRAP_TOKEN`` / ``VB_E2E_BOOTSTRAP_PORT`` pin an
    explicit (dedicated) CIW instead.

    Note: the bootstrap request is ``RBStop() + load(<new setup>)`` — it stops
    the daemon in the chosen CIW and starts the new one there.  The chosen CIW
    must therefore be dedicated to this test, not shared with other runs.
    """
    pinned_token = os.environ.get("VB_E2E_BOOTSTRAP_TOKEN")
    pinned_port = os.environ.get("VB_E2E_BOOTSTRAP_PORT")
    if pinned_token and pinned_port:
        return pinned_token, int(pinned_port)
    # P-046（2026-09-23）：**默认不再自动挑**。引导请求是 RBStop()+load(新 setup)，
    # 挑中别人的 CIW 会把那个实例的 daemon 换掉（本轮实测把在用实例打挂过）。
    # 只有在明确声明"整机专用、随便挑"时才允许自动发现。
    if os.environ.get("VB_E2E_ALLOW_AUTO_DISCOVER") != "1":
        return None
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
        if "fakevirt" in line:
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
        wd = work_root()
        server = BusinessServer()
        # 1-4. six-step registration: apply (validate + probe + deploy)
        flow = RegistrationFlow(server.registry)
        local_port = _free_local_port()  # avoid stale detached tunnels
        state = flow.apply(RegistrationRequest(
            mode="remote", user="e2e", token=token,
            # spec r22: remote role 必须带 SSH 凭据（key_dir 缺省 ~/.ssh，key 必填）。
            # 本 TB 之前没带 → 注册第一步直接 ValidationError（第五轮 live 复跑抓到）。
            ssh={"default": {"host": HOST, "user": USER,
                             "key_dir": os.environ.get("VB_E2E_KEY_DIR", "~/.ssh"),
                             "key": os.environ.get("VB_E2E_KEY", "id_ed25519")}},
            root={"default": SCRATCH},
            roles={"daemon": {"local_port": local_port}},
        ))
        self.assertEqual(state.stage, "deployed", str(state.errors))
        self.assertTrue(state.setup_path.startswith(SCRATCH))

        # load into CIW (through whichever new daemon is running)
        current = _discover_current_daemon()
        if current is None:
            self.skipTest(
                "需要**专用**引导 CIW：设 VB_E2E_BOOTSTRAP_TOKEN/PORT（或明确声明整机专用时 "
                "设 VB_E2E_ALLOW_AUTO_DISCOVER=1）。默认不自动挑实例 —— 见 P-046："
                "引导会 RBStop()+load(新 setup)，挑中别人的 CIW 会把对方打挂。")
        cur_token, cur_port = current
        _send_load(state.setup_path, cur_token, cur_port)
        time.sleep(2)

        # 5-6. verify (connectivity smoke) then explicit registry commit
        state = flow.verify()
        self.assertEqual(state.stage, "verified", str(state.errors) + str(state.report))
        state = flow.commit()
        self.assertEqual(state.stage, "committed", str(state.errors) + str(state.report))

        # 5. skill returns value + log: the bridge never injects CDS.log
        #    output, so write one user line and assert the [start,end) delta
        #    captures exactly that request's own output
        marker = f"vb-e2e-log-{token}"
        r = server.execute_skill(
            f'progn(hiPrintToLogFile("{marker}") 1+1)', token=token
        )
        self.assertTrue(r.ok, str(r))
        self.assertEqual(r.output.strip().strip('"'), "2")
        self.assertIn(marker, r.log)

        # 6. command
        c = server.run_command("echo vb-ok", token=token)
        self.assertEqual((c.returncode, c.stdout.strip()), (0, "vb-ok"))

        # 7. upload/download roundtrip with digest verify
        local = Path(wd) / "payload.bin"
        local.write_bytes(b"hello-vb-" * 2000)
        remote = f"{SCRATCH}/e2e/status/payload.bin"  # paths use the username, not token
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
