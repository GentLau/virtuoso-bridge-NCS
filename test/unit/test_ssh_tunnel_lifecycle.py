"""隧道生命周期契约：两个 OS 分支都必须登记端口/退避（BUG-1 及同类残留回归）。

关键点（评审指出过）：测试必须走**代码路径**，不能手工往对象里注入
``_tunnel_local_port`` 之类的状态，否则测的是“修复后的状态”而不是“修复后的代码”。
这里通过伪造 ``Popen`` + ``can_reach_port`` 真实调用 ``start_port_forward``。
"""

import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from transport import ssh as ssh_mod
from transport.ssh import SSHRunner


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
        # Windows 分支靠 can_reach_port 判定成功；POSIX 分支只要求进程还活着
        proc = self._start(r, alive=True, port_reachable=(self.platform == "nt"))
        self.assertIsNotNone(proc)
        self.assertEqual(r._tunnel_local_port, 65081)
        self.assertFalse(r._tunnel_using_external)
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
        with mock.patch.object(ssh_mod.os, "kill") as kill, \
             mock.patch.object(ssh_mod.os, "name", "posix"):
            r.close()
        self.assertTrue(kill.called, "close() 必须向自己的隧道进程发信号")
        self.assertIsNone(r._tunnel_local_port)


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


if __name__ == "__main__":
    unittest.main()
