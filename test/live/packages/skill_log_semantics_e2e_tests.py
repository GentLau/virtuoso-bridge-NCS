# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-29 23:00
# 依赖: 无
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查：`basic.skill.execute("1+1")` 探活（新契约：载荷在顶层 `result`）；
# ②③ 无需构建：每条用例用**唯一带时间戳的标记**，避免旧缓冲内容误判；
# ④ 只做被测动作：print/printf 各一次（print 不带换行是 C06 的触发形态）；
# ⑤ 读回比对：断言标记出现在**同一条请求**的 `CDSlog`、且**不串到**后续请求；
# ⑥ 不改共享库；JSON 证据落盘。
"""C06 回归/攻击：`print` 输出的 flush 时机与 `CDSlog` 归属。

背景（C06 卡片）：`ramic_bridge.il` 的 `evalstring` 路径是**行缓冲**——不带换行的 `print`
不会立即 flush；桥在表达式尾部补的是 `hiFlush()`（对 CIW 输出与日志都无效，见
`spec/design-concepts/底层/6-日志返回设计标准.md:49`）。后果：
  ① 该请求的 `CDSlog` 为空（输出还没落到日志）；
  ② 缓冲内容会在**后续请求**（下一次触发 flush 的 printf/手动交互）里涌出来 → 串场。

判据（C06 修好后应全绿；设计侧修法：evalstring 之后、`lo_end` 抓取之前 `errset(hiFlushInfo())`）：
  * C06-A  同一请求：`print("MARK")`（不带换行）→ 该请求 `CDSlog` 含 MARK；
  * C06-B  不串场：紧接着 `printf("\\n")` → 其 `CDSlog` **不含** 上一条 MARK；
  * C06-C  回归：`printf("MARK2\\n")` → 同一请求 `CDSlog` 含 MARK2（既有能力不回归）；
  * C06-D  边界记录：`print("MARK3\\n")` → `CDSlog` 是否含 MARK3 只打 NOTE（待 spec 定义）。
  * C06-E  load 路径：上传 `.il`（内含 `printf("MARK4\\n")`）→ `load(path)` → 同一请求 `CDSlog` 含 MARK4
    （brief 要求 print/printf/load 三类每类至少一条断言；C06 红钉只覆盖前两类）。

round9 攻击扩展（同一根因的**多形态**，防"修一半"；判据取自
`spec/design-concepts/底层/6-日志返回设计标准.md` §3「增量 = 本次指令产生的内容」与 §8 验收标准）：
  * C06-F  同一请求 **3 次 print**（不带换行）→ 三个标记都必须落同一请求 `CDSlog`；
  * C06-G  同一请求 `print`(无换行) + `printf`(换行) → 两个标记都在同一请求（换行是缓冲触发点）；
  * C06-H  同一请求 **循环内 5 次 print**（`foreach` + `list`）→ 五个标记全部落同一请求；
  * C06-I  **600B 长行 print**（不带换行）→ 同一请求 `CDSlog` 仍含标记（长行不得"消失"）；
  * C06-J  跨请求隔离：`print`(all) → `printf`(off) → `printf`(all)，**第三条不得带出第一条的缓冲**
    （spec §3：`off` 不 flush；缓冲属于第一条请求的增量，出现在第三条即跨请求串场）；
  * C06-K  load 路径的 **print（不带换行）** → 同请求 `CDSlog` 含标记（E 只覆盖 printf 形态）。

关闭口径：F/H/I/J/K 是 C06 本体的同族形态，修好 A 应同时转绿；**只绿 A 而 F–K 仍红 = 修复不彻底**，
C06 卡以本 TB 全绿为关闭条件。

用法::

    PYTHONPATH=src python test/live/packages/skill_log_semantics_e2e_tests.py --transport http
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"
STAMP = time.strftime("%H%M%S")


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


def _payload(response: dict[str, Any]) -> dict[str, Any]:
    """C1 契约：skill 型载荷在顶层 `result`（兼容 `value`/旧 `data` 只为容错，不作为判据）。"""
    for key in ("result", "value"):
        value = response.get(key)
        if isinstance(value, dict):
            return value
    data = response.get("data")
    if isinstance(data, dict):
        inner = data.get("value") or data.get("result")
        return inner if isinstance(inner, dict) else data
    return {}


def _cdslog(transport, code: str) -> str:
    response = _op(transport, "basic.skill.execute", skill_code=code)
    if response.get("ok") is not True:
        raise AssertionError(f"skill failed: {response.get('error')}")
    return str(_payload(response).get("CDSlog") or "")


def _command(transport, cmd: str) -> str:
    """C4 契约：`basic.command.run` 的 result 是命名对象（{returncode,stdout,stderr,kind}）。"""
    response = _op(transport, "basic.command.run", cmd=cmd, timeout=120)
    if response.get("ok") is not True:
        raise AssertionError(f"command failed: {response.get('error')}")
    result = response.get("result")
    if not isinstance(result, dict):
        raise AssertionError(f"command result 不是命名对象（C4）: {response}")
    if result.get("returncode") != 0:
        raise AssertionError(f"command rc != 0: {response}")
    return str(result.get("stdout") or "")


def _upload_il(transport, content: str, tag: str) -> str:
    """写本地 `.il` → 上传到远端 `$HOME/.virtuoso-bridge/`，返回远端绝对路径。"""
    local = Path(tempfile.gettempdir()) / f"{tag}_{STAMP}.il"
    local.write_text(content, encoding="utf-8", newline="\n")
    home = _command(transport, "echo $HOME").strip().splitlines()
    remote = f"{home[0] if home else '/home/Gent'}/.virtuoso-bridge/{tag}_{STAMP}.il"
    uploaded = _op(transport, "basic.file.upload",
                   local_path=str(local), remote_path=remote, timeout=120)
    if uploaded.get("ok") is not True:
        raise AssertionError(f"上传 {tag} 失败: {uploaded.get('error')}")
    visible = _command(transport, f"test -f {remote} && echo yes || echo no")
    if "yes" not in visible:
        raise AssertionError(f"上传的 {tag} 在远端不可见: {remote!r}")
    return remote


def _purge(transport) -> None:
    """把此前留在 CIW 行缓冲里的内容冲出来（后续用例只断言自己的标记，不受残留影响）。"""
    _op(transport, "basic.skill.execute", skill_code='printf("\\n")', log_level="all")


def run_suite(transport) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    results: list[tuple[str, str]] = []
    evidence: dict[str, Any] = {"stamp": STAMP, "cases": {}}

    def run(name: str, func) -> Any:
        try:
            value = func()
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            print(f"FAIL    {name}: {type(exc).__name__}: {exc}", flush=True)
            return None
        results.append((name, "PASS"))
        return value

    def case_env() -> str:
        output = _cdslog(transport, "1+1")
        return output

    mark_a = f"C06A_{STAMP}"
    mark_c = f"C06C_{STAMP}"
    mark_d = f"C06D_{STAMP}"

    def case_a_print_no_newline() -> None:
        log = _cdslog(transport, f'progn(print("{mark_a}") 11)')
        evidence["cases"]["A_print_no_newline"] = {"mark": mark_a, "CDSlog": log[:200]}
        assert mark_a in log, (
            f"C06-A：不带换行的 print 文本未落在**同一请求**的 CDSlog（实测 {log[:120]!r}）"
            "——行缓冲未 flush（C06 本体）")

    def case_b_no_leak_to_next() -> None:
        log = _cdslog(transport, 'printf("\\n")')
        evidence["cases"]["B_next_request"] = {"CDSlog": log[:200]}
        assert mark_a not in log, (
            f"C06-B：上一条 print 的缓冲串进了后续请求的 CDSlog（实测 {log[:160]!r}）"
            "——跨请求串场（C06 后果②）")

    def case_c_printf_newline_regression() -> None:
        log = _cdslog(transport, f'progn(printf("{mark_c}\\n") 22)')
        evidence["cases"]["C_printf_newline"] = {"mark": mark_c, "CDSlog": log[:200]}
        assert mark_c in log, f"C06-C：带换行 printf 未落 CDSlog（回归）：{log[:120]!r}"

    def case_d_print_newline_boundary() -> None:
        log = _cdslog(transport, f'progn(print("{mark_d}\\n") 33)')
        hit = mark_d in log
        evidence["cases"]["D_print_newline"] = {"mark": mark_d, "in_CDSlog": hit,
                                                "CDSlog": log[:200]}
        print(f"NOTE  C06-D 边界记录：print+换行 的文本 {'在' if hit else '不在'} CDSlog"
              f"（待 spec 定义该边界；不作判据）", flush=True)

    mark_e = f"C06E_{STAMP}"

    def case_e_load_printf() -> None:
        """C06-E：load 一个含 printf(带换行) 的 .il → 同请求 CDSlog 含标记（load 路径回归）。"""
        remote = _upload_il(transport, f'printf("{mark_e}\\n")\n', "c06_load_e")
        try:
            log = _cdslog(transport, f'load("{remote}")')
            evidence["cases"]["E_load_printf"] = {"mark": mark_e, "remote": remote,
                                                  "CDSlog": log[:200]}
            assert mark_e in log, (
                f"C06-E：load 文件内的 printf(带换行) 未落**同一请求**的 CDSlog（实测 {log[:120]!r}）")
        finally:
            _command(transport, f"rm -f {remote}")

    mark_f = [f"C06F{i}_{STAMP}" for i in range(3)]

    def case_f_multi_print_same_request() -> None:
        """C06-F：同一请求 3 次 print（不带换行）→ 三个标记都要落同一请求 CDSlog。"""
        _purge(transport)
        body = " ".join(f'print("{m}")' for m in mark_f)
        log = _cdslog(transport, f"progn({body} 44)")
        evidence["cases"]["F_multi_print"] = {"marks": mark_f, "CDSlog": log[:400]}
        missing = [m for m in mark_f if m not in log]
        assert not missing, (
            f"C06-F：同一请求 {len(mark_f)} 次 print（不带换行）只有部分落 CDSlog，缺 {missing}"
            f"（同根因：行缓冲未刷；实测 {log[:200]!r}）")

    mark_g1, mark_g2 = f"C06G1_{STAMP}", f"C06G2_{STAMP}"

    def case_g_print_plus_printf() -> None:
        """C06-G：print(无换行) + printf(换行) 同请求 → 两标记都在本请求（换行是缓冲触发点）。"""
        _purge(transport)
        log = _cdslog(transport, f'progn(print("{mark_g1}") printf("{mark_g2}\\n") 55)')
        evidence["cases"]["G_print_plus_printf"] = {"marks": [mark_g1, mark_g2],
                                                    "CDSlog": log[:300]}
        assert mark_g1 in log and mark_g2 in log, (
            f"C06-G：同请求 print+printf 未同时落 CDSlog（mark_g1 in={mark_g1 in log}, "
            f"mark_g2 in={mark_g2 in log}；实测 {log[:200]!r}）")

    mark_h = [f"C06H{i}_{STAMP}" for i in range(5)]

    def case_h_loop_print() -> None:
        """C06-H：循环内 5 次 print（不带换行）→ 五个标记全部落同一请求（量级形态）。"""
        _purge(transport)
        items = " ".join(f'"{m}"' for m in mark_h)
        code = f'progn(foreach(x (list {items}) print(x)) 66)'
        log = _cdslog(transport, code)
        evidence["cases"]["H_loop_print"] = {"marks": mark_h, "CDSlog": log[:500]}
        missing = [m for m in mark_h if m not in log]
        assert not missing, (
            f"C06-H：循环内 print 有 {len(missing)}/{len(mark_h)} 个标记未落同一请求 CDSlog，"
            f"缺 {missing}（实测 {log[:200]!r}）")

    def case_i_long_line_print() -> None:
        """C06-I：600B 无换行长行 print → 同请求 CDSlog 仍含标记（长行不得"消失"）。"""
        _purge(transport)
        mark = f"C06I_{STAMP}_BEGIN"
        payload = mark + "L" * 600
        log = _cdslog(transport, f'progn(print("{payload}") 77)')
        evidence["cases"]["I_long_line_print"] = {"mark": mark, "payload_bytes": len(payload),
                                                  "CDSlog_len": len(log), "CDSlog": log[:200]}
        assert mark in log, (
            f"C06-I：600B 无换行长行 print 未落同一请求 CDSlog（实测空/残缺，len={len(log)}，"
            f"{log[:120]!r}）——长行丢失属 C06 同族")

    mark_j = f"C06J_{STAMP}"

    def case_j_off_between_two_logged_requests() -> None:
        """C06-J：print(all) → printf(off) → printf(all)：第三条不得带出第一条的缓冲（§3）。"""
        _purge(transport)
        log_a = _cdslog(transport, f'progn(print("{mark_j}") 88)')
        resp_b = _op(transport, "basic.skill.execute", skill_code='printf("\\n")',
                     log_level="off")
        assert resp_b.get("ok") is True, f"C06-J：off 请求失败 {resp_b.get('error')}"
        log_b = str(_payload(resp_b).get("CDSlog") or "")
        log_c = _cdslog(transport, 'printf("\\n")')
        evidence["cases"]["J_off_between"] = {"mark": mark_j, "A_CDSlog": log_a[:200],
                                              "B_off_CDSlog": log_b[:200], "C_CDSlog": log_c[:200]}
        assert mark_j in log_a, (
            f"C06-J：第一条请求（all）自己的 print 未归属到本请求的 CDSlog（实测 {log_a[:120]!r}）"
            "——修复必须归属到产生它的请求，不得靠后续请求带出（C06 本体）")
        assert log_b == "", f"C06-J：log_level=off 的 CDSlog 应为空串（实测 {log_b[:120]!r}）"
        assert mark_j not in log_c, (
            f"C06-J：第一条请求（all）的 print 缓冲串进了第三条请求的 CDSlog（实测 {log_c[:200]!r}）"
            "——跨请求串场，且说明 off 请求没有把它冲掉（C06 后果②）")

    mark_k = f"C06K_{STAMP}"

    def case_k_load_print_no_newline() -> None:
        """C06-K：load 内含 print（不带换行）→ 同请求 CDSlog 含标记（load 的 print 形态）。"""
        _purge(transport)
        remote = _upload_il(transport, f'print("{mark_k}")\n', "c06_load_k")
        try:
            log = _cdslog(transport, f'load("{remote}")')
            evidence["cases"]["K_load_print_no_newline"] = {"mark": mark_k, "remote": remote,
                                                            "CDSlog": log[:300]}
            assert mark_k in log, (
                f"C06-K：load 文件内 print（不带换行）未落同一请求 CDSlog（实测 {log[:120]!r}）")
        finally:
            _command(transport, f"rm -f {remote}")

    run("C06-ENV 环境检查（1+1）", case_env)
    run("C06-A print(不带换行) → 同一请求 CDSlog 含标记", case_a_print_no_newline)
    run("C06-B 后续请求不得串入上一条 print 的缓冲", case_b_no_leak_to_next)
    run("C06-C printf(带换行) → 同一请求 CDSlog 含标记（回归）", case_c_printf_newline_regression)
    run("C06-D print(带换行) 的 CDSlog 归属（NOTE，不作判据）", case_d_print_newline_boundary)
    run("C06-E load(printf+换行) → 同一请求 CDSlog 含标记（回归）", case_e_load_printf)
    run("C06-F 同请求 3×print(无换行) → 三标记全落本请求", case_f_multi_print_same_request)
    run("C06-G 同请求 print+printf(换行) → 两标记同落", case_g_print_plus_printf)
    run("C06-H 循环内 5×print(无换行) → 五标记全落本请求", case_h_loop_print)
    run("C06-I 600B 长行 print(无换行) → 本请求 CDSlog 含标记", case_i_long_line_print)
    run("C06-J print(all)→printf(off)→printf(all) → 第三条不串场", case_j_off_between_two_logged_requests)
    run("C06-K load(print+无换行) → 同一请求 CDSlog 含标记", case_k_load_print_no_newline)
    return results, evidence


def main() -> int:
    global API, TOKEN
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("http",), default="http")
    parser.add_argument("--api", default=API)
    parser.add_argument("--token", default=TOKEN)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    API, TOKEN = args.api, args.token
    results, evidence = run_suite(HttpTransport())
    for name, status in results:
        print(f"{status:6}  {name}")
    if args.out:
        from pathlib import Path
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
