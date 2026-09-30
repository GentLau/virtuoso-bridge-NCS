# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-30 11:20
# 依赖: 无
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查（真机靶机指纹/业务面）；②③ 造并校验基线；④ 只做被测动作；
# ⑤ 读回比对（期望/实际入证据）；⑥ 跑完不清理现场。某步不适用时，正文有一行注释说明。
"""End-to-end acceptance tests for ``virtuoso.veriloga.*``.

Run with ``--transport direct`` (in-process dispatch) or ``--transport http``
(the 8127 business face).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"
WORK_DIR = ROOT / "test" / "artifacts" / "env" / "log-vblog"
LIB, CELL, VIEW = "schemtest", "va_e2e", "veriloga"

GOOD_CODE = """// va_e2e - minimal Verilog-A
`include "constants.vams"
`include "disciplines.vams"

module va_e2e(a, b);
  inout a, b;
  electrical a, b;
  parameter real g = 2.5;
  analog V(b) <+ g * V(a);
endmodule
"""

BAD_CODE = """`include "constants.vams"
`include "disciplines.vams"

module va_e2e(a, b);
  inout a, b;
  electrical a b;
  analog V(b) <+ V(a);
endmodule
"""


class HttpTransport:
    middle = None

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
    return response


def _value(transport, operation: str, **fields: Any) -> dict[str, Any]:
    value = _op(transport, operation, **fields).get("value")
    if not isinstance(value, dict):
        raise AssertionError(f"{operation} returned no value dict")
    return value


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _case_write_create(transport) -> None:
    _value(
        transport, "virtuoso.veriloga.write",
        library=LIB, cell=CELL, view=VIEW,
        commands=[
            {"op": "ensure_view", "create_if_missing": True},
            {"op": "set_source", "text": GOOD_CODE},
        ],
    )
    source = _value(
        transport, "virtuoso.veriloga.read",
        library=LIB, cell=CELL, view=VIEW, focus=["source"],
    )
    _check("module va_e2e" in source["source"]["text"], "source text not written")
    _check(source["source"]["sha256"], "sha256 missing")


def _case_check_and_save(transport) -> None:
    checked = _value(
        transport, "virtuoso.veriloga.check_and_save",
        library=LIB, cell=CELL, view=VIEW,
    )
    _check(checked["module_name"] == "va_e2e", f"module_name: {checked}")
    names = {port["name"] for port in checked["ports"]}
    _check(names == {"a", "b"}, f"ports: {checked['ports']}")
    _check(checked["pin_order"] == ["a", "b"], f"pin_order: {checked}")
    params = {param["name"]: param for param in checked["param_list"]}
    _check(params.get("g", {}).get("default") == "2.5", f"params: {checked['param_list']}")


def _case_patch(transport) -> None:
    _value(
        transport, "virtuoso.veriloga.write",
        library=LIB, cell=CELL, view=VIEW,
        commands=[
            {"op": "patch_source",
             "edits": [{"old_text": "g * V(a)", "new_text": "(g + 1.0) * V(a)"}]},
        ],
    )
    source = _value(
        transport, "virtuoso.veriloga.read",
        library=LIB, cell=CELL, view=VIEW, focus=["source"],
    )
    _check("(g + 1.0) * V(a)" in source["source"]["text"], "patch not applied")


def _case_guard(transport) -> None:
    source = _value(
        transport, "virtuoso.veriloga.read",
        library=LIB, cell=CELL, view=VIEW, focus=["source"],
    )
    sha = source["source"]["sha256"]
    bad = transport.call({
        "operation": "virtuoso.veriloga.write", "token": TOKEN,
        "library": LIB, "cell": CELL, "view": VIEW,
        "commands": [{"op": "set_source", "text": "// x\n",
                      "expected_sha256": "0" * 64}],
    })
    _check(not bad.get("ok"), "expected_sha256 mismatch must fail")
    _check("sha256 mismatch" in (bad.get("error") or ""), f"guard error: {bad.get('error')}")
    _value(
        transport, "virtuoso.veriloga.write",
        library=LIB, cell=CELL, view=VIEW,
        commands=[{"op": "set_source", "text": GOOD_CODE, "expected_sha256": sha}],
    )


def _case_bad_syntax(transport) -> None:
    _value(
        transport, "virtuoso.veriloga.write",
        library=LIB, cell=CELL, view=VIEW,
        commands=[{"op": "set_source", "text": BAD_CODE}],
    )
    response = transport.call({
        "operation": "virtuoso.veriloga.check_and_save", "token": TOKEN,
        "library": LIB, "cell": CELL, "view": VIEW,
    })
    _check(not response.get("ok"), "bad syntax must fail check")
    errors = (response).get("value") or {}
    _check(any("VACOMP-" in item for item in errors.get("errors", [])),
           f"VACOMP diagnostics missing: {errors}")
    _value(
        transport, "virtuoso.veriloga.write",
        library=LIB, cell=CELL, view=VIEW,
        commands=[{"op": "set_source", "text": GOOD_CODE}],
    )
    _value(
        transport, "virtuoso.veriloga.check_and_save",
        library=LIB, cell=CELL, view=VIEW,
    )


def _case_delete(transport) -> None:
    _value(
        transport, "virtuoso.veriloga.write",
        library=LIB, cell=CELL, view=VIEW,
        commands=[{"op": "delete_view"}],
    )
    response = transport.call({
        "operation": "virtuoso.veriloga.read", "token": TOKEN,
        "library": LIB, "cell": CELL, "view": VIEW,
    })
    _check(not response.get("ok"), "read after delete must fail")
    # 2026-09-30 加强：断言失败**原因**是视图已不存在（证明 delete_view 真的生效），
    # 而不是别的偶发错误；并点名被删的视图路径。
    error = str(response.get("error") or "")
    _check("missing" in error.lower(), f"read 失败原因应为视图缺失（实测 {error!r}）")
    _check(VIEW in error, f"错误文案应点名视图路径（实测 {error!r}）")


def _stage_file(name: str, content: str) -> str:
    path = (ROOT / "test" / "artifacts" / "env" / "log-vblog" / "tmp-veriloga" / name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return str(path)


def _case_params(transport) -> None:
    """READ-02：file_path / file_is_local（本地+远端）+ view_type 显式路径。"""
    # ① file_is_local=True：客户端文件直接读，sha256 必须等于本地内容
    local = _stage_file("va_params.va", GOOD_CODE)
    local_read = _value(
        transport, "virtuoso.veriloga.read",
        file_path=local, file_is_local=True, focus=["source"], timeout=120,
    )
    _check(local_read["source"]["sha256"]
           == hashlib.sha256(GOOD_CODE.encode("utf-8")).hexdigest(),
           f"local file sha mismatch: {local_read['source']['sha256']}")
    # ② file_is_local=False：远端 POSIX 路径必须逐字节透传（P-081 修复后恢复断言）。
    #    通过 deOwner 查询拿 role root，再拼出视图主文件的远端路径。
    # 库路径固定：schemtest → /home/Gent/project/vblog/schemtest（vblog cds.lib）
    remote_src = "/home/Gent/project/vblog/schemtest/va_e2e/veriloga/veriloga.va"
    remote_read = _value(
        transport, "virtuoso.veriloga.read",
        file_path=remote_src, file_is_local=False, focus=["source"], timeout=120,
    )
    lib_read = _value(
        transport, "virtuoso.veriloga.read",
        library=LIB, cell=CELL, view=VIEW, focus=["source"], timeout=120,
    )
    _check(remote_read["source"]["sha256"] == lib_read["source"]["sha256"],
           "远端 file_path 读取与库路径读取 sha256 不一致（P-081）")
    _check(remote_read["source"]["path"].startswith("/"),
           f"远端 source.path 被改写：{remote_read['source']['path']}")
    # ③ view_type 显式给出（默认 text.veriloga）时 read/write/check_and_save 全部接受且语义一致
    typed = _value(
        transport, "virtuoso.veriloga.read",
        library=LIB, cell=CELL, view=VIEW, view_type="text.veriloga",
        focus=["source"], timeout=120,
    )
    _check(typed["source"]["sha256"] == lib_read["source"]["sha256"],
           "explicit view_type read must match default read")
    _value(
        transport, "virtuoso.veriloga.write",
        library=LIB, cell=CELL, view=VIEW, view_type="text.veriloga", timeout=120,
        commands=[{"op": "set_source", "text": lib_read["source"]["text"]}],
    )
    checked = _value(
        transport, "virtuoso.veriloga.check_and_save",
        library=LIB, cell=CELL, view=VIEW, view_type="text.veriloga", timeout=120,
    )
    _check(checked["module_name"] == "va_e2e",
           f"explicit view_type check_and_save: {checked}")


def run_suite(transport) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []

    def run(name: str, func: Callable[[], Any]) -> None:
        try:
            func()
            results.append((name, "PASS"))
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            raise

    run("WRITE-01 ensure_view + set_source", lambda: _case_write_create(transport))
    run("CHECK-01 check_and_save ports/params", lambda: _case_check_and_save(transport))
    run("WRITE-02 patch_source", lambda: _case_patch(transport))
    run("WRITE-03 expected_sha256 guard", lambda: _case_guard(transport))
    run("CHECK-02 bad syntax diagnostics", lambda: _case_bad_syntax(transport))
    run("READ-02 file_path/view_type params", lambda: _case_params(transport))
    run("WRITE-04 delete_view", lambda: _case_delete(transport))
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("direct", "http"), default="http",
                        help="direct=故障定位/覆盖率；真机判据必须 http")
    args = parser.parse_args()
    transport = HttpTransport() if args.transport == "http" else DirectTransport()
    try:
        results = run_suite(transport)
    finally:
        middle = getattr(transport, "middle", None)
        if middle is not None:
            middle.close()
    for name, status in results:
        print(f"{status:6}  {name}")
    return 0 if results and all(status == "PASS" for _, status in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
