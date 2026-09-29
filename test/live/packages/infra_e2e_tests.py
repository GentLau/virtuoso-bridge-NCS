# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-28 22:10
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
    return _c1_wrapper(response)


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _case_basic(transport) -> None:
    skill = _op(transport, "basic.skill.execute", skill_code="1+1")
    _check("2" in (skill.get("result", {}).get("output") or ""), f"skill: {skill}")

    command = _op(transport, "basic.command.run", cmd="echo bridge-ok")
    command_result = command.get("result") or []
    _check(command_result[0] == 0 and "bridge-ok" in command_result[1],
           f"command: {command}")

    gui = _op(transport, "basic.gui.run", cmd="echo gui-ok")
    _check((gui.get("result") or [1])[0] == 0, f"gui: {gui}")

    spectre = _op(transport, "basic.spectre.run", cmd="echo spectre-ok", timeout=30)
    _check((spectre.get("result") or [1])[0] == 0, f"spectre: {spectre}")


def _case_file_roundtrip(transport) -> None:
    local_in = SCRATCH / "roundtrip_in.txt"
    local_in.write_text("vb-file-roundtrip\n", encoding="utf-8")
    run_dir = _remote_run_dir("roundtrip")
    remote = posixpath.join(run_dir, "roundtrip.txt")
    local_out = SCRATCH / "roundtrip_out.txt"
    up = _op(transport, "basic.file.upload",
             local_path=str(local_in), remote_path=remote)
    _check((up.get("result") or [1])[0] == 0, f"upload: {up}")
    down = _op(transport, "basic.file.download",
               remote_path=remote, local_path=str(local_out))
    _check((down.get("result") or [1])[0] == 0, f"download: {down}")
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
    _check((up.get("result") or [1])[0] == 0, f"recursive upload: {up}")
    listing = _op(transport, "basic.command.run",
                  cmd=f"find {run_dir} -type f | sort", timeout=60)
    files = (listing.get("result") or ["", ""])[1]
    _check("root.txt" in files and "leaf.txt" in files and "blob.bin" in files,
           f"remote tree incomplete: {files}")

    back = SCRATCH / "rt_tree_back"
    if back.exists():
        for path in sorted(back.rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
    down = _op(transport, "basic.file.download",
               remote_path=run_dir, local_path=str(back), recursive=True, timeout=120)
    _check((down.get("result") or [1])[0] == 0, f"recursive download: {down}")
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
                _check((result.get("result") or [1])[0] == 0,
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
    result = (_c1_wrapper(response)).get("result") or []
    _check(result and result[0] == 124,
           f"timeout rc must be 124: {result}")
    detail = (_c1_wrapper(response)).get("steps") or [{}]
    kind = ((detail[0].get("detail") or {}).get("kind")
            if isinstance(detail[0].get("detail"), dict) else None)
    if kind is not None:
        _check(kind == "timeout", f"timeout kind must be 'timeout': {kind}")


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
    run("GUI-01 list/auto_dismiss/send_key/screenshot", lambda: _case_gui(transport))
    return results


def main() -> int:
    global API, TOKEN, WORK_DIR, SCRATCH

    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("direct", "http"), default="direct")
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
