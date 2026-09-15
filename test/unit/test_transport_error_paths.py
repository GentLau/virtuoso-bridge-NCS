"""错误路径与诊断分支（ssh.py）：纯函数级覆盖。"""

import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pyapi.models import CommandResult
from transport import ssh as ssh_mod
from transport.ssh import SSHRunner


class TestTransportErrorSummaries(unittest.TestCase):
    def setUp(self):
        self.runner = SSHRunner("server-a", user="u", backend="openssh", persistent_shell=False)

    def test_auth_failure(self):
        msg = self.runner._summarize_ssh_transport_error("Permission denied (publickey).")
        self.assertIn("SSH authentication failed", msg)

    def test_timeout(self):
        for raw in ("Connection timed out", "Operation timed out", "No route to host"):
            self.assertIn("timed out", self.runner._summarize_ssh_transport_error(raw))

    def test_refused(self):
        msg = self.runner._summarize_ssh_transport_error("ssh: connect to host x port 22: Connection refused")
        self.assertIn("refused", msg)

    def test_closed_before_login_with_and_without_jump(self):
        plain = self.runner._summarize_ssh_transport_error("kex_exchange_identification: read: Connection reset")
        self.assertIn("closed before login", plain)
        with_jump = SSHRunner("server-a", user="u", jump_host="bastion", backend="openssh")
        jumped = with_jump._summarize_ssh_transport_error("Connection closed by 10.0.0.1")
        self.assertIn("bastion", jumped)

    def test_unknown_message_falls_back(self):
        self.assertEqual(self.runner._summarize_ssh_transport_error("weird failure"), "weird failure")
        # 空消息走“连接失败”兜底文案（不是空字符串）
        self.assertIn("SSH connection to server-a failed", self.runner._summarize_ssh_transport_error(None))

    def test_describe_failure_prefers_known_translation(self):
        r = CommandResult(255, "", "kex_exchange_identification: Connection closed")
        text = self.runner.describe_ssh_command_failure("upload file", r)
        self.assertIn("Failed to upload file", text)
        self.assertIn("closed before login", text)

    def test_describe_failure_without_details(self):
        r = CommandResult(1, "", "")
        text = self.runner.describe_ssh_command_failure("run command", r)
        self.assertIn("Failed to run command", text)
        self.assertIn("SSH connection to server-a failed", text)


class TestRetryClassifiers(unittest.TestCase):
    def test_transient(self):
        self.assertTrue(SSHRunner._is_transient_ssh_error(255, "kex_exchange_identification: failed"))
        self.assertFalse(SSHRunner._is_transient_ssh_error(0, "kex_exchange_identification"))

    def test_cm_failure_markers(self):
        for text in ("mux_client_request_session: failed", "ControlPath too long",
                     "getsockname failed: Not a socket", "not a socket"):
            self.assertTrue(SSHRunner._is_cm_failure(255, text), text)
        self.assertFalse(SSHRunner._is_cm_failure(0, "mux_client_request_session"))

    def test_retryable_persistent_shell_errors(self):
        self.assertTrue(ssh_mod.SSHRunner._is_retryable_persistent_shell_error(
            RuntimeError("unexpected persistent shell protocol line: 'x'")))
        self.assertFalse(ssh_mod.SSHRunner._is_retryable_persistent_shell_error(RuntimeError("boom")))


class TestTimeoutBudgetAndTools(unittest.TestCase):
    def test_budget_exhaustion_raises(self):
        budget = ssh_mod._TimeoutBudget.start(0.05, 1.0)
        time.sleep(0.15)
        self.assertEqual(budget.available(), 0.0)
        with self.assertRaises(subprocess.TimeoutExpired):
            budget.remaining("cmd")

    def test_derive_tool_prefers_sibling_binary(self):
        d = Path(tempfile.mkdtemp())
        sshbin = d / "ssh"
        sshbin.write_text("")
        scpbin = d / "scp"
        scpbin.write_text("")
        self.assertEqual(ssh_mod._derive_tool(str(sshbin), "ssh", "scp"), str(scpbin))
        # missing sibling -> falls back to PATH lookup / literal name
        self.assertTrue(ssh_mod._derive_tool(str(sshbin), "ssh", "nosuchtool").endswith("nosuchtool"))

    def test_as_text_handles_bytes_and_none(self):
        self.assertEqual(ssh_mod._as_text(b"abc"), "abc")
        self.assertEqual(ssh_mod._as_text(None), "")
        self.assertEqual(ssh_mod._as_text("x"), "x")


class TestRemoteScpTarget(unittest.TestCase):
    def test_target_shape(self):
        runner = SSHRunner("server-a", user="alice", backend="openssh")
        self.assertEqual(runner._remote_scp_target("/tmp/f.bin"), "alice@server-a:/tmp/f.bin")
        plain = SSHRunner("server-a", backend="openssh")
        self.assertEqual(plain._remote_scp_target("/tmp/f.bin"), "server-a:/tmp/f.bin")


if __name__ == "__main__":
    unittest.main()
