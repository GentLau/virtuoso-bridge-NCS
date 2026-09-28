# === TB 注释头（规范见 test/docs/写TB规范.md §0）=====================
# 作者: 设计/Codex
# 最后改动: 2026-09-28 17:45
# 依赖: 无
# =====================================================================
# 六步流程（按 test/docs/写TB规范.md §1–§6）：
# §1 环境检查：离线确定性 case，不需要远端环境（写注释跳过）。
# §2 构建：构造“channel 已结束 + 本地 tar 已退出 + pump 线程卡死”的夹具。
# §3 最终检查：确认两个完成门已就绪、pump 仍 alive。
# §4 执行：调用真实 _wait_tar_transfer / download_tar。
# §5 比对：必须立即返回、必须 install、返回后不得留下 pump 线程。
# §6 重复/收尾：三个 case；释放阻塞线程、清临时目录，JSON 留证。
"""P-076 确定性 TB：递归 tar 下载的完成判定不得依赖 pump 线程。

现场是间歇的：对端 channel 已关闭、本地 tar 已结束，但
``_copy_stream(remote_stdout -> tar stdin)`` 仍阻塞在已失效的
``ChannelFile.read()``；旧代码要求所有 pump 线程死亡才结束，于是
``download_tar`` 一直等到 per-call deadline，``install_staged_path`` 永不执行。

本 TB 用三个确定性 case 复现：

1. ``wait_completion_ignores_stuck_pump``：直接调用真实
   ``_wait_tar_transfer``；channel/process 已完成，pump 永远 alive。
2. ``download_installs_with_stuck_pump``：调用真实 ``download_tar``，
   卡住 copy 线程，断言返回 0 且最终目标目录已安装。
3. ``no_residual_pump_after_download``：同样卡住 channel 读，但断言
   ``download_tar`` 返回后所有 pump 线程都已退出——只有协作取消才过。

旧完成判定下 case 1/2 会 timeout；只有“完成判定 + 可取消 pump”都修好，
三个 case 才会全绿。

用法::

    PYTHONPATH=src python test/offline/core/p076_tar_completion_tb.py \
        --out test/artifacts/evidence/p076-tar-completion.json
"""
from __future__ import annotations

import argparse
import io
import json
import queue
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common import paramiko_backend as pb  # noqa: E402
from common.paramiko_backend import ParamikoSessionBackend  # noqa: E402
from common.transfer import build_tar_download_plan  # noqa: E402


def case_wait_completion_ignores_stuck_pump() -> dict:
    """Channel + local process done; a stuck pump must not gate completion."""
    channel = type("C", (), {})()
    channel.exit_status_ready = lambda: True
    channel.recv_exit_status = lambda: 0
    process = type("P", (), {})()
    process.poll = lambda: 0
    process.wait = lambda timeout=None: 0
    worker = type("W", (), {})()
    worker.is_alive = lambda: True
    worker.name = "stuck-copy-stream"

    started = time.monotonic()
    try:
        remote_rc, local_rc = ParamikoSessionBackend._wait_tar_transfer(
            channel, process, [worker], queue.Queue(),
            pb._Deadline.start(2), "download",
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "elapsed_s": round(time.monotonic() - started, 3)}
    elapsed = time.monotonic() - started
    return {"ok": (remote_rc, local_rc) == (0, 0) and elapsed < 1.0,
            "remote_rc": remote_rc, "local_rc": local_rc,
            "elapsed_s": round(elapsed, 3)}


def case_download_installs_with_stuck_pump() -> dict:
    """Real download_tar must install the staged result with a stuck pump."""
    with tempfile.TemporaryDirectory(prefix="vb-p076-") as temp:
        target = Path(temp) / "out"
        plan = build_tar_download_plan("tar", "/remote/dir", target)
        backend = object.__new__(ParamikoSessionBackend)

        @contextmanager
        def fake_lease(*args, **kwargs):
            yield object()

        class Channel:
            def settimeout(self, value):
                return None

            def exec_command(self, command):
                return None

            def makefile(self, *args, **kwargs):
                class _Blocked:
                    def read(self, _n):
                        release.wait(timeout=10)
                        return b""

                    def close(self):
                        return None

                return _Blocked()

            def makefile_stderr(self, *args, **kwargs):
                return io.BytesIO(b"")

            def close(self):
                return None

            def exit_status_ready(self):
                return True

            def recv_exit_status(self):
                return 0

            def recv_ready(self):
                return False

            def recv(self, _n):
                return b""

            def recv_stderr_ready(self):
                return False

            def recv_stderr(self, _n):
                return b""

        class Process:
            def __init__(self):
                self.stdin = io.BytesIO()
                self.stderr = io.BytesIO()

            def poll(self):
                return 0

            def wait(self, timeout=None):
                return 0

            def kill(self):
                return None

        release = threading.Event()

        def fake_popen(command, **kwargs):
            plan.staged_item.mkdir(parents=True, exist_ok=True)
            (plan.staged_item / "payload.txt").write_text("ok", encoding="utf-8")
            return Process()

        started = time.monotonic()
        try:
            with mock.patch.object(backend, "_session_lease", fake_lease), \
                 mock.patch.object(backend, "_open_session_channel",
                                   return_value=Channel()), \
                 mock.patch.object(pb.subprocess, "Popen", side_effect=fake_popen), \
                 mock.patch.object(pb, "_read_stream", new=lambda *a, **k: None):
                rc, out, err = backend.download_tar(plan, timeout=2)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "elapsed_s": round(time.monotonic() - started, 3)}
        finally:
            release.set()
        elapsed = time.monotonic() - started
        payload = target / "payload.txt"
        return {
            "ok": rc == 0 and payload.is_file()
            and payload.read_text(encoding="utf-8") == "ok" and elapsed < 3.0,
            "rc": rc, "stderr": err, "target": str(target),
            "installed": payload.is_file(), "elapsed_s": round(elapsed, 3),
        }


