"""Skill 投递闸门：排队、串行；对外超时统一为结果未知（spec v17）。
六步流程（test/docs/写TB规范.md §1）——离线用例：
① 环境检查**不适用**：纯函数 / 假 middle，不连真机；②③ 前置构建/校验**不适用**：无持久对象；
④⑤ = Arrange→Act→Assert；⑥ 无现场可留（不落盘、不起服务、不占端口）。
"""

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pyapi.models import ExecutionStatus, VirtuosoResult
from common.skill_client import SkillClient
from transport.middle import BusinessServer
from common.registry import UserEntry, load_registry
from common.paths import registry_path, init_work_dir


class RecordingSkillClient:
    """记录每次投递，并可让第一次调用阻塞以占住投递闸门。"""

    def __init__(self, delay=0.0, result=None, delivery="completed",
                 probe_results=None):
        self.delay = delay
        self.result = result
        self.delivery = delivery
        self.probe_results = list(probe_results or [])
        self.calls = []
        self.probe_calls = []
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def probe(self, timeout=None):
        self.probe_calls.append(timeout)
        if self.probe_results:
            return self.probe_results.pop(0)
        return "unknown"

    def execute_skill_checked(
        self,
        code,
        timeout=None,
        *,
        log_level=None,
        log_max_bytes=None,
    ):
        with self.lock:
            self.calls.append((code, timeout))
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                time.sleep(self.delay)
            if self.result is not None:
                return self.result, self.delivery
            return (
                VirtuosoResult(status=ExecutionStatus.SUCCESS, output=code),
                self.delivery,
            )
        finally:
            with self.lock:
                self.active -= 1

    def execute_skill(self, *args, **kwargs):
        return self.execute_skill_checked(*args, **kwargs)[0]


class SkillAdmissionBase(unittest.TestCase):
    pool_size = 32

    def setUp(self):
        wd = Path(tempfile.mkdtemp(prefix="vb-"))
        self.registry = load_registry(registry_path())
        entry = UserEntry(token="tok-skill", mode="local")
        entry.runtime.thread_pool_size = type(self).pool_size
        self.registry.register("alice", entry)
        self.server = BusinessServer()
        self.addCleanup(self.server.close)

    def use_client(self, client):
        with mock.patch.object(BusinessServer, "_skill", lambda self, token: client):
            yield


class TestWithdrawnWhileQueued(SkillAdmissionBase):
    def test_second_request_times_out_without_being_delivered(self):
        client = RecordingSkillClient(delay=0.6)
        started = threading.Event()

        with mock.patch.object(BusinessServer, "_skill", lambda self, token: client):
            first = threading.Thread(
                target=lambda: (started.set(), self.server.execute_skill("1+1", timeout=3, token="tok-skill"))
            )
            first.start()
            started.wait(1)
            time.sleep(0.1)          # 让第一个请求真正占住闸门

            t0 = time.monotonic()
            second = self.server.execute_skill("2+2", timeout=0.15, token="tok-skill")
            elapsed = time.monotonic() - t0
            first.join(timeout=5)

        self.assertEqual(second.status, ExecutionStatus.ERROR)
        self.assertEqual(second.errors, ["SKILL execution timed out"])
        self.assertNotIn("metadata", second.model_dump())
        self.assertLess(elapsed, 1.0, "超时应发生在队列等待阶段")
        self.assertEqual(len(client.calls), 1, "被撤回的请求绝不能投递")
        self.assertEqual(client.calls[0][0], "1+1")

    def test_delivery_is_serial(self):
        client = RecordingSkillClient(delay=0.2)
        with mock.patch.object(BusinessServer, "_skill", lambda self, token: client):
            threads = [
                threading.Thread(
                    target=lambda i=i: self.server.execute_skill(f"{i}+{i}", timeout=3, token="tok-skill")
                )
                for i in range(3)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)
        self.assertEqual(client.max_active, 1, "同一 token 的 skill 投递必须串行")
        self.assertEqual(len(client.calls), 3)


class TestDeliveredTimeout(SkillAdmissionBase):
    def test_delivered_timeout_is_not_observably_distinguished(self):
        timed_out = VirtuosoResult(
            status=ExecutionStatus.ERROR, errors=["SKILL execution timed out"]
        )
        client = RecordingSkillClient(result=timed_out)
        with mock.patch.object(BusinessServer, "_skill", lambda self, token: client):
            res = self.server.execute_skill("1+1", timeout=1, token="tok-skill")
        self.assertEqual(res.errors, ["SKILL execution timed out"])
        self.assertNotIn("metadata", res.model_dump())
        self.assertEqual(res.warnings, [])

    def test_gate_is_released_after_completion(self):
        client = RecordingSkillClient(delay=0.1)
        with mock.patch.object(BusinessServer, "_skill", lambda self, token: client):
            r1 = self.server.execute_skill("1+1", timeout=2, token="tok-skill")
            r2 = self.server.execute_skill("2+2", timeout=2, token="tok-skill")
        self.assertTrue(r1.ok and r2.ok)


class TestThreadPoolUnchanged(SkillAdmissionBase):
    pool_size = 1

    def test_pool_exhaustion_still_rejects(self):
        client = RecordingSkillClient(delay=0.4)
        with mock.patch.object(BusinessServer, "_skill", lambda self, token: client):
            t = threading.Thread(
                target=lambda: self.server.execute_skill("1+1", timeout=3, token="tok-skill")
            )
            t.start()
            time.sleep(0.1)
            rejected = self.server.execute_skill("2+2", timeout=3, token="tok-skill")
            t.join(timeout=5)
        self.assertEqual(rejected.errors, ["thread pool exceeded"])
        self.assertEqual(len(client.calls), 1)


