"""Six-step registration flow unit tests (probes/deploy/connectivity mocked)."""

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pyapi.models import CommandResult, ExecutionStatus, VirtuosoResult

from register import (
    ConnectivityReport,
    RegistrationState,
    RegistrationFlow,
    RegistrationProbeError,
    RegistrationRequest,
    ProbeResult,
    register_user,
    validate_local,
)
from common.registry import UserEntry, SshDefaults, endpoint_key, load_registry
from common.paths import registry_path, override_work_dir_for_tests


def _probe_run(cmd, timeout=None):
    """Smart fake for per-role probes: smoke / $HOME / writable check."""
    if "vb-ok" in cmd:
        return CommandResult(0, "vb-ok", "")
    if "$HOME" in cmd:
        return CommandResult(0, "/home/alice", "")
    return CommandResult(0, "", "")



def complete_remote_entry(token="tok-1"):
    entry = UserEntry(token=token, mode="remote")
    entry.ssh.default.host = "server-a"
    entry.ssh.default.user = "alice"
    entry.roles.daemon.daemon_port = 65081
    entry.roles.daemon.local_port = 65082
    entry.roles.daemon.python = "/usr/bin/python3"
    entry.roles.daemon.expected_hostname = "server-a"
    entry.roles.daemon.expected_user = "alice"
    for name in ("gui", "daemon", "command", "file", "spectre"):
        role = getattr(entry.roles, name)
        role.root = f"/home/alice/.virtuoso-bridge/alice/{name}"
        role.expected_fingerprint = "SHA256:test"
    entry.roles.spectre.bin = "/opt/spectre"
    return entry


def remote_request(**kwargs):
    return RegistrationRequest(
        mode="remote", user="alice", token="tok-1",
        ssh={"default": {"host": "server-a", "user": "alice"}},
        **kwargs,
    )


class TestValidateLocal(unittest.TestCase):
    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))
        self.reg = load_registry(registry_path())

    def test_clean(self):
        self.assertEqual(validate_local(self.reg, remote_request()), [])

    def test_user_duplicate(self):
        self.reg.register("alice", UserEntry(token="other", mode="remote"))
        errors = validate_local(self.reg, remote_request())
        self.assertTrue(any("already registered" in e for e in errors))

    def test_daemon_port_conflict(self):
        other = UserEntry(token="other", mode="remote")
        other.roles.daemon.host = "server-a"          # same daemon host as the request
        other.roles.daemon.daemon_port = 65081
        self.reg.register("bob", other)
        errors = validate_local(self.reg, remote_request(roles={"daemon": {"daemon_port": 65081}}))
        self.assertTrue(any("daemon port 65081 conflicts" in e for e in errors))

    def test_daemon_port_same_number_other_host_is_allowed(self):
        """daemon_port uniqueness scope is the daemon target host (配置一览 §6.4)."""
        other = UserEntry(token="other", mode="remote")
        other.roles.daemon.host = "server-b"          # different host
        other.roles.daemon.daemon_port = 65081
        self.reg.register("bob", other)
        errors = validate_local(self.reg, remote_request(roles={"daemon": {"daemon_port": 65081}}))
        self.assertEqual(errors, [])

    def test_local_port_conflict(self):
        other = UserEntry(token="other", mode="remote")
        other.roles.daemon.local_port = 65082
        self.reg.register("bob", other)
        errors = validate_local(self.reg, remote_request(roles={"daemon": {"local_port": 65082}}))
        self.assertTrue(any("local port 65082 conflicts" in e for e in errors))


class TestFlowApply(unittest.TestCase):
    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))
        self.reg = load_registry(registry_path())

    def test_validation_failure_stops_flow(self):
        self.reg.register("alice", UserEntry(token="other", mode="remote"))
        state = RegistrationFlow(self.reg).apply(remote_request())
        self.assertEqual(state.stage, "failed")
        self.assertIsNone(state.entry)

    def test_probe_failure_stops_flow(self):
        with mock.patch("register.flow.probe_user", side_effect=RegistrationProbeError("boom")):
            state = RegistrationFlow(self.reg).apply(remote_request())
        self.assertEqual(state.stage, "failed")
        self.assertIn("boom", state.errors)

    def test_deploy_failure_stops_flow(self):
        with mock.patch("register.flow.probe_user", return_value=ProbeResult(complete_remote_entry(), 3)), \
             mock.patch.object(RegistrationFlow, "_recheck_ports_before_deploy", lambda self, state, budget: None), \
             mock.patch("register.flow.deploy_user", side_effect=RuntimeError("deploy boom")):
            state = RegistrationFlow(self.reg).apply(remote_request())
        self.assertEqual(state.stage, "failed")
        self.assertIn("deploy boom", state.errors[0])

    def test_happy_apply_reaches_deployed(self):
        entry = UserEntry(token="tok-1", mode="remote")
        with mock.patch("register.flow.probe_user", return_value=ProbeResult(entry, 3)), \
             mock.patch.object(RegistrationFlow, "_recheck_ports_before_deploy", lambda self, state, budget: None), \
             mock.patch("register.flow.deploy_user", return_value="/home/alice/setup.il"):
            state = RegistrationFlow(self.reg).apply(remote_request())
        self.assertEqual(state.stage, "deployed")
        self.assertEqual(state.setup_path, "/home/alice/setup.il")
        self.assertEqual(state.token, "tok-1")


