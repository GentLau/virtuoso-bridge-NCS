#!/usr/bin/env python3
"""RAMIC Bridge Daemon - Virtuoso Skill Bridge Service (Python 3).

Launched by ``ipcBeginProcess`` from ``ramic_bridge.il``:

    python3 ramic_bridge_daemon_3.py <host> <port> <token>

Wire protocol (bottom <-> middle):
  request : UTF-8 JSON {"skill", "timeout", "token", "log_level", "log_max_bytes"}
  response: 02/15 + UTF-8 JSON {"value"|"error", "log"} + 1e
"""

import errno
import json
import os
import signal
import socket
import sys
import tempfile
import threading
import time
import traceback

try:
    import fcntl as _fcntl
except ImportError:
    _fcntl = None

HOST = "127.0.0.1"
PORT = 65432
DAEMON_TOKEN: str = ""

STX = b"\x02"
NAK = b"\x15"
RS = b"\x1e"
US = b"\x1f"

virtuoso_pid = None
try:
    with open("/proc/self/stat") as _f:
        _ppid = int(_f.read().split()[3])
    with open(f"/proc/{_ppid}/stat") as _f:
        virtuoso_pid = int(_f.read().split()[3])
except Exception:
    virtuoso_pid = None

_timeout_flag = False
_watchdog = None

if _fcntl is not None:
    _fd = sys.stdin.fileno()
    _fl = _fcntl.fcntl(_fd, _fcntl.F_GETFL)
    _fcntl.fcntl(_fd, _fcntl.F_SETFL, _fl | os.O_NONBLOCK)

_RB_START_T = time.time()
_RB_CALLS = 0
_RB_ERRORS = 0
_RB_LAST_STAT_T = 0.0


def _emit_stat(force=False):
    global _RB_LAST_STAT_T
    now = time.time()
    if not force and now - _RB_LAST_STAT_T < 1.0:
        return
    _RB_LAST_STAT_T = now
    try:
        sys.stderr.write(
            f"[RB-stat] count={_RB_CALLS} errors={_RB_ERRORS} uptime={int(now - _RB_START_T)}\n"
        )
        sys.stderr.flush()
    except Exception:
        pass


def _safe_sendall(conn, data):
    try:
        conn.sendall(data)
    except OSError:
        pass


def _safe_close(conn):
    try:
        conn.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        conn.close()
    except OSError:
        pass


def _watchdog_cb():
    global _timeout_flag
    if not _timeout_flag:
        _timeout_flag = True
        if virtuoso_pid:
            try:
                os.kill(virtuoso_pid, signal.SIGINT)
            except Exception:
                pass


def _read_frame() -> bytes:
    """Read one STX/NAK ... RS frame from Virtuoso (daemon stdin)."""
    out = bytearray()
    while True:
        try:
            ch = sys.stdin.buffer.read(1)
            if not ch:
                if _timeout_flag:
                    return b"\x15TimeoutError\x1e"
                time.sleep(0.001)
                continue
            if ch[0] in (STX[0], NAK[0]):
                out.extend(ch)
                break
        except IOError as e:
            if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                if _timeout_flag:
                    return b"\x15TimeoutError\x1e"
                time.sleep(0.001)
                continue
            raise
        if _timeout_flag:
            return b"\x15TimeoutError\x1e"
    while True:
        try:
            ch = sys.stdin.buffer.read(1)
            if not ch:
                if _timeout_flag:
                    return b"\x15TimeoutError\x1e"
                time.sleep(0.001)
                continue
            if ch[0] == RS[0]:
                break
            out.extend(ch)
        except IOError as e:
            if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                if _timeout_flag:
                    return b"\x15TimeoutError\x1e"
                time.sleep(0.001)
                continue
            raise
        if _timeout_flag:
            return b"\x15TimeoutError\x1e"
    return bytes(out)


def _parse_meta(payload):
    """Meta frame payload: ``<path> US <start-offset> US <end-offset>``."""
    if US not in payload:
        return None, 0, 0
    parts = payload.split(US)
    if len(parts) < 3:
        return None, 0, 0
    path = parts[0].decode("utf-8", errors="replace").strip().strip('"') or None
    try:
        start = int(parts[1].decode("ascii", errors="ignore").strip() or "0")
        end = int(parts[2].decode("ascii", errors="ignore").strip() or "0")
    except ValueError:
        start = 0
        end = 0
    return path, start, end


def classify_level(line: str) -> str:
    if line.startswith("\\e"):
        return "error"
    if line.startswith("\\w"):
        return "warning"
    return "info"


def _keep(level: str, line: str) -> bool:
    if level == "off":
        return False
    lvl = classify_level(line)
    if level == "all":
        return True
    if level == "warn":
        return lvl in ("warning", "error")
    if level == "error":
        return lvl == "error"
    return True


_DEGRADE_NOTE = "\n[log auto-degraded: error-only due to log_max_bytes]"
_TRUNCATE_NOTE = "\n[log truncated: increment not fully returned due to log_max_bytes]"


def filter_delta(raw, level, max_bytes):
    """Filter by level; on overflow degrade to error-only, then to the
    leading ``max_bytes`` bytes of the increment.  Marker lines explaining
    degradation/truncation are exempt from ``max_bytes``."""
    if level == "off":
        return "", False
    lines = raw.splitlines()
    kept = [ln for ln in lines if _keep(level, ln)]
    text = "\n".join(kept)
    if len(text.encode("utf-8")) <= max_bytes:
        return text, False
    err_lines = [ln for ln in lines if classify_level(ln) == "error"]
    err_text = "\n".join(err_lines)
    if len(err_text.encode("utf-8")) <= max_bytes:
        return err_text + _DEGRADE_NOTE, True
    body = err_text.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
    return body + _DEGRADE_NOTE + _TRUNCATE_NOTE, True


