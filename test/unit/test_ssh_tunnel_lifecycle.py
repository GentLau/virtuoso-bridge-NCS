"""隧道生命周期契约（BUG-1 回归）：外部复用、退避、close 拆隧道、ControlPath 命名。"""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from transport import ssh as ssh_mod
from transport.ssh import SSHRunner


class FakePopen:
    def __init__(self, *args, **kwargs):
        self.pid = 4242
        self.returncode = 0            # 立即退出（模拟 ExitOnForwardFailure 绑定失败）
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.terminated = True

    def wait(self, timeout=None):
        return self.returncode


class TestTunnelReuse(unittest.TestCase):
    def test_external_listener_counts_as_alive(self):
        """修复 BUG-1：复用外部监听时，端口可达即视为隧道存活（不再每请求重开）。"""
        runner = SSHRunner(host="server-a", user="u", backend="openssh", persistent_shell=False)
        runner._tunnel_using_external = True
        runner._tunnel_local_port = 65081
        runner._tunnel_pid = None
        with mock.patch.object(SSHRunner, "can_reach_port", staticmethod(lambda port: True)):
            self.assertTrue(runner.is_tunnel_alive)
        with mock.patch.object(SSHRunner, "can_reach_port", staticmethod(lambda port: False)):
            self.assertFalse(runner.is_tunnel_alive)


class TestTunnelBackoff(unittest.TestCase):
    def test_failure_sets_backoff_and_second_call_fast_fails(self):
        if os.name != "nt":
            self.skipTest("Windows-only tunnel start path")
        runner = SSHRunner(host="server-a", user="u", backend="openssh", persistent_shell=False)
        with mock.patch.object(ssh_mod.subprocess, "Popen", FakePopen), \
             mock.patch.object(SSHRunner, "can_reach_port", staticmethod(lambda port: False)):
            with self.assertRaises(RuntimeError):
                runner.start_port_forward(65081, remote_port=65103)
            self.assertEqual(runner._tunnel_failures, 1)
            self.assertGreater(runner._tunnel_next_try_at, time.monotonic())
            # 退避期内不得再 spawn 进程
            with mock.patch.object(ssh_mod.subprocess, "Popen") as popen2:
                with self.assertRaises(RuntimeError):
                    runner.start_port_forward(65081, remote_port=65103)
                popen2.assert_not_called()

    def test_close_stops_own_tunnel(self):
        runner = SSHRunner(host="server-a", user="u", backend="openssh", persistent_shell=False)
        with mock.patch.object(SSHRunner, "stop_port_forward") as stop:
            runner.close()
            stop.assert_called_once()


class TestControlPathNamespace(unittest.TestCase):
    def test_control_path_includes_pid_and_identity(self):
        a = ssh_mod._short_control_path("server-a", "u", None, "tok-1")
        b = ssh_mod._short_control_path("server-a", "u", None, "tok-1")
        c = ssh_mod._short_control_path("server-a", "u", None, "tok-2")
        self.assertEqual(a, b)          # 同进程同 token 稳定
        self.assertNotEqual(a, c)       # 不同 token 不共享
        with mock.patch.object(os, "getpid", return_value=os.getpid() + 1):
            d = ssh_mod._short_control_path("server-a", "u", None, "tok-1")
        self.assertNotEqual(a, d)       # 进程分量：避免复用被 kill 进程遗留的 master


if __name__ == "__main__":
    unittest.main()
