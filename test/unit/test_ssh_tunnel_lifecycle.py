"""隧道生命周期契约：两个 OS 分支都必须登记端口/退避（BUG-1 及同类残留回归）。

关键点（评审指出过）：测试必须走**代码路径**，不能手工往对象里注入
``_tunnel_local_port`` 之类的状态，否则测的是“修复后的状态”而不是“修复后的代码”。
这里通过伪造 ``Popen`` + ``can_reach_port`` 真实调用 ``start_port_forward``。
"""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from common import ssh as ssh_mod
from common.ssh import SSHRunner


class FakeStream:
    def readable(self):
        return True

    def read(self):
        return b""


class FakePopen:
    """可配置的假隧道进程：alive=False 表示 ssh 立刻退出（如端口被占用）。"""

    instances = 0

    def __init__(self, cmd=None, alive=True, stderr=None, **kwargs):
        FakePopen.instances += 1
        self.pid = 4242
        self.cmd = cmd
        self.alive = alive
        self.returncode = None if alive else 1
        # real callers pass stderr=subprocess.PIPE (an int); only a stream-like
        # object is useful to the code under test
        self.stderr = stderr if hasattr(stderr, "readable") else FakeStream()
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


def runner():
    return SSHRunner(host="server-a", user="u", backend="openssh", persistent_shell=False)


class TunnelPathMixin:
    """在 POSIX / Windows 两个分支上跑同一组断言。"""

    platform = "nt"

    def setUp(self):
        FakePopen.instances = 0
        self._plat_patch = mock.patch.object(ssh_mod, "_IS_WINDOWS", self.platform == "nt")
        self._plat_patch.start()
        self.addCleanup(self._plat_patch.stop)

    def _start(self, r, alive=True, port_reachable=False, settle=0.05):
        with mock.patch.object(ssh_mod.subprocess, "Popen",
                               side_effect=lambda cmd, **kw: FakePopen(cmd, alive=alive, **kw)), \
             mock.patch.object(SSHRunner, "can_reach_port",
                               staticmethod(lambda port: port_reachable)):
            return r.start_port_forward(65081, remote_port=65103, settle=settle)

    def test_own_process_records_port_and_is_alive(self):
        r = runner()
        # O6: 两个分支都以“进程活着 + forwarding 可达”判定健康
        proc = self._start(r, alive=True, port_reachable=True)
        self.assertIsNotNone(proc)
        self.assertEqual(r._tunnel_local_port, 65081)
        self.assertFalse(r._tunnel_using_external)
        with mock.patch.object(SSHRunner, "can_reach_port", staticmethod(lambda p: True)):
            self.assertTrue(r.is_tunnel_alive)
        self.assertEqual(r._tunnel_failures, 0)

    def test_external_listener_is_recorded_and_alive(self):
        """复用别人的监听：必须记录端口，否则每个请求都会重开隧道（BUG-1）。"""
        r = runner()
        result = self._start(r, alive=False, port_reachable=True)
        if self.platform == "nt":
            self.assertIsNone(result)
        self.assertTrue(r._tunnel_using_external)
        self.assertEqual(r._tunnel_local_port, 65081)
        with mock.patch.object(SSHRunner, "can_reach_port", staticmethod(lambda p: True)):
            self.assertTrue(r.is_tunnel_alive)

    def test_failure_sets_backoff_and_next_call_fast_fails(self):
        r = runner()
        with self.assertRaises(RuntimeError):
            self._start(r, alive=False, port_reachable=False)
        self.assertEqual(r._tunnel_failures, 1)
        self.assertGreater(r._tunnel_next_try_at, time.monotonic())
        # 退避期内不得再 spawn
        with mock.patch.object(ssh_mod.subprocess, "Popen") as popen:
            with self.assertRaises(RuntimeError):
                r.start_port_forward(65081, remote_port=65103, settle=0.05)
            popen.assert_not_called()


class TestPosixBranch(TunnelPathMixin, unittest.TestCase):
    platform = "posix"


class TestWindowsBranch(TunnelPathMixin, unittest.TestCase):
    platform = "nt"


class TestCloseTearsDownTunnel(unittest.TestCase):
    def test_close_terminates_own_tunnel_process(self):
        r = runner()
        proc = FakePopen(alive=True)
        r._tunnel_proc = proc
        r._tunnel_pid = proc.pid
        r._tunnel_local_port = 65081
        r.close()
        self.assertTrue(proc.terminated, "close() 必须终止自己的隧道句柄")
        self.assertIsNone(r._tunnel_local_port)