class TestStepRetryAfterFailure(unittest.TestCase):
    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))
        self.reg = load_registry(registry_path())

    def test_validate_can_retry_same_step(self):
        flow = RegistrationFlow(self.reg)
        flow.start(remote_request())
        with mock.patch(
            "register.flow.validate_local",
            side_effect=[["validation boom"], []],
        ):
            failed_stage = flow.validate().stage
            retried = flow.validate()
        self.assertEqual(failed_stage, "failed")
        self.assertEqual(retried.stage, "validated")

    def test_probe_can_retry_same_step(self):
        flow = RegistrationFlow(self.reg)
        flow.start(remote_request())
        flow.validate()
        with mock.patch(
            "register.flow.probe_user",
            side_effect=[
                RegistrationProbeError("probe boom"),
                ProbeResult(complete_remote_entry(), 3),
            ],
        ):
            failed_stage = flow.probe().stage
            retried = flow.probe()
        self.assertEqual(failed_stage, "failed")
        self.assertEqual(retried.stage, "probed")

    def test_validate_preallocates_missing_local_port(self):
        """§6.4: 第二步在内存分配候选——缺省 local_port 必须在本机预分配。"""
        flow = RegistrationFlow(self.reg)
        flow.start(remote_request())
        state = flow.validate()
        self.assertEqual(state.stage, "validated")
        records = flow.reservations.records()
        self.assertEqual(len(records), 1)
        self.assertIsNotNone(records[0].local_port)
        self.assertEqual(
            state.request.roles.daemon.local_port, records[0].local_port
        )

    def test_validate_preallocates_joint_port_for_local_mode(self):
        """§6.4: local 模式 daemon_port/local_port 是同一个候选端口。"""
        request = RegistrationRequest(
            mode="local", user="u", token="tok-local",
            roles={"daemon": {"daemon_port": 65091}},
        )
        flow = RegistrationFlow(self.reg)
        flow.start(request)
        flow.validate()
        records = flow.reservations.records()
        self.assertEqual(records[0].local_port, 65091)
        self.assertEqual(request.roles.daemon.daemon_port, 65091)
        self.assertEqual(request.roles.daemon.local_port, 65091)

    def test_validate_rejects_busy_explicit_local_port(self):
        """§3 第二步: local_port 本机已被占用必须在这一步拒绝。"""
        flow = RegistrationFlow(self.reg)
        flow.start(remote_request(roles={"daemon": {"local_port": 65092}}))
        with mock.patch("register.probe.local_port_free", return_value=False):
            state = flow.validate()
        self.assertEqual(state.stage, "failed")
        self.assertTrue(any("not usable" in e for e in state.errors), state.errors)


