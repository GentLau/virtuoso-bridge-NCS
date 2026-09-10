"""Registry persistence / integrity edge cases."""

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pydantic import ValidationError
from transport.registry import Registry, UserEntry, load_registry
from transport.runtime_paths import registry_path, set_working_dir


class TestRegistryMore(unittest.TestCase):
    def setUp(self):
        self.wd = set_working_dir(Path(tempfile.mkdtemp()))

    def test_register_auto_timestamps_and_persists(self):
        reg = load_registry(registry_path())
        entry = UserEntry(token="tok-1", mode="remote")
        reg.register("alice", entry)
        self.assertIsNotNone(entry.registered_at)
        self.assertFalse(registry_path().with_suffix(".json.tmp").exists())
        reg2 = load_registry(registry_path())
        self.assertEqual(reg2.get("alice").registered_at, entry.registered_at)

    def test_overwrite_refreshes_timestamp(self):
        reg = load_registry(registry_path())
        first = UserEntry(token="tok-1", mode="remote")
        reg.register("alice", first)
        first_at = first.registered_at
        time.sleep(1.01)
        second = UserEntry(token="tok-2", mode="remote")
        reg.register("alice", second, overwrite=True)
        self.assertGreaterEqual(second.registered_at, first_at + 1)

    def test_remove_persists(self):
        reg = load_registry(registry_path())
        reg.register("alice", UserEntry(token="tok-1", mode="remote"))
        reg.remove("alice")
        self.assertIsNone(reg.get("alice"))
        reg2 = load_registry(registry_path())
        self.assertIsNone(reg2.get("alice"))

    def test_entries_snapshot_and_token_index(self):
        reg = load_registry(registry_path())
        a = UserEntry(token="ta", mode="remote")
        b = UserEntry(token="tb", mode="remote")
        reg.register("alice", a)
        reg.register("bob", b)
        self.assertEqual(sorted(name for name, _ in reg.entries()), ["alice", "bob"])
        self.assertIs(reg.by_token("ta"), a)
        self.assertIs(reg.by_token("tb"), b)

    def test_malformed_json_raises(self):
        registry_path().write_text("{not json", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            load_registry(registry_path())

    def test_entry_without_mode_rejected_on_load(self):
        registry_path().write_text(json.dumps({"users": {"alice": {"token": "t"}}}), encoding="utf-8")
        with self.assertRaises(ValidationError):
            load_registry(registry_path())


    def test_register_persist_failure_rolls_back_memory(self):
        reg = load_registry(registry_path())
        from unittest import mock
        with mock.patch.object(reg, "_save_payload_locked", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                reg.register("alice", UserEntry(token="tok-1", mode="remote"))
        self.assertIsNone(reg.get("alice"))
        self.assertIsNone(reg.by_token("tok-1"))

    def test_remove_persist_failure_keeps_entry(self):
        reg = load_registry(registry_path())
        reg.register("alice", UserEntry(token="tok-1", mode="remote"))
        from unittest import mock
        with mock.patch.object(reg, "_save_payload_locked", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                reg.remove("alice")
        self.assertIsNotNone(reg.get("alice"))

    def test_mode_validation(self):
        with self.assertRaises(ValidationError):
            UserEntry(token="t", mode="banana")

    def test_port_validation(self):
        with self.assertRaises(ValidationError):
            UserEntry(token="t", mode="remote", route={"skill": {"daemon_port": 0}})
        with self.assertRaises(ValidationError):
            UserEntry(token="t", mode="remote", route={"skill": {"local_port": 70000}})

    def test_empty_token_rejected(self):
        with self.assertRaises(ValidationError):
            UserEntry(token="", mode="remote")

    def test_model_dump_has_no_runtime_state(self):
        entry = UserEntry(token="t", mode="remote")
        keys = set(entry.model_dump().keys())
        self.assertEqual(keys, {"token", "mode", "route", "expected", "deploy", "ssh", "runtime", "cdslog", "registered_at"})


if __name__ == "__main__":
    unittest.main()
