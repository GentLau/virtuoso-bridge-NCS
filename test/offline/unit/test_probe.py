"""Remote probe helpers: python detection and port allocation."""

import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pyapi.models import CommandResult
from register.probe import allocate_local_port, allocate_remote_port, detect_remote_python, port_free_on_remote
from common.paths import override_work_dir_for_tests


class FakeRunner:
    def __init__(self, responses: list[CommandResult]):
        self.responses = list(responses)
        self.commands: list[str] = []

    def run_command(self, cmd: str, timeout=None) -> CommandResult:
        self.commands.append(cmd)
        if self.responses:
            return self.responses.pop(0)
        return CommandResult(0, "", "")


class TestProbeHelpers(unittest.TestCase):
    def setUp(self) -> None:
        override_work_dir_for_tests(Path(tempfile.mkdtemp(prefix="vb-")))

    def test_python_version_window_r17(self) -> None:
        """r17: role 机器 2.7+ 或 3.6.8+；边界值必须精确。"""
        from register import probe as probes

        cases = {
            (2, 6, 9): False,
            (2, 7, 0): True,
            (2, 7, 18): True,
            (3, 6, 7): False,
            (3, 6, 8): True,
            (3, 6, 9): True,
            (3, 9, 25): True,
            (4, 0, 0): False,
        }
        for version, expected in cases.items():
            with self.subTest(version=version):
                self.assertEqual(
                    probes.python_version_supported(version), expected
                )
        self.assertFalse(probes.python_version_supported(None))

    def test_remote_python_version_parses_interpreter_output(self) -> None:
        from register import probe as probes

        runner = FakeRunner([CommandResult(0, "Python 3.6.8\n", "")])
        self.assertEqual(
            probes.remote_python_version(runner, "python3"), (3, 6, 8)
        )
        runner = FakeRunner([CommandResult(1, "", "not found")])
        self.assertIsNone(probes.remote_python_version(runner, "nope"))
        runner = FakeRunner([CommandResult(0, "garbage output", "")])
        self.assertIsNone(probes.remote_python_version(runner, "weird"))

    def test_local_helpers(self) -> None:
        from register import probe as probes
        self.assertTrue(probes.local_hostname())
        self.assertTrue(probes.local_user())
        cmd, major = probes.local_python()
        self.assertTrue(cmd)
        self.assertIn(major, (2, 3))
        s = socket.socket()
        s.bind(("0.0.0.0", 0))
        port = s.getsockname()[1]
        self.assertFalse(probes.local_port_free(port))
        s.close()
        root = Path(tempfile.mkdtemp(prefix="vb-"))
        self.assertTrue(probes.local_path_writable(root))
        file_path = root / "not_a_dir"
        file_path.write_text("x", encoding="utf-8")
        self.assertFalse(probes.local_path_writable(file_path))

    def test_remote_probes_with_fake_runner(self) -> None:
        from register import probe as probes
        runner = FakeRunner([
            CommandResult(0, "host-a.example.com\n", ""),   # hostname -f
            CommandResult(0, "alice\n", ""),               # whoami
            CommandResult(0, "uid=1000(alice)\n", ""),     # id alice
            CommandResult(0, "", ""),                       # mkdir + test -w
        ])
        self.assertEqual(probes.remote_hostname(runner), "host-a.example.com")
        self.assertEqual(probes.remote_user(runner), "alice")
        self.assertTrue(probes.remote_user_exists(runner, "alice"))
        self.assertTrue(probes.remote_path_writable(runner, "/home/alice/.vb"))
        self.assertEqual(probes.remote_user_exists(runner, "alice"), True)

    def test_host_key_fingerprint_uses_known_hosts(self) -> None:
        from register import probe as probes
        def fake_run(argv, **_kwargs):
            if argv[:2] == ["ssh", "-G"]:
                return mock.Mock(stdout="hostname server-a\n", returncode=0)
            if argv[:2] == ["ssh-keygen", "-F"]:
                return mock.Mock(
                    stdout=(
                        "# Host server-a found: line 1\n"
                        "server-a ssh-ed25519 AAAAB3NzaC1yc2EAAAADAQABAAAB\n"
                    ),
                    returncode=0,
                )
            if argv[:2] == ["ssh-keygen", "-lf"]:
                return mock.Mock(
                    stdout="256 SHA256:abcdef server-a (ED25519)\n",
                    returncode=0,
                )
            return mock.Mock(stdout="", returncode=1)

        # patch 的是全局 subprocess.run，并行线程（paramiko/SSH 测试）的调用也会进
        # call_args_list —— 断言只统计 probe 自己发起的两类命令（2026-09-22 实测的隔离缺陷）。
        with mock.patch.object(probes.subprocess, "run", side_effect=fake_run) as run:
            fp = probes.host_key_fingerprint("server-a")
        self.assertEqual(fp, "SHA256:abcdef")
        probe_calls = [call.args[0][:2] for call in run.call_args_list
                       if call.args and list(call.args[0][:1]) in (["ssh"], ["ssh-keygen"])]
        self.assertEqual(
            probe_calls,
            [["ssh", "-G"], ["ssh-keygen", "-F"], ["ssh-keygen", "-lf"]],
        )
        self.assertFalse(Path("keys.tmp").exists())

    def test_host_key_fingerprint_resolves_ssh_config_alias(self) -> None:
        """known_hosts 里只有真实主机名时，要通过 ssh -G 解析别名再查。"""
        from register import probe as probes
        def fake_run(argv, **_kwargs):
            if argv[:2] == ["ssh", "-G"]:
                return mock.Mock(stdout="hostname real.example.com\n", returncode=0)
            if argv[:2] == ["ssh-keygen", "-F"]:
                return mock.Mock(
                    stdout=(
                        "" if argv[2] == "alias"
                        else "real.example.com ssh-ed25519 "
                        "AAAAB3NzaC1yc2EAAAADAQABAAAB\n"
                    ),
                    returncode=0 if argv[2] != "alias" else 1,
                )
            if argv[:2] == ["ssh-keygen", "-lf"]:
                return mock.Mock(
                    stdout="256 SHA256:real real.example.com (ED25519)\n",
                    returncode=0,
                )
            return mock.Mock(stdout="", returncode=1)

        with mock.patch.object(probes.subprocess, "run", side_effect=fake_run):
            fp = probes.host_key_fingerprint("alias")
        self.assertEqual(fp, "SHA256:real")

    def test_host_key_fingerprint_missing_entry_is_none(self) -> None:
        from register import probe as probes
        def fake_run(argv, **_kwargs):
            if argv[:2] == ["ssh", "-G"]:
                return mock.Mock(stdout="hostname same\n", returncode=0)
            return mock.Mock(stdout="", returncode=1)

        with mock.patch.object(probes.subprocess, "run", side_effect=fake_run):
            self.assertIsNone(probes.host_key_fingerprint("same"))

    def test_ssh_port_rule_enforces_22(self) -> None:
        """配置一览 §6.5: 注册期校验目标/jump 的 SSH 端口必须是 22。"""
        from register import probe as probes

        def run_with(port_line: str):
            return mock.Mock(stdout=f"hostname h\n{port_line}\n", returncode=0)

        with mock.patch.object(probes.subprocess, "run", return_value=run_with("port 2222")):
            self.assertFalse(probes.ssh_port_is_22("alias"))
        with mock.patch.object(probes.subprocess, "run", return_value=run_with("port 22")):
            self.assertTrue(probes.ssh_port_is_22("alias"))
        with mock.patch.object(probes.subprocess, "run", return_value=run_with("")):
            self.assertTrue(probes.ssh_port_is_22("alias"))
        with mock.patch.object(probes.subprocess, "run", side_effect=OSError("no ssh")):
            self.assertFalse(probes.ssh_port_is_22("alias"))

    def test_detect_cadence_python3(self) -> None:
        runner = FakeRunner([CommandResult(0, "CMD:/opt/x/python3 3.9.5\n", "")])
        self.assertEqual(detect_remote_python(runner), ("/opt/x/python3", 3))

    def test_detect_python27(self) -> None:
        runner = FakeRunner([CommandResult(0, "CMD:/opt/x/python2.7 2.7.18\n", "")])
        self.assertEqual(detect_remote_python(runner), ("/opt/x/python2.7", 2))

    def test_detect_accepts_oldest_supported_36_8(self) -> None:
        runner = FakeRunner([CommandResult(0, "CMD:/opt/x/python3.6 3.6.8\n", "")])
        self.assertEqual(detect_remote_python(runner), ("/opt/x/python3.6", 3))

    def test_detect_skips_unsupported_then_picks_supported(self) -> None:
        """r17: 3.5 存在也要跳过，不能被部署。"""
        runner = FakeRunner([CommandResult(
            0,
            "CMD:/opt/old/python3 3.5.9\n"
            "CMD:/opt/new/python3 3.9.18\n",
            "",
        )])
        self.assertEqual(detect_remote_python(runner), ("/opt/new/python3", 3))

    def test_detect_prefers_first_supported_candidate(self) -> None:
        """2.7.x 任意 micro 都合格，先命中的就是被固定的解释器。"""
        runner = FakeRunner([CommandResult(
            0,
            "CMD:/opt/python27 2.7.5\nCMD:/opt/new/python3 3.9.18\n",
            "",
        )])
        self.assertEqual(detect_remote_python(runner), ("/opt/python27", 2))

    def test_detect_rejects_only_unsupported_candidates(self) -> None:
        runner = FakeRunner([
            CommandResult(0, "CMD:/opt/old/python 2.6.9\nCMD:/opt/old3 3.6.7\n", ""),
            CommandResult(1, "", "missing"),   # fallback python3
            CommandResult(1, "", "missing"),   # fallback python
            CommandResult(1, "", "missing"),   # fallback python2.7
            CommandResult(1, "", "missing"),   # fallback python2
        ])
        self.assertIsNone(detect_remote_python(runner))

    def test_detect_falls_back_to_path(self) -> None:
        runner = FakeRunner([
            CommandResult(0, "", ""),                 # one-shot found nothing
            CommandResult(1, "", "no python3"),       # python3 missing
            CommandResult(0, "2.7.18", ""),           # python works
        ])
        self.assertEqual(detect_remote_python(runner), ("python", 2))

    def test_allocate_port_batch(self) -> None:
        runner = FakeRunner([CommandResult(0, "65083\n", "")])
        self.assertEqual(allocate_remote_port(runner, "python3"), 65083)

    def test_allocate_port_falls_back_to_single_checks(self) -> None:
        runner = FakeRunner([
            CommandResult(1, "", "no ports"),   # batch probe failed
            CommandResult(0, "", ""),           # first single check succeeds
        ])
        self.assertEqual(allocate_remote_port(runner, "python3"), 65081)


    def test_allocate_local_port(self) -> None:
        port = allocate_local_port(start=65081)
        self.assertIsNotNone(port)
        self.assertTrue(65081 <= port < 65131)

    def test_allocate_remote_port_respects_reserved(self) -> None:
        runner = FakeRunner([CommandResult(0, "65082\n", "")])
        self.assertEqual(allocate_remote_port(runner, "python3", reserved={65081}), 65082)
        self.assertIn("65081", runner.commands[0])  # reserved set baked into probe


    def test_detect_remote_spectre(self) -> None:
        from register import probe as probes
        runner = FakeRunner([CommandResult(0, "/opt/cad/bin/spectre\n", "")])
        self.assertEqual(probes.detect_remote_spectre(runner), "/opt/cad/bin/spectre")
        runner2 = FakeRunner([CommandResult(0, "", "")])
        self.assertIsNone(probes.detect_remote_spectre(runner2))

    def test_detect_local_spectre_returns_path_or_none(self) -> None:
        from register import probe as probes

        detected = probes.detect_local_spectre()
        # the previous "None or isinstance(str)" assertion accepted any string;
        # require a real executable path when something is returned
        if detected is not None:
            self.assertIsInstance(detected, str)
            self.assertTrue(detected.strip(), detected)
            self.assertTrue(
                detected.endswith("spectre") or "spectre" in Path(detected).name,
                f"unexpected spectre probe result: {detected!r}",
            )


if __name__ == "__main__":
    unittest.main()
