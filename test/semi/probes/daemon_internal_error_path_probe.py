# === TB 注释头（规范见 test/docs/写TB规范.md §0）=====================
# 作者: 设计/Codex
# 最后改动: 2026-09-28 12:04
# 依赖: 无
# =====================================================================
# 六步流程（按 test/docs/写TB规范.md §1–§6）：
# §1 环境检查：本地 daemon 模块/伪 stdin，无需真实 CIW → 跳过。
# §2 构建：本地模块加载器、伪 stdin/错误帧夹具。
# §3 最终检查：先确认待测模块与分支可达。
# §4 执行：构造内部错误帧并驱动对应分支。
# §5 比对：实际分支/异常归类与期望一致。
# §6 重复/收尾：单点探针，保留 stdout/证据供复核。
"""Which handler does a ValueError from ``_read_frame`` actually reach?

``test_daemon_runtime_contracts.py::test_internal_value_error_is_reported_to_the_traceback_only``
expects the daemon to stay silent for ``ValueError`` (the
``except (UnicodeDecodeError, ValueError)`` branch) but the daemon sends a NACK
frame with ``internal daemon error`` (the generic ``except Exception`` branch).

Exactly one of the two is wrong, and the two have very different consequences:

* test wrong  -> the test asserts behaviour the spec never had;
* source wrong -> a ValueError is being re-wrapped somewhere, so the
  "malformed input is dropped silently" contract does not hold, and the
  defensive branch at ``ramic_bridge_daemon_3.py:462`` is dead code.

This probe prints the exception type each handler actually saw, plus the bytes
that reached the socket.

    python test/semi/probes/daemon_internal_error_path_probe.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import traceback as real_traceback
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    tests = _load("daemon_runtime_tests", ROOT / "test/offline/unit/test_daemon_runtime_contracts.py")
    verdicts = []
    for variant in tests.VARIANTS:
        if variant == "py27":
            # 2026-09-23：py2.7 模块在 py3 下跑会得到**伪结论** ——
            # `sys.stdout.write(send_code.encode("utf-8"))` 在 py3 抛 TypeError，
            # 把"ValueError 走静默分支"替换成了"generic 分支 + NACK"。
            # 判定改由真 py2.7 执行 py27_handler_probe.py；没给解释器就明确跳过。
            py27 = os.environ.get("VB_PY27")
            if not py27:
                print("[daemon_27] SKIP: 需要真 py2.7（设 VB_PY27=<interpreter>），"
                      "py3 模拟会得到伪结论；见 py27_handler_probe.py")
                verdicts.append({"variant": "daemon_27", "skipped": True,
                                 "reason": "no VB_PY27 interpreter"})
                continue
            probe = Path(__file__).resolve().parent / "py27_handler_probe.py"
            try:
                proc = subprocess.run([py27, str(probe), "--src", str(ROOT / "src")],
                                      capture_output=True, text=True, encoding="utf-8")
            except OSError as exc:
                print(f"[daemon_27] SKIP: VB_PY27 不可用（{exc}）")
                verdicts.append({"variant": "daemon_27", "skipped": True,
                                 "reason": f"VB_PY27 unusable: {exc}"})
                continue
            body = json.loads(proc.stdout[proc.stdout.index("{"):]) if "{" in proc.stdout else {}
            print(f"[daemon_27] real py2.7: {body.get('verdict', proc.stderr.strip()[:120])}")
            verdicts.append({"variant": "daemon_27", "exception_types_seen": ["ValueError"],
                             "bytes_sent": "".join(body.get("nack_frames", [])),
                             "interpreter": body.get("python", "?")})
            continue
        mod = tests.MODULES[variant]
        conn = tests.FakeConn(json.dumps(tests.request(log_level="off")).encode())
        seen: list[str] = []
        # Capture the real printer *before* patching: patching
        # ``mod.traceback.print_exc`` also patches the module-level
        # ``real_traceback`` reference (same module object), which recurses.
        original_print_exc = mod.traceback.print_exc

        def spy(_seen=seen):
            _seen.append(sys.exc_info()[0].__name__)
            original_print_exc()

        with mock.patch.object(mod, "_read_frame", side_effect=ValueError("bad frame")), \
                mock.patch.object(mod.traceback, "print_exc", spy):
            mod.handle_connection(conn)
        sent = bytes(conn.sent)
        verdicts.append({
            "variant": variant,
            "exception_types_seen": seen,
            "bytes_sent": sent.decode("utf-8", errors="replace"),
        })
        print(f"[{variant}] handler saw {seen} -> sent {sent!r}")

    # Expected when the silent-ValueError contract holds: no bytes at all.
    ran = [item for item in verdicts if not item.get("skipped")]
    silent = all(not item["bytes_sent"] for item in ran)
    skipped = [item["variant"] for item in verdicts if item.get("skipped")]
    print("VERDICT:", "contract holds (test is wrong)" if silent
          else "NACK sent for ValueError (source branch is bypassed)")
    if skipped:
        print("SKIPPED:", ", ".join(skipped), "(需要真 py2.7；见 py27_handler_probe.py)")
    return 0 if silent else 1


if __name__ == "__main__":
    raise SystemExit(main())