def _read_range(path, start_offset, end_offset):
    """Read CDS.log bytes in [start,end); never touches cursor state."""
    if not path:
        return "", "CDS.log path unavailable"
    try:
        size = os.path.getsize(path)
    except OSError:
        return "", "CDS.log unreadable"
    start = max(start_offset, 0)
    end = min(max(end_offset, 0), size)
    if size < start:
        # log rotated/truncated mid-request: read the current file from 0
        start = 0
    if end < start:
        end = start
    try:
        with open(path, "rb") as f:
            f.seek(start)
            data = f.read(end - start)
    except OSError:
        return "", "CDS.log unreadable"
    return data.decode("utf-8", errors="replace"), None


def handle_connection(conn):
    global _timeout_flag, _watchdog, _RB_CALLS, _RB_ERRORS
    tmp_il_path = None
    try:
        chunks = []
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
        req = json.loads(b"".join(chunks).decode("utf-8"))

        skill_code = req.get("skill", "")
        timeout_seconds = float(req.get("timeout", 30.0))
        token = req.get("token")
        log_level = req.get("log_level", "all")
        log_max_bytes = int(req.get("log_max_bytes", 65536))
        log_on = log_level != "off"

        if not DAEMON_TOKEN or token != DAEMON_TOKEN:
            _safe_sendall(conn, NAK + json.dumps({"error": "invalid token", "log": ""}).encode("utf-8") + RS)
            return

        _timeout_flag = False
        while True:
            try:
                if not sys.stdin.buffer.read(1):
                    break
            except IOError:
                break

        log_directive = "RBDLogOn=t " if log_on else "RBDLogOn=nil "
        if "\n" in skill_code:
            fd, tmp_il_path = tempfile.mkstemp(suffix=".il", prefix="vb_eval_")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(f"_vb_eval_result = progn(\n{skill_code}\n)\n")
            escaped = tmp_il_path.replace("\\", "/")
            send_code = log_directive + f'load("{escaped}") hiFlush() _vb_eval_result\n'
        else:
            send_code = log_directive + f'let(((__vb_r {skill_code})) hiFlush() __vb_r)\n'

        sys.stdout.buffer.write(send_code.encode("utf-8"))
        sys.stdout.buffer.flush()

        _watchdog = threading.Timer(timeout_seconds, _watchdog_cb)
        _watchdog.daemon = True
        _watchdog.start()

        frame1 = _read_frame()

        _timeout_flag = True
        if _watchdog:
            _watchdog.cancel()

        status_byte = frame1[:1]
        value_payload = frame1[1:].decode("utf-8", errors="replace")
        ok = status_byte == STX

        log_text = ""
        warnings = []
        if log_on:
            frame2 = _read_frame()
            meta = _parse_meta(frame2[1:])
            log_path, start_offset, end_offset = meta
            raw_delta, warn = _read_range(log_path, start_offset, end_offset)
            if warn:
                warnings.append(warn)
            log_text, _truncated = filter_delta(raw_delta, log_level, log_max_bytes)

        resp = {"value" if ok else "error": value_payload, "log": log_text}
        if warnings:
            resp["warnings"] = warnings
        payload = json.dumps(resp, ensure_ascii=False)
        _safe_sendall(conn, (STX if ok else NAK) + payload.encode("utf-8") + RS)

        _RB_CALLS += 1
        if not ok:
            _RB_ERRORS += 1
        _emit_stat()

    except json.JSONDecodeError as e:
        _safe_sendall(conn, NAK + json.dumps({"error": f"JSONDecodeError: {e}", "log": ""}).encode("utf-8") + RS)
        _RB_ERRORS += 1
        _emit_stat()
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        _safe_sendall(conn, NAK + json.dumps({"error": str(e), "log": ""}).encode("utf-8") + RS)
        _RB_ERRORS += 1
        _emit_stat()
    finally:
        _timeout_flag = True
        if _watchdog:
            _watchdog.cancel()
        if tmp_il_path:
            try:
                os.unlink(tmp_il_path)
            except OSError:
                pass
        _safe_close(conn)


def start_server():
    global HOST, PORT, DAEMON_TOKEN
    if len(sys.argv) > 1:
        HOST = sys.argv[1]
    if len(sys.argv) > 2:
        PORT = int(sys.argv[2])
    if len(sys.argv) > 3 and sys.argv[3]:
        DAEMON_TOKEN = sys.argv[3]
    else:
        sys.stderr.write("ERROR: daemon requires a non-empty token (argv[3]).\n")
        sys.exit(1)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((HOST, PORT))
        except OSError as e:
            if e.errno == errno.EADDRINUSE or getattr(e, "winerror", None) in (10048, 10013):
                sys.stderr.write(f"ERROR: Port {PORT} is already in use. Another daemon may be running.\n")
                sys.exit(1)
            raise
        s.listen(128)
        try:
            hn = socket.gethostname() or "unknown"
        except Exception:
            hn = "unknown"
        ip = ""
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                probe.connect(("8.8.8.8", 80))
                ip = probe.getsockname()[0]
            finally:
                probe.close()
        except Exception:
            try:
                ip = socket.gethostbyname(hn)
            except Exception:
                ip = ""
        sys.stderr.write(f"[RB-banner] pid={os.getpid()} bind={HOST}:{PORT} host={hn} ip={ip or 'unknown'}\n")
        sys.stderr.flush()
        while True:
            conn, _addr = s.accept()
            try:
                handle_connection(conn)
            except Exception:  # noqa: BLE001
                traceback.print_exc()
                _safe_close(conn)


if __name__ == "__main__":
    start_server()