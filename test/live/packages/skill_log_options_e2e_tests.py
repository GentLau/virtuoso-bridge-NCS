# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-30 21:45
# 依赖: 无
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查：业务面可达 + 目标 token 可用（`basic.skill.execute` 探活）；
# ②③ 无需构建：同一 SKILL 表达式（printf 短标记）分别在缺省/off/all/warn 下调用；
# ④ 只做被测动作（basic.skill.execute ×4 + 一个多步领域操作）；
# ⑤ 读回比对：`result.CDSlog` 是否含标记（缺省/all ⇒ 有；off ⇒ 无）；
# ⑥ 不改共享库、不留现场；JSON 证据落盘。
r"""C2 回归：`log_level` / `log_max_bytes` 请求字段真机 HTTP 透传。

判据（spec/上层 请求契约）：
  * 不给字段 → 吃注册表默认（`vblog` = all）⇒ `CDSlog` 含标记；
  * `log_level="off"` → 该次请求 `CDSlog` 为空（按请求覆盖）；
  * `log_level="all"` → 含标记；
  * `log_level="warn"` → **按 §4 分级过滤**：warning 前缀行保留、info 行剔除
    （round9 补强：原用例只断言 ok，属 weak-assertions W-1）；
  * `log_max_bytes` → **按 §5 断言内容**：过滤后增量超限 ⇒ 自动降级为 error-only 并附
    `[log auto-degraded: error-only due to log_max_bytes]`（info 洪泛、warn 洪泛两档）
    （round9 补强）；
  * §5 第 3 档（error 增量仍超限 ⇒ `[log truncated: …]`）**本 TB 无法触发**：
    SKILL 侧无法产出 `\e` 前缀的 CDS.log 行（`error()`/`errset` 只进 CIW 与 `errors[]`，
    实测 CDSlog 为空）——列为残留，见 `test/reports/round9/log-options-w1-r9.md`；
  * 多步领域操作（`virtuoso.maestro.read_config`）带 `log_level="off"` 仍 ok，且
    **该请求 `CDSlog` 为空串**（round9 补强）。
  * 并发归属（§3 "daemon 同一时刻只接收/执行一个由闸门放行的 Skill 请求"）：同一 token
    并发 4 条 `log_level=all` 请求 → 每条 `CDSlog` **只含自己的标记**、不含其它并发请求的
    标记（round9 补强 LOG-07；反例若命中说明投递闸门/区间归属被破坏）。

用法::

    PYTHONPATH=src python test/live/packages/skill_log_options_e2e_tests.py --transport http
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"
MARKER = "VB_C2_LOG_MARKER"
SKILL = f'progn(printf("{MARKER}\\n") 1)'
MARKER_INFO = "VB_W1_INFO"
MARKER_WARN = "VB_W1_WARN"
MARKER_ERR = "VB_W1_ERR"


def _skill_lines(lines: list[str]) -> str:
    """把若干"CDS.log 行"包成一个 SKILL 表达式（`\\\\w`/`\\\\e` 为 §4 的字面前缀）。"""
    body = "".join('printf("' + line.replace("\\", "\\\\") + '\\n") ' for line in lines)
    return f"progn({body}1)"


class HttpTransport:
    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            API, data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return json.loads(error.read().decode("utf-8"))


def _op(transport, operation: str, **fields: Any) -> dict[str, Any]:
    return transport.call({"operation": operation, "token": TOKEN, **fields})


def _cdslog(response: dict[str, Any]) -> str:
    result = response.get("result")
    if not isinstance(result, dict):
        result = ((response).get("value") or {})
    return str(result.get("CDSlog") or "")


def run_suite(transport) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []

    def run(name: str, func) -> Any:
        try:
            value = func()
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            print(f"FAIL    {name}: {type(exc).__name__}: {exc}", flush=True)
            return None
        results.append((name, "PASS"))
        return value

    def case_default_uses_registry() -> None:
        response = _op(transport, "basic.skill.execute", skill_code=SKILL)
        assert response.get("ok"), f"缺省调用失败: {response.get('error')}"
        log = _cdslog(response)
        assert MARKER in log, f"缺省（注册表默认 all）未捕获 CDSlog 标记: {log[:120]!r}"

    def case_off_silences() -> None:
        response = _op(transport, "basic.skill.execute", skill_code=SKILL,
                       log_level="off")
        assert response.get("ok"), f"log_level=off 调用失败: {response.get('error')}"
        log = _cdslog(response)
        assert MARKER not in log, f"log_level=off 仍捕获到日志: {log[:120]!r}"
        assert log == "", f"log_level=off 的 CDSlog 应为空，实测 {log[:120]!r}"

    def case_all_explicit() -> None:
        response = _op(transport, "basic.skill.execute", skill_code=SKILL,
                       log_level="all")
        assert response.get("ok"), f"log_level=all 调用失败: {response.get('error')}"
        assert MARKER in _cdslog(response), "log_level=all 未捕获 CDSlog 标记"

    def case_warn_filters_info() -> None:
        """§4：warn = warning+error；info 行必须被剔除（warning 用 `warn()` 产出）。"""
        skill = f'progn(warn("{MARKER_WARN}") printf("{MARKER_INFO}\\n") 1)'
        response = _op(transport, "basic.skill.execute", skill_code=skill,
                       log_level="warn")
        assert response.get("ok"), f"log_level=warn 调用失败: {response.get('error')}"
        log = _cdslog(response)
        assert MARKER_WARN in log, f"warn 未保留 warning 行: {log[:160]!r}"
        assert MARKER_INFO not in log, f"warn 未剔除 info 行（§4）: {log[:160]!r}"

    def case_max_bytes_degrades_to_error_only() -> None:
        """§5 第 2 档：info 增量超限 ⇒ 降级 error-only + 降级说明。"""
        flood = _skill_lines([f"{MARKER_INFO}_{i:03d}_" + "x" * 40 for i in range(40)])
        response = _op(transport, "basic.skill.execute", skill_code=flood,
                       log_level="all", log_max_bytes=200)
        assert response.get("ok"), f"降级用例调用失败: {response.get('error')}"
        log = _cdslog(response)
        assert "auto-degraded" in log, \
            f"info 超限未给降级说明（§5）: {log[:200]!r}"
        assert MARKER_INFO not in log, f"降级后仍返回 info 行（§5）: {log[:200]!r}"

    def case_max_bytes_warn_flood_degrades() -> None:
        """§5：`log_level=warn` 下 warn 洪泛超限 ⇒ 同样降级 error-only + 说明。"""
        body = "".join(f'warn("{MARKER_WARN}_F{i:03d}_' + "y" * 40 + '") '
                       for i in range(40))
        response = _op(transport, "basic.skill.execute",
                       skill_code=f"progn({body}1)",
                       log_level="warn", log_max_bytes=300)
        assert response.get("ok"), f"warn 洪泛调用失败: {response.get('error')}"
        log = _cdslog(response)
        assert "auto-degraded" in log, \
            f"warn 超限未给降级说明（§5）: {log[:200]!r}"
        assert f"{MARKER_WARN}_F000" not in log, \
            f"降级后仍返回 warn 行（§5 只保留 error）: {log[:200]!r}"

    def case_domain_operation_accepts() -> None:
        response = _op(transport, "virtuoso.maestro.read_config",
                       library="maestro_tb", cell="rc_probe", log_level="off",
                       # C1 契约：成功响应默认省略 steps，本用例要断言多步结构 → 显式开启
                       step_details=True)
        assert response.get("ok"), f"领域操作带 log_level=off 失败: {response.get('error')}"
        assert response.get("steps"), "多步领域操作未返回 steps（C1 契约）"
        log = _cdslog(response)
        assert log == "", f"领域操作 log_level=off 的 CDSlog 应为空串: {log[:160]!r}"

    def case_concurrent_increment_isolation() -> None:
        """§3：同一 token 并发投递时，每条请求的 `CDSlog` 只含本次增量（不串场）。

        判别力：若投递闸门失效且 daemon 变成并发处理/区间交错，本条即红
        （标记交叉出现在别条请求的 CDSlog 里）。
        """
        stamp = time.strftime("%H%M%S")
        marks = [f"VB_LOG07_CONC_{stamp}_{i}" for i in range(4)]
        slots: list[tuple[bool, str, str | None] | None] = [None] * len(marks)
        crash: list[tuple[int, str]] = []

        def worker(index: int) -> None:
            try:
                response = _op(transport, "basic.skill.execute",
                               skill_code=f'progn(printf("{marks[index]}\\n") {index})',
                               log_level="all")
                slots[index] = (bool(response.get("ok")), _cdslog(response),
                                response.get("error"))
            except Exception as exc:  # noqa: BLE001
                crash.append((index, f"{type(exc).__name__}: {exc}"))

        threads = [threading.Thread(target=worker, args=(i,), daemon=True)
                   for i in range(len(marks))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=180)
        alive = [i for i, thread in enumerate(threads) if thread.is_alive()]
        assert not alive, f"并发请求线程未在 180s 内返回（序号 {alive}）"
        assert not crash, f"并发请求抛异常: {crash}"
        for index, mark in enumerate(marks):
            slot = slots[index]
            assert slot is not None, f"并发请求 {index} 未回填结果"
            ok, log, err = slot
            assert ok, f"并发请求 {index}（log_level=all）失败: {err}"
            assert mark in log, \
                f"并发请求 {index} 的本次增量未落自己的 CDSlog: {log[:200]!r}"
            foreign = [other for j, other in enumerate(marks)
                       if j != index and other in log]
            assert not foreign, \
                f"并发请求 {index} 的 CDSlog 混入其它请求的输出 {foreign}: {log[:200]!r}"

    def case_illegal_log_options_rejected() -> None:
        """§8.7：非法 `log_level` / `log_max_bytes` 必须在请求路径上**结构化拒绝**，
        且**不得执行 SKILL**（零副作用）。

        daemon 侧裸帧契约（NAK + `invalid log_level` / `invalid log_max_bytes`）见
        `test/offline/unit/test_daemon_runtime_contracts.py::test_bad_log_level_and_budget_are_naked`；
        本用例补的是**经业务面/中层**的端到端可见行为（此前只有 L0）。
        """
        stamp = time.strftime("%H%M%S")
        marker = f"VB_LOG08_{stamp}"
        skill = f'progn(printf("{marker}\\n") 1)'
        cases = (
            ({"log_level": "loud"}, "invalid log_level"),
            ({"log_level": "OFF"}, "invalid log_level"),
            ({"log_max_bytes": "many"}, "invalid log_max_bytes"),
            ({"log_max_bytes": 0}, "invalid log_max_bytes"),
            ({"log_max_bytes": -5}, "invalid log_max_bytes"),
        )
        for overrides, expected in cases:
            response = _op(transport, "basic.skill.execute", skill_code=skill, **overrides)
            text = json.dumps(response, ensure_ascii=False)
            assert not response.get("ok"), f"{overrides} 必须被拒绝: {text[:220]}"
            assert expected in text, f"拒绝原因应含 {expected!r}: {text[:260]}"
        # 零副作用：5 次被拒绝的请求都不得真的执行 SKILL（标记不得出现在后续 CDSlog）
        check = _op(transport, "basic.skill.execute", skill_code='printf("")',
                    log_level="all")
        assert marker not in _cdslog(check), \
            "被拒绝的非法 log 选项请求不得执行 SKILL（标记出现在后续 CDSlog）"

    run("LOG-01 缺省 → 用注册表默认（CDSlog 含标记）", case_default_uses_registry)
    run("LOG-02 log_level=off → 该请求 CDSlog 为空", case_off_silences)
    run("LOG-03 log_level=all → 含标记", case_all_explicit)
    run("LOG-04 log_level=warn → 保留 warning、剔除 info（§4）", case_warn_filters_info)
    run("LOG-04b log_max_bytes 超限 → 降级 error-only + 说明（§5）",
        case_max_bytes_degrades_to_error_only)
    run("LOG-04d warn 洪泛超限 → 同样降级 error-only（§5）",
        case_max_bytes_warn_flood_degrades)
    run("LOG-06 多步领域操作带 log_level=off → ok 且 CDSlog 为空", case_domain_operation_accepts)
    run("LOG-07 并发 4 请求 → 各自 CDSlog 只含本次增量（§3）",
        case_concurrent_increment_isolation)
    run("LOG-08 非法 log_level/log_max_bytes 结构化拒绝且零副作用（§8.7）",
        case_illegal_log_options_rejected)
    return results


def main() -> int:
    global API, TOKEN
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("http",), default="http")
    parser.add_argument("--api", default=API)
    parser.add_argument("--token", default=TOKEN)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    API, TOKEN = args.api, args.token
    results = run_suite(HttpTransport())
    for name, status in results:
        print(f"{status:6}  {name}")
    if args.out:
        from pathlib import Path
        evidence = {"api": API, "token": TOKEN, "marker": MARKER,
                    "python": sys.version.split()[0],
                    "results": [{"case": n, "status": s} for n, s in results]}
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
        print(f"evidence: {out_path}")
    return 0 if results and all(s == "PASS" for _, s in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
