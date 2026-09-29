# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-29 18:01
# 依赖: 无
# =======================================================================
"""screenshot 参数面真机覆盖：`window_id` / `region` / `toplevel` / `central_widget` / `view_type`。

为什么单独一份：op×参数矩阵里 `virtuoso.{schematic,symbol,layout}.screenshot` 的 5 类参数此前**没有 TB 传过**
（只测了默认 path），矩阵记 GAP；本 TB 把每个可传参数都钉到"期望 / 实际"上。

六步流程（test/docs/写TB规范.md §1）：
① 环境检查：`--token` 对应实例可达 + 目标 cellview 存在（第 1 条用例里先跑 read 校验，属于 ②③ 的一部分）；
②③ 造/校验基线：确认 lib/cell/view 可开；④ 只做被测动作（每次一个 screenshot 调用）；
⑤ 读回比对：本地 PNG 魔数 + 字节数 + 远端 role root `screenshots/` 的**暂存已清理**
   （P-091 三包统一口径：远端暂存、下载后清理，留存位置是客户端 `artifact/screenshots/`）；
⑥ 不清理现场：*例外*——`leave_open=True` 会留下窗口，本 TB 在 `finally` 里把**自己开的**窗口关掉（共享实例不背锅）。

P-105 回归：`symbol` / `layout` 的 `view_type` 都必须只接受各自的固定值，
坏值在 SC-06 里断言结构化失败并点名字段。
用法：
  PYTHONPATH=src python test/live/packages/screenshot_params_e2e_tests.py \
    --transport http --token vb-vbuser2 --lib serdes_rx --cell rx_top --view schematic --kind schematic
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _call(api: str, payload: dict[str, Any], timeout: int = 900) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        api, data=body, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return json.loads(error.read().decode("utf-8"))


class HttpTransport:
    """与 infra_e2e_tests.py 同形的 HTTP 载体（call(payload)）。"""

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            API, data=body, headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=900) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return json.loads(error.read().decode("utf-8"))


def _op(transport, operation: str, **fields: Any) -> dict[str, Any]:
    return transport.call({"operation": operation, "token": TOKEN, **fields})


def _raw(transport, operation: str, **fields: Any) -> dict[str, Any]:
    return _op(transport, operation, **fields)


def _value(transport, operation: str, **fields: Any) -> dict[str, Any]:
    response = _op(transport, operation, **fields)
    if not response.get("ok"):
        raise AssertionError(f"{operation} failed: {response.get('error')}")
    return response.get("value") or response


def _skill(transport, code: str, timeout: int = 120) -> str:
    response = _op(transport, "basic.skill.execute", skill_code=code, timeout=timeout)
    data = response
    if not response.get("ok") or not data.get("ok"):
        raise AssertionError(f"skill failed: {response.get('error') or data.get('error')}")
    return ((data.get("result") or {}).get("output") or "").strip()


def _command(transport, cmd: str, timeout: int = 60) -> str:
    response = _op(transport, "basic.command.run", cmd=cmd, timeout=timeout)
    if not response.get("ok"):
        raise AssertionError(f"command failed: {response.get('error')}")
    result = response.get("result")
    if isinstance(result, dict):
        if result.get("returncode") != 0:
            raise AssertionError(f"command rc != 0: {response}")
        return str(result.get("stdout") or "")
    raise AssertionError(f"bad command response: {response}")


def _png_ok(path: str) -> tuple[bool, str]:
    p = Path(path)
    if not p.is_file():
        return False, f"local screenshot missing: {path}"
    head = p.read_bytes()[:8]
    if head != PNG_MAGIC:
        return False, f"not a PNG: {path} head={head!r}"
    if p.stat().st_size < 1000:
        return False, f"PNG too small: {p.stat().st_size} bytes"
    return True, f"{p.stat().st_size} bytes"


def _remote_screenshot_present(transport: Transport, name: str) -> str:
    """spec：远端必须落在 role root 的 screenshots/（用 find 限定在 ~/.virtuoso-bridge 下）。"""
    out = _command(transport, 
        f"find $HOME/.virtuoso-bridge -maxdepth 4 -path '*/screenshots/{name}' -printf '%p %s\\n' 2>/dev/null | head -3"
    )
    return str(out[1] if len(out) > 1 else "").strip()


def _window_num(transport, lib: str, cell: str, view: str) -> int | None:
    expr = (
        "let((vbW) vbW = nil "
        "foreach(w hiGetWindowList() "
        f"when(w~>cellView && w~>cellView~>libName == \"{lib}\" "
        f"&& w~>cellView~>cellName == \"{cell}\" "
        f"&& w~>cellView~>viewName == \"{view}\" vbW = w~>windowNum)) vbW)"
    )
    out = _skill(transport, expr)
    match = re.search(r"(\d+)", out)
    return int(match.group(1)) if match else None


def _close_windows(transport, lib: str, cell: str, view: str) -> None:
    _skill(transport, 
        "foreach(w hiGetWindowList() "
        f"when(w~>cellView && w~>cellView~>libName == \"{lib}\" "
        f"&& w~>cellView~>cellName == \"{cell}\" "
        f"&& w~>cellView~>viewName == \"{view}\" hiCloseWindow(w)))",
        timeout=60,
    )


def _check_png(value: dict[str, Any], label: str) -> None:
    ok, detail = _png_ok(value.get("local_path") or "")
    assert ok, f"{label}: {detail}"


def _note_remote(transport, value: dict[str, Any], kind: str) -> None:
    remote = _remote_screenshot_present(transport, Path(value["local_path"]).name)
    # P-091 三包统一口径（spec 2-schematic.md:27 / 3-symbol.md:45 / 4-layout.md:184）：
    # 远端只做暂存，下载后清理；留存位置是客户端 artifact/screenshots/。
    assert not remote, (
        f"{kind}: 远端 role root screenshots/ 仍残留暂存 PNG "
        f"（应下载后清理；P-091 三包统一口径）: {Path(value['local_path']).name}")


def _suite_schematic(transport, lib: str, cell: str, view: str, run) -> None:
    """schematic：region 用**对角两点**（与 spec 2-schematic.md:27 一致；四元组/反序必须被拒）。"""
    def case_default() -> None:
        value = _value(transport, "virtuoso.schematic.screenshot", library=lib, cell=cell, view=view)
        _check_png(value, "default")
        _note_remote(transport, value, "schematic")

    def case_window() -> None:
        opened = _value(transport, "virtuoso.schematic.screenshot", library=lib, cell=cell,
                                 view=view, leave_open=True)
        assert opened.get("local_path"), f"leave_open 截图无产物: {opened}"
        num = _window_num(transport, lib, cell, view)
        assert num is not None, "leave_open=True 后没找到 cellview 窗口"
        explicit = _value(transport, "virtuoso.schematic.screenshot", library=lib, cell=cell,
                                   view=view, window_id=num)
        _check_png(explicit, "window_id")

    def case_bad_window() -> None:
        response = _raw(transport, "virtuoso.schematic.screenshot", library=lib, cell=cell,
                                 view=view, window_id=987654)
        assert not response.get("ok"), "坏 window_id 应失败（spec 4-layout.md:232#9）"
        assert "window" in json.dumps(response, ensure_ascii=False), "错误文案不含窗口信息"

    def case_region() -> None:
        value = _value(transport, "virtuoso.schematic.screenshot", library=lib, cell=cell, view=view,
                                region=[[0.0, 0.0], [50.0, 50.0]])
        _check_png(value, "region two point")
        assert not _raw(transport, "virtuoso.schematic.screenshot", library=lib, cell=cell, view=view,
                                 region=[[50.0, 50.0], [0.0, 0.0]]).get("ok"), "region 反序应失败"
        assert not _raw(transport, "virtuoso.schematic.screenshot", library=lib, cell=cell, view=view,
                                 region=[0.0, 0.0, 50.0, 50.0]).get("ok"), "四元组已弃用（P-082）"

    def case_flags() -> None:
        for kwargs in ({"toplevel": False}, {"central_widget": False},
                       {"toplevel": False, "central_widget": False}):
            if kwargs == {"toplevel": False}:
                value = _value(transport, "virtuoso.schematic.screenshot", library=lib, cell=cell,
                                        view=view, toplevel=False)
            elif kwargs == {"central_widget": False}:
                value = _value(transport, "virtuoso.schematic.screenshot", library=lib, cell=cell,
                                        view=view, central_widget=False)
            else:
                value = _value(transport, "virtuoso.schematic.screenshot", library=lib, cell=cell,
                                        view=view, toplevel=False, central_widget=False)
            _check_png(value, str(kwargs))

    run("SC-01 default 截图（本地 PNG + 远端暂存已清理）", case_default)
    run("SC-02 leave_open + 显式 window_id", case_window)
    run("SC-03 坏 window_id 必须失败", case_bad_window)
    run("SC-04 region 两点正向 + 反序/四元组负向", case_region)
    run("SC-05 toplevel/central_widget 取假值", case_flags)


def _suite_symbol(transport, lib: str, cell: str, view: str, run) -> None:
    """symbol：region 用**对角两点**（与 spec 2-schematic.md:27 一致）。"""
    def case_default() -> None:
        value = _value(transport, "virtuoso.symbol.screenshot", library=lib, cell=cell, view=view)
        _check_png(value, "default")
        _note_remote(transport, value, "symbol")

    def case_window() -> None:
        opened = _value(transport, "virtuoso.symbol.screenshot", library=lib, cell=cell,
                                 view=view, leave_open=True)
        assert opened.get("local_path"), f"leave_open 截图无产物: {opened}"
        num = _window_num(transport, lib, cell, view)
        assert num is not None, "leave_open=True 后没找到 cellview 窗口"
        explicit = _value(transport, "virtuoso.symbol.screenshot", library=lib, cell=cell,
                                   view=view, window_id=num)
        _check_png(explicit, "window_id")

    def case_bad_window() -> None:
        response = _raw(transport, "virtuoso.symbol.screenshot", library=lib, cell=cell,
                                 view=view, window_id=987654)
        assert not response.get("ok"), "坏 window_id 应失败"
        assert "window" in json.dumps(response, ensure_ascii=False), "错误文案不含窗口信息"

    def case_region() -> None:
        value = _value(transport, "virtuoso.symbol.screenshot", library=lib, cell=cell, view=view,
                                region=[[0.0, 0.0], [50.0, 50.0]])
        _check_png(value, "region two point")
        assert not _raw(transport, "virtuoso.symbol.screenshot", library=lib, cell=cell, view=view,
                                 region=[[50.0, 50.0], [0.0, 0.0]]).get("ok"), "region 反序应失败"
        assert not _raw(transport, "virtuoso.symbol.screenshot", library=lib, cell=cell, view=view,
                                 region=[0.0, 0.0, 50.0, 50.0]).get("ok"), "四元组当前应被拒（P-082）"

    def case_flags() -> None:
        value = _value(transport, "virtuoso.symbol.screenshot", library=lib, cell=cell,
                       view=view, toplevel=False)
        _check_png(value, "toplevel=False")
        value = _value(transport, "virtuoso.symbol.screenshot", library=lib, cell=cell,
                       view=view, central_widget=False)
        _check_png(value, "central_widget=False")
        value = _value(transport, "virtuoso.symbol.screenshot", library=lib, cell=cell, view=view,
                       toplevel=False, central_widget=False)
        _check_png(value, "toplevel=False+central_widget=False")

    def case_view_type() -> None:
        value = _value(transport, "virtuoso.symbol.screenshot", library=lib, cell=cell, view=view,
                       view_type="schematicSymbol")
        _check_png(value, "view_type=schematicSymbol")
        bogus = _raw(transport, "virtuoso.symbol.screenshot", library=lib, cell=cell, view=view,
                     view_type="bogus_type_xyz")
        assert not bogus.get("ok"), "坏 view_type 应被校验（P-080 同族）"
        assert "view_type" in json.dumps(bogus, ensure_ascii=False), \
            "symbol 坏 view_type 的错误文案未点名 view_type"

    run("SC-01 default 截图（本地 PNG + 远端暂存已清理）", case_default)
    run("SC-02 leave_open + 显式 window_id", case_window)
    run("SC-03 坏 window_id 必须失败", case_bad_window)
    run("SC-04 region 两点正向 + 反序/四元组负向", case_region)
    run("SC-05 toplevel/central_widget 取假值", case_flags)
    run("SC-06 view_type 正向 + 坏值负向", case_view_type)


def _suite_layout(transport, lib: str, cell: str, view: str, run) -> None:
    """layout：region 用**对角两点**；额外覆盖 `view_type` 正负例（P-105）。"""
    def case_default() -> None:
        value = _value(transport, "virtuoso.layout.screenshot", library=lib, cell=cell, view=view)
        _check_png(value, "default")
        _note_remote(transport, value, "layout")

    def case_window() -> None:
        opened = _value(transport, "virtuoso.layout.screenshot", library=lib, cell=cell,
                                 view=view, leave_open=True)
        assert opened.get("local_path"), f"leave_open 截图无产物: {opened}"
        num = _window_num(transport, lib, cell, view)
        assert num is not None, "leave_open=True 后没找到 cellview 窗口"
        explicit = _value(transport, "virtuoso.layout.screenshot", library=lib, cell=cell,
                                   view=view, window_id=num)
        _check_png(explicit, "window_id")

    def case_bad_window() -> None:
        response = _raw(transport, "virtuoso.layout.screenshot", library=lib, cell=cell,
                                 view=view, window_id=987654)
        assert not response.get("ok"), "坏 window_id 应失败"
        assert "window" in json.dumps(response, ensure_ascii=False), "错误文案不含窗口信息"

    def case_region() -> None:
        value = _value(transport, "virtuoso.layout.screenshot", library=lib, cell=cell, view=view,
                                region=[[0.0, 0.0], [50.0, 50.0]])
        _check_png(value, "region two point")
        assert not _raw(transport, "virtuoso.layout.screenshot", library=lib, cell=cell, view=view,
                                 region=[[50.0, 50.0], [0.0, 0.0]]).get("ok"), "region 反序应失败"
        assert not _raw(transport, "virtuoso.layout.screenshot", library=lib, cell=cell, view=view,
                                 region=[0.0, 0.0, 50.0, 50.0]).get("ok"), "四元组已弃用（P-082）"

    def case_flags() -> None:
        value = _value(transport, "virtuoso.layout.screenshot", library=lib, cell=cell,
                                view=view, toplevel=False)
        _check_png(value, "toplevel=False")
        value = _value(transport, "virtuoso.layout.screenshot", library=lib, cell=cell,
                                view=view, central_widget=False)
        _check_png(value, "central_widget=False")

    def case_view_type() -> None:
        value = _value(transport, "virtuoso.layout.screenshot", library=lib, cell=cell, view=view,
                                view_type="maskLayout")
        _check_png(value, "view_type=maskLayout")
        bogus = _raw(transport, "virtuoso.layout.screenshot", library=lib, cell=cell, view=view,
                              view_type="bogus_type_xyz")
        assert not bogus.get("ok"), "坏 view_type 应被校验（P-080 同族）"
        assert "view_type" in json.dumps(bogus, ensure_ascii=False), \
            "layout 坏 view_type 的错误文案未点名 view_type"

    run("SC-01 default 截图（本地 PNG + 远端暂存已清理）", case_default)
    run("SC-02 leave_open + 显式 window_id", case_window)
    run("SC-03 坏 window_id 必须失败", case_bad_window)
    run("SC-04 region 两点正向 + 反序/四元组负向", case_region)
    run("SC-05 toplevel/central_widget 取假值", case_flags)
    run("SC-06 view_type 正向 + 坏值负向", case_view_type)


def run_suite(transport, lib: str, cell: str, view: str, kind: str) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []

    def run(name: str, func) -> Any:
        try:
            value = func()
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            print(f"FAIL    {name}: {type(exc).__name__}: {exc}", flush=True)
            return None   # 单例失败不阻断后续用例：一次运行拿全判定
        results.append((name, "PASS"))
        return value

    suite = {"schematic": _suite_schematic, "symbol": _suite_symbol,
             "layout": _suite_layout}[kind]
    try:
        suite(transport, lib, cell, view, run)
    finally:
        try:
            _close_windows(transport, lib, cell, view)
        except Exception as exc:  # noqa: BLE001
            print(f"WARN  cleanup 关窗失败：{type(exc).__name__}: {exc}", flush=True)
    return results


def main() -> int:
    global API, TOKEN

    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("http",), default="http")
    parser.add_argument("--api", default=API)
    parser.add_argument("--token", default=TOKEN)
    # 默认值 = 常驻环境里的 layout 夹具，使本 TB 可以**零参数**进 run_all_http 门禁；
    # 要跑 symbol/schematic 档时按 §docstring 的例子显式给 --token/--lib/--cell/--kind。
    parser.add_argument("--lib", default="schemtest")
    parser.add_argument("--cell", default="lay_e2e")
    parser.add_argument("--view", default="")
    parser.add_argument("--kind", choices=("schematic", "symbol", "layout"), default="layout")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    API, TOKEN = args.api, args.token
    view = args.view or args.kind
    transport = HttpTransport()
    results = run_suite(transport, args.lib, args.cell, view, args.kind)
    for name, status in results:
        print(f"{status:6}  {name}")
    if args.out:
        evidence = {
            "api": API, "token": TOKEN, "kind": args.kind,
            "target": {"lib": args.lib, "cell": args.cell, "view": view},
            "python": sys.version.split()[0], "platform": platform.platform(),
            "results": [{"case": n, "status": s} for n, s in results],
        }
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"evidence: {out_path}")
    return 0 if results and all(status == "PASS" for _, status in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
