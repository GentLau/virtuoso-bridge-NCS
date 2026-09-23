"""Registry decoupling contract tests.

- registration = probe (no persistence) + verified atomic commit;
- runtime = load-once in-memory consumption, no setup-phase methods on the
  runtime facade;
- token uniqueness / user overwrite policy / duplicate-token load detection.
"""

import json
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pyapi.models import CommandResult
from transport.middle import BusinessServer
from register import RegistrationRequest, probe_user
from common.registry import (
    RegistryError,
    TokenConflictError,
    UserAlreadyRegisteredError,
    UserEntry,
    load_registry,
)
from common.paths import registry_path, override_work_dir_for_tests


class _FakeProbeRunner:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    def test_connection(self, timeout=None) -> bool:
        return True

    def close(self):
        pass

    def run_command(self, cmd: str, timeout=None) -> CommandResult:
        if "vb-ok" in cmd:
            return CommandResult(0, "vb-ok", "")
        return CommandResult(0, "/home/alice", "")


class TestRegistryCommitPolicy(unittest.TestCase):
    def setUp(self) -> None:
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp(prefix="vb-")))
        self.reg = load_registry(registry_path())

    def test_duplicate_user_rejected_without_overwrite(self) -> None:
        self.reg.register("alice", UserEntry(token="tok-a", mode="remote"))
        with self.assertRaises(UserAlreadyRegisteredError):
            self.reg.register("alice", UserEntry(token="tok-b", mode="remote"))

    def test_overwrite_with_same_token_replaces_entry(self) -> None:
        self.reg.register("alice", UserEntry(token="tok-a", mode="remote"))
        updated = UserEntry(token="tok-a", mode="remote")
        updated.runtime.thread_pool_size = 8
        self.reg.register("alice", updated, overwrite=True)
        self.assertEqual(self.reg.by_token("tok-a").runtime.thread_pool_size, 8)

    def test_overwrite_must_not_rotate_token(self) -> None:
        """§1: token 终生有效、不轮换；轮换 = 删除用户重新注册。"""
        self.reg.register("alice", UserEntry(token="tok-a", mode="remote"))
        with self.assertRaises(RegistryError):
            self.reg.register(
                "alice", UserEntry(token="tok-b", mode="remote"), overwrite=True
            )
        self.assertIsNotNone(self.reg.by_token("tok-a"))
        self.assertIsNone(self.reg.by_token("tok-b"))

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
                "alice": UserEntry(token="tok-a", mode="remote").model_dump(),
                "bob": UserEntry(token="tok-a", mode="remote").model_dump(),
            }),
            encoding="utf-8",
        )
        with self.assertRaises(RegistryError):
            load_registry(registry_path())

    def test_user_groups_round_trip_through_registry_file(self) -> None:
        entry = UserEntry(token="tok-group", mode="local")
        entry.roles.command.calibre = {
            "bin": "/opt/eda/mentor/calibre/bin/calibre",
            "version": "2024.4",
        }
        self.reg.register("grouped", entry)
        reloaded = self.reg.__class__(registry_path()).load()
        self.assertEqual(
            reloaded.by_token("tok-group").roles.command.calibre["version"],
            "2024.4",
        )

    def test_user_group_update_replaces_deletes_and_preserves(self) -> None:
        entry = UserEntry(token="tok-group-update", mode="local")
        entry.roles.command.calibre = {
            "bin": "/old/calibre",
            "version": "2024.4",
        }
        entry.roles.command.other = {"flag": True}
        self.reg.register("grouped-update", entry)

        replaced = self.reg.update(
            "grouped-update",
            {"roles": {"command": {"calibre": {"bin": "/new/calibre"}}}},
        )
        self.assertEqual(
            replaced.roles.command.calibre,
            {"bin": "/new/calibre"},
        )
        self.assertEqual(replaced.roles.command.other, {"flag": True})

        preserved = self.reg.update(
            "grouped-update",
            {"roles": {"command": {"root": "/new/root"}}},
        )
        self.assertEqual(
            preserved.roles.command.calibre,
            {"bin": "/new/calibre"},
        )
        self.assertEqual(preserved.roles.command.other, {"flag": True})

        deleted = self.reg.update(
            "grouped-update",
            {"roles": {"command": {"calibre": None}}},
        )
        self.assertNotIn("calibre", deleted.roles.command.model_dump())
        self.assertEqual(deleted.roles.command.other, {"flag": True})


class TestProbeNeverPersists(unittest.TestCase):
    def setUp(self) -> None:
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp(prefix="vb-")))

    def test_local_probe_does_not_touch_registry(self) -> None:
        result = probe_user(RegistrationRequest(user="alice", mode="local", roles={"spectre": {"bin": sys.executable}}), token="tok-1")
        self.assertEqual(result.entry.mode.default, "local")
        self.assertFalse(registry_path().exists())

    def test_remote_probe_returns_candidate_without_commit(self) -> None:
        # Pin the local tunnel port: this test is about "probe never persists",
        # not about port allocation; letting the real allocator run makes it
        # flaky when the suite's own SSH connections occupy 65081+.
        probe_sock = socket.socket()
        probe_sock.bind(("127.0.0.1", 0))
        pinned_local_port = probe_sock.getsockname()[1]
        probe_sock.close()
        with mock.patch("register.flow.SSHRunner", _FakeProbeRunner), \
             mock.patch("register.probe.detect_remote_python", return_value=("python3", 3)), \
             mock.patch("register.probe.allocate_remote_port", return_value=65081), \
             mock.patch("register.probe.allocate_local_port", return_value=pinned_local_port), \
             mock.patch("register.probe.remote_hostname", return_value="compute-a"), \
             mock.patch("register.probe.remote_user", return_value="alice"), \
             mock.patch("register.probe.remote_user_exists", return_value=True), \
             mock.patch("register.probe.remote_path_writable", return_value=True), \
             mock.patch("register.probe.host_key_fingerprint", return_value="SHA256:abc"):
            result = probe_user(
                RegistrationRequest(mode="remote", user="alice", ssh={"default": {"host": "compute-a", "user": "alice"}}),
                token="tok-1",
            )
        self.assertEqual(result.entry.roles.daemon.daemon_port, 65081)
        self.assertEqual(result.entry.roles.daemon.expected_user, "alice")
        self.assertFalse(registry_path().exists())


class TestRuntimeFacadePurity(unittest.TestCase):
    def setUp(self) -> None:
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp(prefix="vb-")))

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
        registry_path().write_text(json.dumps({}), encoding="utf-8")
        self.assertIsNotNone(server.registry.by_token("tok-1"))

    def test_explicit_reload_refreshes_registry_snapshot(self) -> None:
        server = BusinessServer(self.wd)
        fresh_registry = load_registry(registry_path())
        fresh_registry.register("bob", UserEntry(token="tok-bob", mode="local"))
        server.reload_registry()
        self.assertIsNotNone(server.registry.by_token("tok-bob"))
        server.close()


if __name__ == "__main__":
    unittest.main()
