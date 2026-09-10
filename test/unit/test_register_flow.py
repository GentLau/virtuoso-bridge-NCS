"""Six-step registration flow unit tests (probes/deploy/connectivity mocked)."""

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pyapi.models import CommandResult, ExecutionStatus, VirtuosoResult

from transport.register import (
    ConnectivityReport,
    RegistrationState,
    RegistrationFlow,
    RegistrationProbeError,
    RegistrationRequest,
    ProbeResult,
    register_user,
    validate_local,
)
from transport.registry import UserEntry, load_registry
from transport.runtime_paths import registry_path, set_working_dir


def remote_request(**kwargs):
    base = dict(user="alice", host="server-a", ssh_user="alice", token="tok-1")
    base.update(kwargs)
    return RegistrationRequest(**base)


class TestValidateLocal(unittest.TestCase):
    def setUp(self):
        self.wd = set_working_dir(Path(tempfile.mkdtemp()))
        self.reg = load_registry(registry_path())

    def test_clean(self):
        self.assertEqual(validate_local(self.reg, remote_request()), [])

    def test_user_duplicate(self):
        self.reg.register("alice", UserEntry(token="other", mode="remote"))
        errors = validate_local(self.reg, remote_request())
        self.assertTrue(any("already registered" in e for e in errors))

    def test_daemon_port_conflict(self):
        other = UserEntry(token="other", mode="remote")
        other.route.skill.daemon_port = 65081
        self.reg.register("bob", other)
        errors = validate_local(self.reg, remote_request(daemon_port=65081))
        self.assertTrue(any("daemon port 65081 conflicts" in e for e in errors))

    def test_local_port_conflict(self):
        other = UserEntry(token="other", mode="remote")
        other.route.skill.local_port = 65082
        self.reg.register("bob", other)
        errors = validate_local(self.reg, remote_request(local_port=65082))
        self.assertTrue(any("local port 65082 conflicts" in e for e in errors))


class TestFlowApply(unittest.TestCase):
    def setUp(self):
        self.wd = set_working_dir(Path(tempfile.mkdtemp()))
        self.reg = load_registry(registry_path())

    def test_validation_failure_stops_flow(self):
        self.reg.register("alice", UserEntry(token="other", mode="remote"))
        state = RegistrationFlow(self.reg).apply(remote_request())
        self.assertEqual(state.stage, "failed")
        self.assertIsNone(state.entry)

    def test_probe_failure_stops_flow(self):
        with mock.patch("transport.register.flow.probe_user", side_effect=RegistrationProbeError("boom")):
            state = RegistrationFlow(self.reg).apply(remote_request())
        self.assertEqual(state.stage, "failed")
        self.assertIn("boom", state.errors)

    def test_deploy_failure_stops_flow(self):
        with mock.patch("transport.register.flow.probe_user", return_value=ProbeResult(UserEntry(token="tok-1", mode="remote"), 3)), \
             mock.patch("transport.register.flow.deploy_user", side_effect=RuntimeError("deploy boom")):
            state = RegistrationFlow(self.reg).apply(remote_request())
        self.assertEqual(state.stage, "failed")
        self.assertIn("deploy boom", state.errors[0])

    def test_happy_apply_reaches_deployed(self):
        entry = UserEntry(token="tok-1", mode="remote")
        with mock.patch("transport.register.flow.probe_user", return_value=ProbeResult(entry, 3)), \
             mock.patch("transport.register.flow.deploy_user", return_value="/home/alice/setup.il"):
            state = RegistrationFlow(self.reg).apply(remote_request())
        self.assertEqual(state.stage, "deployed")
        self.assertEqual(state.setup_path, "/home/alice/setup.il")
        self.assertEqual(state.token, "tok-1")


class TestFlowVerifyAndCommit(unittest.TestCase):
    def setUp(self):
        self.wd = set_working_dir(Path(tempfile.mkdtemp()))
        self.reg = load_registry(registry_path())

    def _deployed_flow(self):
        flow = RegistrationFlow(self.reg)
        with mock.patch("transport.register.flow.probe_user", return_value=ProbeResult(UserEntry(token="tok-1", mode="remote"), 3)), \
             mock.patch("transport.register.flow.deploy_user", return_value="/home/alice/setup.il"):
            flow.apply(remote_request())
        return flow

    def test_connectivity_failure_does_not_commit(self):
        flow = self._deployed_flow()
        report = ConnectivityReport("tok-1", True, False, True, detail="skill failed")
        with mock.patch("transport.register.flow.test_connectivity", return_value=report):
            state = flow.verify()
        self.assertEqual(state.stage, "failed")
        self.assertIsNone(self.reg.by_token("tok-1"))
        self.assertFalse(registry_path().exists())

    def test_success_commits_with_timestamp(self):
        flow = self._deployed_flow()
        report = ConnectivityReport("tok-1", True, True, True)
        with mock.patch("transport.register.flow.test_connectivity", return_value=report):
            state = flow.verify()
        self.assertEqual(state.stage, "committed")
        entry = self.reg.by_token("tok-1")
        self.assertIsNotNone(entry)
        self.assertIsNotNone(entry.registered_at)

    def test_verify_without_apply_reports_error(self):
        state = RegistrationFlow(self.reg).verify()
        self.assertEqual(state.stage, "failed")
        self.assertIn("no registration in progress", state.errors)


