"""Registry decoupling contract tests.

- registration = probe (no persistence) + verified atomic commit;
- runtime = load-once in-memory consumption, no setup-phase methods on the
  runtime facade;
- token uniqueness / user overwrite policy / duplicate-token load detection.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pyapi.models import CommandResult
from transport.middle import BusinessServer
from transport.register import RegistrationRequest, probe_user
from transport.registry import (
    RegistryError,
    TokenConflictError,
    UserAlreadyRegisteredError,
    UserEntry,
    load_registry,
)
from transport.runtime_paths import registry_path, set_working_dir


class _FakeProbeRunner:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    def test_connection(self) -> bool:
        return True

    def run_command(self, cmd: str, timeout=None) -> CommandResult:
        return CommandResult(0, "/home/alice", "")


class TestRegistryCommitPolicy(unittest.TestCase):
    def setUp(self) -> None:
        self.wd = set_working_dir(Path(tempfile.mkdtemp()))
        self.reg = load_registry(registry_path())

    def test_duplicate_user_rejected_without_overwrite(self) -> None:
        self.reg.register("alice", UserEntry(token="tok-a", mode="remote"))
        with self.assertRaises(UserAlreadyRegisteredError):
            self.reg.register("alice", UserEntry(token="tok-b", mode="remote"))

    def test_overwrite_replaces_entry_and_token_index(self) -> None:
        self.reg.register("alice", UserEntry(token="tok-a", mode="remote"))
        self.reg.register("alice", UserEntry(token="tok-b", mode="remote"), overwrite=True)
        self.assertIsNone(self.reg.by_token("tok-a"))
        self.assertEqual(self.reg.by_token("tok-b").token, "tok-b")

    def test_token_conflict_across_users_rejected(self) -> None:
        self.reg.register("alice", UserEntry(token="tok-a", mode="remote"))
        with self.assertRaises(TokenConflictError):
            self.reg.register("bob", UserEntry(token="tok-a", mode="remote"))

    def test_remove_clears_token_mapping(self) -> None:
        self.reg.register("alice", UserEntry(token="tok-a", mode="remote"))
        self.reg.remove("alice")
        self.assertIsNone(self.reg.by_token("tok-a"))
        self.assertIsNone(self.reg.get("alice"))

    def test_load_rejects_duplicate_tokens(self) -> None:
        registry_path().write_text(
            json.dumps({
                "users": {
                    "alice": UserEntry(token="tok-a", mode="remote").model_dump(),
                    "bob": UserEntry(token="tok-a", mode="remote").model_dump(),
                }
            }),
            encoding="utf-8",
        )
        with self.assertRaises(RegistryError):
            load_registry(registry_path())


class TestProbeNeverPersists(unittest.TestCase):
    def setUp(self) -> None:
        self.wd = set_working_dir(Path(tempfile.mkdtemp()))

    def test_local_probe_does_not_touch_registry(self) -> None:
        result = probe_user(RegistrationRequest(user="alice", local=True), token="tok-1")
        self.assertEqual(result.entry.mode, "local")
        self.assertFalse(registry_path().exists())

    def test_remote_probe_returns_candidate_without_commit(self) -> None:
        with mock.patch("transport.ssh.SSHRunner", _FakeProbeRunner), \
             mock.patch("transport.register.probe.detect_remote_python", return_value=("python3", 3)), \
             mock.patch("transport.register.probe.allocate_remote_port", return_value=65081), \
             mock.patch("transport.register.probe.remote_hostname", return_value="compute-a"), \
             mock.patch("transport.register.probe.remote_user", return_value="alice"), \
             mock.patch("transport.register.probe.remote_user_exists", return_value=True), \
             mock.patch("transport.register.probe.remote_path_writable", return_value=True), \
             mock.patch("transport.register.probe.host_key_fingerprint", return_value="SHA256:abc"):
            result = probe_user(
                RegistrationRequest(user="alice", host="compute-a", ssh_user="alice"),
                token="tok-1",
            )
        self.assertEqual(result.entry.route.skill.daemon_port, 65081)
        self.assertEqual(result.entry.expected.daemon_user, "alice")
        self.assertFalse(registry_path().exists())


class TestRuntimeFacadePurity(unittest.TestCase):
    def setUp(self) -> None:
        self.wd = set_working_dir(Path(tempfile.mkdtemp()))

    def test_business_server_has_no_setup_phase_methods(self) -> None:
        server = BusinessServer(self.wd)
        for name in ("register_user", "deploy", "connect"):
            self.assertFalse(hasattr(server, name), name)

    def test_token_is_required_keyword(self) -> None:
        server = BusinessServer(self.wd)
        with self.assertRaises(TypeError):
            server.execute_skill("1+1")  # noqa: B008
        with self.assertRaises(TypeError):
            server.run_command("echo x")
        with self.assertRaises(TypeError):
            server.upload_file(Path("a"), "b")
        with self.assertRaises(TypeError):
            server.download_file("a", Path("b"))

    def test_runtime_consumes_registry_in_memory_only(self) -> None:
        reg = load_registry(registry_path())
        reg.register("alice", UserEntry(token="tok-1", mode="local"))
        server = BusinessServer(self.wd)  # load once from disk
        # mutate disk behind the loaded registry's back
        registry_path().write_text(json.dumps({"users": {}}), encoding="utf-8")
        self.assertIsNotNone(server.registry.by_token("tok-1"))


if __name__ == "__main__":
    unittest.main()
