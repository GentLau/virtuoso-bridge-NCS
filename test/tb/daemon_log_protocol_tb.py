"""CDS.log return-protocol TB (daemon side, scripted CIW).

Covers the daemon half of ``test/计划/日志返回.md`` without needing a real
Virtuoso: the harness scripts the CIW side of the ipc protocol, so off/level/
rotate/unavailable/degrade/truncate/second-frame-timeout are all deterministic.

Run with::

    PYTHONPATH=src python test/tb/daemon_log_protocol_tb.py [--case NAME] [--out F]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from _daemon_harness import (  # noqa: E402
    DAEMON_FILES,
    NAK,
    RS,
    STX,
    error_frame,
    load_daemon,
    meta_frame,
    run_request,
    value_frame,
)

DEGRADE_NOTE = "[log auto-degraded: error-only due to log_max_bytes]"
TRUNCATE_NOTE = "[log truncated: increment not fully returned due to log_max_bytes]"


class ProbeFailure(AssertionError):
    pass


def _request(**overrides) -> dict:
    payload = {"skill": "1+1", "timeout": 5.0, "token": "tok"}
    payload.update(overrides)
    return payload


def case_off_reads_one_frame(daemon) -> dict:
    """off = 源头掐断：不发日志指令、不读第二帧、不看文件。"""
    frame1 = value_frame("2")
    trailing = meta_frame("/definitely/not/read.log", 0, 10)
    ciw_out, sent, unread, parsed = run_request(
        daemon, _request(log_level="off"), frame1 + trailing
    )
    if b"RBDLogOn=nil" not in ciw_out:
        raise ProbeFailure(f"off did not send the nil directive: {ciw_out[:120]!r}")
    if unread != trailing:
        raise ProbeFailure(
            "off consumed a second frame (log must be cut at the source): "
            f"unread={unread!r}"
        )
    if parsed is None or parsed.get("log") != "" or parsed.get("warnings"):
        raise ProbeFailure(f"off returned log/warnings: {parsed!r}")
    if not sent.startswith(STX):
        raise ProbeFailure(f"off response was not a value frame: {sent[:40]!r}")
    return {"directive": "RBDLogOn=nil", "unread_bytes": len(unread), "log": ""}


def case_all_reads_meta_and_returns_bytes(daemon) -> dict:
    """all + 增量未超限：返回的 log 与文件区间逐字节一致。"""
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "CDS.log"
        log.write_bytes(b"line-1\nline-2\n")
        ciw = value_frame("2") + meta_frame(str(log), 0, len(b"line-1\nline-2\n"))
        ciw_out, sent, _unread, parsed = run_request(
            daemon, _request(log_level="all", log_max_bytes=65536), ciw
        )
    if b"RBDLogOn=t" not in ciw_out:
        raise ProbeFailure("all did not request log capture from the CIW")
    if parsed is None or parsed.get("log") != "line-1\nline-2\n":
        raise ProbeFailure(f"log bytes not returned verbatim: {parsed!r}")
    return {"log": parsed["log"], "value": parsed.get("value")}


def case_second_frame_timeout(daemon) -> dict:
    """第二帧超时：第一帧结果优先返回 + 固定 warning，不判 Skill 失败。"""
    started = time.monotonic()
    _ciw_out, sent, _unread, parsed = run_request(
        daemon, _request(timeout=0.4, log_level="all"), value_frame("2")
    )
    elapsed = time.monotonic() - started
    if parsed is None:
        raise ProbeFailure(f"timeout path did not produce JSON: {sent[:80]!r}")
    if parsed.get("value") != "2":
        raise ProbeFailure(f"first frame was not preferred: {parsed!r}")
    if parsed.get("log") != "":
        raise ProbeFailure(f"timeout path returned log bytes: {parsed!r}")
    warnings = parsed.get("warnings") or []
    if not warnings or not str(warnings[0]).startswith("CDS.log unavailable:"):
        raise ProbeFailure(f"missing fixed warning text: {parsed!r}")
    if not sent.startswith(STX):
        raise ProbeFailure("second-frame timeout must not NAK the Skill result")
    return {"warnings": warnings, "elapsed_s": round(elapsed, 3)}


def case_rotation_truncation(daemon) -> dict:
    """轮转/截断：size < start 时从 0 读，可读多少算多少。"""
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "CDS.log"
        log.write_bytes(b"rotated-content\n")
        # start/end were captured against a much longer pre-rotation file
        ciw = value_frame("2") + meta_frame(str(log), 5000, 5016)
        _ciw_out, sent, _unread, parsed = run_request(
            daemon, _request(log_level="all"), ciw
        )
    if parsed is None:
        raise ProbeFailure(f"rotation path did not return JSON: {sent[:80]!r}")
    if parsed.get("log") != "rotated-content\n":
        raise ProbeFailure(f"rotation did not fall back to offset 0: {parsed!r}")
    if parsed.get("warnings"):
        raise ProbeFailure(f"rotation must not warn: {parsed!r}")
    return {"log": parsed["log"]}


def case_unreadable_log(daemon) -> dict:
    """读不到日志：固定 warning 文案 + Skill 结果照常返回。"""
    missing = Path(tempfile.gettempdir()) / "vb-absent-CDS.log"
    if missing.exists():
        missing.unlink()
    ciw = value_frame("2") + meta_frame(str(missing), 0, 10)
    _ciw_out, sent, _unread, parsed = run_request(
        daemon, _request(log_level="all"), ciw
    )
    if parsed is None or parsed.get("value") != "2":
        raise ProbeFailure(f"Skill result lost when the log is unreadable: {parsed!r}")
    warnings = parsed.get("warnings") or []
    if not warnings or not str(warnings[0]).startswith("CDS.log unavailable:"):
        raise ProbeFailure(f"missing fixed warning: {parsed!r}")
    if parsed.get("log") != "":
        raise ProbeFailure(f"unreadable log must return empty text: {parsed!r}")
    if not sent.startswith(STX):
        raise ProbeFailure("unreadable log must not NAK the Skill result")
    return {"warnings": warnings}


def case_level_filter(daemon) -> dict:
    """分级过滤：all/warn/error 三档按行首 \\e / \\w 判定。"""
    text = "plain-info\n\\w warn-line\n\\e error-line\n"
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "CDS.log"
        log.write_bytes(text.encode("utf-8"))
        result = {}
        for level in ("all", "warn", "error"):
            ciw = value_frame("2") + meta_frame(str(log), 0, len(text.encode()))
            _out, _sent, _unread, parsed = run_request(
                daemon, _request(log_level=level), ciw
            )
            result[level] = parsed["log"] if parsed else None
    if result["all"] != text:
        raise ProbeFailure(f"all must keep every line: {result['all']!r}")
    if "info" in (result["warn"] or "") or "warn-line" not in (result["warn"] or ""):
        raise ProbeFailure(f"warn filter wrong: {result['warn']!r}")
    if "error-line" not in (result["error"] or "") or "warn-line" in (result["error"] or ""):
        raise ProbeFailure(f"error filter wrong: {result['error']!r}")
    return result


def case_degrade_and_truncate(daemon) -> dict:
    """限长：先降级到 error，再头截断，并各带一句提示（提示不占预算）。"""
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "CDS.log"
        long_info = "i" * 400 + "\n"
        log.write_bytes((long_info + "\\e err-line\n").encode("utf-8"))
        size = log.stat().st_size
        ciw = value_frame("2") + meta_frame(str(log), 0, size)
        _out, _sent, _unread, degraded = run_request(
            daemon, _request(log_level="all", log_max_bytes=64), ciw
        )

        # error-only content that still overflows the budget -> head truncation
        log.write_bytes((("\\e " + "e" * 400 + "\n") * 3).encode("utf-8"))
        size = log.stat().st_size
        ciw = value_frame("2") + meta_frame(str(log), 0, size)
        _out, _sent, _unread, truncated = run_request(
            daemon, _request(log_level="all", log_max_bytes=64), ciw
        )

    if DEGRADE_NOTE not in (degraded or {}).get("log", ""):
        raise ProbeFailure(f"degrade note missing: {degraded!r}")
    if "err-line" not in degraded["log"]:
        raise ProbeFailure(f"degrade must keep error lines: {degraded!r}")
    if "i" * 50 in degraded["log"]:
        raise ProbeFailure(f"degrade must drop info lines: {degraded!r}")
    if TRUNCATE_NOTE not in (truncated or {}).get("log", ""):
        raise ProbeFailure(f"truncate note missing: {truncated!r}")
    if DEGRADE_NOTE not in truncated["log"]:
        raise ProbeFailure(f"truncate path must report the degrade too: {truncated!r}")
    body = truncated["log"].split(DEGRADE_NOTE)[0].rstrip("\n")
    if len(body.encode("utf-8")) > 64:
        raise ProbeFailure(f"byte budget exceeded: {len(body.encode('utf-8'))} bytes")
    return {
        "degraded_log": degraded["log"][:120],
        "truncated_len": len(truncated["log"]),
        "truncated_body_bytes": len(body.encode("utf-8")),
    }


def case_error_first_frame_propagates(daemon) -> dict:
    """SKILL 报错帧：NAK 透传，且不影响日志字段。"""
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "CDS.log"
        log.write_bytes(b"delta\n")
        ciw = error_frame("boom") + meta_frame(str(log), 0, 6)
        _out, sent, _unread, parsed = run_request(
            daemon, _request(log_level="error"), ciw
        )
    if not sent.startswith(NAK):
        raise ProbeFailure(f"error frame was not propagated: {sent[:40]!r}")
    if parsed is None or parsed.get("error") != "boom":
        raise ProbeFailure(f"error payload changed: {parsed!r}")
    if parsed.get("log") != "":
        raise ProbeFailure(f"error level kept an info line: {parsed!r}")
    return {"error": parsed["error"], "log": parsed["log"]}


def case_server_loop(daemon) -> dict:
    """真实监听循环：accept/失败 JSON/响应/统计（覆盖 start_server）。"""
    import socket as _socket
    import threading as _threading

    created = []

    class RecordingSocket(_socket.socket):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)

    real_socket = daemon.socket.socket
    real_argv = daemon.sys.argv
    with _socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    errors = []

    def run():
        try:
            daemon.start_server()
        except Exception as exc:  # noqa: BLE001 - expected on shutdown
            errors.append(repr(exc))

    try:
        daemon.socket.socket = RecordingSocket
        daemon.sys.argv = ["daemon", "127.0.0.1", str(port), "tok"]
        thread = _threading.Thread(target=run, daemon=True)
        thread.start()
        deadline = time.monotonic() + 10
        response = b""
        while time.monotonic() < deadline:
            try:
                with _socket.create_connection(("127.0.0.1", port), timeout=2) as conn:
                    conn.sendall(b"{not json")
                    conn.shutdown(_socket.SHUT_WR)
                    response = conn.recv(65536)
                break
            except OSError:
                time.sleep(0.1)
        if not response.startswith(NAK) or b"JSONDecodeError" not in response:
            raise ProbeFailure(f"server loop did not NAK a bad payload: {response[:80]!r}")
        if daemon._RB_ERRORS < 1:
            raise ProbeFailure("server loop did not account the protocol error")
    finally:
        for sock in created:
            try:
                sock.close()
            except OSError:
                pass
        daemon.socket.socket = real_socket
        daemon.sys.argv = real_argv
    return {"port": port, "response": response[:60].decode("utf-8", "replace"),
            "errors": daemon._RB_ERRORS}


CASES = {
    "off-reads-one-frame": case_off_reads_one_frame,
    "all-reads-meta": case_all_reads_meta_and_returns_bytes,
    "second-frame-timeout": case_second_frame_timeout,
    "rotation-truncation": case_rotation_truncation,
    "unreadable-log": case_unreadable_log,
    "level-filter": case_level_filter,
    "degrade-and-truncate": case_degrade_and_truncate,
    "error-first-frame": case_error_first_frame_propagates,
    "server-loop": case_server_loop,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=sorted(CASES), action="append", default=[])
    parser.add_argument("--variant", choices=sorted(DAEMON_FILES), action="append", default=[])
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    selected = args.case or sorted(CASES)
    variants = args.variant or sorted(DAEMON_FILES)
    results = {}
    failed = 0
    for variant in variants:
        for name in selected:
            key = f"{variant}:{name}"
            started = time.monotonic()
            try:
                daemon = load_daemon(f"{variant}_{name}", "tok", DAEMON_FILES[variant])
                daemon._RB_ERRORS = 0
                results[key] = {"status": "pass", "detail": CASES[name](daemon)}
            except Exception as exc:  # noqa: BLE001
                failed += 1
                results[key] = {"status": "fail", "error": f"{type(exc).__name__}: {exc}"}
            results[key]["elapsed_s"] = time.monotonic() - started
    payload = {
        "ok": failed == 0,
        "failed": failed,
        "variant_note": (
            "py27 keys mean 'ramic_bridge_daemon_27.py source executed under "
            "CPython 3' (protocol parity).  A real Python 2.7 run is PENDING: "
            "the test environment has no python2 interpreter."
        ),
        "results": results,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