class TestRegisterUserOneShot(unittest.TestCase):
    def setUp(self):
        self.wd = set_working_dir(Path(tempfile.mkdtemp()))
        self.reg = load_registry(registry_path())

    def test_committed_roundtrip(self):
        entry = UserEntry(token="tok-1", mode="remote")
        report = ConnectivityReport("tok-1", True, True, True)
        with mock.patch("transport.register.flow.probe_user", return_value=ProbeResult(entry, 3)), \
             mock.patch("transport.register.flow.deploy_user", return_value="/home/alice/setup.il"), \
             mock.patch("transport.register.flow.test_connectivity", return_value=report):
            state = register_user(self.reg, user="alice", host="server-a", ssh_user="alice", token="tok-1")
        self.assertEqual(state.stage, "committed")
        self.assertIsNotNone(self.reg.get("alice"))


class TestProbeFailureBranches(unittest.TestCase):
    def setUp(self):
        self.wd = set_working_dir(Path(tempfile.mkdtemp()))

    def _remote(self, **patches):
        from transport.register import probe_user
        from unittest import mock
        with mock.patch("transport.ssh.SSHRunner") as runner, \
             mock.patch("transport.register.probe.host_key_fingerprint", return_value="SHA256:fp"), \
             mock.patch("transport.register.probe.remote_hostname", return_value="host-a"), \
             mock.patch("transport.register.probe.remote_user", return_value="alice"), \
             mock.patch("transport.register.probe.remote_user_exists", return_value=True), \
             mock.patch("transport.register.probe.detect_remote_python", return_value=("python3", 3)), \
             mock.patch("transport.register.probe.allocate_remote_port", return_value=65081), \
             mock.patch("transport.register.probe.remote_path_writable", return_value=True):
            runner.return_value.test_connection.return_value = True
            runner.return_value.run_command.return_value = CommandResult(0, "/home/alice", "")
            for name, value in patches.items():
                pass
            return probe_user, runner

    def test_local_port_busy(self):
        from transport.register import probe_user
        import socket
        s = socket.socket()
        s.bind(("0.0.0.0", 0))
        port = s.getsockname()[1]
        try:
            with self.assertRaises(RegistrationProbeError):
                probe_user(RegistrationRequest(user="u", local=True, daemon_port=port), token="t")
        finally:
            s.close()

    def test_local_unwritable_scratch(self):
        from transport.register import probe_user
        from unittest import mock
        request = RegistrationRequest(user="u", local=True, scratch_root=str(Path(self.wd)))
        with mock.patch("transport.register.probe.local_path_writable", return_value=False):
            with self.assertRaises(RegistrationProbeError):
                probe_user(request, token="t")

    def test_remote_fingerprint_missing(self):
        from transport.register import probe_user
        from unittest import mock
        with mock.patch("transport.ssh.SSHRunner") as runner, \
             mock.patch("transport.register.probe.host_key_fingerprint", return_value=None):
            runner.return_value.test_connection.return_value = True
            runner.return_value.run_command.return_value = CommandResult(0, "/home/alice", "")
            with self.assertRaises(RegistrationProbeError):
                probe_user(RegistrationRequest(user="u", host="h", ssh_user="a"), token="t")

    def test_remote_scratch_not_writable(self):
        from transport.register import probe_user
        from unittest import mock
        with mock.patch("transport.ssh.SSHRunner") as runner, \
             mock.patch("transport.register.probe.host_key_fingerprint", return_value="SHA256:fp"), \
             mock.patch("transport.register.probe.remote_hostname", return_value="host-a"), \
             mock.patch("transport.register.probe.remote_user", return_value="alice"), \
             mock.patch("transport.register.probe.remote_user_exists", return_value=True), \
             mock.patch("transport.register.probe.detect_remote_python", return_value=("python3", 3)), \
             mock.patch("transport.register.probe.allocate_remote_port", return_value=65081), \
             mock.patch("transport.register.probe.remote_path_writable", return_value=False):
            runner.return_value.test_connection.return_value = True
            runner.return_value.run_command.return_value = CommandResult(0, "/home/alice", "")
            with self.assertRaises(RegistrationProbeError):
                probe_user(RegistrationRequest(user="u", host="h", ssh_user="a"), token="t")

    def test_remote_daemon_user_missing(self):
        from transport.register import probe_user
        from unittest import mock
        with mock.patch("transport.ssh.SSHRunner") as runner, \
             mock.patch("transport.register.probe.host_key_fingerprint", return_value="SHA256:fp"), \
             mock.patch("transport.register.probe.remote_hostname", return_value="host-a"), \
             mock.patch("transport.register.probe.remote_user", return_value="alice"), \
             mock.patch("transport.register.probe.remote_user_exists", return_value=False), \
             mock.patch("transport.register.probe.detect_remote_python", return_value=("python3", 3)), \
             mock.patch("transport.register.probe.allocate_remote_port", return_value=65081), \
             mock.patch("transport.register.probe.remote_path_writable", return_value=True):
            runner.return_value.test_connection.return_value = True
            runner.return_value.run_command.return_value = CommandResult(0, "/home/alice", "")
            with self.assertRaises(RegistrationProbeError):
                probe_user(RegistrationRequest(user="u", host="h", ssh_user="a", daemon_user="ghost"), token="t")


