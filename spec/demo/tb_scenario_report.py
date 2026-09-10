# -*- coding: utf-8 -*-
"""按 TB 典型场景实测 full_demo / cdslog_demo，输出可复核的数据。

运行：
    python -m spec.demo.tb_scenario_report

输出每个场景的输入、实测结果和通过/失败判据，供
``TB测试场景验证报告.md`` 引证；重复运行可重新生成数字（耗时类数字随机器
不同会有浮动，确定性判据不会变）。
"""
from __future__ import annotations

import json
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict

try:
    from .full_demo import MiddleLayer
    from .cdslog_demo import CdsLogIncrementReader, DemoSkillExecutor
except ImportError:  # 允许直接执行 python spec/demo/tb_scenario_report.py
    from full_demo import MiddleLayer
    from cdslog_demo import CdsLogIncrementReader, DemoSkillExecutor


def scenario_join(middle: MiddleLayer) -> Dict[str, Any]:
    """场景 1：多用户接入（注册→部署→load→连接）。"""
    alice = middle.register_and_start("alice", token="alice-prod")
    bob = middle.register_and_start("bob", token="bob-prod")
    alice_raw = middle.registry.get("alice") or {}
    return {
        "users": middle.registry.users(),
        "alice": {
            "token": alice["entry"]["token"],
            "port": alice["entry"]["route"]["skill"]["port"],
            "connect_success": alice["connected"]["success"],
        },
        "bob": {
            "token": bob["entry"]["token"],
            "port": bob["entry"]["route"]["skill"]["port"],
            "connect_success": bob["connected"]["success"],
        },
        "registry_has_runtime_fields": bool(
            {"status", "authorized"} & set(alice_raw)
        ),
    }


def scenario_routing(middle: MiddleLayer) -> Dict[str, Any]:
    """场景 2：token 路由到正确端口；未知 token 拒绝。"""
    alice = middle.execute_skill("alice-tb-op", token="alice-prod")
    bob = middle.execute_skill("bob-tb-op", token="bob-prod")
    unknown = middle.execute_skill("should-not-run", token="wrong-token")
    return {
        "alice": {"ok": alice.ok, "endpoint": alice.endpoint},
        "bob": {"ok": bob.ok, "endpoint": bob.endpoint},
        "unknown_token": {"ok": unknown.ok, "errors": unknown.errors},
        "alice_received": [a.skill for a in middle.arrivals("alice-prod")],
        "bob_received": [a.skill for a in middle.arrivals("bob-prod")],
        "cross_routing_clean": all(
            a.endpoint == "alice" for a in middle.arrivals("alice-prod")
        ) and all(a.endpoint == "bob" for a in middle.arrivals("bob-prod")),
    }


def _load_user(middle: MiddleLayer, user: str, delay: float) -> str:
    entry = middle.register(user)
    middle.deploy(user)
    middle.load(user, daemon_delay=delay)
    return str(entry["token"])


def scenario_skill_serial(middle: MiddleLayer) -> Dict[str, Any]:
    """场景 3：同一用户两条 TB Skill 操作（单 CIW）串行。"""
    token = _load_user(middle, "serial", delay=0.3)
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=2) as callers:
        futures = [
            callers.submit(middle.execute_skill, "tb-op-{}".format(i), 5.0, token)
            for i in range(2)
        ]
        results = [future.result() for future in futures]
    wall_ms = (time.perf_counter() - started) * 1000.0
    arrivals = middle.arrivals(token)
    return {
        "delay_per_op_ms": 300,
        "wall_ms": round(wall_ms, 1),
        "all_ok": all(result.ok for result in results),
        "arrival_durations_ms": [
            round((a.finished_at - a.started_at) * 1000.0, 1) for a in arrivals
        ],
        "overlap": arrivals[0].overlaps(arrivals[1]),
    }


def scenario_skill_parallel(middle: MiddleLayer) -> Dict[str, Any]:
    """场景 4：两个用户（两个 daemon）的 TB Skill 操作并行。"""
    token_a = _load_user(middle, "par-a", delay=0.3)
    token_b = _load_user(middle, "par-b", delay=0.3)
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=2) as callers:
        futures = [
            callers.submit(middle.execute_skill, "tb-op-{}".format(name), 5.0, token)
            for name, token in (("a", token_a), ("b", token_b))
        ]
        results = [future.result() for future in futures]
    wall_ms = (time.perf_counter() - started) * 1000.0
    arrival_a = middle.arrivals(token_a)[0]
    arrival_b = middle.arrivals(token_b)[0]
    return {
        "delay_per_op_ms": 300,
        "wall_ms": round(wall_ms, 1),
        "all_ok": all(result.ok for result in results),
        "overlap": arrival_a.overlaps(arrival_b),
    }


def scenario_command_serial_state(middle: MiddleLayer) -> Dict[str, Any]:
    """场景 5：命令默认串行 + persistent shell 状态（网表→仿真依赖）。"""
    middle.run_command("$tb_netlist_ready=41", token="alice-prod")
    state = middle.run_command("Write-Output ($tb_netlist_ready+1)", token="alice-prod")

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=2) as callers:
        futures = [
            callers.submit(
                middle.run_command,
                "Start-Sleep -Milliseconds 300; Write-Output step{}".format(i),
                None,
                "alice-prod",
                False,
            )
            for i in range(2)
        ]
        results = [future.result() for future in futures]
    wall_ms = (time.perf_counter() - started) * 1000.0
    records = middle.command_records("alice-prod")
    serial_records = [record for record in records if "step" in record.cmd]
    return {
        "state_output": state.stdout,
        "two_steps_wall_ms": round(wall_ms, 1),
        "all_ok": all(result.ok for result in results),
        "overlap": (
            serial_records[0].overlaps(serial_records[1])
            if len(serial_records) >= 2
            else True
        ),
        "step_order": [record.cmd for record in serial_records],
    }


