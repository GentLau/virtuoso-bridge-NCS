# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-28 23:27
# 依赖: test/live/packages/maestro_e2e_tests.py（夹具与调用姿势一致）
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查（靶机指纹 / 业务面 / 夹具就位）；②③ 造并校验基线（选现有夹具，
# 不新建 cellview）；④ 只做被测动作；⑤ 读回比对（期望/实际入证据）；
# ⑥ 跑完不清理现场（history 覆盖只作用于已存在的 Interactive.*）。
"""`view` 参数专职验收：maestro 包 **全部 10 个** 带 view 的 op。

覆盖动机（第八轮 op×参数矩阵）：`virtuoso.maestro.{read_config, write, read_results,
export, read_history, write_history, open_gui, close_gui, run, open_waveform_gui}`
的 `view` 参数此前**没有任何调用点显式传值**（全部吃默认 `"maestro"`），
属于"参数名存在于请求模型但未被 TB 触碰"的缺口。

判据设计（每个 op 两件事，能观测到的才写）：

* **语义等价**：显式 `view="maestro"` 与缺省调用的返回值必须**逐字段相同**
  —— 证明显式值被接收且不改变语义；
* **参数可达**（只读 op）：传一个不存在的 view 必须**结构化失败**，且错误文本里
  出现该 view 名 —— 证明这个参数真的进了实现（不是被静默丢弃后返回默认 view 的数据）。

写类 op（write / write_history / run / open_gui / open_waveform_gui）**只做正例**：
`_open_session` 走 `maeOpenSetup`，给不存在的 view 有创建 cellview 的副作用，
不适合做负例（改由只读族承担"参数可达"证明）。

两种传输：``--transport direct``（进程内 dispatch）/ ``--transport http``（8127 业务面）。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"
WORK_DIR = ROOT / "test" / "artifacts" / "env" / "log-vblog"
EVIDENCE = ROOT / "test" / "artifacts" / "evidence" / "round8" / "maestro-view-params"
VIEW = "maestro"
BOGUS_VIEW = "no_such_view_tb"

class HttpTransport:
    def __init__(self) -> None:
        self.middle = None

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        import urllib.request

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            API, data=body, headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=900) as response:
            return json.loads(response.read().decode("utf-8"))


class DirectTransport:
    def __init__(self) -> None:
        from common.paths import init_work_dir
        from server import dispatch
        from server.api_server import register_packages
        from transport.middle import BusinessServer

        init_work_dir(str(WORK_DIR))
        register_packages()
        self.dispatch = dispatch
        self.middle = BusinessServer()

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        status, body = self.dispatch.dispatch(self.middle, payload)
        if status != 200:
            if isinstance(body, dict):
                return body
            return {"ok": False, "error": f"dispatch status {status}: {body}"}
        return body


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _op(transport, operation: str, **fields: Any) -> Any:
    response = transport.call({"operation": operation, "token": TOKEN, **fields})
    if not response.get("ok"):
        raise AssertionError(
            f"{operation} failed: {response.get('error')}; data={response.get('data')}"
        )
    return response["data"]


def _value(transport, operation: str, **fields: Any) -> dict[str, Any]:
    data = _op(transport, operation, **fields)
    value = data.get("value")
    if not isinstance(value, dict):
        raise AssertionError(f"{operation} returned no value dict: {data}")
    return value


def _expect_fail_text(transport, operation: str, **fields: Any) -> tuple[str, dict]:
    """断言结构化失败并返回错误文本（HTTP 4xx 也算失败）。"""
    import urllib.error

    try:
        response = transport.call({"operation": operation, "token": TOKEN, **fields})
    except urllib.error.HTTPError as error:
        return f"HTTP {error.code}: {error.read().decode('utf-8', 'replace')[:300]}", {}
    data = response.get("data") or {}
    ok = response.get("ok")
    if ok is not False and data.get("ok") is not False:
        raise AssertionError(f"{operation} expected structured failure, got ok: {response}")
    return str(response.get("error") or data.get("error") or ""), response


def _existing_history(transport, cell: str, prefix: str = "Interactive.") -> str:
    value = _value(transport, "virtuoso.maestro.read_history",
                   library="maestro_tb", cell=cell, view=VIEW)
    names = [str(item.get("name")) for item in value.get("histories") or []
             if str(item.get("name", "")).startswith(prefix)]
    _check(bool(names), f"no {prefix}* history fixture in maestro_tb/{cell}")
    return names[-1]


# --- 只读族：显式值语义等价 + 不存在的 view 必须结构化失败 ---------------------

def _case_read_config(transport, ev: dict) -> None:
    base = dict(library="maestro_tb", cell="rc_probe")
    default = _value(transport, "virtuoso.maestro.read_config", **base)
    explicit = _value(transport, "virtuoso.maestro.read_config", **base, view=VIEW)
    _check(default == explicit,
           "read_config: 显式 view=maestro 与缺省返回不一致")
    ev["read_config"] = {"default_keys": sorted(default)[:8],
                         "explicit_equal": True,
                         "variables": len(default.get("variables") or {})}

    error, raw = _expect_fail_text(
        transport, "virtuoso.maestro.read_config", **base, view=BOGUS_VIEW)
    _check(BOGUS_VIEW in error,
           f"read_config: 不存在的 view 未在错误里体现（error={error[:200]}）")
    ev["read_config_bogus"] = {"error": error[:300], "ok": raw.get("ok")}


def _case_read_history(transport, ev: dict) -> None:
    base = dict(library="maestro_tb", cell="rc_probe")
    default = _value(transport, "virtuoso.maestro.read_history", **base)
    explicit = _value(transport, "virtuoso.maestro.read_history", **base, view=VIEW)
    _check(default.get("histories") == explicit.get("histories"),
           "read_history: 显式 view=maestro 与缺省返回不一致")
    _check(explicit.get("current_history") == default.get("current_history"),
           "read_history: current_history 不一致")
    ev["read_history"] = {"count": len(default.get("histories") or []),
                          "current": default.get("current_history")}

    error, _ = _expect_fail_text(
        transport, "virtuoso.maestro.read_history", **base, view=BOGUS_VIEW)
    _check(BOGUS_VIEW in error,
           f"read_history: 不存在的 view 未在错误里体现（error={error[:200]}）")
    ev["read_history_bogus"] = {"error": error[:300]}


def _case_read_results(transport, ev: dict, history: str) -> None:
    # 夹具说明：`rc_probe` 的 history 会被别的工作流换成 `MonteCarlo.*`（无 ac 点），
    # 所以这里统一用 `logic_probe` 的 `Interactive.*`（自带 tran 结果，读回稳定）。
    base = dict(library="maestro_tb", cell="logic_probe", history=history,
                test="logic_tb")
    default = _value(transport, "virtuoso.maestro.read_results", **base)
    explicit = _value(transport, "virtuoso.maestro.read_results", **base, view=VIEW)
    _check(default.get("tests") == explicit.get("tests"),
           "read_results: 显式 view=maestro 与缺省 tests 不一致")
    _check(default.get("points") == explicit.get("points"),
           "read_results: 显式 view=maestro 与缺省 points 不一致")
    ev["read_results"] = {"tests": explicit.get("tests"),
                          "points": len(explicit.get("points") or [])}

    error, _ = _expect_fail_text(
        transport, "virtuoso.maestro.read_results", **base, view=BOGUS_VIEW)
    _check(BOGUS_VIEW in error,
           f"read_results: 不存在的 view 未在错误里体现（error={error[:200]}）")
    ev["read_results_bogus"] = {"error": error[:300]}


def _case_export(transport, ev: dict) -> None:
    base = dict(library="maestro_tb", cell="rc_probe", kind="snapshot")
    default = _value(transport, "virtuoso.maestro.export", **base)
    explicit = _value(transport, "virtuoso.maestro.export", **base, view=VIEW)
    default_files = {Path(p).name for p in default.get("files") or []}
    explicit_files = {Path(p).name for p in explicit.get("files") or []}
    _check(default_files == explicit_files,
           f"export(snapshot): 显式 view 与缺省产物不一致 {default_files} vs {explicit_files}")
    _check("maestro.sdb" in explicit_files or "active.state" in explicit_files,
           f"export(snapshot): 默认 view 下没拿到 sdb/state：{sorted(explicit_files)}")
    ev["export"] = {"files": sorted(explicit_files)}

    error, raw = _expect_fail_text(
        transport, "virtuoso.maestro.export", **base, view=BOGUS_VIEW)
    bogus_files = {Path(p).name for p in
                   (raw.get("data") or {}).get("value", {}).get("files") or []}
    _check(not bogus_files,
           f"export(snapshot): 不存在的 view 仍导出真实文件 {sorted(bogus_files)}")
    ev["export_bogus"] = {"error": error[:300], "files": sorted(bogus_files)}


# --- 写类：只做正例（显式 view 与缺省行为等价，且不引入额外副作用） -------------

def _case_write(transport, ev: dict) -> None:
    base = dict(library="maestro_tb", cell="rc_probe")
    name = f"view_param_{time.strftime('%H%M%S')}"
    data = _op(transport, "virtuoso.maestro.write", **base, view=VIEW, save=False,
               commands=[{"op": "set_var", "name": name, "value": "1.0",
                          "scope": "global"}])
    steps = [s.get("name") for s in data.get("steps") or []]
    _check("command:set_var" in steps, f"write: 变量命令未执行 {steps}")
    _check("save_setup" not in steps, f"write(save=False): 仍落盘 {steps}")
    ev["write"] = {"steps": steps}


def _case_write_history(transport, ev: dict, history: str) -> None:
    base = dict(library="maestro_tb", cell="logic_probe")
    data = _op(transport, "virtuoso.maestro.write_history", **base, view=VIEW,
               commands=[{"op": "lock", "history": history},
                         {"op": "unlock", "history": history}])
    steps = [s.get("name") for s in data.get("steps") or []]
    _check(any("lock" in s for s in steps),
           f"write_history: 未见 lock/unlock 步骤 {steps}")
    detail = _value(transport, "virtuoso.maestro.read_history", **base,
                    history=history, view=VIEW)
    _check(not detail["history"].get("lock_flag"),
           f"write_history: lock/unlock 未回到未锁状态 {detail['history']}")
    ev["write_history"] = {"steps": steps, "lock_flag": detail["history"].get("lock_flag")}


def _case_gui_lifecycle(transport, ev: dict) -> None:
    base = dict(library="maestro_tb", cell="logic_probe")
    opened = _value(transport, "virtuoso.maestro.open_gui", **base, view=VIEW)
    _check(bool(opened.get("session")), f"open_gui(view): 未返回 session {opened}")
    closed = _value(transport, "virtuoso.maestro.close_gui", **base, view=VIEW)
    _check(closed.get("closed") is True, f"close_gui(view): 未关闭 {closed}")
    ev["gui"] = {"session": opened.get("session"), "closed": closed.get("closed")}


def _case_waveform_gui(transport, ev: dict, history: str) -> None:
    base = dict(library="maestro_tb", cell="logic_probe")
    opened = _value(transport, "virtuoso.maestro.open_waveform_gui", **base,
                    view=VIEW, history=history, test="logic_tb",
                    analysis="tran", signals=["Q", "CLK", "Y"])
    _check(bool(opened.get("window")), f"open_waveform_gui(view): 无窗口 {opened}")
    closed = _value(transport, "virtuoso.maestro.close_waveform_gui",
                    session=opened["session"], window=opened["window"])
    _check(closed.get("closed"), f"close_waveform_gui: 未关闭 {closed}")
    ev["waveform"] = {"history": history, "window": opened.get("window")}


def _case_run(transport, ev: dict, history: str) -> None:
    base = dict(library="maestro_tb", cell="logic_probe")
    value = _value(transport, "virtuoso.maestro.run", **base, view=VIEW,
                   history=history, blocking=False, timeout=120)
    got = value.get("history")
    _check(got == history,
           f"run(view, history={history}): 返回 history={got}")
    deadline = time.monotonic() + 150
    last: dict = {}
    while time.monotonic() < deadline:
        last = _value(transport, "virtuoso.maestro.read_history", **base,
                      history=history, view=VIEW).get("history") or {}
        if last.get("status") in ("done", "failed"):
            break
        time.sleep(1.0)
    _check(last.get("status") == "done",
           f"run(view): history 未 done —— {last}")
    ev["run"] = {"history": history, "status": last.get("status")}


BASE_CASES: tuple[tuple[str, Callable[[Any, dict], None]], ...] = (
    ("VIEW-01 read_config", _case_read_config),
    ("VIEW-02 read_history", _case_read_history),
    ("VIEW-03 export(snapshot)", _case_export),
    ("VIEW-04 write(save=False)", _case_write),
    ("VIEW-05 open_gui/close_gui", _case_gui_lifecycle),
)


def run_suite(transport) -> tuple[list[tuple[str, str]], dict]:
    ev: dict[str, Any] = {
        "view": VIEW, "bogus_view": BOGUS_VIEW,
        "transport": type(transport).__name__,
    }
    results: list[tuple[str, str]] = []

    def run(name: str, fn, *args) -> None:
        try:
            fn(transport, ev, *args)
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            raise
        results.append((name, "PASS"))

    for name, fn in BASE_CASES:
        run(name, fn)

    logic_history = _existing_history(transport, "logic_probe")
    run("VIEW-06 read_results", _case_read_results, logic_history)
    run("VIEW-07 write_history lock/unlock", _case_write_history, logic_history)
    run("VIEW-08 run(history)", _case_run, logic_history)
    run("VIEW-09 open_waveform_gui", _case_waveform_gui, logic_history)
    return results, ev


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("direct", "http"), default="http")
    parser.add_argument("--out", default=str(EVIDENCE / "maestro-view-params.json"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    transport = HttpTransport() if args.transport == "http" else DirectTransport()
    ev: dict[str, Any] = {}
    try:
        results, ev = run_suite(transport)
    finally:
        middle = getattr(transport, "middle", None)
        if middle is not None:
            middle.close()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"cases": results, "evidence": ev}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for name, status in results:
            print(f"{status:6}  {name}")
        print(f"[evidence] {out}")
    return 0 if results and all(s == "PASS" for _, s in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
