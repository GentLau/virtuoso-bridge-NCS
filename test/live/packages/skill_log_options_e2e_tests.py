# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-29 17:05
# 依赖: 无
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查：业务面可达 + 目标 token 可用（`basic.skill.execute` 探活）；
# ②③ 无需构建：同一 SKILL 表达式（printf 短标记）分别在缺省/off/all/warn 下调用；
# ④ 只做被测动作（basic.skill.execute ×4 + 一个多步领域操作）；
# ⑤ 读回比对：`result.CDSlog` 是否含标记（缺省/all ⇒ 有；off ⇒ 无）；
# ⑥ 不改共享库、不留现场；JSON 证据落盘。
"""C2 回归：`log_level` / `log_max_bytes` 请求字段真机 HTTP 透传。

判据（spec/上层 请求契约）：
  * 不给字段 → 吃注册表默认（`vblog` = all）⇒ `CDSlog` 含标记；
  * `log_level="off"` → 该次请求 `CDSlog` 为空（按请求覆盖）；
  * `log_level="all"` → 含标记；`log_level="warn"` → 被接受（ok=true）；
  * `log_max_bytes` → 被接受（**不按内容断言**：CDS.log 捕获对超长行不落盘，见 NOTE）；
  * 多步领域操作（`virtuoso.maestro.read_config`）带 `log_level="off"` 仍 ok。

用法::

    PYTHONPATH=src python test/live/packages/skill_log_options_e2e_tests.py --transport http
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"
MARKER = "VB_C2_LOG_MARKER"
SKILL = f'progn(printf("{MARKER}\\n") 1)'


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
        result = ((_c1_wrapper(response)).get("value") or {})
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

    def case_warn_accepted() -> None:
        response = _op(transport, "basic.skill.execute", skill_code=SKILL,
                       log_level="warn")
        assert response.get("ok"), f"log_level=warn 调用失败: {response.get('error')}"

    def case_max_bytes_accepted() -> None:
        # NOTE: CDS.log 捕获对超长行不落盘，无法用内容证明截断；
        # 这里只钉"字段被接受、请求不被拒"，数值透传由离线合同保证。
        response = _op(transport, "basic.skill.execute", skill_code=SKILL,
                       log_level="all", log_max_bytes=65536)
        assert response.get("ok"), f"log_max_bytes 调用失败: {response.get('error')}"

    def case_domain_operation_accepts() -> None:
        response = _op(transport, "virtuoso.maestro.read_config",
                       library="maestro_tb", cell="rc_probe", log_level="off")
        assert response.get("ok"), f"领域操作带 log_level=off 失败: {response.get('error')}"
        assert response.get("steps"), "多步领域操作未返回 steps（C1 契约）"

    run("LOG-01 缺省 → 用注册表默认（CDSlog 含标记）", case_default_uses_registry)
    run("LOG-02 log_level=off → 该请求 CDSlog 为空", case_off_silences)
    run("LOG-03 log_level=all → 含标记", case_all_explicit)
    run("LOG-04 log_level=warn → 被接受", case_warn_accepted)
    run("LOG-05 log_max_bytes → 被接受（内容截断不做断言，见 NOTE）", case_max_bytes_accepted)
    run("LOG-06 多步领域操作带 log_level=off → ok", case_domain_operation_accepts)
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


# --- C1 兼容垫片（2026-09-29，C3）------------------------------------------------
# C1（2f88853）起：业务载荷直返顶层（值型 `value`、命令/skill 型 `result`）、
# 成功默认省略 `steps`、失败壳去掉 `data`。历史 TB 按 `response["data"]` 解析，
# 本垫片把新契约响应合成为旧 `data` 壳，让既有解析零改动继续工作。
def _c1_wrapper(body):
    if not isinstance(body, dict):
        return {}
    if isinstance(body.get("data"), dict):
        return body["data"]
    wrapped = {"ok": body.get("ok"), "error": body.get("error")}
    for key in ("value", "result", "steps"):
        if key in body:
            wrapped[key] = body[key]
    return wrapped