class TestVerifyExceptionBranches(unittest.TestCase):
    def setUp(self):
        self.wd = set_working_dir(Path(tempfile.mkdtemp()))
        self.reg = load_registry(registry_path())

    def test_verify_connectivity_exception(self):
        from unittest import mock
        flow = RegistrationFlow(self.reg)
        flow.state = type("S", (), {
            "user": "alice", "entry": UserEntry(token="t", mode="remote"),
            "stage": "deployed", "setup_path": None, "token": "t",
            "errors": [], "warnings": [], "report": None,
        })()
        with mock.patch("transport.register.flow.test_connectivity", side_effect=RuntimeError("boom")):
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
        with mock.patch("transport.register.flow.test_connectivity", return_value=report):
            state = flow.verify()
        self.assertEqual(state.stage, "failed")
        self.assertTrue(any("already belongs" in e for e in state.errors))


class TestFlowMoreBranches(unittest.TestCase):
    def setUp(self):
        self.wd = set_working_dir(Path(tempfile.mkdtemp()))

    def test_resolve_scratch_absolute_passthrough_and_failure(self):
        from transport.register.flow import _resolve_remote_scratch
        self.assertEqual(_resolve_remote_scratch(None, "/abs/path"), "/abs/path")
        runner = type("R", (), {})()
        runner.run_command = lambda *a, **k: CommandResult(1, "", "")
        with self.assertRaises(RegistrationProbeError):
            _resolve_remote_scratch(runner, "~/.vb")

    def test_remote_probe_unreachable_host(self):
        from unittest import mock
        from transport.register import probe_user
        with mock.patch("transport.ssh.SSHRunner") as runner:
            runner.return_value.test_connection.return_value = False
            with self.assertRaises(RegistrationProbeError):
                probe_user(RegistrationRequest(user="u", host="h", ssh_user="a"), token="t")

    def test_remote_probe_missing_hostname(self):
        from unittest import mock
        from transport.register import probe_user
        with mock.patch("transport.ssh.SSHRunner") as runner, \
             mock.patch("transport.register.probe.host_key_fingerprint", return_value="fp"), \
             mock.patch("transport.register.probe.remote_hostname", return_value=""):
            runner.return_value.test_connection.return_value = True
            runner.return_value.run_command.return_value = CommandResult(0, "/home/u", "")
            with self.assertRaises(RegistrationProbeError):
                probe_user(RegistrationRequest(user="u", host="h", ssh_user="a"), token="t")

    def test_remote_probe_no_python(self):
        from unittest import mock
        from transport.register import probe_user
        with mock.patch("transport.ssh.SSHRunner") as runner, \
             mock.patch("transport.register.probe.host_key_fingerprint", return_value="fp"), \
             mock.patch("transport.register.probe.remote_hostname", return_value="host-a"), \
             mock.patch("transport.register.probe.remote_user", return_value="alice"), \
             mock.patch("transport.register.probe.remote_user_exists", return_value=True), \
             mock.patch("transport.register.probe.detect_remote_python", return_value=None):
            runner.return_value.test_connection.return_value = True
            runner.return_value.run_command.return_value = CommandResult(0, "/home/u", "")
            with self.assertRaises(RegistrationProbeError):
                probe_user(RegistrationRequest(user="u", host="h", ssh_user="a"), token="t")

    def test_remote_probe_explicit_port_busy(self):
        from unittest import mock
        from transport.register import probe_user
        with mock.patch("transport.ssh.SSHRunner") as runner, \
             mock.patch("transport.register.probe.host_key_fingerprint", return_value="fp"), \
             mock.patch("transport.register.probe.remote_hostname", return_value="host-a"), \
             mock.patch("transport.register.probe.remote_user", return_value="alice"), \
             mock.patch("transport.register.probe.remote_user_exists", return_value=True), \
             mock.patch("transport.register.probe.detect_remote_python", return_value=("python3", 3)), \
             mock.patch("transport.register.probe.port_free_on_remote", return_value=False):
            runner.return_value.test_connection.return_value = True
            runner.return_value.run_command.return_value = CommandResult(0, "/home/u", "")
            with self.assertRaises(RegistrationProbeError):
                probe_user(RegistrationRequest(user="u", host="h", ssh_user="a", daemon_port=65081), token="t")

    def test_remote_probe_no_free_port(self):
        from unittest import mock
        from transport.register import probe_user
        with mock.patch("transport.ssh.SSHRunner") as runner, \
             mock.patch("transport.register.probe.host_key_fingerprint", return_value="fp"), \
             mock.patch("transport.register.probe.remote_hostname", return_value="host-a"), \
             mock.patch("transport.register.probe.remote_user", return_value="alice"), \
             mock.patch("transport.register.probe.remote_user_exists", return_value=True), \
             mock.patch("transport.register.probe.detect_remote_python", return_value=("python3", 3)), \
             mock.patch("transport.register.probe.allocate_remote_port", return_value=None):
            runner.return_value.test_connection.return_value = True
            runner.return_value.run_command.return_value = CommandResult(0, "/home/u", "")
            with self.assertRaises(RegistrationProbeError):
                probe_user(RegistrationRequest(user="u", host="h", ssh_user="a"), token="t")

    def test_short_host_match(self):
        from transport.register.flow import _short_host_match
        self.assertTrue(_short_host_match("GLIS", "GLIS.localdomain"))
        self.assertFalse(_short_host_match(None, "x"))
        self.assertFalse(_short_host_match("a", "b"))

    def test_banner_hostname_local_file(self):
        from unittest import mock
        from transport.register.flow import _banner_hostname
        entry = UserEntry(token="t", mode="local")
        root = Path(tempfile.mkdtemp())
        entry.deploy.scratch_root = str(root)
        from transport.remote_paths import identity_path
        p = Path(identity_path("t", str(root)))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("host=my-host\nip=1.2.3.4\n", encoding="utf-8")
        self.assertEqual(_banner_hostname(entry), "my-host")

    def test_connectivity_warning_on_banner_drift(self):
        from unittest import mock
        from transport.register.flow import test_connectivity
        entry = UserEntry(token="t", mode="local")
        entry.expected.daemon_endpoint_hostname = "expected-host"
        with mock.patch("transport.register.flow.SkillClient") as skill_cls, \
             mock.patch("transport.register.flow._banner_hostname", return_value="different-host"):
            skill_cls.return_value.execute_skill.return_value = VirtuosoResult(
                status=ExecutionStatus.SUCCESS, output="2"
            )
            report = test_connectivity(entry)
        self.assertTrue(report.ok)
        self.assertTrue(any("differs from expected" in w for w in report.warnings))


class TestRequestAndIdempotence(unittest.TestCase):
    def setUp(self):
        self.wd = set_working_dir(Path(tempfile.mkdtemp()))
        self.reg = load_registry(registry_path())

    def test_remote_requires_host_and_ssh_user(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            RegistrationRequest(user="u", host="h")
        with self.assertRaises(ValidationError):
            RegistrationRequest(user="u", ssh_user="a")

    def test_port_range_validation(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            RegistrationRequest(user="u", local=True, daemon_port=0)
        with self.assertRaises(ValidationError):
            RegistrationRequest(user="u", host="h", ssh_user="a", local_port=70000)

    def test_token_charset_validation(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            RegistrationRequest(user="u", local=True, token='bad"token')

    def test_verify_idempotent_after_commit(self):
        from unittest import mock
        flow = RegistrationFlow(self.reg)
        flow.state = RegistrationState(user="alice", stage="committed")
        with mock.patch("transport.register.flow.test_connectivity") as tc:
            state = flow.verify()
        self.assertEqual(state.stage, "committed")
        tc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
