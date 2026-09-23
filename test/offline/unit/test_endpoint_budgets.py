"""Endpoint-scoped max_sessions accounting (spec v24 / concurrency v17)."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from transport.budgets import TokenBudgets
from common.registry import UserEntry
from transport.roles import resolve
from transport.tunnel import RemoteClient


class FakeRunner:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        FakeRunner.instances.append(self)

    @property
    def is_tunnel_alive(self):
        return False

    def close(self):
        pass


class TestEndpointBudgets(unittest.TestCase):
    def test_same_endpoint_uses_min_max_sessions(self):
        budgets = TokenBudgets(thread_pool_size=32, channel_budget=10)
        key = "v1:shared"
        budgets.set_endpoint_limit(key, 8)
        budgets.set_endpoint_limit(key, 3)
        self.assertEqual(budgets.endpoint_limit(key), 3)
        leases = [budgets.try_acquire_channel(endpoint_key=key) for _ in range(3)]
        self.assertTrue(all(lease is not None for lease in leases))
        self.assertIsNone(budgets.try_acquire_channel(endpoint_key=key))
        self.assertEqual(budgets.denial_reason(key), "role max_sessions exceeded")
        for lease in leases:
            lease.release()

    def test_token_budget_is_across_endpoints(self):
        budgets = TokenBudgets(thread_pool_size=32, channel_budget=2)
        budgets.set_endpoint_limit("a", 10)
        budgets.set_endpoint_limit("b", 10)
        first = budgets.try_acquire_channel(endpoint_key="a")
        second = budgets.try_acquire_channel(endpoint_key="b")
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertIsNone(budgets.try_acquire_channel(endpoint_key="a"))
        self.assertEqual(budgets.denial_reason("a"), "channel budget exceeded")
        first.release()
        second.release()

    def test_thread_budget_and_idempotent_release(self):
        budgets = TokenBudgets(thread_pool_size=1, channel_budget=1)
        self.assertTrue(budgets.try_acquire_thread())
        self.assertFalse(budgets.try_acquire_thread())
        budgets.release_thread()
        self.assertEqual(budgets.threads_in_use, 0)
        with self.assertRaises(RuntimeError):
            budgets.release_thread()
        lease = budgets.try_acquire_channel(endpoint_key="e", role_max_sessions=2)
        self.assertEqual(budgets.channels_in_use_for("e"), 1)
        lease.release(); lease.release()
        self.assertEqual(budgets.channels_in_use_for("e"), 0)

    def test_release_without_lease_is_error(self):
        budgets = TokenBudgets(thread_pool_size=1, channel_budget=1)
        with self.assertRaises(RuntimeError):
            budgets._release_channel("missing")

    def test_remote_client_precomputes_endpoint_minimum(self):
        entry = UserEntry(token="tok", mode="remote")
        entry.ssh.default.host = "server-a"
        entry.ssh.default.user = "alice"
        entry.roles.daemon.daemon_port = 65081
        entry.roles.daemon.local_port = 65082
        entry.roles.gui.max_sessions = 8
        entry.roles.command.max_sessions = 3
        entry.roles.file.max_sessions = 6
        targets = resolve(entry, "alice")
        FakeRunner.instances.clear()
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, targets, "alice")
        self.assertEqual(client.budgets.endpoint_limit(targets.command.key), 3)
        client.close()


if __name__ == "__main__":
    unittest.main()
