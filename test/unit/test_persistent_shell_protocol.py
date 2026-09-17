"""常驻 shell 协议循环（ssh.py::_run_command_via_persistent_shell_locked）。

覆盖：正常回包（stdout/stderr/rc）、协议异常、EOF（unknown-effect vs 安全失败）、超时、b64 解码。
"""

import base64
import queue
import re
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from common.ssh import SSHRunner, UnknownEffectError


class FakeStdin:
    def __init__(self):
        self.payload = b""
        self.closed = False

    def write(self, data):
        self.payload += data

    def flush(self):
        return None

    def close(self):
        self.closed = True


class FakeProc:
    def __init__(self):
        self.stdin = FakeStdin()
        self.stdout = None
        self.terminated = False
        self.killed = False
        self._rc = None

    def poll(self):
        return self._rc

    def terminate(self):
        self.terminated = True
        self._rc = -15

    def kill(self):
        self.killed = True
        self._rc = -9

    def wait(self, timeout=None):
        return self._rc


def runner_with_shell():
    r = SSHRunner("server-a", user="u", backend="openssh", persistent_shell=False)
    r._shell_proc = FakeProc()
    r._shell_queue = queue.Queue()
    return r


def _await_token(runner, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        payload = runner._shell_proc.stdin.payload.decode("utf-8", errors="ignore")
        m = re.search(r"__vb_RC_([0-9a-f]+)__", payload)
        if m:
            return m.group(1)
        time.sleep(0.005)
    raise AssertionError("shell script was never written")


def feed_async(runner, *, stdout=b"", stderr=b"", rc=0, preamble=(), marker_override=None, raw=None):
    """调用期间投递回包：等脚本写入后解析 token，再按协议塞行。"""
    q = runner._shell_queue

    def worker():
        token = _await_token(runner)
        if raw is not None:
            for line in raw(token):
                q.put(line)
            return
        for line in preamble:
            q.put(line + "\n")
        q.put(f"__vb_STDOUT_B64_BEGIN_{token}__\n")
        q.put(base64.b64encode(stdout).decode() + "\n")
        q.put((marker_override or f"__vb_STDERR_B64_BEGIN_{token}__") + "\n")
        q.put(base64.b64encode(stderr).decode() + "\n")
        q.put(f"__vb_RC_{token}__{rc}\n")

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return t


class TestPersistentShellProtocol(unittest.TestCase):
    def test_success_round_trip(self):
        r = runner_with_shell()
        feed_async(r, stdout=b"hello\n", stderr=b"warn\n", rc=7, preamble=("bash: no job control",))
        res = r._run_command_via_persistent_shell_locked("echo hello", timeout=5)
        self.assertEqual((res.returncode, res.stdout, res.stderr), (7, "hello\n", "warn\n"))

    def test_unexpected_protocol_line_raises(self):
        r = runner_with_shell()
        feed_async(r, marker_override="WRONG_MARKER")
        with self.assertRaises(RuntimeError):
            r._run_command_via_persistent_shell_locked("echo hi", timeout=5)

    def test_bad_return_line_raises(self):
        r = runner_with_shell()
        feed_async(r, raw=lambda tok: [
            f"__vb_STDOUT_B64_BEGIN_{tok}__\n", "\n",
            f"__vb_STDERR_B64_BEGIN_{tok}__\n", "\n",
            "NOT_A_RC_LINE\n",
        ])
        with self.assertRaises(RuntimeError):
            r._run_command_via_persistent_shell_locked("echo hi", timeout=5)

    def test_eof_after_delivery_is_unknown_effect(self):
        r = runner_with_shell()
        feed_async(r, raw=lambda tok: [None])
        with self.assertRaises(UnknownEffectError):
            r._run_command_via_persistent_shell_locked("do-once", timeout=5)

    def test_eof_before_delivery_is_plain_failure(self):
        r = runner_with_shell()
        feed_async(r, raw=lambda tok: [None])
        with self.assertRaises(RuntimeError) as ctx:
            r._run_command_via_persistent_shell_locked(
                "probe", timeout=5, _unknown_effect_on_exit=False
            )
        self.assertNotIsInstance(ctx.exception, UnknownEffectError)

    def test_timeout_closes_shell_and_raises(self):
        r = runner_with_shell()
        closed = []
        orig_close = r._close_persistent_shell_locked

        def record_close(*, _budget=None):
            closed.append(True)
            orig_close(_budget=_budget)

        r._close_persistent_shell_locked = record_close
        with self.assertRaises(subprocess.TimeoutExpired):
            r._run_command_via_persistent_shell_locked("sleep 99", timeout=0.05)
        self.assertTrue(closed)

    def test_shell_not_running_raises(self):
        r = runner_with_shell()
        r._shell_proc = None
        with self.assertRaises(RuntimeError):
            r._run_command_via_persistent_shell_locked("x", timeout=1)

    def test_decode_b64_text_tolerates_whitespace_and_garbage(self):
        self.assertEqual(SSHRunner._decode_b64_text(None), "")
        self.assertEqual(SSHRunner._decode_b64_text(base64.b64encode(b"x").decode()), "x")
        self.assertEqual(SSHRunner._decode_b64_text("!!!!"), "")


if __name__ == "__main__":
    unittest.main()