class TestFlowVerifyAndCommit(unittest.TestCase):
    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))
        self.reg = load_registry(registry_path())

    def _deployed_flow(self):
        flow = RegistrationFlow(self.reg)
        with mock.patch("register.flow.probe_user", return_value=ProbeResult(complete_remote_entry(), 3)), \
             mock.patch.object(RegistrationFlow, "_recheck_ports_before_deploy", lambda self, state, budget: None), \
             mock.patch("register.flow.deploy_user", return_value="/home/alice/setup.il"):
            flow.apply(remote_request())
        return flow

    def test_connectivity_failure_does_not_commit(self):
        flow = self._deployed_flow()
        report = ConnectivityReport("tok-1", True, False, True, detail="skill failed")
        with mock.patch("register.flow.test_connectivity", return_value=report):
            state = flow.verify()
        self.assertEqual(state.stage, "failed")
        self.assertIsNone(self.reg.by_token("tok-1"))
        self.assertFalse(registry_path().exists())

    def test_success_commits_with_timestamp(self):
        flow = self._deployed_flow()
        report = ConnectivityReport("tok-1", True, True, True)
        with mock.patch("register.flow.test_connectivity", return_value=report):
            state = flow.verify()
        # 第五步只报告：注册表在 commit 之前不能有该用户
        self.assertEqual(state.stage, "verified")
        self.assertIsNone(self.reg.by_token("tok-1"))

        state = flow.commit()
        self.assertEqual(state.stage, "committed")
        entry = self.reg.by_token("tok-1")
        self.assertIsNotNone(entry)
        self.assertIsNotNone(entry.registered_at)

    def test_verify_without_apply_reports_error(self):
        state = RegistrationFlow(self.reg).verify()
        self.assertEqual(state.stage, "failed")
        self.assertIn("no registration in progress", state.errors)

    def test_verify_retry_success_clears_stale_errors(self):
        """§3.3: 同一步失败后可原样重试；成功后不得残留上一次的 errors。"""
        flow = self._deployed_flow()
        bad = ConnectivityReport("tok-1", True, False, True, detail="skill failed")
        with mock.patch("register.flow.test_connectivity", return_value=bad):
            state = flow.verify()
        self.assertEqual(state.stage, "failed")
        self.assertTrue(state.errors)

        good = ConnectivityReport("tok-1", True, True, True)
        with mock.patch("register.flow.test_connectivity", return_value=good):
            state = flow.verify()
        self.assertEqual(state.stage, "verified")
        self.assertEqual(state.errors, [])

    def test_commit_retry_success_clears_stale_errors(self):
        flow = self._deployed_flow()
        good = ConnectivityReport("tok-1", True, True, True)
        with mock.patch("register.flow.test_connectivity", return_value=good):
            flow.verify()
        flow.state.stage = "failed"
        flow.state.step = 6
        flow.state.errors = ["previous commit failure"]
        state = flow.commit()
        self.assertEqual(state.stage, "committed")
        self.assertEqual(state.errors, [])

    def test_reserved_daemon_ports_are_scoped_by_target_host(self):
        """§6.4: daemon_port 唯一性作用域是 daemon 目标主机。"""
        from register.reservation import Reservation
        flow = RegistrationFlow(self.reg)
        flow.start(remote_request())
        flow.reservations.reserve(Reservation(
            user="bob", token="tok-2", daemon_scope="server-b",
            daemon_port=65081, local_port=65082,
        ))
        self.assertEqual(flow.reserved_daemon_ports("server-a"), set())
        self.assertEqual(flow.reserved_daemon_ports("server-b"), {65081})


class TestRegisterUserOneShot(unittest.TestCase):
    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))
        self.reg = load_registry(registry_path())

    def test_committed_roundtrip(self):
        entry = complete_remote_entry()
        report = ConnectivityReport("tok-1", True, True, True)
        with mock.patch("register.flow.probe_user", return_value=ProbeResult(entry, 3)), \
             mock.patch.object(RegistrationFlow, "_recheck_ports_before_deploy", lambda self, state, budget: None), \
             mock.patch("register.flow.deploy_user", return_value="/home/alice/setup.il"), \
             mock.patch("register.flow.test_connectivity", return_value=report):
            state = register_user(
                self.reg, mode="remote", user="alice", token="tok-1",
                ssh={"default": {"host": "server-a", "user": "alice"}},
                confirm_commit=True,
            )
        self.assertEqual(state.stage, "committed")
        self.assertIsNotNone(self.reg.get("alice"))

    def test_requires_explicit_commit_confirmation(self):
        """§3.1/§3.3: 第六步必须由用户显式确认；一次性辅助不得默认落盘。"""
        entry = complete_remote_entry()
        report = ConnectivityReport("tok-1", True, True, True)
        with mock.patch("register.flow.probe_user", return_value=ProbeResult(entry, 3)), \
             mock.patch.object(RegistrationFlow, "_recheck_ports_before_deploy", lambda self, state, budget: None), \
             mock.patch("register.flow.deploy_user", return_value="/home/alice/setup.il"), \
             mock.patch("register.flow.test_connectivity", return_value=report):
            with self.assertRaises(ValueError):
                register_user(
                    self.reg, mode="remote", user="alice", token="tok-1",
                    ssh={"default": {"host": "server-a", "user": "alice"}},
                )
        self.assertIsNone(self.reg.get("alice"))


class TestFlowCancelGuard(unittest.TestCase):
    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))
        self.reg = load_registry(registry_path())

    def test_cancel_does_not_release_committed_session(self):
        """§3.3: cancel 只合法于任意非 committed 进行中会话。"""
        flow = RegistrationFlow(self.reg)
        flow.state = RegistrationState(user="alice", stage="committed", step=6)
        state = flow.cancel()
        self.assertEqual(state.stage, "committed")


