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

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"

#: The production admin plaintext must not live in the repository (the server
#: stores only its SHA-256; see ``src/register/server.py``).  Priority:
#:   1) ``VB_ADMIN_TOKEN`` env var（CI/临时跑法）；
#:   2) 仓库根下 **gitignored** 的 ``test/artifacts/admin-token.txt``。
#: 第二条是 2026-09-23 补的：以前只认 env，没人 export 时这 3 条管理端点用例
#: 会**静默 skip**（离线层看上去"全绿"，其实父子生命周期/restart 根本没验）。
#: 两条都没有才 skip。
def _admin_token() -> str:
    token = os.environ.get("VB_ADMIN_TOKEN", "").strip()
    if token:
        return token
    token_file = ROOT / "test" / "artifacts" / "admin-token.txt"
    try:
        return token_file.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


ADMIN = _admin_token()
_ADMIN_REASON = (
    "set VB_ADMIN_TOKEN or create the gitignored test/artifacts/admin-token.txt "
    "to exercise the admin endpoints"
)


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
        # 系统 temp + ``vb-`` 前缀：由 test/conftest.py 在会话结束时回收，
        # 不再写进 test/artifacts/（那是 TB 证据树）。
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
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
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

    @unittest.skipUnless(ADMIN, _ADMIN_REASON)
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

    @unittest.skipUnless(ADMIN, _ADMIN_REASON)
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

    @unittest.skipUnless(ADMIN, _ADMIN_REASON)
    def test_http_reload_picks_up_registry_file(self):
        """spec《其他/多用户与注册》§1 + 《顶层/控制面与业务面》§1.1 的**语义**：

        ① 运行期**不自动读文件**——改了 `registry.json` 但没触发 reload，新 token 必须仍无效；
        ② `POST /api/process/reload`（管理权限）后**立即生效**——新 token 马上可用。

        这是"热重载要手动发命令"的端到端证据（走控制面 HTTP，不是 spawn 通道直发）。
        """
        user_dir = self.work_dir / "role-root"
        for name in ("gui", "daemon", "command", "file", "spectre"):
            (user_dir / name).mkdir(parents=True, exist_ok=True)

        def _entry(token: str) -> dict:
            return {
                "token": token,
                "mode": {"default": "local"},
                "ssh": {"default": {}},
                "root": {"default": None},
                "roles": {name: {"root": str(user_dir / name), "max_sessions": 10}
                          for name in ("gui", "daemon", "command", "file", "spectre")},
                "runtime": {"thread_pool_size": 32, "channel_budget": 10, "connect_timeout": 15.0},
                "cdslog": {"log_level": "off", "log_max_bytes": 65536},
                "registered_at": None,
            }

        def _write(users: dict) -> None:
            (self.work_dir / "registry.json").write_text(
                json.dumps(users), encoding="utf-8")

        def _run(token: str) -> tuple[int, dict]:
            connection = http.client.HTTPConnection("127.0.0.1", self.business_port, timeout=35)
            connection.request("POST", "/api/operation", json.dumps(
                {"operation": "basic.command.run", "token": token, "cmd": "echo reload-ok"}),
                {"Content-Type": "application/json"})
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            connection.close()
            return response.status, payload

        def _reload() -> None:
            status, raw = _http("POST", self.control_port, "/api/process/reload",
                                {"target": "business"}, admin=True)
            self.assertEqual(status, 200, raw)

        # v1：一个 local 模式用户，先 reload 装进业务进程
        _write({"reload-probe": _entry("tok-reload-probe")})
        _reload()
        status, body = _run("tok-reload-probe")
        self.assertEqual(status, 200, body)
        self.assertTrue(body["ok"], body)
        self.assertIn("reload-ok", str((_c1_wrapper(body)).get("result")))

        # ② v2 多一个用户，但**不** reload → 新 token 仍无效（运行期不自动读文件）
        _write({"reload-probe": _entry("tok-reload-probe"),
                "reload-probe2": _entry("tok-reload-probe2")})
        status, body = _run("tok-reload-probe2")
        self.assertEqual(status, 200, body)
        self.assertFalse(body["ok"], f"must not auto-read registry: {body}")
        self.assertIn("invalid token", str(body.get("error")))

        # ③ 显式 reload 后 → 立刻可用
        _reload()
        status, body = _run("tok-reload-probe2")
        self.assertEqual(status, 200, body)
        self.assertTrue(body["ok"], f"reload must take effect immediately: {body}")

    @unittest.skipUnless(ADMIN, _ADMIN_REASON)
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


# --- C1 兼容垫片（2026-09-29，C3）------------------------------------------------
# C1（2f88853）起：业务载荷直返顶层（值型 `value`、命令/skill 型 `result`）、
# 成功默认省略 `steps`、失败壳去掉 `data`。历史 TB 按 `response["data"]` 解析，
# 本垫片把新契约响应合成为旧 `data` 壳，让既有解析零改动继续工作。
def _c1_wrapper(body):
    if not isinstance(body, dict):
        return {}
    if isinstance(body.get("data"), dict):
        return body["data"]
    wrapped = {"ok": body.get("ok"), "error": body.get("error")}
    for key in ("value", "result", "steps"):
        if key in body:
            wrapped[key] = body[key]
    return wrapped
