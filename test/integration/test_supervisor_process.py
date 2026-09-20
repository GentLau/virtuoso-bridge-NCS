"""Supervisor integration: parent/child lifecycle + /api/process/* endpoints.

Spec: 顶层补充 v27 §1/§1.1/§3 — 标准形态 = 同机双进程父子模型；管理端点在
控制端口；子进程意外退出不自动拉起；管理退出停止业务。
"""

import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
ADMIN = "V-9-ZM32KpykwpNXyMnmSTUTFB2o_jJVfG0-D_Vd_JA"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _http(method: str, port: int, path: str, body=None, admin=False, timeout=35):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if admin:
        headers["Authorization"] = "Bearer " + ADMIN
    payload = None if body is None else json.dumps(body)
    conn.request(method, path, payload, headers)
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8")
    conn.close()
    return resp.status, raw


class TestSupervisorProcess(unittest.TestCase):
    def setUp(self):
        self.work_dir = Path(tempfile.mkdtemp(prefix="vb-supervisor-"))
        self.control_port = _free_port()
        self.business_port = _free_port()
        env = dict(os.environ)
        env["PYTHONPATH"] = str(SRC)
        self.proc = subprocess.Popen(
            [
                sys.executable, "-m", "server.supervisor",
                "--control-port", str(self.control_port),
                "--business-port", str(self.business_port),
                "--work-dir", str(self.work_dir),
            ],
            cwd=str(ROOT),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        threading.Thread(target=self._drain, args=(self.proc.stdout,), daemon=True).start()
        threading.Thread(target=self._drain, args=(self.proc.stderr,), daemon=True).start()
        self._wait_http("/health", expect=200, timeout=40)

    def tearDown(self):
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=10)

    @staticmethod
    def _drain(stream):
        try:
            for _line in stream:
                pass
        except (OSError, ValueError):
            pass

    def _wait_http(self, path, *, expect, timeout, admin=False):
        deadline = time.monotonic() + timeout
        last = ""
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise AssertionError(
                    f"supervisor exited rc={self.proc.returncode}"
                )
            try:
                status, raw = _http("GET", self.control_port, path, admin=admin)
                last = raw
                if status == expect:
                    return raw
            except OSError:
                pass
            time.sleep(0.2)
        raise AssertionError(f"timed out waiting for {path}: {last}")

    def test_status_reload_restart(self):
        status, raw = _http(
            "GET", self.control_port, "/api/process/status", admin=True
        )
        self.assertEqual(status, 200, raw)
        payload = json.loads(raw)
        self.assertFalse(payload["same_process"])
        self.assertEqual(payload["state"], "ready")
        self.assertEqual(payload["port"], self.business_port)
        first_pid = payload["pid"]
        self.assertTrue(first_pid)

        status, raw = _http(
            "POST", self.control_port, "/api/process/reload",
            {"target": "business"}, admin=True,
        )
        self.assertEqual(status, 200, raw)
        self.assertEqual(json.loads(raw)["state"], "ready")

        status, raw = _http(
            "POST", self.control_port, "/api/process/restart",
            {"target": "business"}, admin=True,
        )
        self.assertEqual(status, 200, raw)
        payload = json.loads(raw)
        self.assertEqual(payload["state"], "ready")
        self.assertNotEqual(payload["pid"], first_pid, "restart must replace child")

    def test_target_and_permission_validation(self):
        status, _raw = _http(
            "POST", self.control_port, "/api/process/reload",
            {"target": "control"}, admin=True,
        )
        self.assertEqual(status, 400)
        status, _raw = _http(
            "POST", self.control_port, "/api/process/restart",
            {"target": "business"}, admin=False,
        )
        self.assertEqual(status, 401)

    def test_parent_exit_stops_business_child(self):
        """管理退出（子进程 stdin EOF）→ 业务进程自行收尾退出。"""
        status, raw = _http(
            "GET", self.control_port, "/api/process/status", admin=True
        )
        self.assertEqual(status, 200, raw)
        self.proc.kill()
        self.proc.wait(timeout=10)
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(
                    ("127.0.0.1", self.business_port), timeout=1
                ):
                    pass
            except OSError:
                return  # child no longer serves the business port
            time.sleep(0.5)
        self.fail("business child kept serving after the parent exited")


if __name__ == "__main__":
    unittest.main()
