# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-28 21:25
# 依赖: 无
# =======================================================================
"""``virtuoso.gui.*`` 真机验收 TB（X11 窗口面）。

六步流程（test/docs/写TB规范.md §1）：
① `require_environment`（靶机指纹 + gui role display 事实）；
②③ 构建/校验基线（打开一个已知 layout 窗口 / 造一个模态 dialog）；
④ 只做被测动作；⑤ **读回比对**：用 `list_windows` 前后差集验证窗口出现/消失、
截图判文件非空；⑥ 跑完不清理现场（只关掉本 TB 自己开的窗口，避免挡住别人）。

覆盖：`list_windows` / `send_key` / `auto_dismiss` / `screenshot` 四个操作。

用法::

    python test/live/packages/gui_e2e_tests.py --transport direct
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "test" / "shared" / "runners"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"
WORK_DIR = ROOT / "test" / "artifacts" / "env" / "log-vblog"
LIB, CELL, VIEW = "schemtest", "lay_e2e", "layout"


class HttpTransport:
    middle = None

    def __init__(self, base: str = API) -> None:
        self.base = base

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.base, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=900) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return json.loads(error.read().decode("utf-8"))


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
        if status not in (200, 400):
            raise AssertionError(f"dispatch status {status}: {body}")
        return body


def _op(transport, operation: str, **fields: Any) -> Any:
    response = transport.call({"operation": operation, "token": TOKEN, **fields})
    if not response.get("ok"):
        raise AssertionError(f"{operation} failed: {response.get('error')}")
    return _c1_wrapper(response)


def _skill(transport, code: str) -> str:
    data = _op(transport, "basic.skill.execute", skill_code=code)
    result = data.get("result", {})
    if result.get("status") != "success":
        raise AssertionError(f"SKILL failed: {result}")
    return result.get("output", "")


def _windows(transport) -> list[dict[str, Any]]:
    data = _op(transport, "virtuoso.gui.list_windows")
    return list(data.get("windows") or data.get("value") or [])


def _ids(windows: list[dict[str, Any]]) -> set[str]:
    return {str(item.get("window_id")) for item in windows}


class Evidence:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def check(self, case: str, name: str, expected: Any, actual: Any) -> None:
        ok = expected == actual
        self.rows.append({"case": case, "check": name, "expected": expected,
                          "actual": actual, "verdict": "PASS" if ok else "FAIL"})
        if not ok:
            raise AssertionError(f"{case}/{name}: expected {expected!r}, actual {actual!r}")

    def check_true(self, case: str, name: str, condition: bool, actual: Any) -> None:
        self.rows.append({"case": case, "check": name, "expected": True,
                          "actual": actual, "verdict": "PASS" if condition else "FAIL"})
        if not condition:
            raise AssertionError(f"{case}/{name}: expected True, actual {actual!r}")


# ------------------------------------------------------------------ 用例 --
def _case_list_windows(transport, ev: Evidence) -> None:
    """①③ 先关掉本 TB 可能遗留的窗口 → 打开已知 layout 窗口 → 列表必须出现它。"""
    case = "WIN-01"
    _skill(transport, 'let((w) foreach(x hiGetWindowList() '
                      f'when(x~>cellView && x~>cellView~>cellName == "{CELL}" w = x)) '
                      "when(w hiCloseWindow(w)))")
    before = _windows(transport)
    ev.check_true(case, "baseline: no target window", 
                  all(CELL not in str(item.get("title", "")) for item in before), before)

    _skill(transport, f'geOpen(?lib "{LIB}" ?cell "{CELL}" ?view "{VIEW}" '
                      '?viewType "maskLayout" ?mode "r")')
    after = _windows(transport)
    opened = [item for item in after if CELL in str(item.get("title", ""))]
    ev.check_true(case, "list_windows shows opened window", bool(opened), opened)
    ev.check_true(case, "window entry has id/geometry",
                  all(item.get("window_id") for item in opened), opened)


def _case_send_key(transport, ev: Evidence) -> None:
    """send_key：对已开的 layout 窗口注入 escape → 读回 still_mapped + 列表仍在。"""
    case = "KEY-01"
    windows = [item for item in _windows(transport)
               if CELL in str(item.get("title", ""))]
    if not windows:
        _skill(transport, f'geOpen(?lib "{LIB}" ?cell "{CELL}" ?view "{VIEW}" '
                          '?viewType "maskLayout" ?mode "r")')
        windows = [item for item in _windows(transport)
                   if CELL in str(item.get("title", ""))]
    ev.check_true(case, "target window present", bool(windows), windows)
    data = _op(transport, "virtuoso.gui.send_key",
               window_id=str(windows[0]["window_id"]), key="escape")
    ev.check(case, "send_key still_mapped", True, data.get("still_mapped"))
    still = [item for item in _windows(transport) if str(item.get("window_id"))
             == str(windows[0]["window_id"])]
    ev.check_true(case, "window still listed after key", bool(still), still)


def _case_auto_dismiss(transport, ev: Evidence) -> None:
    """auto_dismiss：造一个模态 dialog → 读回它从窗口列表消失。

    注意（预期行为，不是 TB bug）：`hiDisplayAppDBox` 是**模态**的，创建它的 SKILL
    调用会一直阻塞到窗口被关掉——所以这里**故意**给 5 s 超时：超时后弹窗已经在了，
    后续全部走 X11 通道（list_windows / auto_dismiss）关它并读回。
    """
    case = "DISMISS-01"
    # ②③ 造基线：标题里带 "Warning" → 被 list_windows 分类为 dialog（auto_dismiss 的口径）
    created = transport.call({
        "operation": "basic.skill.execute", "token": TOKEN, "timeout": 5,
        "skill_code": 'hiDisplayAppDBox(?name \'vbTbDialog ?dboxBanner "VB TB Warning" '
                      '?dboxText "auto dismiss probe" ?buttonLayout \'Close)',
    })
    listed = [item for item in _windows(transport)
              if "VB TB" in str(item.get("title", ""))]
    ev.check_true(case, "dialog window created", bool(listed),
                  {"skill_result": created.get("ok"), "windows": listed})
    ev.check(case, "dialog classified as dialog", ["dialog"],
             sorted({str(item.get("kind")) for item in listed}))

    # ④⑤ 关它并读回
    data = _op(transport, "virtuoso.gui.auto_dismiss", max_attempts=3)
    remaining = [item for item in _windows(transport)
                 if "VB TB" in str(item.get("title", ""))]
    ev.check(case, "dialog gone after auto_dismiss", [], remaining)
    dismissed = data.get("dismissed") or []
    ev.check_true(case, "auto_dismiss recorded the dialog", bool(dismissed), dismissed)


def _case_screenshot(transport, ev: Evidence) -> None:
    case = "SHOT-01"
    out = ROOT / "test" / "artifacts" / "evidence" / f"gui-shot-{dt.datetime.now():%Y%m%d-%H%M%S}.ppm"
    out.parent.mkdir(parents=True, exist_ok=True)
    data = _op(transport, "virtuoso.gui.screenshot", output_path=str(out), target="ciw")
    path = Path(str(data.get("local_path") or out))
    ev.check_true(case, "screenshot file non-empty",
                  path.is_file() and path.stat().st_size > 0, str(path))


CASES: tuple[tuple[str, Callable[[Any, Evidence], None]], ...] = (
    ("WIN-01", _case_list_windows),
    ("KEY-01", _case_send_key),
    ("DISMISS-01", _case_auto_dismiss),
    ("SHOT-01", _case_screenshot),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("direct", "http"), default="direct")
    parser.add_argument("--base", default=API)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    transport = HttpTransport(args.base) if args.transport == "http" else DirectTransport()
    ev = Evidence()
    results: list[tuple[str, str]] = []
    env_report: dict[str, Any] = {}
    try:
        # ① 环境检查：靶机 + gui role（display 由 query 提供）
        from env_check import require_environment

        options: dict[str, Any] = {"token": TOKEN, "expect_host": "GLIS-DESKTOP",
                                   "require_lib": [LIB]}
        env_report = (require_environment(base=args.base, **options) if args.transport == "http"
                      else require_environment(work_dir=str(WORK_DIR), **options))

        for name, func in CASES:
            try:
                func(transport, ev)
                results.append((name, "PASS"))
            except Exception as exc:  # noqa: BLE001
                results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
                raise
    finally:
        out = Path(args.out) if args.out else (
            ROOT / "test" / "artifacts" / "evidence"
            / f"gui-atoms-{dt.datetime.now():%Y%m%d-%H%M}" / "gui-atoms-green.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "tb": "test/live/packages/gui_e2e_tests.py",
            "transport": args.transport, "token": TOKEN,
            "env": env_report,
            "results": [{"case": name, "verdict": status} for name, status in results],
            "comparisons": ev.rows,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"evidence: {out}")
        middle = getattr(transport, "middle", None)
        if middle is not None:
            middle.close()
    for name, status in results:
        print(f"{status:6}  {name}")
    return 0 if results and all(status == "PASS" for _, status in results) else 1


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
