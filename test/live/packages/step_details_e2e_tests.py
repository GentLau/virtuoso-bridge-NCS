# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-29 20:54
# 依赖: 无
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查：`basic.skill.execute("1+1")` 探活（新契约：载荷在顶层 `result`）；
# ②③ 无需构建：同一 op 分别以 `step_details=true` / 缺省 调用（一次只动一个变量）；
# ④ 只做被测动作：skill 单步 + 一个多步领域操作 + 一个业务失败；
# ⑤ 读回比对：`step_details=true` → 响应含 `steps`（每步 name/ok/detail）；缺省成功 → `steps` 整个省略；
#    失败 → 无论是否传 `step_details` 都带 `steps`（C1 决策 2）；
# ⑥ 不改共享库；JSON 证据落盘。
"""C1「`step_details`」参数真机覆盖（round9 op×参数矩阵最大 GAP：无一 TB 传过该字段）。

判据（spec/顶层响应壳决策 2：`steps` 出现条件 = 开启 `step_details` 或操作失败）：
  * SD-01 `basic.skill.execute(step_details=True)` → 含 `steps`，且每步有 `name`/`ok`/`detail`；
  * SD-02 同 op 缺省 → 成功响应**不含** `steps`；
  * SD-03 多步领域操作（`virtuoso.maestro.write`）传 `step_details=True` → 含 `steps`（≥2 步）；
  * SD-04 同领域操作缺省 → 成功响应不含 `steps`；
  * SD-05 业务失败（`basic.command.run(cmd="false")`）缺省 → 仍带 `steps`（失败必带）。

用法::

    PYTHONPATH=src python test/live/packages/step_details_e2e_tests.py --transport http
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"


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


def run_suite(transport) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    results: list[tuple[str, str]] = []
    evidence: dict[str, Any] = {"cases": {}}

    def run(name: str, func) -> Any:
        try:
            value = func()
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            print(f"FAIL    {name}: {type(exc).__name__}: {exc}", flush=True)
            return None
        results.append((name, "PASS"))
        return value

    def _steps_of(response: dict[str, Any]) -> list | None:
        return response.get("steps") if "steps" in response else None

    def case_env() -> None:
        response = _op(transport, "basic.skill.execute", skill_code="1+1")
        assert response.get("ok") is True, f"环境探活失败: {response.get('error')}"

    def case_skill_with_step_details() -> None:
        response = _op(transport, "basic.skill.execute", skill_code="1+1",
                       step_details=True)
        evidence["cases"]["skill_with_step_details"] = {
            "has_steps": "steps" in response,
            "steps": response.get("steps"),
        }
        assert response.get("ok") is True, f"调用失败: {response.get('error')}"
        steps = _steps_of(response)
        assert steps, f"SD-01：step_details=True 时成功响应必须带 steps：{response}"
        for step in steps:
            assert isinstance(step, dict), f"SD-01：step 不是对象：{step!r}"
            for key in ("name", "ok", "detail"):
                assert key in step, f"SD-01：step 缺字段 {key}：{step}"

    def case_skill_default_omits_steps() -> None:
        response = _op(transport, "basic.skill.execute", skill_code="1+1")
        evidence["cases"]["skill_default"] = {"has_steps": "steps" in response}
        assert response.get("ok") is True, f"调用失败: {response.get('error')}"
        assert "steps" not in response, (
            f"SD-02：缺省成功响应不得带 steps（实测 {_steps_of(response)!r}）")

    def case_domain_with_step_details() -> None:
        response = _op(transport, "virtuoso.maestro.read_config",
                       library="maestro_tb", cell="rc_probe", step_details=True)
        steps = _steps_of(response)
        evidence["cases"]["domain_with_step_details"] = {
            "has_steps": "steps" in response,
            "names": [s.get("name") for s in (steps or []) if isinstance(s, dict)],
        }
        assert response.get("ok") is True, f"领域操作失败: {response.get('error')}"
        assert steps and len(steps) >= 2, (
            f"SD-03：多步领域操作带 step_details=True 必须带 ≥2 步 steps：{response}")

    def case_domain_default_omits_steps() -> None:
        response = _op(transport, "virtuoso.maestro.read_config",
                       library="maestro_tb", cell="rc_probe")
        evidence["cases"]["domain_default"] = {"has_steps": "steps" in response}
        assert response.get("ok") is True, f"领域操作失败: {response.get('error')}"
        assert "steps" not in response, (
            f"SD-04：缺省成功响应不得带 steps（实测 {_steps_of(response)!r}）")

    def case_failure_keeps_steps() -> None:
        response = _op(transport, "basic.command.run", cmd="false")
        steps = _steps_of(response)
        evidence["cases"]["failure_keeps_steps"] = {
            "ok": response.get("ok"), "has_steps": "steps" in response,
            "names": [s.get("name") for s in (steps or []) if isinstance(s, dict)],
        }
        assert response.get("ok") is False, f"`false` 命令必须判失败: {response}"
        assert steps, f"SD-05：业务失败响应必须带 steps：{response}"
        # round9 W-3 补强：失败步骤的**形状**也必须有判据（原用例只验 steps 非空）
        last = steps[-1]
        assert isinstance(last, dict) and last.get("ok") is False, \
            f"SD-05：末步必须 ok=false：{last}"
        assert last.get("name") == "command", f"SD-05：末步名应为 command：{last}"
        detail = last.get("detail")
        assert isinstance(detail, dict) and detail.get("returncode") == 1, \
            f"SD-05：末步 detail 应带 returncode=1：{detail}"
        assert "rc=1" in str(response.get("error") or ""), \
            f"SD-05：失败原因应点明 rc=1：{response.get('error')!r}"

    run("SD-ENV 环境检查（1+1）", case_env)
    run("SD-01 skill + step_details=True → 含 steps（name/ok/detail）", case_skill_with_step_details)
    run("SD-02 skill 缺省成功 → steps 省略", case_skill_default_omits_steps)
    run("SD-03 多步领域操作 + step_details=True → 含 ≥2 步", case_domain_with_step_details)
    run("SD-04 多步领域操作缺省成功 → steps 省略", case_domain_default_omits_steps)
    run("SD-05 业务失败缺省 → 仍带 steps", case_failure_keeps_steps)
    return results, evidence


def main() -> int:
    global API, TOKEN
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("http",), default="http")
    parser.add_argument("--api", default=API)
    parser.add_argument("--token", default=TOKEN)
    parser.add_argument("--out", default=str(
        Path(__file__).resolve().parents[3] / "test" / "artifacts" / "evidence"
        / "step-details" / "step-details.json"))
    args = parser.parse_args()
    API, TOKEN = args.api, args.token
    results, evidence = run_suite(HttpTransport())
    for name, status in results:
        print(f"{status:6}  {name}")
    if args.out:
        evidence["api"] = API
        evidence["results"] = [{"case": n, "status": s} for n, s in results]
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
        print(f"evidence: {out_path}")
    return 0 if results and all(s == "PASS" for _, s in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
