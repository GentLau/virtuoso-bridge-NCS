"""ssh.py 分派分支：paramiko / 常驻 shell / 一次性回退，以及连接探测与文本上传。"""

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pyapi.models import CommandResult
from transport import ssh as ssh_mod
from transport.ssh import SSHRunner, UnknownEffectError


def openssh_runner(**kw):
    return SSHRunner("server-a", user="alice", backend="openssh", **kw)


class TestOptionBuilders(unittest.TestCase):
    def test_common_options_include_mux_by_default(self):
        r = openssh_runner()
        opts = r._common_ssh_options()
        self.assertIn("ControlPath=" + r._control_path, opts)
        self.assertIn("BatchMode=yes", opts)

    def test_common_options_without_mux(self):
        r = openssh_runner()
        opts = r._common_ssh_options(control_master=False)
        self.assertNotIn("ControlMaster=auto", opts)
        self.assertIn("-o", opts)

    def test_build_base_contains_target_and_config(self):
        r = openssh_runner()
        base = r._build_ssh_base()
        self.assertIn("alice@server-a", base)
        self.assertEqual(base[0], ssh_mod.shutil.which("ssh") or "ssh")


class TestRunCommandDispatch(unittest.TestCase):
    def test_paramiko_backend_path(self):
        r = openssh_runner()
        backend = mock.Mock()
        backend.run_command.return_value = (0, "out", "")
        r._paramiko_backend = backend
        res = r.run_command("echo hi", timeout=5)
        self.assertEqual((res.returncode, res.stdout), (0, "out"))
        backend.run_command.assert_called_once()
        self.assertGreater(backend.run_command.call_args.kwargs["timeout"], 0)

    def test_persistent_shell_path(self):
        r = openssh_runner()
        r._persistent_shell_enabled = True
        with mock.patch.object(SSHRunner, "_run_via_persistent_shell_with_retry",
                               return_value=CommandResult(0, "shell", "")) as shell:
            res = r.run_command("echo hi", timeout=5)
        self.assertEqual(res.stdout, "shell")
        shell.assert_called_once()

    def test_unknown_effect_is_not_replayed(self):
        r = openssh_runner()
        r._persistent_shell_enabled = True
        with mock.patch.object(SSHRunner, "_run_via_persistent_shell_with_retry",
                               side_effect=UnknownEffectError("died mid-flight")), \
             mock.patch.object(SSHRunner, "_run_command_once") as once:
            with self.assertRaises(UnknownEffectError):
                r.run_command("do-once", timeout=5)
        once.assert_not_called()          # 绝不重放可能已生效的命令

    def test_generic_failure_falls_back_to_one_shot(self):
        r = openssh_runner()
        r._persistent_shell_enabled = True
        with mock.patch.object(SSHRunner, "_run_via_persistent_shell_with_retry",
                               side_effect=RuntimeError("shell died before delivery")), \
             mock.patch.object(SSHRunner, "_run_command_once",
                               return_value=CommandResult(0, "one-shot", "")) as once:
            res = r.run_command("echo hi", timeout=5)
        self.assertEqual(res.stdout, "one-shot")
        once.assert_called_once()

    def test_timeout_without_wedged_mux_is_raised(self):
        r = openssh_runner()
        r._persistent_shell_enabled = True
        with mock.patch.object(SSHRunner, "_run_via_persistent_shell_with_retry",
                               side_effect=subprocess.TimeoutExpired("cmd", 5)), \
             mock.patch.object(SSHRunner, "_mux_master_wedged", return_value=False):
            with self.assertRaises(subprocess.TimeoutExpired):
                r.run_command("sleep 99", timeout=5)


class TestConnectionProbe(unittest.TestCase):
    def test_paramiko_delegates(self):
        r = openssh_runner()
        backend = mock.Mock()
        backend.test_connection.return_value = True
        r._paramiko_backend = backend
        self.assertTrue(r.test_connection(5))
        backend.test_connection.assert_called_once_with(5)

    def test_openssh_success(self):
        r = openssh_runner()
        with mock.patch.object(ssh_mod.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            self.assertTrue(r.test_connection(5))
        self.assertEqual(run.call_args.args[0][-3:], ["-T", "exit", "0"])

    def test_openssh_failure(self):
        r = openssh_runner()
        with mock.patch.object(ssh_mod.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=255, stdout="", stderr="Permission denied")
            self.assertFalse(r.test_connection(5))

    def test_openssh_timeout(self):
        r = openssh_runner()
        with mock.patch.object(ssh_mod.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("ssh", 5)):
            self.assertFalse(r.test_connection(5))


class TestUploadText(unittest.TestCase):
    def test_paramiko_delegates(self):
        r = openssh_runner()
        backend = mock.Mock()
        backend.upload_text.return_value = (0, "", "")
        r._paramiko_backend = backend
        res = r.upload_text("payload", "/tmp/x.txt", timeout=5)
        self.assertEqual(res.returncode, 0)
        backend.upload_text.assert_called_once()

    def test_persistent_shell_path(self):
        r = openssh_runner()
        r._persistent_shell_enabled = True
        with mock.patch.object(SSHRunner, "_run_via_persistent_shell_with_retry",
                               return_value=CommandResult(0, "", "")) as shell:
            res = r.upload_text("payload", "/tmp/x.txt", timeout=5)
        self.assertEqual(res.returncode, 0)
        self.assertIn("base64", shell.call_args.args[0])

    def test_fallback_one_shot(self):
        r = openssh_runner()
        r._persistent_shell_enabled = True
        with mock.patch.object(SSHRunner, "_run_via_persistent_shell_with_retry",
                               side_effect=RuntimeError("shell down")), \
             mock.patch.object(ssh_mod.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0, stdout=b"ok", stderr=b"")
            res = r.upload_text("payload", "/tmp/x.txt", timeout=5)
        self.assertEqual((res.returncode, res.stdout), (0, "ok"))


if __name__ == "__main__":
    unittest.main()