class TestProbeFailureBranches(unittest.TestCase):
    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))

    def _remote(self, **patches):
        from register import probe_user
        from unittest import mock
        with mock.patch("register.flow.SSHRunner") as runner, \
             mock.patch("register.probe.host_key_fingerprint", return_value="SHA256:fp"), \
             mock.patch("register.probe.remote_hostname", return_value="host-a"), \
             mock.patch("register.probe.remote_user", return_value="alice"), \
             mock.patch("register.probe.remote_user_exists", return_value=True), \
             mock.patch("register.probe.detect_remote_python", return_value=("python3", 3)), \
             mock.patch("register.probe.allocate_remote_port", return_value=65081), \
             mock.patch("register.probe.remote_path_writable", return_value=True):
            runner.return_value.test_connection.return_value = True
            runner.return_value.run_command.side_effect = _probe_run
            for name, value in patches.items():
                pass
            return probe_user, runner

    def test_user_path_escape_rejected(self):
        from register.models import RegistrationRequest
        from pydantic import ValidationError
        for bad in ("../escape", "/tmp/escape", "a/b", "a..b", ".", ".."):
            with self.assertRaises(ValidationError):
                RegistrationRequest(user=bad, mode="local")
        for good in ("alice", "vb01", "a.b-c_d"):
            req = RegistrationRequest(user=good, mode="local")
            self.assertEqual(req.user, good)

    def test_local_port_busy(self):
        from register import probe_user
        import socket
        s = socket.socket()
        s.bind(("0.0.0.0", 0))
        port = s.getsockname()[1]
        try:
            with self.assertRaises(RegistrationProbeError):
                probe_user(
                RegistrationRequest(
                    user="u", mode="local",
                    roles={"daemon": {"daemon_port": port}},
                ), token="t"
            )
        finally:
            s.close()

    def test_local_unwritable_scratch(self):
        from register import probe_user
        from unittest import mock
        request = RegistrationRequest(user="u", mode="local", root={"default": str(Path(self.wd))})
        with mock.patch("register.probe.local_path_writable", return_value=False):
            with self.assertRaises(RegistrationProbeError):
                probe_user(request, token="t")

    def test_remote_fingerprint_missing(self):
        from register import probe_user
        from unittest import mock
        with mock.patch("register.flow.SSHRunner") as runner, \
             mock.patch("register.probe.host_key_fingerprint", return_value=None):
            runner.return_value.test_connection.return_value = True
            runner.return_value.run_command.side_effect = _probe_run
            with self.assertRaises(RegistrationProbeError):
                probe_user(
                RegistrationRequest(
                    mode="remote", user="u",
                    ssh={"default": {"host": "h", "user": "a"}},
                ), token="t"
            )

    def test_remote_scratch_not_writable(self):
        from register import probe_user
        from unittest import mock
        with mock.patch("register.flow.SSHRunner") as runner, \
             mock.patch("register.probe.host_key_fingerprint", return_value="SHA256:fp"), \
             mock.patch("register.probe.remote_hostname", return_value="host-a"), \
             mock.patch("register.probe.remote_user", return_value="alice"), \
             mock.patch("register.probe.remote_user_exists", return_value=True), \
             mock.patch("register.probe.detect_remote_python", return_value=("python3", 3)), \
             mock.patch("register.probe.allocate_remote_port", return_value=65081), \
             mock.patch("register.probe.remote_path_writable", return_value=False):
            runner.return_value.test_connection.return_value = True
            runner.return_value.run_command.side_effect = _probe_run
            with self.assertRaises(RegistrationProbeError):
                probe_user(RegistrationRequest(mode="remote", user="u", ssh={"default": {"host": "h", "user": "a"}}), token="t")

    def test_remote_daemon_user_unresolvable(self):
        from register import probe_user
        from unittest import mock
        with mock.patch("register.flow.SSHRunner") as runner, \
             mock.patch("register.probe.host_key_fingerprint", return_value="SHA256:fp"), \
             mock.patch("register.probe.remote_hostname", return_value="host-a"), \
             mock.patch("register.probe.remote_user", return_value=""), \
             mock.patch("register.probe.detect_remote_python", return_value=("python3", 3)), \
             mock.patch("register.probe.allocate_remote_port", return_value=65081), \
             mock.patch("register.probe.remote_path_writable", return_value=True):
            runner.return_value.test_connection.return_value = True
            runner.return_value.run_command.side_effect = _probe_run
            with self.assertRaises(RegistrationProbeError):
                probe_user(
                RegistrationRequest(
                    mode="remote", user="u",
                    ssh={"default": {"host": "h", "user": "a"}},
                ), token="t"
            )


