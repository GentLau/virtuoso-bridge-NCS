"""五接口错误契约（spec 三层架构 §4.4）——用假 RemoteClient 覆盖映射分支。"""

import subprocess
import json
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pyapi.models import CommandResult, VirtuosoResult, ExecutionStatus
from transport.middle import BusinessServer
from common.registry import UserEntry, load_registry
from common.remote_paths import RemotePathError
from common.paths import registry_path, override_work_dir_for_tests
from common.ssh import UnknownEffectError


class FakeRemote:
    """只暴露 BusinessServer 用到的那几个入口。"""

    def __init__(self):
        self.error = None
        self.parallel_seen = None

    def _raise(self):
        if self.error is not None:
            raise self.error
        return None

    def ensure_tunnel(self, deadline=None):
        self._raise()

    def run_command(self, cmd, timeout=None, parallel=False):
        self.parallel_seen = parallel
        self._raise()
        return CommandResult(0, "ok", "")

    def run_one_shot(self, role_name, cmd, timeout=None):
        self._raise()
        return CommandResult(0, role_name, "")

    def upload_file(self, local, remote, timeout=None, recursive=False):
        self._raise()
        return CommandResult(0, "", "")

    def download_file(self, remote, local, timeout=None, recursive=False):
        self._raise()
        return CommandResult(0, "", "")

    def close(self):
        return None


def remote_entry():
    entry = UserEntry(token="tok-c", mode="remote")
    entry.ssh.default.host = "daemon-a"
    entry.ssh.default.user = "alice"
    for name in ("gui", "daemon", "command", "file", "spectre"):
        role = getattr(entry.roles, name)
        role.host = "server-a"
        role.user = "alice"
    entry.roles.daemon.daemon_port = 65081
    entry.roles.daemon.local_port = 65082
    return entry


class MiddleContractBase(unittest.TestCase):
    def setUp(self):
        wd = Path(tempfile.mkdtemp())
        override_work_dir_for_tests(wd)
        registry = load_registry(registry_path())
        registry.register("alice", remote_entry())
        self.server = BusinessServer(wd)
        self.fake = FakeRemote()
        fakes = {"tok-c": self.fake}
        self._patched = mock.patch.object(
            BusinessServer, "_remote", lambda server, token: fakes[token]
        )
        self.fakes = fakes
        self._patched.start()
        self.addCleanup(self._patched.stop)
        self.addCleanup(self.server.close)

    def assert_kind(self, result, kind, rc=None):
        self.assertEqual(result.kind, kind, result)
        if rc is not None:
            self.assertEqual(result.returncode, rc)


class TestCommandContracts(MiddleContractBase):
    def test_transport_error_maps_to_kind_transport(self):
        self.fake.error = RuntimeError("ssh blew up")
        r = self.server.run_command("echo hi", token="tok-c")
        self.assert_kind(r, "transport", 255)
        self.assertIn("VB-TRANSPORT:", r.stderr)

    def test_timeout_maps_to_124(self):
        self.fake.error = subprocess.TimeoutExpired("cmd", 30)
        r = self.server.run_command("sleep 99", token="tok-c")
        self.assert_kind(r, "timeout", 124)

    def test_unknown_effect_is_not_replayed(self):
        self.fake.error = UnknownEffectError("shell died mid-command")
        r = self.server.run_command("do-once", token="tok-c")
        self.assert_kind(r, "unknown-effect", 255)
        self.assertIn("VB-UNKNOWN-EFFECT:", r.stderr)

    def test_path_error_prefix(self):
        self.fake.error = RemotePathError("cannot resolve remote $HOME")
        r = self.server.run_command("echo hi", token="tok-c")
        self.assert_kind(r, "path", 1)
        self.assertIn("VB-PATH-NOT-VISIBLE:", r.stderr)

    def test_invalid_token(self):
        r = self.server.run_command("echo hi", token="nope")
        self.assert_kind(r, "invalid-token", 1)
        self.assertEqual(r.stderr, "invalid token")

    def test_parallel_flag_is_forwarded(self):
        r = self.server.run_command("echo hi", token="tok-c", parallel=True)
        self.assertEqual(r.returncode, 0)
        self.assertTrue(self.fake.parallel_seen)

    def test_invalid_timeout_is_a_parameter_error(self):
        """NaN/Infinity/bool 不能被当作合法秒数送进传输层。"""
        for bad in (
            float("nan"), float("inf"), float("-inf"), True, 1e9,
        ):
            with self.subTest(timeout=bad):
                with self.assertRaises(ValueError):
                    self.server.run_command(
                        "echo hi", timeout=bad, token="tok-c"
                    )

    def test_invalid_timeout_maps_to_dispatch_400(self):
        from server import dispatch as dispatch_module
        from server.dispatch import dispatch

        @dataclass(frozen=True)
        class TimeoutRequest:
            token: str
            timeout: float | None = None

        class TimeoutPackage:
            def __init__(self, middle):
                self.middle = middle

            def run(self, request):
                return self.middle.run_command(
                    "echo hi",
                    timeout=request.timeout,
                    token=request.token,
                )

        dispatch_module.register_operation(
            "tb.timeout.contract", TimeoutPackage, "run",
            TimeoutRequest, replace=True,
        )
        try:
            for bad in (True, 1e9):
                with self.subTest(timeout=bad):
                    status, body = dispatch(
                        self.server,
                        {
                            "operation": "tb.timeout.contract",
                            "token": "tok-c",
                            "timeout": bad,
                        },
                    )
                    self.assertEqual(status, 400, body)
            self.assertIsNone(self.fake.parallel_seen)
        finally:
            dispatch_module.PACKAGES.pop("tb.timeout.contract", None)


