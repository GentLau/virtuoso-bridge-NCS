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
    def test_file_root_is_the_single_bridge_workdir(self):
        entry = UserEntry(token="tok-123", mode="remote")
        entry.roles.daemon.root = "~/.virtuoso-bridge/alice"
        entry.roles.daemon.host = "server"
        entry.roles.daemon.daemon_port = 65081
        targets = resolve(entry, user="alice")
        self.assertEqual(targets.daemon.root, "~/.virtuoso-bridge/alice")


if __name__ == "__main__":
    unittest.main()