class TestVerifyExceptionBranches(unittest.TestCase):
    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))
        self.reg = load_registry(registry_path())

    def test_verify_connectivity_exception(self):
        from unittest import mock
        flow = RegistrationFlow(self.reg)
        flow.state = type("S", (), {
            "user": "alice", "entry": UserEntry(token="t", mode="remote"),
            "stage": "deployed", "setup_path": None, "token": "t",
            "errors": [], "warnings": [], "report": None,
        })()
        with mock.patch("register.flow.test_connectivity", side_effect=RuntimeError("boom")):
            state = flow.verify()
        self.assertEqual(state.stage, "failed")
        self.assertIn("connectivity test failed", state.errors[0])

    def test_commit_registry_error(self):
        from unittest import mock
        flow = RegistrationFlow(self.reg)
        flow.state = type("S", (), {
            "user": "alice", "entry": UserEntry(token="t", mode="remote"),
            "stage": "deployed", "setup_path": None, "token": "t",
            "errors": [], "warnings": [], "report": None,
        })()
        self.reg.register("other", UserEntry(token="t", mode="remote"))
        report = ConnectivityReport("t", True, True, True)
        with mock.patch("register.flow.test_connectivity", return_value=report):
            state = flow.verify()
        # 第五步通过只报告，不落盘；token 冲突在第六步 commit 时才暴露
        self.assertEqual(state.stage, "verified")
        state = flow.commit()
        self.assertEqual(state.stage, "failed")
        self.assertTrue(any("already belongs" in e for e in state.errors))


class TestFlowMoreBranches(unittest.TestCase):
    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))

    def test_resolve_scratch_absolute_passthrough_and_failure(self):
        from register.flow import _resolve_remote_scratch
        self.assertEqual(_resolve_remote_scratch(None, "/abs/path"), "/abs/path")
        runner = type("R", (), {})()
        runner.run_command = lambda *a, **k: CommandResult(1, "", "")
        with self.assertRaises(RegistrationProbeError):
            _resolve_remote_scratch(runner, "~/.vb")

    def test_remote_probe_unreachable_host(self):
        from unittest import mock
        from register import probe_user
        with mock.patch("register.flow.SSHRunner") as runner:
            runner.return_value.test_connection.return_value = False
            with self.assertRaises(RegistrationProbeError):
                probe_user(RegistrationRequest(mode="remote", user="u", ssh={"default": {"host": "h", "user": "a"}}), token="t")

    def test_remote_probe_missing_hostname(self):
        from unittest import mock
        from register import probe_user
        with mock.patch("register.flow.SSHRunner") as runner, \
             mock.patch("register.probe.host_key_fingerprint", return_value="fp"), \
             mock.patch("register.probe.remote_hostname", return_value=""):
            runner.return_value.test_connection.return_value = True
            runner.return_value.run_command.side_effect = _probe_run
            with self.assertRaises(RegistrationProbeError):
                probe_user(RegistrationRequest(mode="remote", user="u", ssh={"default": {"host": "h", "user": "a"}}), token="t")

    def test_remote_probe_no_python(self):
        from unittest import mock
        from register import probe_user
        with mock.patch("register.flow.SSHRunner") as runner, \
             mock.patch("register.probe.host_key_fingerprint", return_value="fp"), \
             mock.patch("register.probe.remote_hostname", return_value="host-a"), \
             mock.patch("register.probe.remote_user", return_value="alice"), \
             mock.patch("register.probe.remote_user_exists", return_value=True), \
             mock.patch("register.probe.detect_remote_python", return_value=None):
            runner.return_value.test_connection.return_value = True
            runner.return_value.run_command.side_effect = _probe_run
            with self.assertRaises(RegistrationProbeError):
                probe_user(RegistrationRequest(mode="remote", user="u", ssh={"default": {"host": "h", "user": "a"}}), token="t")

    def test_remote_probe_explicit_port_busy(self):
        from unittest import mock
        from register import probe_user
        with mock.patch("register.flow.SSHRunner") as runner, \
             mock.patch("register.probe.host_key_fingerprint", return_value="fp"), \
             mock.patch("register.probe.remote_hostname", return_value="host-a"), \
             mock.patch("register.probe.remote_user", return_value="alice"), \
             mock.patch("register.probe.remote_user_exists", return_value=True), \
             mock.patch("register.probe.detect_remote_python", return_value=("python3", 3)), \
             mock.patch("register.probe.port_free_on_remote", return_value=False):
            runner.return_value.test_connection.return_value = True
            runner.return_value.run_command.side_effect = _probe_run
            with self.assertRaises(RegistrationProbeError):
                probe_user(RegistrationRequest(mode="remote", user="u", ssh={"default": {"host": "h", "user": "a"}}, roles={"daemon": {"daemon_port": 65081}}), token="t")

    def test_remote_probe_no_free_port(self):
        from unittest import mock
        from register import probe_user
        with mock.patch("register.flow.SSHRunner") as runner, \
             mock.patch("register.probe.host_key_fingerprint", return_value="fp"), \
             mock.patch("register.probe.remote_hostname", return_value="host-a"), \
             mock.patch("register.probe.remote_user", return_value="alice"), \
             mock.patch("register.probe.remote_user_exists", return_value=True), \
             mock.patch("register.probe.detect_remote_python", return_value=("python3", 3)), \
             mock.patch("register.probe.allocate_remote_port", return_value=None):
            runner.return_value.test_connection.return_value = True
            runner.return_value.run_command.side_effect = _probe_run
            with self.assertRaises(RegistrationProbeError):
                probe_user(RegistrationRequest(mode="remote", user="u", ssh={"default": {"host": "h", "user": "a"}}), token="t")

    def test_short_host_match(self):
        from register.flow import _short_host_match
        self.assertTrue(_short_host_match("GLIS", "GLIS.localdomain"))
        self.assertFalse(_short_host_match(None, "x"))
        self.assertFalse(_short_host_match("a", "b"))

    def test_banner_hostname_local_file(self):
        from unittest import mock
        from register.flow import _banner_hostname
        entry = UserEntry(token="t", mode="local")
        root = Path(tempfile.mkdtemp())
        entry.roles.daemon.root = str(root)
        from common.remote_paths import identity_path
        p = Path(identity_path("alice", str(root)))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("host=my-host\nip=1.2.3.4\n", encoding="utf-8")
        self.assertEqual(_banner_hostname(entry, "alice"), "my-host")

    def test_connectivity_warning_on_banner_drift(self):
        from unittest import mock
        from register.flow import test_connectivity
        entry = UserEntry(token="t", mode="local")
        entry.roles.daemon.expected_hostname = "expected-host"
        with mock.patch("register.flow.SkillClient") as skill_cls, \
             mock.patch(
                 "register.flow._identity_text",
                 return_value="host=different-host\nip=1.2.3.4\n",
             ):
            skill_cls.return_value.execute_skill.return_value = VirtuosoResult(
                status=ExecutionStatus.SUCCESS, output="2"
            )
            report = test_connectivity(entry, "alice")
        self.assertTrue(report.ok)
        self.assertTrue(any("differs from expected" in w for w in report.warnings))

    def test_connectivity_reads_identity_once_and_reports_both_drifts(self):
        """步骤 5 只读一次 identity 文件，同时给出 host/user 两条 WARNING。"""
        from unittest import mock
        from register.flow import test_connectivity
        entry = UserEntry(token="t", mode="local")
        entry.roles.daemon.expected_hostname = "expected-host"
        entry.roles.daemon.expected_user = "expected-user"
        identity = (
            "host=different-host\nip=1.2.3.4\nbind=127.0.0.1:1\nuser=other-user\n"
        )
        with mock.patch("register.flow.SkillClient") as skill_cls, \
             mock.patch(
                 "register.flow._identity_text", return_value=identity
             ) as identity_read:
            skill_cls.return_value.execute_skill.return_value = VirtuosoResult(
                status=ExecutionStatus.SUCCESS, output="2"
            )
            report = test_connectivity(entry, "alice")
        self.assertTrue(report.ok)
        self.assertEqual(identity_read.call_count, 1, "identity read more than once")
        joined = " ".join(report.warnings)
        self.assertIn("banner host", joined)
        self.assertIn("daemon user", joined)