def scenario_command_parallel(middle: MiddleLayer) -> Dict[str, Any]:
    """场景 6：同一用户两个独立 corner 命令并行（显式 parallel=True）。"""
    # 预热一次独立 pwsh，避免首次冷启动淹没计时。
    middle.run_command("Write-Output warm", token="alice-prod", parallel=True)

    started = time.perf_counter()
    middle.run_command(
        "Start-Sleep -Seconds 1; Write-Output base-0",
        token="alice-prod",
        parallel=False,
    )
    middle.run_command(
        "Start-Sleep -Seconds 1; Write-Output base-1",
        token="alice-prod",
        parallel=False,
    )
    serial_baseline_ms = (time.perf_counter() - started) * 1000.0

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=2) as callers:
        futures = [
            callers.submit(
                middle.run_command,
                "Start-Sleep -Seconds 1; Write-Output corner-{}".format(corner),
                None,
                "alice-prod",
                True,
            )
            for corner in ("tt", "ss")
        ]
        results = [future.result() for future in futures]
    parallel_wall_ms = (time.perf_counter() - started) * 1000.0

    records = [
        record
        for record in middle.command_records("alice-prod")
        if "corner-" in record.cmd
    ]
    return {
        "serial_baseline_ms": round(serial_baseline_ms, 1),
        "parallel_wall_ms": round(parallel_wall_ms, 1),
        "speedup": round(serial_baseline_ms / max(parallel_wall_ms, 0.001), 2),
        "all_ok": all(result.ok for result in results),
        "overlap": records[0].overlaps(records[1]) if len(records) >= 2 else False,
        "max_parallel_in_use": middle.stats("alice-prod")["max_parallel_in_use"],
    }


def scenario_capacity() -> Dict[str, Any]:
    """场景 7：worker 池满时立即拒绝，不排队。"""
    with tempfile.TemporaryDirectory(prefix="vb-tb-capacity-") as temporary:
        middle = MiddleLayer(Path(temporary), max_workers=1)
        try:
            token = _load_user(middle, "cap", delay=0.0)
            caller = ThreadPoolExecutor(max_workers=1)
            try:
                held = caller.submit(
                    middle.run_command,
                    "Start-Sleep -Milliseconds 300; Write-Output held",
                    None,
                    token,
                    True,
                )
                deadline = time.monotonic() + 5.0
                while middle.stats(token)["max_parallel_in_use"] < 1:
                    if time.monotonic() > deadline:
                        return {"error": "first command never started"}
                    time.sleep(0.02)
                started = time.perf_counter()
                rejected = middle.run_command(
                    "Write-Output should-not-run",
                    None,
                    token,
                    True,
                )
                reject_ms = (time.perf_counter() - started) * 1000.0
                first = held.result(timeout=10.0)
                return {
                    "first_ok": first.ok,
                    "rejected_error_kind": rejected.error_kind,
                    "reject_latency_ms": round(reject_ms, 2),
                    "arrivals": len(middle.arrivals(token)),
                }
            finally:
                caller.shutdown(wait=True)
        finally:
            middle.close()


def scenario_cdslog() -> Dict[str, Any]:
    """场景 8：每次 TB 操作返回本次 CDS.log 增量（过滤/限长/轮转）。"""
    with tempfile.TemporaryDirectory(prefix="vb-tb-log-") as temporary:
        path = Path(temporary) / "CDS.log"
        path.write_bytes("old history\n".encode("utf-8"))
        old_size = path.stat().st_size

        reader = CdsLogIncrementReader(path, log_level="all", start_at_end=True)
        executor = DemoSkillExecutor(path, reader)
        first = executor.execute_skill("open-tb", ["\\i open tb ok", "\\w missing corner"])
        second = executor.execute_skill("run-corner-tt", ["\\e syntax error", "tt info"])

        trunc_path = Path(temporary) / "CDS_big.log"
        trunc_reader = CdsLogIncrementReader(
            trunc_path, log_level="all", log_max_bytes=220, start_at_end=False
        )
        trunc_executor = DemoSkillExecutor(trunc_path, trunc_reader)
        trunc_result = trunc_executor.execute_skill(
            "noisy-tb-op",
            ["\\i " + ("info-" * 30), "\\w " + ("warning-" * 10), "\\e important error"],
        )

        rotation_result = CdsLogIncrementReader(
            path, log_level="all", start_at_end=True
        )
        path.write_text("fresh after rotation\n", encoding="utf-8")
        rotated = rotation_result.read_increment()

        return {
            "old_size_bytes": old_size,
            "first_increment": first.log,
            "second_increment": second.log,
            "truncated": trunc_result.log and "important error" in trunc_result.log,
            "trunc_notice": "[log truncated: error-only" in trunc_result.log,
            "rotation_reset_start_offset": rotated.start_offset,
        }


def main() -> None:
    report: Dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="vb-tb-scenario-") as temporary:
        middle = MiddleLayer(Path(temporary))
        try:
            report["1_接入"] = scenario_join(middle)
            report["2_token路由"] = scenario_routing(middle)
            report["3_同用户Skill串行"] = scenario_skill_serial(middle)
            report["4_跨用户Skill并行"] = scenario_skill_parallel(middle)
            report["5_命令串行保状态"] = scenario_command_serial_state(middle)
            report["6_命令并行corner"] = scenario_command_parallel(middle)
        finally:
            middle.close()
    report["7_worker池超限"] = scenario_capacity()
    report["8_CDSlog增量"] = scenario_cdslog()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
