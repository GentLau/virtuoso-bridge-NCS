"""常驻 shell 协议循环（ssh.py::_run_command_via_persistent_shell_locked）。

覆盖：正常回包（stdout/stderr/rc）、协议异常、EOF（unknown-effect vs 安全失败）、超时、b64 解码。
"""

import base64
import queue
import re
import shutil
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


def _posix_shell_args():
    """Return an argv that reads a shell script from stdin, or None."""
    if sys.platform == "win32":
        shell = shutil.which("wsl") or shutil.which("wsl.exe")
        return [shell, "-e", "sh"] if shell else None
    shell = shutil.which("sh") or shutil.which("bash")
    return [shell] if shell else None


def script_for_command(command: str) -> str:
    """Build the same persistent-shell payload without a live SSH session."""
    r = SSHRunner(
        "server-a", user="u", backend="openssh", persistent_shell=False
    )
    r._shell_proc = FakeProc()
    r._shell_queue = queue.Queue()
    feed_async(r, stdout=b"")
    r._run_command_via_persistent_shell_locked(command, timeout=5)
    return r._shell_proc.stdin.payload.decode("utf-8")


class TestPersistentShellProtocol(unittest.TestCase):
    def test_success_round_trip(self):
        r = runner_with_shell()
        feed_async(r, stdout=b"hello\n", stderr=b"warn\n", rc=7, preamble=("bash: no job control",))
        res = r._run_command_via_persistent_shell_locked("echo hello", timeout=5)
        self.assertEqual((res.returncode, res.stdout, res.stderr), (7, "hello\n", "warn\n"))

    def test_unexpected_protocol_line_after_delivery_is_unknown_effect(self):
        """命令已写入远端后再出现协议错乱：不得重发（§4.5/§5.8）。"""
        r = runner_with_shell()
        feed_async(r, marker_override="WRONG_MARKER")
        with self.assertRaises(UnknownEffectError):
            r._run_command_via_persistent_shell_locked("echo hi", timeout=5)

    def test_bad_return_line_after_delivery_is_unknown_effect(self):
        r = runner_with_shell()
        feed_async(r, raw=lambda tok: [
            f"__vb_STDOUT_B64_BEGIN_{tok}__\n", "\n",
            f"__vb_STDERR_B64_BEGIN_{tok}__\n", "\n",
            "NOT_A_RC_LINE\n",
        ])
        with self.assertRaises(UnknownEffectError):
            r._run_command_via_persistent_shell_locked("echo hi", timeout=5)

    def test_unknown_effect_is_never_retryable(self):
        """仅“确认未投递”的异常允许重建常驻 shell 后重发。"""
        self.assertFalse(
            SSHRunner._is_retryable_persistent_shell_error(
                UnknownEffectError("Unexpected persistent shell protocol line: 'x'")
            )
        )

    def test_remote_temp_files_use_injected_work_dir(self):
        """O5: 捕获文件落在 role 工作根内，并带异常路径清理。"""
        r = SSHRunner(
            "server-a", user="u", backend="openssh", persistent_shell=False,
            work_dir="/home/alice/.virtuoso-bridge/alice/command",
        )
        r._shell_proc = FakeProc()
        r._shell_queue = queue.Queue()
        feed_async(r, stdout=b"ok\n")
        res = r._run_command_via_persistent_shell_locked("echo ok", timeout=5)
        self.assertEqual(res.stdout, "ok\n")
        payload = r._shell_proc.stdin.payload.decode("utf-8", errors="ignore")
        self.assertIn("mktemp -p", payload)
        self.assertIn("/home/alice/.virtuoso-bridge/alice/command", payload)
        self.assertIn("trap '__vb_emit $?' 0", payload)
        self.assertIn('rm -f "$__vb_stdout" "$__vb_stderr"', payload)

    def test_script_reports_real_rc_even_if_command_exits_shell(self):
        """BUG-3: 用户命令 exit 时用 EXIT trap 回传真实 rc（不再假超时）。"""
        r = SSHRunner(
            "server-a", user="u", backend="openssh", persistent_shell=False,
            work_dir="/home/alice/.virtuoso-bridge/alice/command",
        )
        r._shell_proc = FakeProc()
        r._shell_queue = queue.Queue()
        feed_async(r, stdout=b"")
        res = r._run_command_via_persistent_shell_locked("exit 7", timeout=5)
        self.assertEqual(res.returncode, 0)  # feed_async 默认 rc=0
        payload = r._shell_proc.stdin.payload.decode("utf-8", errors="ignore")
        self.assertIn("trap '__vb_emit $?' 0", payload)
        self.assertIn('__vb_emit "$__vb_rc"', payload)
        self.assertIn("trap - 0", payload)
        self.assertIn('} >"$__vb_stdout" 2>"$__vb_stderr"', payload)
        self.assertIn("} >&9 2>&8", payload)
        self.assertIn("exit 7", payload)

    def test_exit_returns_real_rc_in_a_real_posix_shell(self):
        """BUG-3 端到端：真实 POSIX shell 执行生成的脚本后仍能回传 rc=7。"""
        shell_args = _posix_shell_args()
        if not shell_args:
            self.skipTest("no POSIX shell available")
        script = script_for_command("echo before-exit; exit 7")
        proc = subprocess.run(
            shell_args,
            input=script.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
        )
        self.assertEqual(proc.returncode, 7, proc.stderr.decode("utf-8", "replace"))
        self.assertIn(base64.b64encode(b"before-exit\n"), proc.stdout)
        match = re.search(rb"__vb_RC_[0-9a-f]+__(\d+)", proc.stdout)
        self.assertIsNotNone(match, proc.stdout.decode("utf-8", "replace"))
        self.assertEqual(match.group(1), b"7")

    def test_command_state_persists_across_calls_in_real_shell(self):
        """常驻 shell 的 cwd/env 跨命令保留；exit 才结束该会话。"""
        shell_args = _posix_shell_args()
        if not shell_args:
            self.skipTest("no POSIX shell available")
        script = (
            script_for_command("cd /tmp; export VB_PERSIST=ok")
            + script_for_command('pwd; printf "%s" "$VB_PERSIST"')
        )
        proc = subprocess.run(
            shell_args,
            input=script.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        outputs = [
            base64.b64decode(m.group(1))
            for m in re.finditer(
                rb"__vb_STDOUT_B64_BEGIN_[0-9a-f]+__\n([A-Za-z0-9+/=]*)\n",
                proc.stdout,
            )
        ]
        self.assertEqual(outputs, [b"", b"/tmp\nok"])

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
