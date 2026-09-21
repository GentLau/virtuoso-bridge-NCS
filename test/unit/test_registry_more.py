"""Registry persistence / integrity edge cases."""

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pydantic import ValidationError
from common.registry import Registry, RegistryError, UserEntry, load_registry
from common.paths import registry_path, override_work_dir_for_tests


class TestRegistryMore(unittest.TestCase):
    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))

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
        second = UserEntry(token="tok-1", mode="remote")  # token is immutable
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
        registry_path().write_text(json.dumps({"alice": {"token": "t"}}), encoding="utf-8")
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
            UserEntry(token="t", mode="remote", roles={"daemon": {"daemon_port": 0}})
        with self.assertRaises(ValidationError):
            UserEntry(token="t", mode="remote", roles={"daemon": {"local_port": 70000}})

    def test_numeric_fields_are_strict_on_load(self):
        for patch in (
            {"roles": {"daemon": {"daemon_port": "65081"}}},
            {"roles": {"daemon": {"local_port": "65081"}}},
            {"roles": {"daemon": {"max_sessions": "10"}}},
            {"runtime": {"thread_pool_size": "32"}},
            {"runtime": {"channel_budget": "10"}},
            {"runtime": {"connect_timeout": "15"}},
            {"cdslog": {"log_max_bytes": "65536"}},
        ):
            with self.subTest(patch=patch):
                with self.assertRaises(ValidationError):
                    UserEntry.model_validate(
                        {"token": "t", "mode": "remote", **patch}
                    )

    def test_connect_timeout_rejects_non_finite(self):
        for value in (float("inf"), float("-inf"), float("nan")):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    UserEntry(
                        token="t", mode="remote",
                        runtime={"connect_timeout": value},
                    )

    def test_empty_token_rejected(self):
        with self.assertRaises(ValidationError):
            UserEntry(token="", mode="remote")

    def test_model_dump_has_no_runtime_state(self):
        entry = UserEntry(token="t", mode="remote")
        keys = set(entry.model_dump().keys())
        self.assertEqual(keys, {"token", "mode", "ssh", "root", "roles", "runtime", "cdslog", "registered_at"})


class TestRegistryUpdate(unittest.TestCase):
    """Registry.update：锁内读改写、深合并、整体校验、token 不可变。"""

    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))
        self.reg = load_registry(registry_path())

    def _register(self, user="alice", token="tok-u"):
        entry = UserEntry(token=token, mode="remote")
        entry.runtime.thread_pool_size = 8
        entry.cdslog.log_level = "all"
        self.reg.register(user, entry)
        return entry

    def test_patch_merges_and_preserves_untouched_fields(self):
        self._register()
        updated = self.reg.update("alice", {"cdslog": {"log_level": "error"}})
        self.assertEqual(updated.cdslog.log_level, "error")
        self.assertEqual(updated.runtime.thread_pool_size, 8)
        self.assertEqual(updated.token, "tok-u")
        # 重新从磁盘加载，确认写回生效
        reloaded = load_registry(registry_path())
        self.assertEqual(reloaded.get("alice").cdslog.log_level, "error")

    def test_unknown_user_raises_keyerror(self):
        with self.assertRaises(KeyError):
            self.reg.update("ghost", {"cdslog": {"log_level": "error"}})

    def test_validator_rejection_keeps_previous_entry(self):
        self._register()
        before = self.reg.get("alice").model_dump()
        with self.assertRaises(RegistryError):
            self.reg.update(
                "alice",
                {"cdslog": {"log_level": "error"}},
                validator=lambda entry: ["rejected by validator"],
            )
        self.assertEqual(self.reg.get("alice").model_dump(), before)

    def test_token_cannot_change_via_patch(self):
        self._register()
        with self.assertRaises(RegistryError):
            self.reg.update("alice", {"token": "tok-rotated"})
        self.assertEqual(self.reg.get("alice").token, "tok-u")

    def test_numeric_patch_is_rejected_strictly(self):
        self._register()
        for patch in (
            {"roles": {"daemon": {"local_port": "65081"}}},
            {"runtime": {"thread_pool_size": "64"}},
            {"runtime": {"connect_timeout": "15"}},
            {"cdslog": {"log_max_bytes": "65536"}},
        ):
            with self.subTest(patch=patch):
                with self.assertRaises(ValidationError):
                    self.reg.update("alice", patch)
        self.assertEqual(self.reg.get("alice").runtime.thread_pool_size, 8)


class TestCrossProcessLock(unittest.TestCase):
    """§5: registry 写采用 OS 文件锁；锁被别的进程持有时必须超时报错。"""

    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))

    def test_file_lock_times_out_when_held_by_another_process(self):
        from common import registry as registry_mod

        src = str(Path(__file__).resolve().parents[2] / "src")
        lock_target = registry_path()
        script = (
            "import sys, time\n"
            f"sys.path.insert(0, {src!r})\n"
            "from pathlib import Path\n"
            "from common.registry import file_lock\n"
            f"with file_lock(Path({str(lock_target)!r}), timeout=30):\n"
            "    print('locked', flush=True)\n"
            "    time.sleep(5)\n"
        )
        proc = subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            self.assertEqual(proc.stdout.readline().strip(), "locked")
            with self.assertRaises(OSError):
                with registry_mod.file_lock(lock_target, timeout=0.3):
                    pass
        finally:
            proc.kill()
            proc.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
