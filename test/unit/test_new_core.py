import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from bridge.resources.ramic_bridge_daemon_3 import (
    _parse_meta,
    classify_level,
    filter_delta,
)
from pyapi.models import ExecutionStatus
from common.registry import UserEntry, load_registry
from common.paths import (
    artifact_dir,
    log_dir,
    registry_path,
    override_work_dir_for_tests,
    temp_dir,
)
from common.skill_client import SkillClient


class TestFoundations(unittest.TestCase):
    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))

    def test_working_dir_subdirs(self):
        self.assertEqual(temp_dir().name, "temp")
        self.assertEqual(log_dir().name, "log")
        self.assertEqual(artifact_dir().name, "artifact")
        self.assertEqual(registry_path().name, "registry.json")

    def test_registry_load_once_register(self):
        reg = load_registry(registry_path())
        entry = UserEntry(token="tok-1", mode="remote")
        entry.roles.daemon.host = "compute-a"
        entry.roles.daemon.daemon_port = 65081
        reg.register("alice", entry)
        self.assertIs(reg.by_token("tok-1"), entry)
        self.assertEqual(reg.get("alice").roles.daemon.daemon_port, 65081)

    def test_skill_client_parse(self):
        ok = SkillClient._parse_response("\x02" + json.dumps({"value": "3", "log": r"\e *Error*"}) + "\x1e", 0.1)
        self.assertTrue(ok.ok)
        self.assertEqual(ok.output, "3")
        self.assertEqual(ok.log, r"\e *Error*")

        err = SkillClient._parse_response("\x15" + json.dumps({"error": "boom", "log": ""}) + "\x1e", 0.1)
        self.assertEqual(err.status, ExecutionStatus.ERROR)
        self.assertEqual(err.errors, ["boom"])

        # old plain-text payloads are no longer accepted: strict protocol only
        legacy = SkillClient._parse_response("\x02legacy-value\x1e", 0.1)
        self.assertEqual(legacy.status, ExecutionStatus.ERROR)

    def test_daemon_cdslog_filter(self):
        raw = "\\o output\n\\w warn\n\\e error line\n"
        self.assertEqual(classify_level("\\e x"), "error")
        text, trunc = filter_delta(raw, "error", 100)
        self.assertIn("error line", text)
        self.assertNotIn("warn", text)
        self.assertFalse(trunc)

        text2, trunc2 = filter_delta(raw, "all", 5)
        self.assertTrue(trunc2)
        self.assertIn("[log auto-degraded", text2)
        self.assertIn("[log truncated", text2)

        self.assertEqual(_parse_meta(b"/tmp/CDS.log\x1f10\x1f42"), ("/tmp/CDS.log", 10, 42))


class TestSkillClientMore(unittest.TestCase):
    def test_remaining_timeout_raises(self):
        import socket as sock
        import time as _time
        with self.assertRaises(sock.timeout):
            from common.skill_client import _remaining_timeout
            _remaining_timeout(_time.monotonic() - 1)

    def test_execute_skill_immediate_timeout(self):
        client = SkillClient(timeout=0)
        r = client.execute_skill("1+1")
        self.assertEqual(r.status, ExecutionStatus.ERROR)
        self.assertIn("timed out", r.errors[0])

    def test_execute_skill_oserror(self):
        import socket as sock
        from unittest import mock
        client = SkillClient(timeout=5)
        with mock.patch.object(client, "_execute_once", side_effect=OSError("boom")):
            r = client.execute_skill("1+1")
        self.assertEqual(r.status, ExecutionStatus.ERROR)
        self.assertIn("boom", r.errors[0])

    def test_execute_skill_socket_timeout(self):
        import socket as sock
        from unittest import mock
        client = SkillClient(timeout=5)
        with mock.patch.object(client, "_execute_once", side_effect=sock.timeout):
            r = client.execute_skill("1+1")
        self.assertEqual(r.status, ExecutionStatus.ERROR)
        self.assertIn("timed out", r.errors[0])


if __name__ == "__main__":
    unittest.main()
