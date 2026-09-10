import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from transport.legacy_env import import_user, load_legacy_env
from transport.legacy_profile import resolve_legacy_profile
from transport.registry import load_registry
from transport.runtime_paths import registry_path, set_working_dir


class TestLegacyAdapters(unittest.TestCase):
    def test_import_user(self):
        wd = set_working_dir(Path(tempfile.mkdtemp()))
        env_file = Path(wd) / "legacy.env"
        env_file.write_text(
            "VB_REMOTE_HOST=server-a\nVB_REMOTE_USER=alice\nVB_REMOTE_PORT=65081\nVB_LOCAL_PORT=65082\n",
            encoding="utf-8",
        )
        reg = load_registry(registry_path())
        entry = import_user(reg, user="alice", token="tok-1", env_path=env_file)
        self.assertEqual(entry.mode, "remote")
        self.assertEqual(entry.route.skill.daemon_host, "server-a")
        self.assertEqual(entry.route.skill.daemon_port, 65081)
        self.assertEqual(entry.route.skill.local_port, 65082)
        self.assertEqual(entry.expected.daemon_user, "alice")
        self.assertIsNotNone(reg.get("alice"))

    def test_profile_resolve(self):
        self.assertIsNone(resolve_legacy_profile(None))


if __name__ == "__main__":
    unittest.main()
