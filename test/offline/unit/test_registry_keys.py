"""Registry 凭据字段（spec r18–r22）：role.key_dir/key + ssh.default.key_dir/key。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from common.registry import RoleConfig, SshDefaults, UserEntry, load_registry
from common.paths import registry_path, override_work_dir_for_tests


class TestRegistryCredentialFields(unittest.TestCase):
    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp(prefix="vb-")))
        self.registry = load_registry(registry_path())

    def _entry(self) -> UserEntry:
        entry = UserEntry(token="tok-key", mode="remote")
        entry.ssh.default.host = "server-a"
        entry.ssh.default.user = "alice"
        entry.ssh.default.key_dir = "/home/alice/.ssh"
        entry.ssh.default.key = "id_ed25519"
        entry.roles.command.key_dir = "/keys/command"
        entry.roles.command.key = "id_rsa"
        return entry

    def test_round_trip_through_registry_json(self):
        self.registry.register("alice", self._entry())
        reloaded = load_registry(registry_path()).load().get("alice")
        self.assertEqual(reloaded.ssh.default.key_dir, "/home/alice/.ssh")
        self.assertEqual(reloaded.ssh.default.key, "id_ed25519")
        self.assertEqual(reloaded.roles.command.key_dir, "/keys/command")
        self.assertEqual(reloaded.roles.command.key, "id_rsa")

    def test_key_must_be_a_plain_file_name(self):
        for bad in ("a/b", "a\\b", "..", "."):
            with self.subTest(bad=bad):
                with self.assertRaises(ValidationError):
                    RoleConfig(key=bad)
                with self.assertRaises(ValidationError):
                    SshDefaults(key=bad)

    def test_local_role_rejects_credential_fields(self):
        with self.assertRaises(ValidationError):
            UserEntry(
                token="t", mode="local",
                roles={"gui": {"key_dir": "/x", "key": "id_rsa"}},
            )

    def test_update_replaces_role_credential(self):
        self.registry.register("alice", self._entry())
        updated = self.registry.update(
            "alice", {"roles": {"command": {"key_dir": "/new", "key": "id_ecdsa"}}}
        )
        self.assertEqual(updated.roles.command.key_dir, "/new")
        self.assertEqual(updated.roles.command.key, "id_ecdsa")
        # 未涉及的角色字段保持原样
        self.assertEqual(updated.ssh.default.key, "id_ed25519")


if __name__ == "__main__":
    unittest.main()
