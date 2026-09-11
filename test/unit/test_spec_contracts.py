"""Unit contracts for the frozen spec additions (file-root, connect budget)."""

import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from transport.remote_roles import resolve
from transport.registry import UserEntry


class TestFileRootFallback(unittest.TestCase):
    def test_root_defaults_to_username_not_token(self):
        entry = UserEntry(token="tok-123", mode="remote")
        entry.deploy.scratch_root = "~/.virtuoso-bridge"
        entry.route.skill.daemon_host = "server"
        entry.route.skill.daemon_port = 65081
        targets = resolve(entry, user="alice")
        self.assertEqual(targets.file_root, "~/.virtuoso-bridge/alice")

    def test_explicit_root_wins(self):
        entry = UserEntry(token="tok-123", mode="remote")
        entry.route.file.root = "/explicit/root"
        targets = resolve(entry, user="alice")
        self.assertEqual(targets.file_root, "/explicit/root")


if __name__ == "__main__":
    unittest.main()