class TestParamikoTunnelPath(unittest.TestCase):
    def test_paramiko_backend_uses_in_process_forward(self):
        class FakeTunnel:
            pid = 9999

            def __init__(self):
                self.terminated = False

            def poll(self):
                return None

            def terminate(self):
                self.terminated = True

            def wait(self, timeout=None):
                return 0

        class FakeBackend:
            def __init__(self):
                self.tunnel = FakeTunnel()
                self.calls = []

            def open_port_forward(self, local_port, remote_port, **kwargs):
                self.calls.append((local_port, remote_port, kwargs))
                return self.tunnel

        runner = SSHRunner(
            host="server-a", user="u", backend="paramiko",
            persistent_shell=False,
        )
        backend = FakeBackend()
        runner._paramiko_backend = backend
        with mock.patch.object(ssh_mod.subprocess, "Popen") as popen, \
             mock.patch.object(
                 SSHRunner, "can_reach_port",
                 staticmethod(lambda port: False),
             ):
            proc = runner.start_port_forward(
                65081, remote_port=65103, settle=0.05
            )
        self.assertIs(proc, backend.tunnel)
        self.assertEqual(backend.calls[0][0:2], (65081, 65103))
        popen.assert_not_called()
        runner.stop_port_forward()
        self.assertTrue(backend.tunnel.terminated)


class TestControlPathNamespace(unittest.TestCase):
    def test_control_path_includes_pid_and_identity(self):
        a = ssh_mod._short_control_path("server-a", "u", None, "tok-1")
        b = ssh_mod._short_control_path("server-a", "u", None, "tok-1")
        c = ssh_mod._short_control_path("server-a", "u", None, "tok-2")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        with mock.patch.object(os, "getpid", return_value=os.getpid() + 1):
            d = ssh_mod._short_control_path("server-a", "u", None, "tok-1")
        self.assertNotEqual(a, d)

    def test_control_path_covers_full_endpoint_identity(self):
        """§6.5/§4: endpoint=(host,user,jump_host,jump_user,proxy)；只差
        jump_user 或 proxy 的两个 endpoint 不得复用同一个 ControlMaster。"""
        base = ssh_mod._short_control_path("server-a", "u", "bastion")
        other_jump_user = ssh_mod._short_control_path(
            "server-a", "u", "bastion", jump_user="other"
        )
        other_proxy = ssh_mod._short_control_path(
            "server-a", "u", "bastion", proxy="socks5://proxy-a:1080"
        )
        self.assertNotEqual(base, other_jump_user)
        self.assertNotEqual(base, other_proxy)
        self.assertNotEqual(other_jump_user, other_proxy)


class _NeverReadyProc:
    """ssh -L 进程“活着”，但本地端口永远不可达。"""

    def __init__(self):
        self._rc = None

    def poll(self):
        return None

    def terminate(self):
        self._rc = -15

    def kill(self):
        self._rc = -9

    def wait(self, timeout=None):
        self._rc = self._rc if self._rc is not None else 0
        return self._rc


class TestTunnelDeadlineAndHealth(unittest.TestCase):
    def setUp(self):
        self.wd = Path(tempfile.mkdtemp())
        from common.paths import override_work_dir_for_tests

        override_work_dir_for_tests(self.wd)

    def test_port_forward_retry_shares_the_call_deadline(self):
        """O2/§5.8: 隧道启动重试不得重置端到端 deadline。"""
        runner = ssh_mod.SSHRunner(
            "server-a", user="u", backend="openssh", jump_host="bastion",
            control_master="disable",
        )
        clock = {"t": 1000.0}

        def now():
            return clock["t"]

        def sleep(seconds):
            clock["t"] += max(0.0, float(seconds))

        with mock.patch.object(ssh_mod.subprocess, "Popen", return_value=_NeverReadyProc()), \
             mock.patch.object(ssh_mod.time, "monotonic", now), \
             mock.patch.object(ssh_mod.time, "sleep", sleep), \
             mock.patch.object(runner, "can_reach_port", return_value=False):
            with self.assertRaises((RuntimeError, ssh_mod.subprocess.TimeoutExpired)):
                runner._start_port_forward_locked(
                    65099, settle=30.0, deadline=clock["t"] + 0.2
                )
        self.assertLess(clock["t"] - 1000.0, 2.0)

    def test_alive_process_with_dead_forward_is_not_healthy(self):
        """O6/§4: 隧道健康 = 进程活着且 forwarding 可用。"""
        runner = ssh_mod.SSHRunner("server-a", user="u", control_master="disable")
        runner._tunnel_proc = _NeverReadyProc()
        runner._tunnel_local_port = 65081
        with mock.patch.object(runner, "can_reach_port", return_value=False):
            self.assertFalse(runner.is_tunnel_alive)


if __name__ == "__main__":
    unittest.main()