class TestRequestAndIdempotence(unittest.TestCase):
    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))
        self.reg = load_registry(registry_path())

    def test_remote_requires_host_and_ssh_user(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            RegistrationRequest(mode="remote", user="u", ssh={"default": {"host": "h"}})
        with self.assertRaises(ValidationError):
            RegistrationRequest(mode="remote", user="u", ssh={"default": {"user": "a"}})

    def test_port_range_validation(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            RegistrationRequest(user="u", mode="local", roles={"daemon": {"daemon_port": 0}})
        with self.assertRaises(ValidationError):
            RegistrationRequest(mode="remote", user="u", ssh={"default": {"host": "h", "user": "a"}}, roles={"daemon": {"local_port": 70000}})

    def test_token_charset_validation(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            RegistrationRequest(user="u", mode="local", token='bad"token')

    def test_verify_idempotent_after_commit(self):
        from unittest import mock
        flow = RegistrationFlow(self.reg)
        flow.state = RegistrationState(user="alice", stage="committed")
        with mock.patch("register.flow.test_connectivity") as tc:
            state = flow.verify()
        self.assertEqual(state.stage, "committed")
        tc.assert_not_called()


class TestLocalJointPort(unittest.TestCase):
    """§6.4: local 模式下 daemon_port 与 local_port 是同一个候选端口。"""

    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))
        self.reg = load_registry(registry_path())

    def _probe_local(self, **daemon_fields):
        from register import probe_user
        request = RegistrationRequest(
            mode="local", user="u", token="tok",
            roles={"daemon": daemon_fields},
        )
        with mock.patch("register.probe.local_path_writable", return_value=True), \
             mock.patch("register.probe.local_port_free", return_value=True), \
             mock.patch("register.probe.detect_local_spectre", return_value=None):
            return probe_user(request, token="tok")

    def test_single_explicit_local_port_is_used_for_both(self):
        result = self._probe_local(local_port=65091)
        daemon = result.entry.roles.daemon
        self.assertEqual(daemon.daemon_port, 65091)
        self.assertEqual(daemon.local_port, 65091)

    def test_single_explicit_daemon_port_is_used_for_both(self):
        result = self._probe_local(daemon_port=65092)
        daemon = result.entry.roles.daemon
        self.assertEqual(daemon.daemon_port, 65092)
        self.assertEqual(daemon.local_port, 65092)

    def test_mismatched_explicit_ports_are_rejected(self):
        with self.assertRaises(RegistrationProbeError):
            self._probe_local(daemon_port=65093, local_port=65094)

    def test_default_port_in_use_falls_back_to_a_free_port(self):
        from register import probe_user
        request = RegistrationRequest(mode="local", user="u", token="tok")
        with mock.patch("register.probe.local_path_writable", return_value=True), \
             mock.patch("register.probe.local_port_free",
                        side_effect=lambda port: port != 65432), \
             mock.patch("register.probe.allocate_local_port", return_value=65123), \
             mock.patch("register.probe.detect_local_spectre", return_value=None):
            result = probe_user(request, token="tok")
        daemon = result.entry.roles.daemon
        self.assertEqual(daemon.daemon_port, 65123)
        self.assertEqual(daemon.local_port, 65123)

    def test_local_role_expected_fingerprint_is_cleared(self):
        """§2.3: mode=local 的 role 没有 endpoint，expected_fingerprint 必须为 null。"""
        from register import probe_user
        request = RegistrationRequest(
            mode="local", user="u", token="tok",
            roles={"gui": {"expected_fingerprint": "SHA256:stale"}},
        )
        with mock.patch("register.probe.local_path_writable", return_value=True), \
             mock.patch("register.probe.local_port_free", return_value=True), \
             mock.patch("register.probe.detect_local_spectre", return_value=None):
            result = probe_user(request, token="tok")
        self.assertIsNone(result.entry.roles.gui.expected_fingerprint)


class TestPolicyFieldsApplied(unittest.TestCase):
    def test_policy_fields_are_written_into_entry(self):
        from unittest import mock
        from register import probe_user
        request = RegistrationRequest(
            mode="remote", user="u", token="tok",
            ssh={"default": {"host": "h", "user": "a",
                             "proxy": "socks5://127.0.0.1:1080"}},
            roles={"spectre": {"host": "spec-host",
                              "bin": "/opt/spectre/bin/spectre"}},
            ssh_backend="paramiko", ssh_control_master="disable",
            thread_pool_size=8, channel_budget=3, connect_timeout=9.5,
            log_level="error", log_max_bytes=4096,
        )
        with mock.patch("register.flow.SSHRunner") as runner, \
             mock.patch("register.probe.host_key_fingerprint", return_value="fp"), \
             mock.patch("register.probe.remote_hostname", return_value="host-a"), \
             mock.patch("register.probe.remote_user", return_value="alice"), \
             mock.patch("register.probe.remote_user_exists", return_value=True), \
             mock.patch("register.probe.detect_remote_python", return_value=("python3", 3)), \
             mock.patch("register.probe.allocate_remote_port", return_value=65081), \
             mock.patch("register.probe.remote_path_writable", return_value=True), \
             mock.patch("register.probe.allocate_local_port", return_value=65082):
            runner.return_value.test_connection.return_value = True
            runner.return_value.run_command.side_effect = _probe_run
            result = probe_user(request, token="tok")
        entry = result.entry
        self.assertEqual(entry.ssh.backend, "paramiko")
        self.assertEqual(entry.ssh.control_master, "disable")
        self.assertEqual(entry.runtime.thread_pool_size, 8)
        self.assertEqual(entry.runtime.channel_budget, 3)
        self.assertEqual(entry.runtime.connect_timeout, 9.5)
        self.assertEqual(entry.cdslog.log_level, "error")
        self.assertEqual(entry.cdslog.log_max_bytes, 4096)
        self.assertEqual(entry.roles.spectre.host, "spec-host")
        self.assertEqual(entry.roles.spectre.bin, "/opt/spectre/bin/spectre")
        self.assertEqual(entry.roles.daemon.local_port, 65082)


class TestConnectivityFingerprint(unittest.TestCase):
    def test_host_key_mismatch_blocks_commit(self):
        from unittest import mock
        from register.flow import test_connectivity
        entry = UserEntry(token="tok", mode="remote")
        entry.ssh.default = SshDefaults(host="server-a", user="alice")
        entry.roles.daemon.daemon_port = 65081
        entry.roles.daemon.local_port = 65082
        entry.roles.daemon.expected_fingerprint = "SHA256:expected"
        entry.roles.daemon.expected_hostname = "server-a"
        entry.roles.daemon.root = "/home/alice/.virtuoso-bridge"
        fake_cmd = mock.Mock()
        fake_cmd.run_command.return_value = CommandResult(0, "vb-ok", "")
        fake_tunnel = mock.Mock()
        with mock.patch("register.flow.probes.host_key_fingerprint", return_value="SHA256:other"), \
             mock.patch("register.flow.SSHRunner", side_effect=[fake_cmd, fake_tunnel]), \
             mock.patch("register.flow.SkillClient") as skill_cls, \
             mock.patch("register.flow._identity_text", return_value=None):
            skill_cls.return_value.execute_skill.return_value = VirtuosoResult(
                status=ExecutionStatus.SUCCESS, output="2"
            )
            report = test_connectivity(entry, "alice")
        fake_tunnel.start_port_forward.assert_called_once()
        call_args, call_kwargs = fake_tunnel.start_port_forward.call_args
        self.assertEqual(call_args[0], 65082)
        self.assertEqual(call_kwargs.get("remote_port"), 65081)
        fake_tunnel.stop_port_forward.assert_called_once()
        self.assertFalse(report.fingerprint_ok)
        self.assertFalse(report.ok)
        self.assertIn("host key mismatch", report.detail)


class TestSpectreAutoProbe(unittest.TestCase):
    def test_auto_detect_fills_route(self):
        from unittest import mock
        from register import probe_user
        request = RegistrationRequest(mode="remote", user="u", token="tok", ssh={"default": {"host": "h", "user": "a"}})
        with mock.patch("register.flow.SSHRunner") as runner, \
             mock.patch("register.probe.host_key_fingerprint", return_value="fp"), \
             mock.patch("register.probe.remote_hostname", return_value="host-a"), \
             mock.patch("register.probe.remote_user", return_value="alice"), \
             mock.patch("register.probe.remote_user_exists", return_value=True), \
             mock.patch("register.probe.detect_remote_python", return_value=("python3", 3)), \
             mock.patch("register.probe.allocate_remote_port", return_value=65081), \
             mock.patch("register.probe.remote_path_writable", return_value=True), \
             mock.patch("register.probe.allocate_local_port", return_value=65082), \
             mock.patch("register.probe.detect_remote_spectre", return_value="/opt/cad/bin/spectre"):
            runner.return_value.test_connection.return_value = True
            runner.return_value.run_command.side_effect = _probe_run
            result = probe_user(request, token="tok")
        self.assertEqual(result.entry.roles.spectre.bin, "/opt/cad/bin/spectre")
        from transport.remote_roles import resolve
        self.assertEqual(resolve(result.entry).spectre.host, "h")

    def test_explicit_bad_spectre_non_blocking(self):
        from unittest import mock
        from register import probe_user
        request = RegistrationRequest(mode="remote", user="u", token="tok", ssh={"default": {"host": "h", "user": "a"}}, roles={"spectre": {"bin": "/bad/spectre"}})
        with mock.patch("register.flow.SSHRunner") as runner, \
             mock.patch("register.probe.host_key_fingerprint", return_value="fp"), \
             mock.patch("register.probe.remote_hostname", return_value="host-a"), \
             mock.patch("register.probe.remote_user", return_value="alice"), \
             mock.patch("register.probe.detect_remote_python", return_value=("python3", 3)), \
             mock.patch("register.probe.allocate_remote_port", return_value=65081), \
             mock.patch("register.probe.remote_path_writable", return_value=True), \
             mock.patch("register.probe.allocate_local_port", return_value=65082), \
             mock.patch("register.probe.remote_executable_exists", return_value=False):
            runner.return_value.test_connection.return_value = True
            runner.return_value.run_command.side_effect = _probe_run
            result = probe_user(request, token="tok")
        self.assertIsNone(result.entry.roles.spectre.bin)
        self.assertTrue(any("non-blocking" in w for w in result.warnings))
        # §6.2: spectre 探测失败时 root / expected_fingerprint / bin 一并提交为 null
        self.assertIsNone(result.entry.roles.spectre.root)
        self.assertIsNone(result.entry.roles.spectre.expected_fingerprint)


if __name__ == "__main__":
    unittest.main()
