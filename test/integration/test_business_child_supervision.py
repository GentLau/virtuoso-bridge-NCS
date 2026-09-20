"""Supervised business child: stdin commands / stdout events / death-watch.

Spec: 顶层补充 v27 §1.1 — 业务进程由管理进程以父子模型拉起，reload 经内部
控制通道触发；管理退出（stdin EOF）停止业务进程。这里直接以子进程方式驱动
业务面，不经过控制面 HTTP 端点。
"""

import json
import http.client
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"


class _Child:
    """Spawn `python -m server.api_server --supervised` and speak its protocol."""

    def __init__(self):
        self.work_dir = Path(tempfile.mkdtemp(prefix="vb-supervised-"))
        env = dict(os.environ)
        env["PYTHONPATH"] = str(SRC)
        self.proc = subprocess.Popen(
            [
                sys.executable, "-m", "server.api_server",
                "--host", "127.0.0.1", "--port", "0",
                "--work-dir", str(self.work_dir),
                "--supervised",
            ],
            cwd=str(ROOT),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.events: list[dict] = []
        self.deadline = time.monotonic() + 30

    def next_event(self, timeout: float = 20.0) -> dict:
        """Read stdout until one VB-EVENT line arrives (other lines ignored)."""
        assert self.proc.stdout is not None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.proc.stdout.readline()
            if not line:
                raise AssertionError(
                    f"child stdout closed; stderr={self._stderr_tail()!r}"
                )
            if line.startswith("VB-EVENT "):
                event = json.loads(line[len("VB-EVENT "):])
                self.events.append(event)
                return event
            if self.proc.poll() is not None:
                raise AssertionError(
                    f"child exited rc={self.proc.returncode}; "
                    f"stderr={self._stderr_tail()!r}"
                )
        raise AssertionError("timed out waiting for a child event")

    def send(self, command: str) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps({"cmd": command}) + "\n")
        self.proc.stdin.flush()

    def close_stdin(self) -> None:
        if self.proc.stdin is not None:
            self.proc.stdin.close()

    def _stderr_tail(self, limit: int = 800) -> str:
        if self.proc.stderr is None:
            return ""
        try:
            # non-blocking-ish: only read what the child already flushed
            return self.proc.stderr.read(limit)
        except (OSError, ValueError):
            return ""

    def wait(self, timeout: float = 20.0) -> int:
        return self.proc.wait(timeout=timeout)

    def kill(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass


class TestSupervisedBusinessChild(unittest.TestCase):
    def setUp(self):
        self.child = _Child()
        ready = self.child.next_event()
        self.assertEqual(ready["event"], "ready")
        self.port = int(ready["port"])
        self.assertGreater(self.port, 0)

    def tearDown(self):
        self.child.kill()

    def test_reload_round_trip(self):
        self.child.send("reload")
        done = self.child.next_event()
        self.assertEqual(done["event"], "reload_done")
        self.assertTrue(done["ok"], done)

    def test_drain_stops_child_cleanly(self):
        self.child.send("drain")
        started = self.child.next_event()
        self.assertEqual(started["event"], "drain_started")
        done = self.child.next_event()
        self.assertEqual(done["event"], "drain_done")
        self.assertTrue(done["ok"], done)
        self.assertEqual(self.child.wait(timeout=20), 0)

    def test_stdin_eof_stops_child(self):
        """管理进程退出（管道 EOF）→ 业务进程自行收尾退出。"""
        self.child.close_stdin()
        self.assertEqual(self.child.wait(timeout=35), 0)

    # -- helpers -------------------------------------------------------------
    def _health(self) -> dict:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("GET", "/health")
        body = json.loads(conn.getresponse().read().decode("utf-8"))
        conn.close()
        return body

    def _operation(self, payload: dict) -> tuple[int, dict]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        conn.request(
            "POST", "/api/operation", json.dumps(payload),
            {"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        body = json.loads(resp.read().decode("utf-8"))
        conn.close()
        return resp.status, body

    def test_reload_hot_applies_business_thread_pool_size(self):
        """v27: reload 重新导入 config.json，线程池上限热生效。"""
        before = self._health()["data"]["max_inflight"]
        (self.child.work_dir / "config.json").write_text(
            json.dumps({"business_thread_pool_size": 5}), encoding="utf-8"
        )
        self.child.send("reload")
        done = self.child.next_event()
        self.assertEqual(done["event"], "reload_done")
        self.assertTrue(done["ok"], done)
        after = self._health()["data"]["max_inflight"]
        self.assertEqual(after, 5)
        self.assertNotEqual(before, after)

    def test_reload_swaps_registry_snapshot(self):
        """v27: reload 重新导入 registry.json，新 token 立即生效。"""
        status, body = self._operation(
            {
                "operation": "basic.command.run",
                "token": "tok-reload",
                "cmd": "echo reload-ok",
            }
        )
        self.assertEqual(status, 200, body)
        self.assertFalse(body["ok"], "unknown token must fail before reload")

        user_dir = self.child.work_dir / "role-root"
        registry = {
            "reload-user": {
                "token": "tok-reload",
                "mode": {"default": "local"},
                "ssh": {"default": {}},
                "root": {"default": None},
                "roles": {
                    name: {
                        "root": str(user_dir / name),
                        "max_sessions": 10,
                    }
                    for name in ("gui", "daemon", "command", "file", "spectre")
                },
                "runtime": {
                    "thread_pool_size": 32,
                    "channel_budget": 10,
                    "connect_timeout": 15.0,
                },
                "cdslog": {"log_level": "off", "log_max_bytes": 65536},
                "registered_at": None,
            }
        }
        for name in ("gui", "daemon", "command", "file", "spectre"):
            (user_dir / name).mkdir(parents=True, exist_ok=True)
        (self.child.work_dir / "registry.json").write_text(
            json.dumps(registry), encoding="utf-8"
        )
        self.child.send("reload")
        done = self.child.next_event()
        self.assertEqual(done["event"], "reload_done")
        self.assertTrue(done["ok"], done)

        status, body = self._operation(
            {
                "operation": "basic.command.run",
                "token": "tok-reload",
                "cmd": "echo reload-ok",
            }
        )
        self.assertEqual(status, 200, body)
        self.assertTrue(body["ok"], body)
        self.assertIn("reload-ok", json.dumps(body))


if __name__ == "__main__":
    unittest.main()
