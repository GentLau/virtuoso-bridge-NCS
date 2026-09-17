"""Reservation table + step-budget contracts (配置一览 §6.4, 架构 §5.8)."""

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from register.flow import (
    RegistrationFlow,
    RegistrationProbeError,
    StepBudget,
    daemon_scope_of_request,
    validate_final,
    validate_local,
)
from register.models import RegistrationRequest
from register.reservation import Reservation, ReservationTable
from common.registry import UserEntry, load_registry
from common.paths import registry_path, override_work_dir_for_tests


def _table():
    return ReservationTable(Path(tempfile.mkdtemp()) / "registry.reservation")


def _record(user="alice", token="tok-a", scope="server-a", daemon_port=65081, local_port=65082):
    return Reservation.create(
        user=user, token=token, daemon_scope=scope,
        daemon_port=daemon_port, local_port=local_port,
    )


class TestReservationTable(unittest.TestCase):
    def test_reserve_and_release_round_trip(self):
        table = _table()
        self.assertEqual(table.reserve(_record()), [])
        self.assertEqual([r.user for r in table.records()], ["alice"])
        self.assertTrue(table.release("alice"))
        self.assertEqual(table.records(), [])

    def test_daemon_port_conflict_is_scoped_to_daemon_host(self):
        table = _table()
        self.assertEqual(table.reserve(_record(user="alice", token="t1", scope="server-a")), [])
        same_host = table.reserve(_record(user="bob", token="t2", scope="server-a", local_port=65083))
        self.assertTrue(any("daemon port 65081" in c for c in same_host))
        other_host = table.reserve(_record(user="carol", token="t3", scope="server-b", local_port=65084))
        self.assertEqual(other_host, [])
        self.assertEqual(sorted(r.user for r in table.records()), ["alice", "carol"])

    def test_local_port_is_machine_wide(self):
        table = _table()
        table.reserve(_record(user="alice", token="t1"))
        conflicts = table.reserve(_record(user="bob", token="t2", scope="server-b", local_port=65082))
        self.assertTrue(any("local port 65082" in c for c in conflicts))

    def test_token_and_user_conflicts(self):
        table = _table()
        table.reserve(_record(user="alice", token="t1"))
        self.assertTrue(any("token" in c for c in table.reserve(_record(user="bob", token="t1", scope="x"))))
        table.reserve(_record(user="carol", token="t9", scope="x", daemon_port=65100, local_port=65101))
        self.assertTrue(any("user" in c for c in table.reserve(_record(user="alice", token="t8", scope="y", daemon_port=65102, local_port=65103))))

    def test_update_replaces_own_record_with_final_ports(self):
        table = _table()
        table.reserve(_record())
        updated = _record(local_port=65100)
        self.assertEqual(table.update(updated), [])
        self.assertEqual([r.local_port for r in table.records()], [65100])

    def test_reservation_is_memory_only(self):
        table = _table()
        self.assertEqual(table.reserve(_record()), [])
        self.assertFalse(table.path.exists())
        self.assertEqual([r.user for r in table.records()], ["alice"])


class TestStepBudget(unittest.TestCase):
    def test_remaining_is_clamped_and_expiry_raises(self):
        budget = StepBudget("test", seconds=0.2)
        self.assertLessEqual(budget.remaining(10), 0.2)
        time.sleep(0.25)
        self.assertTrue(budget.expired())
        with self.assertRaises(RegistrationProbeError):
            budget.remaining()


class TestDaemonScope(unittest.TestCase):
    def test_request_scope_uses_host_or_local(self):
        remote = RegistrationRequest(
            mode="remote", user="alice", token="t1",
            ssh={"default": {"host": " Server-A. ", "user": "alice"}},
        )
        self.assertEqual(daemon_scope_of_request(remote), "server-a")
        local = RegistrationRequest(mode="local", user="bob", token="t2")
        self.assertEqual(daemon_scope_of_request(local), "local")


class TestFlowReservationLifecycle(unittest.TestCase):
    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))
        self.registry = load_registry(registry_path())
        self.table = ReservationTable(self.wd / "registry.reservation")
        self.flow = RegistrationFlow(self.registry, self.table)

    def _request(self, user="alice", token="t1", port=65081):
        return RegistrationRequest(
            mode="remote", user=user, token=token,
            ssh={"default": {"host": "server-a", "user": "alice"}},
            roles={"daemon": {"daemon_port": port}},
        )

    def test_validation_reserves_and_cancel_releases(self):
        state = self.flow.start(self._request())
        state = self.flow.validate()
        self.assertEqual(state.stage, "validated")
        self.assertEqual([r.user for r in self.table.records()], ["alice"])
        self.flow.cancel()
        self.assertEqual(self.table.records(), [])

    def test_second_registration_sees_the_first_reservation(self):
        first = self.flow.start(self._request(user="alice", token="t1", port=65081))
        self.flow.validate()
        self.assertEqual(first.stage, "validated")

        second = RegistrationFlow(self.registry, self.table)
        state = second.start(self._request(user="bob", token="t2", port=65081))
        state = second.validate()
        self.assertEqual(state.stage, "failed")
        self.assertTrue(any("daemon port 65081" in e for e in state.errors))

    def test_failed_probe_releases_reservation(self):
        state = self.flow.start(self._request())
        self.flow.validate()
        with mock.patch("register.flow.probe_user",
                        side_effect=RegistrationProbeError("probe boom")):
            state = self.flow.probe()
        self.assertEqual(state.stage, "failed")
        self.assertEqual(self.table.records(), [])

    def test_commit_release_and_final_recheck(self):
        entry = UserEntry(token="t1", mode="remote")
        entry.roles.daemon.host = "server-a"
        entry.roles.daemon.daemon_port = 65081
        entry.roles.daemon.local_port = 65082
        self.assertEqual(validate_final(self.registry, entry, "alice"), [])
        self.registry.register("alice", entry)
        self.assertTrue(validate_final(self.registry, entry, "alice"))

    def test_validate_local_sees_registry_token_conflict(self):
        self.registry.register("carol", UserEntry(token="t1", mode="remote"))
        errors = validate_local(self.registry, self._request())
        self.assertTrue(any("already belongs" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