class TestDirtyGate(SkillAdmissionBase):
    def test_delivered_timeout_marks_dirty_and_next_request_probes(self):
        timed_out = VirtuosoResult(
            status=ExecutionStatus.ERROR, errors=["SKILL execution timed out"]
        )
        client = RecordingSkillClient(
            result=timed_out, delivery="delivered_unknown",
        )
        with mock.patch.object(BusinessServer, "_skill", lambda self, token: client):
            self.server.execute_skill("1+1", timeout=1, token="tok-skill")
            self.assertIn("tok-skill", self.server._skill_dirty)

            client.calls.clear()
            client.result = VirtuosoResult(
                status=ExecutionStatus.SUCCESS, output="4",
            )
            client.delivery = "completed"
            client.probe_results = ["busy", "idle"]
            with mock.patch("transport.middle.time.sleep"):
                result = self.server.execute_skill(
                    "2+2", timeout=2, token="tok-skill",
                )
        self.assertTrue(result.ok)
        self.assertEqual(client.probe_calls[:2], [1.0, 1.0])
        self.assertEqual(client.calls, [("2+2", mock.ANY)])
        self.assertNotIn("tok-skill", self.server._skill_dirty)

    def test_dirty_probe_timeout_does_not_deliver_business_request(self):
        self.server._skill_dirty.add("tok-skill")
        client = RecordingSkillClient(probe_results=["busy"] * 100)
        with mock.patch.object(BusinessServer, "_skill", lambda self, token: client), \
             mock.patch("transport.middle.time.sleep"):
            result = self.server.execute_skill(
                "2+2", timeout=0.05, token="tok-skill",
            )
        self.assertFalse(result.ok)
        self.assertEqual(client.calls, [])
        self.assertIn("tok-skill", self.server._skill_dirty)

    def test_pre_delivery_failure_keeps_dirty_false(self):
        client = RecordingSkillClient(
            result=VirtuosoResult(
                status=ExecutionStatus.ERROR,
                errors=["Daemon connection failed (refused/reset)"],
            ),
            delivery="not_delivered",
        )
        with mock.patch.object(BusinessServer, "_skill", lambda self, token: client):
            self.server.execute_skill("1+1", timeout=1, token="tok-skill")
        self.assertNotIn("tok-skill", self.server._skill_dirty)

    def test_reload_registry_preserves_dirty(self):
        self.server._skill_dirty.add("tok-skill")
        self.server.reload_registry()
        self.assertIn("tok-skill", self.server._skill_dirty)


class TestSkillClientOutcome(unittest.TestCase):
    STX = "\x02"
    NAK = "\x15"
    RS = "\x1e"

    def setUp(self):
        self.client = SkillClient(token="tok-skill")

    def _response(self, mark, body):
        import json
        return mark + json.dumps(body) + self.RS

    def test_completed_response_is_clean(self):
        with mock.patch.object(
            self.client, "_round_trip",
            return_value=self._response(self.STX, {"value": "2", "log": ""}),
        ):
            result, delivery = self.client.execute_skill_checked("1+1")
        self.assertTrue(result.ok)
        self.assertEqual(delivery, "completed")

    def test_empty_response_is_delivered_unknown(self):
        with mock.patch.object(self.client, "_round_trip", return_value=""):
            _result, delivery = self.client.execute_skill_checked("1+1")
        self.assertEqual(delivery, "delivered_unknown")

    def test_busy_response_is_not_delivered(self):
        """P-126：busy = daemon 明确未执行，可安全重试，不是结果未知。"""
        with mock.patch.object(
            self.client, "_round_trip",
            return_value=self._response(
                self.NAK,
                {"status": "busy", "code": "skill_busy", "error": "busy", "log": ""},
            ),
        ):
            _result, delivery = self.client.execute_skill_checked("1+1")
        self.assertEqual(delivery, "not_delivered")

    def test_timeout_status_is_delivered_unknown(self):
        with mock.patch.object(
            self.client, "_round_trip",
            return_value=self._response(
                self.NAK,
                {"status": "timeout", "code": "skill_timeout",
                 "error": "SKILL execution timed out", "log": ""},
            ),
        ):
            _result, delivery = self.client.execute_skill_checked("1+1")
        self.assertEqual(delivery, "delivered_unknown")

    def test_connect_refusal_is_not_delivered(self):
        with mock.patch.object(
            self.client, "_round_trip",
            side_effect=ConnectionRefusedError("refused"),
        ), mock.patch("common.skill_client.time.sleep"):
            _result, delivery = self.client.execute_skill_checked("1+1")
        self.assertEqual(delivery, "not_delivered")

    def test_probe_classification(self):
        cases = (
            (self._response(self.STX, {"status": "idle", "log": ""}), "idle"),
            (self._response(self.NAK, {"status": "busy", "log": ""}), "busy"),
            ("", "unknown"),
        )
        for raw, expected in cases:
            with self.subTest(expected=expected), mock.patch.object(
                self.client, "_round_trip", return_value=raw,
            ):
                self.assertEqual(self.client.probe(timeout=0.1), expected)


if __name__ == "__main__":
    unittest.main()
