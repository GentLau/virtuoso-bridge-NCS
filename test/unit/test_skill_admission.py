"""Skill 投递闸门：排队、串行；对外超时统一为结果未知（spec v17）。"""

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pyapi.models import ExecutionStatus, VirtuosoResult
from transport.middle import BusinessServer
from transport.registry import UserEntry, load_registry
from transport.runtime_paths import registry_path, set_working_dir


class RecordingSkillClient:
    """记录每次投递，并可让第一次调用阻塞以占住投递闸门。"""

    def __init__(self, delay=0.0, result=None):
        self.delay = delay
        self.result = result
        self.calls = []
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def execute_skill(self, code, timeout=None):
        with self.lock:
            self.calls.append((code, timeout))
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                time.sleep(self.delay)
            if self.result is not None:
                return self.result
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output=code)
        finally:
            with self.lock:
                self.active -= 1


class SkillAdmissionBase(unittest.TestCase):
    pool_size = 32

    def setUp(self):
        wd = Path(tempfile.mkdtemp())
        set_working_dir(wd)
        self.registry = load_registry(registry_path())
        entry = UserEntry(token="tok-skill", mode="local")
        entry.runtime.thread_pool_size = type(self).pool_size
        self.registry.register("alice", entry)
        self.server = BusinessServer(wd)
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
        self.assertEqual(second.metadata, {})
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
        self.assertEqual(res.metadata, {})
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


if __name__ == "__main__":
    unittest.main()
