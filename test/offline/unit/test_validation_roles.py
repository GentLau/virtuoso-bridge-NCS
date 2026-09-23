"""Input validation and role-resolution contracts."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from common.registry import UserEntry
from register.models import RegistrationRequest
from transport.roles import fingerprint_conflicts, resolve
from common.validation import validate_display, validate_token, validate_user_name


class TestValidation(unittest.TestCase):
    def test_user_names(self):
        self.assertEqual(validate_user_name("Alice-1.test"), "Alice-1.test")
        for bad in ("", "../x", "a/b", "a\\b", "a..b", "CON", "con.txt", "NUL", "name."):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    validate_user_name(bad)

    def test_tokens(self):
        self.assertEqual(validate_token("a.b-c_1"), "a.b-c_1")
        for bad in ("", "a b", "a/b", "x" * 65):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    validate_token(bad)

    def test_gui_displays(self):
        for good in (":11", "localhost:10.0", "unix/:0"):
            with self.subTest(good=good):
                self.assertEqual(validate_display(good), good)
        self.assertIsNone(validate_display(""))
        for bad in ("11", ":abc", " :11", ":11;x", "host:1 1", "$(x):1"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    validate_display(bad)


class TestRoleResolution(unittest.TestCase):
    def test_local_resolution_and_fingerprint_conflict(self):
        e = UserEntry(token="t", mode="remote")
        e.ssh.default.host = "server-a"; e.ssh.default.user = "u"
        e.roles.daemon.daemon_port = 65081; e.roles.daemon.local_port = 65082
        for name in ("gui", "daemon", "command", "file", "spectre"):
            r = getattr(e.roles, name); r.root = f"/home/u/{name}"; r.expected_fingerprint = "A"
        targets = resolve(e, "alice")
        self.assertEqual(targets.command.mode, "remote")
        self.assertEqual(targets.command.key, targets.file.key)
        self.assertEqual(fingerprint_conflicts(e, "alice"), [])
        e.roles.file.expected_fingerprint = "B"
        self.assertTrue(fingerprint_conflicts(e, "alice"))

    def test_local_role_resolution(self):
        e = UserEntry(token="t", mode="local")
        for name in ("gui", "daemon", "command", "file", "spectre"):
            getattr(e.roles, name).root = f"/tmp/{name}"
        e.roles.daemon.daemon_port = 65081; e.roles.daemon.local_port = 65081
        t = resolve(e, "alice")
        self.assertIsNone(t.command.key)
        self.assertEqual(t.daemon_port, 65081)

    def test_gui_role_display_is_validated(self):
        e = UserEntry(
            token="t", mode="remote",
            roles={"gui": {"display": "localhost:10.0"}},
        )
        self.assertEqual(e.roles.gui.display, "localhost:10.0")
        with self.assertRaises(ValueError):
            e.roles.gui.display = "bad display"

    def test_role_user_groups_are_structural_only(self):
        entry = UserEntry(
            token="t",
            mode="remote",
            roles={
                "command": {
                    "root": "/home/alice/command",
                    "calibre": {
                        "bin": "/opt/eda/mentor/calibre/bin/calibre",
                        "version": "2024.4",
                    },
                }
            },
        )
        self.assertEqual(
            entry.roles.command.calibre["version"],
            "2024.4",
        )
        self.assertEqual(
            entry.model_dump()["roles"]["command"]["calibre"]["bin"],
            "/opt/eda/mentor/calibre/bin/calibre",
        )

        request = RegistrationRequest(
            user="alice",
            mode="local",
            roles={"command": {"calibre": {"bin": "/opt/calibre"}}},
        )
        self.assertEqual(
            request.roles.command.calibre["bin"],
            "/opt/calibre",
        )

    def test_role_user_groups_reject_bad_shapes(self):
        bad_groups = (
            {"Bad": {"x": 1}},
            {"calibre": "not-an-object"},
            {"calibre": {"bin": ["not", "scalar"]}},
            {"calibre": {"bin": "nul\x00byte"}},
            {"mode": {"x": 1}},
            {"daemon_port": {"x": 1}},
        )
        for group in bad_groups:
            with self.subTest(group=group):
                with self.assertRaises(ValueError):
                    UserEntry(
                        token="t",
                        mode="remote",
                        roles={"command": group},
                    )

    def test_empty_role_user_group_is_omitted(self):
        entry = UserEntry(
            token="t",
            mode="remote",
            roles={"command": {"calibre": ""}},
        )
        self.assertNotIn("calibre", entry.roles.command.model_dump())


if __name__ == "__main__":
    unittest.main()