def case_no_residual_pump_after_download() -> dict:
    """Every pump created by download_tar must exit before it returns."""
    with tempfile.TemporaryDirectory(prefix="vb-p076-") as temp:
        target = Path(temp) / "out"
        plan = build_tar_download_plan("tar", "/remote/dir", target)
        backend = object.__new__(ParamikoSessionBackend)
        release = threading.Event()

        @contextmanager
        def fake_lease(*args, **kwargs):
            yield object()

        class BlockedRead:
            """Worst-case ChannelFile: close does not interrupt read()."""

            def read(self, _n):
                release.wait(timeout=10)
                return b""

            def close(self):
                return None

        class Channel:
            def settimeout(self, value):
                return None

            def exec_command(self, command):
                return None

            def makefile(self, *args, **kwargs):
                return BlockedRead()

            def makefile_stderr(self, *args, **kwargs):
                return io.BytesIO(b"")

            def recv_ready(self):
                return False

            def recv(self, _n):
                return b""

            def recv_stderr_ready(self):
                return False

            def recv_stderr(self, _n):
                return b""

            def exit_status_ready(self):
                return True

            def recv_exit_status(self):
                return 0

            def close(self):
                return None

        class Process:
            def __init__(self):
                self.stdin = io.BytesIO()
                self.stderr = io.BytesIO()

            def poll(self):
                return 0

            def wait(self, timeout=None):
                return 0

            def kill(self):
                return None

        def fake_popen(command, **kwargs):
            plan.staged_item.mkdir(parents=True, exist_ok=True)
            (plan.staged_item / "payload.txt").write_text("ok", encoding="utf-8")
            return Process()

        created: list[threading.Thread] = []
        real_thread = threading.Thread

        def tracking_thread(*args, **kwargs):
            thread = real_thread(*args, **kwargs)
            created.append(thread)
            return thread

        started = time.monotonic()
        rc = None
        err = ""
        error = ""
        try:
            with mock.patch.object(backend, "_session_lease", fake_lease), \
                 mock.patch.object(backend, "_open_session_channel",
                                   return_value=Channel()), \
                 mock.patch.object(pb.subprocess, "Popen", side_effect=fake_popen), \
                 mock.patch.object(pb.threading, "Thread", side_effect=tracking_thread):
                rc, out, err = backend.download_tar(plan, timeout=2)
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"

        # Check before releasing the synthetic blocking read: a blocking pump
        # must still be visible here, while a cooperative pump has exited.
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline and any(t.is_alive() for t in created):
            time.sleep(0.01)
        leaked = [getattr(t, "name", repr(t)) for t in created if t.is_alive()]
        release.set()
        for thread in created:
            thread.join(timeout=0.2)
        if error:
            return {"ok": False, "error": error,
                    "elapsed_s": round(time.monotonic() - started, 3)}
        return {
            "ok": rc == 0 and not leaked,
            "rc": rc,
            "leaked_threads": leaked,
            "created_threads": len(created),
            "elapsed_s": round(time.monotonic() - started, 3),
        }


CASES = (
    ("wait_completion_ignores_stuck_pump", case_wait_completion_ignores_stuck_pump),
    ("download_installs_with_stuck_pump", case_download_installs_with_stuck_pump),
    ("no_residual_pump_after_download", case_no_residual_pump_after_download),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    results = []
    for name, case in CASES:
        try:
            detail = case()
        except Exception as exc:  # noqa: BLE001
            detail = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        results.append({"name": name, **detail})

    passed = sum(1 for item in results if item["ok"])
    payload = {
        "tb": "p076_tar_completion_tb",
        "status": "PASS" if passed == len(results) else "RED",
        "passed": passed,
        "total": len(results),
        "cases": results,
    }
    out = Path(args.out) if args.out else ROOT / "test" / "artifacts" / "evidence" / "p076-tar-completion.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"evidence: {out}")
    return 0 if passed == len(results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
