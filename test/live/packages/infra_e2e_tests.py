# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-29 20:41
# 依赖: 无
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查（真机靶机指纹/业务面）；②③ 造并校验基线；④ 只做被测动作；
# ⑤ 读回比对（期望/实际入证据）；⑥ 跑完不清理现场。某步不适用时，正文有一行注释说明。
"""End-to-end acceptance tests for basic / gui.

Run with ``--transport direct`` or ``--transport http``.

``--api`` / ``--token`` / ``--work-dir`` 用于换客户端跑同一套用例（例如 Linux
客户端指向本机业务面），默认值保持 Windows 常驻环境口径不变。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import posixpath
import sys
import time
from concurrent.futures import ThreadPoolExecutor
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"
WORK_DIR = ROOT / "test" / "artifacts" / "env" / "log-vblog"
SCRATCH = WORK_DIR / "infra_e2e"
SCRATCH.mkdir(parents=True, exist_ok=True)


def _remote_run_dir(case: str) -> str:
    """Resolve a per-run directory from the registry's file role root."""
    registry = json.loads((WORK_DIR / "registry.json").read_text(encoding="utf-8"))
    entry = next(
        item for item in registry.values()
        if isinstance(item, dict) and item.get("token") == TOKEN
    )
    role = (entry.get("roles") or {}).get("file") or {}
    root = role.get("root") or (entry.get("root") or {}).get("default")
    if not root:
        raise AssertionError("file role root is not configured")
    return posixpath.join(
        str(root).rstrip("/"), "tmp", "tb", f"infra-{case}-{uuid.uuid4().hex[:8]}"
    )


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
        from common import config as config_base
        from common.paths import config_path, init_work_dir
        from server import dispatch
        from server.api_server import register_packages
        from transport.middle import BusinessServer

        init_work_dir(str(WORK_DIR))
        config_base.init_config(config_path())
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


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _case_basic(transport) -> None:
    skill = _op(transport, "basic.skill.execute", skill_code="1+1")
    _check("2" in (skill.get("result", {}).get("output") or ""), f"skill: {skill}")

    command = _op(transport, "basic.command.run", cmd="echo bridge-ok")
    command_result = command.get("result") or {}
    _check(command_result.get("returncode") == 0
           and "bridge-ok" in str(command_result.get("stdout") or ""),
           f"command: {command}")

    gui = _op(transport, "basic.gui.run", cmd="echo gui-ok")
    _check((gui.get("result") or {}).get("returncode") == 0, f"gui: {gui}")

    spectre = _op(transport, "basic.spectre.run", cmd="echo spectre-ok", timeout=30)
    _check((spectre.get("result") or {}).get("returncode") == 0,
           f"spectre: {spectre}")


def _case_file_roundtrip(transport) -> None:
    local_in = SCRATCH / "roundtrip_in.txt"
    local_in.write_text("vb-file-roundtrip\n", encoding="utf-8")
    run_dir = _remote_run_dir("roundtrip")
    remote = posixpath.join(run_dir, "roundtrip.txt")
    local_out = SCRATCH / "roundtrip_out.txt"
    up = _op(transport, "basic.file.upload",
             local_path=str(local_in), remote_path=remote)
    _check((up.get("result") or {}).get("returncode") == 0, f"upload: {up}")
    down = _op(transport, "basic.file.download",
               remote_path=remote, local_path=str(local_out))
    _check((down.get("result") or {}).get("returncode") == 0, f"download: {down}")
    _check(local_out.read_text(encoding="utf-8") == local_in.read_text(encoding="utf-8"),
           "file roundtrip mismatch")
    _op(transport, "basic.command.run", cmd=f"rm -rf {run_dir}")


