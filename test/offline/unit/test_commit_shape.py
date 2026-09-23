"""Final registry-shape validation contracts (config v24)."""
import sys
import unittest
from pathlib import Path
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from common.registry import UserEntry
from register.candidate import validate_commit_shape


def local_entry():
    e = UserEntry(token="t", mode="local")
    for name in ("gui", "daemon", "command", "file", "spectre"):
        getattr(e.roles, name).root = f"/tmp/{name}"
    e.roles.daemon.daemon_port = 65081
    e.roles.daemon.local_port = 65081
    e.roles.daemon.python = "/usr/bin/python3"
    return e


def remote_entry():
    e = UserEntry(token="t", mode="remote")
    e.ssh.default.host = "server-a"; e.ssh.default.user = "u"
    e.roles.daemon.daemon_port = 65081; e.roles.daemon.local_port = 65082
    e.roles.daemon.python = "/usr/bin/python3"
    for name in ("gui", "daemon", "command", "file", "spectre"):
        r = getattr(e.roles, name); r.root = f"/home/u/.vb/t/{name}"; r.expected_fingerprint = "SHA256:x"
    return e


class TestCommitShape(unittest.TestCase):
    def test_local_valid(self):
        self.assertEqual(validate_commit_shape(local_entry(), "alice"), [])

    def test_remote_valid(self):
        self.assertEqual(validate_commit_shape(remote_entry(), "alice"), [])

    def test_root_default_must_be_null(self):
        e = local_entry(); e.root.default = "/tmp/base"
        self.assertTrue(any("root.default" in x for x in validate_commit_shape(e, "alice")))

    def test_relative_role_root_rejected(self):
        e = local_entry(); e.roles.file.root = "relative/path"
        self.assertTrue(any("absolute" in x for x in validate_commit_shape(e, "alice")))

    def test_daemon_ports_and_python_required(self):
        e = local_entry(); e.roles.daemon.daemon_port = None; e.roles.daemon.local_port = None; e.roles.daemon.python = None
        errors = validate_commit_shape(e, "alice")
        self.assertTrue(any("daemon_port" in x for x in errors))
        self.assertTrue(any("local_port" in x for x in errors))
        self.assertTrue(any("python" in x for x in errors))

    def test_local_daemon_ports_must_equal(self):
        e = local_entry(); e.roles.daemon.local_port = 65082
        self.assertTrue(any("local_port == daemon_port" in x for x in validate_commit_shape(e, "alice")))

    def test_remote_requires_fingerprint_except_spectre(self):
        e = remote_entry(); e.roles.command.expected_fingerprint = None; e.roles.spectre.expected_fingerprint = None; e.roles.spectre.root = None
        self.assertFalse(any("spectre" in x for x in validate_commit_shape(e, "alice")))
        self.assertTrue(any("command.expected_fingerprint" in x for x in validate_commit_shape(e, "alice")))

    def test_local_role_with_connection_field_is_model_error(self):
        with self.assertRaises(ValidationError):
            UserEntry(token="t", mode="local", roles={"gui": {"host": "x"}})


if __name__ == "__main__":
    unittest.main()
