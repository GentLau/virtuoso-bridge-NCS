"""Unit contracts for the frozen spec additions (file-root, connect budget)."""

import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from transport.remote_roles import resolve
from transport.registry import UserEntry
from transport.connlimit import connect_slot


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


class TestConnectBudget(unittest.TestCase):
    def test_endpoint_budget_queues_same_endpoint(self):
        order = []
        def hold(key):
            with connect_slot(key, budget=1):
                order.append(key)
                time.sleep(0.15)
        threads = [threading.Thread(target=hold, args=("e1",)) for _ in range(2)]
        t0 = time.time()
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        # budget=1 serializes both handshakes on the same endpoint
        self.assertGreaterEqual(time.time() - t0, 0.3)

    def test_different_endpoints_do_not_queue(self):
        done = []
        def hold(key):
            with connect_slot(key, budget=16):
                time.sleep(0.15)
                done.append(key)
        threads = [threading.Thread(target=hold, args=(f"e{i}",)) for i in range(8)]
        t0 = time.time()
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        self.assertLess(time.time() - t0, 0.35)

    def test_deadline_exhaustion_raises(self):
        # occupy the only permit, then request with an expired deadline
        released = threading.Event()
        def hold():
            with connect_slot("deadline-key", budget=1):
                released.set()
                time.sleep(0.5)
        t = threading.Thread(target=hold)
        t.start()
        released.wait(1)
        with self.assertRaises(TimeoutError):
            with connect_slot("deadline-key", budget=1, deadline=time.monotonic() + 0.05):
                pass
        t.join()


if __name__ == "__main__":
    unittest.main()