def _case_recursive_file_tree(transport) -> None:
    """`recursive=True` 的目录上/下行：两层树、逐字节回环。"""
    tree = SCRATCH / "rt_tree"
    if tree.exists():
        for path in sorted(tree.rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
    (tree / "inner").mkdir(parents=True, exist_ok=True)
    (tree / "root.txt").write_text("root-level\n", encoding="utf-8")
    (tree / "inner" / "leaf.txt").write_text("leaf-level\n", encoding="utf-8")
    (tree / "inner" / "blob.bin").write_bytes(bytes(range(256)) * 4)

    run_dir = _remote_run_dir("rt-tree")
    up = _op(transport, "basic.file.upload",
             local_path=str(tree), remote_path=run_dir, recursive=True, timeout=120)
    _check((up.get("result") or {}).get("returncode") == 0,
           f"recursive upload: {up}")
    listing = _op(transport, "basic.command.run",
                  cmd=f"find {run_dir} -type f | sort", timeout=60)
    files = str((listing.get("result") or {}).get("stdout") or "")
    _check("root.txt" in files and "leaf.txt" in files and "blob.bin" in files,
           f"remote tree incomplete: {files}")

    back = SCRATCH / "rt_tree_back"
    if back.exists():
        for path in sorted(back.rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
    down = _op(transport, "basic.file.download",
               remote_path=run_dir, local_path=str(back), recursive=True, timeout=120)
    _check((down.get("result") or {}).get("returncode") == 0,
           f"recursive download: {down}")
    got = sorted(p.relative_to(back).as_posix() for p in back.rglob("*") if p.is_file())
    want = sorted(p.relative_to(tree).as_posix() for p in tree.rglob("*") if p.is_file())
    _check(got == want, f"tree file set mismatch: got={got} want={want}")
    for rel in want:
        src = (tree / rel).read_bytes()
        dst = (back / rel).read_bytes()
        _check(hashlib.sha256(src).digest() == hashlib.sha256(dst).digest(),
               f"recursive bytes mismatch: {rel}")
    _op(transport, "basic.command.run", cmd=f"rm -rf {run_dir}", timeout=60)


def _case_command_parallel(transport) -> None:
    """spec §5.7：命令默认串行；`parallel=True` 时两条 sleep 必须真正并行。"""
    def timed(parallel: bool) -> float:
        def one() -> dict[str, Any]:
            return _op(transport, "basic.command.run",
                       cmd="sleep 2; echo done", parallel=parallel, timeout=60)

        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(one) for _ in range(2)]
            for future in futures:
                result = future.result()
                _check((result.get("result") or {}).get("returncode") == 0,
                       f"sleep command failed: {result}")
        return time.monotonic() - started

    serial = timed(False)
    parallel = timed(True)
    _check(serial > 3.6, f"serial commands must not overlap: {serial:.2f}s")
    _check(parallel < 3.6, f"parallel=True must overlap: {parallel:.2f}s")


def _case_command_timeout(transport) -> None:
    """spec §4.5/§5.8：命令超时必须 kind=timeout / rc=124，而不是普通失败。"""
    response = transport.call({
        "operation": "basic.command.run", "token": TOKEN,
        "cmd": "sleep 5", "timeout": 1})
    _check(not response.get("ok"), "sleep 5 with timeout=1 must fail")
    result = (response).get("result") or {}
    _check(result.get("returncode") == 124,
           f"timeout rc must be 124: {result}")
    detail = (response).get("steps") or [{}]
    kind = ((detail[0].get("detail") or {}).get("kind")
            if isinstance(detail[0].get("detail"), dict) else None)
    if kind is not None:
        _check(kind == "timeout", f"timeout kind must be 'timeout': {kind}")


def _case_basic_negative(transport) -> None:
    """`basic.*` 四接口的非法档 / 返回值语义（2026-09-30 补：这几个 op 此前只有正例）。

    判据（值级）：
      * `skill.execute("1+")`（语法错）→ **结构化失败**且错误文本非空；
      * `command.run("exit 7")` → **业务失败**（`ok=false`，与超时/传输失败可区分），
        错误文本点名 `rc=7`，且具名 `result.returncode == 7` 原样回传；
      * `command.run("<不存在的命令>")` → 同上，`rc=127`；
      * `gui.run` / `spectre.run` 同口径（不存在命令 → 业务失败、不崩）。
    """
    bad_skill = transport.call({
        "operation": "basic.skill.execute", "token": TOKEN, "skill_code": "1+"})
    _check(not bad_skill.get("ok"), "语法错 SKILL 必须结构化失败")
    _check(bool(str(bad_skill.get("error") or "").strip()),
           f"失败必须带错误文本：{bad_skill}")

    exit7 = transport.call({"operation": "basic.command.run", "token": TOKEN,
                            "cmd": "exit 7"})
    _check(not exit7.get("ok"), f"非零退出应判业务失败：{exit7}")
    _check("rc=7" in str(exit7.get("error") or ""),
           f"错误文本应点名 rc=7：{exit7.get('error')!r}")
    _check((exit7.get("result") or {}).get("returncode") == 7,
           f"具名 result.returncode 必须原样回传 7：{exit7.get('result')}")

    missing = transport.call({"operation": "basic.command.run", "token": TOKEN,
                              "cmd": "no_such_cmd_bridge_qq"})
    _check(not missing.get("ok"), f"不存在的命令应判失败：{missing}")
    _check((missing.get("result") or {}).get("returncode") == 127,
           f"不存在的命令 rc 应为 127：{missing.get('result')}")

    for label, operation in (("gui", "basic.gui.run"), ("spectre", "basic.spectre.run")):
        response = transport.call({"operation": operation, "token": TOKEN,
                                   "cmd": "no_such_cmd_bridge_qq", "timeout": 30})
        rc = (response.get("result") or {}).get("returncode")
        _check(not response.get("ok") and rc not in (0, None),
               f"{label}.run 不存在命令应业务失败且 rc 非 0：{response}")


def _case_gui(transport) -> None:
    listing = _op(transport, "virtuoso.gui.list_windows")
    _check(listing.get("ok") and isinstance(listing.get("windows"), list),
           f"list_windows: {listing}")

    dismissed = _op(transport, "virtuoso.gui.auto_dismiss", max_attempts=1)
    _check(dismissed.get("ok"), f"auto_dismiss: {dismissed}")

    # send_key against a nonexistent window: exercises the injection path and
    # must fail with a structured X11 error (bad window), not a crash.
    response = transport.call({
        "operation": "virtuoso.gui.send_key", "token": TOKEN,
        "window_id": "0xdeadbeef", "key": "enter",
    })
    _check(not response.get("ok"), f"send_key bad window must fail: {response}")
    _check("BadWindow" in (response.get("error") or ""),
           f"send_key error text: {response.get('error')}")

    output = SCRATCH / "ciw.ppm"
    shot = _op(transport, "virtuoso.gui.screenshot",
               target="ciw", output_path=str(output))
    _check(shot.get("ok") and output.is_file() and output.stat().st_size > 0,
           f"screenshot: {shot}")


def run_suite(transport) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []

    def run(name: str, func: Callable[[], Any]) -> None:
        try:
            func()
            results.append((name, "PASS"))
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            raise

    run("BASIC-01 skill/command/gui/spectre", lambda: _case_basic(transport))
    run("BASIC-02 file upload/download", lambda: _case_file_roundtrip(transport))
    run("BASIC-03 recursive file tree", lambda: _case_recursive_file_tree(transport))
    run("BASIC-04 command serial/parallel", lambda: _case_command_parallel(transport))
    run("BASIC-05 command timeout semantics", lambda: _case_command_timeout(transport))
    run("BASIC-06 basic.* 非法档/返回码语义", lambda: _case_basic_negative(transport))
    # 注：**故意不**在常驻门禁里做"投递超时 → dirty"用例：该操作会把**共享实例**
    # 置为 dirty/busy（P-086 语义：需重启 CIW 才恢复），会毒化其他人正在用的实例
    # （2026-09-30 实测踩到：vblog 直连 daemon 报 `SKILL channel busy`，需按 Runbook §10.10 重启）。
    # 该语义由**可丢弃 CIW** 的 `test/live/transport/disposable_ciw_c06_p086_tb.py` 覆盖
    # （它自己重启 destb1，判据见 `evidence/round9/disposable-c06-p086-r9-verify.json`）。
    run("GUI-01 list/auto_dismiss/send_key/screenshot", lambda: _case_gui(transport))
    return results


def main() -> int:
    global API, TOKEN, WORK_DIR, SCRATCH

    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("direct", "http"), default="http",
                        help="direct=故障定位/覆盖率；真机判据必须 http")
    parser.add_argument("--api", default=API,
                        help="HTTP business face, e.g. http://127.0.0.1:8127/api/operation")
    parser.add_argument("--token", default=TOKEN)
    parser.add_argument("--work-dir", default=str(WORK_DIR))
    parser.add_argument("--out", default=None, help="write JSON evidence to this path")
    args = parser.parse_args()
    API = args.api
    TOKEN = args.token
    WORK_DIR = Path(args.work_dir)
    SCRATCH = WORK_DIR / "infra_e2e"
    SCRATCH.mkdir(parents=True, exist_ok=True)
    transport = HttpTransport() if args.transport == "http" else DirectTransport()
    try:
        results = run_suite(transport)
    finally:
        middle = getattr(transport, "middle", None)
        if middle is not None:
            middle.close()
    for name, status in results:
        print(f"{status:6}  {name}")
    if args.out:
        evidence = {
            "transport": args.transport,
            "api": API,
            "token": TOKEN,
            "work_dir": str(WORK_DIR),
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "results": [{"case": name, "status": status} for name, status in results],
        }
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        print(f"evidence: {out_path}")
    return 0 if results and all(status == "PASS" for _, status in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
