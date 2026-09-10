# -*- coding: utf-8 -*-
"""完整业务 demo（full_demo.py）的验收单元。"""
from __future__ import annotations

import json
import shutil
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from spec.demo.full_demo import (
    MiddleLayer,
    RegistrationError,
)

PW = unittest.skipUnless(shutil.which("pwsh"), "pwsh required")


class FullDemoTests(unittest.TestCase):
    def make_middle(self, max_workers: int = 32) -> MiddleLayer:
        temporary = tempfile.TemporaryDirectory(prefix="vb-full-demo-test-")
        self.addCleanup(temporary.cleanup)
        middle = MiddleLayer(Path(temporary.name), max_workers=max_workers)
        self.addCleanup(middle.close)
        return middle

    def start_user(
        self,
        middle: MiddleLayer,
        user: str,
        token: Optional[str] = None,
        delay: float = 0.0,
    ) -> None:
        middle.register(user, token=token)
        middle.deploy(user)
        middle.load(user, daemon_delay=delay)

    # ------------------------------------------------------------------ 注册

    def test_register_multiple_users_gets_distinct_tokens_ports_and_persisted_registry(self) -> None:
        middle = self.make_middle()
        alice = middle.register("alice", token="alice-prod")
        bob = middle.register("bob")  # 自动生成 token

        self.assertEqual(alice["token"], "alice-prod")
        self.assertNotEqual(alice["token"], bob["token"])
        self.assertNotEqual(
            alice["route"]["skill"]["port"],
            bob["route"]["skill"]["port"],
        )
        self.assertTrue((middle.state_root / "registry.json").exists())
        self.assertEqual(middle.registry.users(), ["alice", "bob"])
        self.assertNotIn("status", alice)
        self.assertNotIn("authorized", alice)

        with self.assertRaises(RegistrationError):
            middle.register("alice", token="another-token")
        with self.assertRaises(RegistrationError):
            middle.register("carol", token="alice-prod")
        self.assertEqual(middle.registry.users(), ["alice", "bob"])

    def test_four_step_flow_and_registry_has_no_runtime_fields(self) -> None:
        middle = self.make_middle()
        with self.assertRaises(RegistrationError):
            middle.load("alice")  # 未注册

        middle.register("alice", token="alice-prod")
        with self.assertRaises(RegistrationError):
            middle.load("alice")  # 已注册但未部署

        middle.deploy("alice")
        loaded = middle.load("alice")
        self.assertEqual(loaded["token"], "alice-prod")
        self.assertGreater(loaded["skill_port"], 0)

        raw = json.loads((middle.state_root / "registry.json").read_text(encoding="utf-8"))
        self.assertNotIn("status", raw["users"]["alice"])
        self.assertNotIn("authorized", raw["users"]["alice"])

    # ------------------------------------------------------------ token 路由

    def test_execute_skill_routes_by_token_and_arrival_is_success(self) -> None:
        middle = self.make_middle()
        self.start_user(middle, "alice", token="alice-prod")
        self.start_user(middle, "bob", token="bob-prod")

        alice_result = middle.execute_skill("alice-only", token="alice-prod")
        bob_result = middle.execute_skill("bob-only", token="bob-prod")

        self.assertTrue(alice_result.ok)
        self.assertTrue(bob_result.ok)
        self.assertEqual(alice_result.endpoint, "alice")
        self.assertEqual(bob_result.endpoint, "bob")
        self.assertEqual(alice_result.output, "alice-only")

        alice_arrivals = middle.arrivals("alice-prod")
        bob_arrivals = middle.arrivals("bob-prod")
        self.assertEqual([arrival.skill for arrival in alice_arrivals], ["alice-only"])
        self.assertEqual([arrival.skill for arrival in bob_arrivals], ["bob-only"])
        self.assertEqual(alice_arrivals[0].token, "alice-prod")
        self.assertEqual(bob_arrivals[0].token, "bob-prod")

    def test_unknown_token_is_rejected_without_touching_any_daemon(self) -> None:
        middle = self.make_middle()
        self.start_user(middle, "alice", token="alice-prod")

        skill_result = middle.execute_skill("x", token="nope")
        command_result = middle.run_command("Write-Output x", token="nope")

        self.assertFalse(skill_result.ok)
        self.assertFalse(command_result.ok)
        self.assertEqual(command_result.error_kind, "invalid_token")
        self.assertEqual(middle.arrivals("alice-prod"), [])

    # ------------------------------------------------------------ 并发语义

    def test_same_user_skills_serialize_on_single_threaded_daemon(self) -> None:
        middle = self.make_middle()
        self.start_user(middle, "alice", token="alice-prod", delay=0.15)

        with ThreadPoolExecutor(max_workers=2) as callers:
            futures = [
                callers.submit(middle.execute_skill, "skill-{}".format(i), 5.0, "alice-prod")
                for i in range(2)
            ]
            results = [future.result() for future in futures]

        self.assertTrue(all(result.ok for result in results))
        arrivals = middle.arrivals("alice-prod")
        self.assertEqual(len(arrivals), 2)
        # 单线程 daemon 顺序处理：两条到达区间不重叠。
        self.assertFalse(arrivals[0].overlaps(arrivals[1]))

    def test_cross_user_skills_run_in_parallel(self) -> None:
        middle = self.make_middle()
        self.start_user(middle, "alice", token="alice-prod", delay=0.2)
        self.start_user(middle, "bob", token="bob-prod", delay=0.2)

        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=2) as callers:
            futures = [
                callers.submit(middle.execute_skill, "skill-{}".format(name), 5.0, token)
                for name, token in (("alice", "alice-prod"), ("bob", "bob-prod"))
            ]
            results = [future.result() for future in futures]
        elapsed = time.perf_counter() - started

        self.assertTrue(all(result.ok for result in results))
        self.assertLess(elapsed, 1.0)  # 串行会是 ~0.4s；并行应是 ~0.2s
        alice_arrival = middle.arrivals("alice-prod")[0]
        bob_arrival = middle.arrivals("bob-prod")[0]
        self.assertTrue(alice_arrival.overlaps(bob_arrival))

    # ------------------------------------------------------- pwsh 命令执行

    @PW
    def test_run_command_default_serial_keeps_persistent_shell_state(self) -> None:
        middle = self.make_middle()
        self.start_user(middle, "alice", token="alice-prod")

        first = middle.run_command("$vb_x=41", token="alice-prod")
        second = middle.run_command("Write-Output ($vb_x+1)", token="alice-prod")

        self.assertTrue(first.ok)
        self.assertTrue(second.ok)
        self.assertIn("42", second.stdout)
        records = middle.command_records("alice-prod")
        self.assertEqual([record.mode for record in records], ["serial", "serial"])

    @PW
    def test_run_command_default_serial_never_overlaps(self) -> None:
        middle = self.make_middle()
        self.start_user(middle, "alice", token="alice-prod")

        with ThreadPoolExecutor(max_workers=2) as callers:
            futures = [
                callers.submit(
                    middle.run_command,
                    "Start-Sleep -Milliseconds 250; Write-Output s{}".format(i),
                    None,
                    "alice-prod",
                    False,
                )
                for i in range(2)
            ]
            results = [future.result() for future in futures]

        self.assertTrue(all(result.ok for result in results))
        records = middle.command_records("alice-prod")
        self.assertEqual(len(records), 2)
        self.assertFalse(records[0].overlaps(records[1]))
        self.assertTrue(all(record.mode == "serial" for record in records))

    @PW
    def test_run_command_parallel_true_overlaps(self) -> None:
        middle = self.make_middle(max_workers=8)
        self.start_user(middle, "alice", token="alice-prod")

        with ThreadPoolExecutor(max_workers=2) as callers:
            futures = [
                callers.submit(
                    middle.run_command,
                    "Start-Sleep -Milliseconds 400; Write-Output p{}".format(i),
                    None,
                    "alice-prod",
                    True,
                )
                for i in range(2)
            ]
            results = [future.result() for future in futures]

        self.assertTrue(all(result.ok for result in results))
        records = [
            record for record in middle.command_records("alice-prod")
            if record.mode == "parallel"
        ]
        self.assertEqual(len(records), 2)
        self.assertTrue(records[0].overlaps(records[1]))
        self.assertGreaterEqual(middle.stats("alice-prod")["max_parallel_in_use"], 2)

    @PW
    def test_connect_smoke_through_register_and_start(self) -> None:
        middle = self.make_middle()
        result = middle.register_and_start("alice", token="alice-prod")

        self.assertTrue(result["connected"]["success"])
        self.assertIn(
            "vb-ok",
            result["connected"]["command_smoke"]["stdout"],
        )
        self.assertEqual(
            result["connected"]["skill_smoke"]["endpoint"],
            "alice",
        )
        self.assertTrue(result["connected"]["skill_smoke"]["status"] == "success")

    @PW
    def test_worker_pool_rejects_when_at_capacity(self) -> None:
        middle = self.make_middle(max_workers=1)
        self.start_user(middle, "alice", token="alice-prod")

        caller = ThreadPoolExecutor(max_workers=1)
        try:
            held = caller.submit(
                middle.run_command,
                "Start-Sleep -Milliseconds 400; Write-Output held",
                None,
                "alice-prod",
                True,
            )
            deadline = time.monotonic() + 5.0
            while middle.stats("alice-prod")["max_parallel_in_use"] < 1:
                if time.monotonic() > deadline:
                    self.fail("first command never started")
                time.sleep(0.02)

            rejected = middle.run_command(
                "Write-Output should-not-run",
                None,
                "alice-prod",
                True,
            )
            self.assertFalse(rejected.ok)
            self.assertEqual(rejected.error_kind, "worker_capacity")

            self.assertTrue(held.result(timeout=10.0).ok)
        finally:
            caller.shutdown(wait=True)


if __name__ == "__main__":
    unittest.main()