class TestFileAndRoleContracts(MiddleContractBase):
    def test_upload_transport_error(self):
        self.fake.error = RuntimeError("scp failed")
        src = Path(tempfile.mkdtemp()) / "f.bin"
        src.write_bytes(b"x")
        r = self.server.upload_file(src, "f.bin", token="tok-c")
        self.assert_kind(r, "transport", 255)

    def test_download_path_error(self):
        self.fake.error = RemotePathError("no such file")
        dst = Path(tempfile.mkdtemp()) / "out.bin"
        r = self.server.download_file("missing.bin", dst, token="tok-c")
        self.assert_kind(r, "path", 1)

    def test_nul_remote_path_maps_to_kind_path(self):
        src = Path(tempfile.mkdtemp()) / "f.bin"
        src.write_bytes(b"x")
        up = self.server.upload_file(src, "bad\x00name", token="tok-c")
        self.assert_kind(up, "path", 1)
        down = self.server.download_file("bad\x00name", src, token="tok-c")
        self.assert_kind(down, "path", 1)

    def test_gui_and_spectre_one_shot(self):
        r1 = self.server.run_gui_command("xdotool key Escape", token="tok-c")
        r2 = self.server.run_spectre_command("spectre -v", token="tok-c")
        self.assertEqual((r1.kind, r2.kind), ("command", "command"))
        self.assertEqual(r1.stdout, "gui")
        self.assertEqual(r2.stdout, "spectre")

    def test_gui_transport_error(self):
        self.fake.error = RuntimeError("no ssh")
        r = self.server.run_gui_command("xdotool key Escape", token="tok-c")
        self.assert_kind(r, "transport", 255)


class TestSkillContracts(MiddleContractBase):
    def test_skill_transport_error_reports_daemon_connection(self):
        self.fake.error = RuntimeError("tunnel failed")
        r = self.server.execute_skill("1+1", token="tok-c")
        self.assertEqual(r.status, ExecutionStatus.ERROR)
        self.assertTrue(any("Daemon connection failed" in e for e in r.errors), r.errors)

    def test_skill_path_error(self):
        self.fake.error = RemotePathError("bad root")
        r = self.server.execute_skill("1+1", token="tok-c")
        self.assertTrue(any("VB-PATH-NOT-VISIBLE" in e for e in r.errors), r.errors)

    def test_skill_invalid_token(self):
        r = self.server.execute_skill("1+1", token="nope")
        self.assertEqual(r.errors, ["invalid token"])


class TestFrozenInterfaceSignatures(unittest.TestCase):
    """四层接口 §4.1/§4.2 的唯一签名口径（v34）。"""

    def test_query_token_is_keyword_only(self):
        import inspect
        from pyapi.models import Middle
        from transport.middle import BusinessServer

        for func in (BusinessServer.query, Middle.query):
            params = inspect.signature(func).parameters
            self.assertIn("token", params, func)
            self.assertEqual(
                params["token"].kind,
                inspect.Parameter.KEYWORD_ONLY,
                f"{func} must take token as keyword-only",
            )

    def test_execute_skill_exposes_log_overrides(self):
        import inspect
        from pyapi.models import Middle

        params = inspect.signature(Middle.execute_skill).parameters
        for name in ("log_level", "log_max_bytes"):
            self.assertIn(name, params)
            self.assertEqual(params[name].kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertIsNone(params[name].default)


class TestQueryContract(unittest.TestCase):
    """§4.2 只读查询：返回 role root、gui display、spectre bin。"""

    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))
        self.registry = load_registry(registry_path())
        entry = UserEntry(token="tok-q", mode="remote")
        entry.ssh.default.host = "server-a"
        entry.ssh.default.user = "alice"
        for name in ("gui", "daemon", "command", "file", "spectre"):
            role = getattr(entry.roles, name)
            role.root = f"/home/alice/.virtuoso-bridge/alice/{name}"
        entry.roles.gui.display = ":11"
        entry.roles.spectre.bin = "/opt/spectre/bin/spectre"
        self.registry.register("alice", entry)
        self.server = BusinessServer()

    def tearDown(self):
        self.server.close()

    def test_query_returns_roots_display_and_spectre_bin(self):
        result = self.server.query(token="tok-q")
        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(len(result.roles), 5)
        self.assertEqual(
            result.roles["daemon"].root,
            "/home/alice/.virtuoso-bridge/alice/daemon",
        )
        self.assertEqual(
            result.roles["spectre"].bin, "/opt/spectre/bin/spectre"
        )
        self.assertEqual(result.roles["gui"].display, ":11")
        # 只暴露 root/bin，不得泄漏拓扑
        dumped = json.dumps(result.model_dump())
        for forbidden in ("host", "jump", "proxy", "daemon_port", "local_port"):
            self.assertNotIn(forbidden, dumped)

    def test_query_unknown_token_is_structured_error(self):
        result = self.server.query(token="nope")
        self.assertEqual(result.status, ExecutionStatus.ERROR)
        self.assertEqual(result.errors, ["invalid token"])
        self.assertEqual(result.roles, {})


if __name__ == "__main__":
    unittest.main()
