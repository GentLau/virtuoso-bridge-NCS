#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
"""RAMIC Bridge Daemon (Python 2.7-compatible variant of the v1 protocol).

Same wire protocol as ``ramic_bridge_daemon_3.py``; written with syntax valid
under both Python 2.7 and 3.x so it can be smoke-tested locally and run by a
Cadence-bundled python2.7 on hosts without a system Python 2.
"""

from __future__ import print_function

import errno
import json
import math
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
DAEMON_TOKEN = ""
TEMP_DIR = ""

STX = 2
NAK = 21
RS = 30
US = 31
_US_BYTE = chr(US).encode("latin-1")


def _B(code):
    """Control byte that is consistent under both Python 2 and 3."""
    return chr(code).encode("latin-1")


try:
    _STRING_TYPES = (str, unicode)
except NameError:  # pragma: no cover - Python 3 smoke run
    _STRING_TYPES = (str,)

_REQUEST_READ_TIMEOUT = 10.0
_MAX_REQUEST_BYTES = 16 * 1024 * 1024


def _is_virtuoso_process(pid):
    """Validate the ppid-derived target before sending SIGINT."""
    if not isinstance(pid, int) or pid <= 1:
        return False
    try:
        with open("/proc/%d/comm" % pid, "rb") as fh:
            comm = fh.read().decode("utf-8", "replace").strip().lower()
        if "virtuoso" in comm:
            return True
    except (IOError, OSError):
        return False
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as fh:
            cmdline = fh.read().replace(b"\x00", b" ").decode(
                "utf-8", "replace"
            ).lower()
    except (IOError, OSError):
        return False
    return "virtuoso" in cmdline


_derived_virtuoso_pid = None
try:
    with open("/proc/self/stat") as _f:
        _ppid = int(_f.read().split()[3])
    with open("/proc/%d/stat" % _ppid) as _f:
        _derived_virtuoso_pid = int(_f.read().split()[3])
except Exception:
    _derived_virtuoso_pid = None

virtuoso_pid = (
    _derived_virtuoso_pid
    if _derived_virtuoso_pid and _is_virtuoso_process(_derived_virtuoso_pid)
    else None
)

_timeout_flag = False
_watchdog = None
_watchdog_gen = 0
_watchdog_lock = threading.Lock()

def _set_stdin_nonblocking():
    """Best-effort: make the ipcBeginProcess stdin pipe non-blocking.

    Must run at *runtime*, never at import: pytest/CI replaces sys.stdin with
    a pseudofile whose fileno() raises, and a library module must stay
    importable there (Linux CI otherwise fails during collection).
    """
    if _fcntl is None:
        return
    try:
        fd = sys.stdin.fileno()
        flags = _fcntl.fcntl(fd, _fcntl.F_GETFL)
        _fcntl.fcntl(fd, _fcntl.F_SETFL, flags | os.O_NONBLOCK)
    except (AttributeError, OSError, ValueError):
        # pseudofile / closed pipe: keep blocking mode; real ipc pipes have fileno
        pass

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
        sys.stderr.write("[RB-stat] count=%d errors=%d uptime=%d\n" % (_RB_CALLS, _RB_ERRORS, int(now - _RB_START_T)))
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


def _temp_dir():
    """Runtime working dir configured by the deployment."""
    candidate = os.path.expanduser(
        TEMP_DIR or os.path.dirname(os.path.abspath(__file__))
    )
    try:
        if not os.path.isdir(candidate):
            os.makedirs(candidate)
    except OSError:
        pass
    return candidate


def _valid_timeout(value):
    if isinstance(value, bool):
        return None
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(timeout) or math.isinf(timeout) or timeout <= 0:
        return None
    return timeout


def _send_error(conn, message):
    _safe_sendall(
        conn,
        _B(NAK) + json.dumps({"error": message, "log": ""}).encode("utf-8") + _B(RS),
    )


def _watchdog_cb(gen):
    global _timeout_flag
    with _watchdog_lock:
        if gen != _watchdog_gen or _timeout_flag:
            return
        _timeout_flag = True
        pid = virtuoso_pid
    if pid and _is_virtuoso_process(pid):
        try:
            os.kill(pid, signal.SIGINT)
        except Exception:
            pass


def _read_byte():
    while True:
        try:
            ch = sys.stdin.read(1)
            if not ch:
                if _timeout_flag:
                    return None
                time.sleep(0.001)
                continue
            return ord(ch)
        except IOError as e:
            if getattr(e, "errno", None) in (errno.EAGAIN, errno.EWOULDBLOCK):
                if _timeout_flag:
                    return None
                time.sleep(0.001)
                continue
            raise
        if _timeout_flag:
            return None


def _read_frame():
    out = bytearray()
    while True:
        b = _read_byte()
        if b is None:
            return _B(NAK) + b"SKILL execution timed out" + _B(RS)
        if b in (STX, NAK):
            out.append(b)
            break
    while True:
        b = _read_byte()
        if b is None:
            return _B(NAK) + b"SKILL execution timed out" + _B(RS)
        if b == RS:
            break
        out.append(b)
    return bytes(out)


def _parse_meta(payload):
    if _US_BYTE not in payload:
        return None, 0, 0
    parts = payload.split(_US_BYTE)
    if len(parts) < 3:
        return None, 0, 0
    path = parts[0].decode("utf-8", "replace").strip().strip('"') or None
    try:
        start = int(parts[1].decode("ascii", "ignore").strip() or "0")
        end = int(parts[2].decode("ascii", "ignore").strip() or "0")
    except ValueError:
        start = 0
        end = 0
    return path, start, end


def classify_level(line):
    if line.startswith("\\e"):
        return "error"
    if line.startswith("\\w"):
        return "warning"
    return "info"


def _keep(level, line):
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
    if level == "off":
        return "", False
    if level == "all" and len(raw.encode("utf-8")) <= max_bytes:
        return raw, False  # byte-for-byte identity with the file interval
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


class LocalFileRangeReader(object):
    """Read a CDS.log byte range on the host that owns the file.

    版本边界（spec: 本版范围与明确不支持 §2 第 8 项）：本版假设 CDS.log 与
    daemon 同主机（daemon 是 CIW 的 ipcBeginProcess 子进程），所以这里就是
    一次本地文件读。

    预留（本版不做）：将来 daemon 若跨机启动，**不要**让远端 daemon 直接打开
    异地路径（`/tmp`、项目本地路径在别的主机上无效），也**不要**把读取挪进
    SKILL/CIW（会阻塞单个 CIW、引入转义与自我污染风险）。正确方向是保持契约
    不变（IL 仍给出 `path + [start,end)`），只把"读取"换成**锚定 CIW 主机**的
    实现——例如经 gui role 的连接执行 `dd ... | base64` 或一个小 filter 脚本；
    **过滤/限长必须在读取端就地完成**，避免日志字节多跨一跳网络。
    """

    def read(self, path, start_offset, end_offset):
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
        return data.decode("utf-8", "replace"), None


#: 当前唯一实现：本地读。split-host 版本在这里换成"锚定 CIW 主机"的 reader。
_READER = LocalFileRangeReader()


def _read_range(path, start_offset, end_offset):
    """兼容包装：所有调用都经 `_READER`，将来只替换读取端。"""
    return _READER.read(path, start_offset, end_offset)

def handle_connection(conn):
    global _timeout_flag, _watchdog, _watchdog_gen, _RB_CALLS, _RB_ERRORS
    tmp_il_path = None
    try:
        chunks = []
        total = 0
        conn.settimeout(_REQUEST_READ_TIMEOUT)
        try:
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > _MAX_REQUEST_BYTES:
                    return  # foreign/oversized packet: drop silently
                chunks.append(chunk)
        except socket.timeout:
            return  # slow/incomplete foreign packet: drop silently
        if not chunks:
            return
        try:
            req = json.loads(b"".join(chunks).decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return  # not our JSON protocol: drop silently
        if not isinstance(req, dict):
            return

        skill_code = req.get("skill")
        timeout_seconds = _valid_timeout(req.get("timeout", 30.0))
        token = req.get("token")
        if (
            not isinstance(skill_code, _STRING_TYPES)
            or not isinstance(token, _STRING_TYPES)
            or timeout_seconds is None
        ):
            return  # malformed own-protocol packet: drop silently

        if not DAEMON_TOKEN or token != DAEMON_TOKEN:
            _safe_sendall(conn, _B(NAK) + json.dumps({"error": "invalid token", "log": ""}).encode("utf-8") + _B(RS))
            return

        log_level = req.get("log_level", "off")
        if log_level not in ("off", "all", "warn", "error"):
            _safe_sendall(conn, _B(NAK) + json.dumps({"error": "invalid log_level", "log": ""}).encode("utf-8") + _B(RS))
            return
        try:
            log_max_bytes = int(req.get("log_max_bytes", 65536))
        except (TypeError, ValueError):
            _safe_sendall(conn, _B(NAK) + json.dumps({"error": "invalid log_max_bytes", "log": ""}).encode("utf-8") + _B(RS))
            return
        if log_max_bytes < 1:
            _safe_sendall(conn, _B(NAK) + json.dumps({"error": "invalid log_max_bytes", "log": ""}).encode("utf-8") + _B(RS))
            return
        log_on = log_level != "off"

        with _watchdog_lock:
            _timeout_flag = False
            _watchdog_gen += 1
            watchdog_gen = _watchdog_gen
        while True:
            try:
                if not sys.stdin.read(1):
                    break
            except IOError:
                break

        log_directive = "RBDLogOn=t " if log_on else "RBDLogOn=nil "
        if "\n" in skill_code:
            fd, tmp_il_path = tempfile.mkstemp(
                suffix=".il",
                prefix="vb_eval_",
                dir=_temp_dir(),
            )
            with os.fdopen(fd, "wb") as f:
                f.write(("_vb_eval_result = progn(\n%s\n)\n" % skill_code).encode("utf-8"))
            escaped = tmp_il_path.replace("\\", "/")
            send_code = log_directive + ('load("%s") hiFlush() _vb_eval_result\n' % escaped)
        else:
            # Same contract as the Python 3 daemon: legal multi-form input
            # and trailing comments must survive the inline wrapper.
            send_code = (
                log_directive
                + 'let(((__vb_r progn(%s\n))) hiFlush() __vb_r)\n' % skill_code
            )

        sys.stdout.write(send_code.encode("utf-8"))
        sys.stdout.flush()

        _watchdog = threading.Timer(
            timeout_seconds, _watchdog_cb, args=(watchdog_gen,)
        )
        _watchdog.daemon = True
        _watchdog.start()

        frame1 = _read_frame()

        status_byte = frame1[0] if isinstance(frame1[0], int) else ord(frame1[0])
        value_payload = frame1[1:].decode("utf-8", "replace").rstrip("\x1e")
        ok = status_byte == STX

        log_text = ""
        warnings = []
        if log_on:
            frame2 = _read_frame()

        with _watchdog_lock:
            _timeout_flag = True
            if _watchdog:
                _watchdog.cancel()

        if log_on:
            meta = _parse_meta(frame2[1:])
            log_path, start_offset, end_offset = meta
            raw_delta, warn = _read_range(log_path, start_offset, end_offset)
            if warn:
                # 固定文案由日志标准 §6.3 冻结：middle 只透传，不再自己拼前缀
                warnings.append("CDS.log unavailable: " + warn)
            log_text, _truncated = filter_delta(raw_delta, log_level, log_max_bytes)

        resp = {"value" if ok else "error": value_payload, "log": log_text}
        if warnings:
            resp["warnings"] = warnings
        payload = json.dumps(resp, ensure_ascii=False)
        _safe_sendall(conn, _B(STX if ok else NAK) + payload.encode("utf-8") + _B(RS))

        _RB_CALLS += 1
        if not ok:
            _RB_ERRORS += 1
        _emit_stat()

    except (UnicodeDecodeError, ValueError):
        traceback.print_exc()
    except Exception:
        traceback.print_exc()
        _send_error(conn, "internal daemon error")
        _RB_ERRORS += 1
        _emit_stat()
    finally:
        with _watchdog_lock:
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
    global HOST, PORT, DAEMON_TOKEN, TEMP_DIR
    _set_stdin_nonblocking()
    if len(sys.argv) > 1:
        HOST = sys.argv[1]
    if len(sys.argv) > 2:
        PORT = int(sys.argv[2])
    if len(sys.argv) > 3 and sys.argv[3]:
        DAEMON_TOKEN = sys.argv[3]
    else:
        sys.stderr.write("ERROR: daemon requires a non-empty token (argv[3]).\n")
        sys.exit(1)
    if len(sys.argv) > 4 and sys.argv[4]:
        TEMP_DIR = sys.argv[4]

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((HOST, PORT))
    except OSError as e:
        if getattr(e, "errno", None) == errno.EADDRINUSE or getattr(e, "winerror", None) in (10048, 10013):
            sys.stderr.write("ERROR: Port %d is already in use. Another daemon may be running.\n" % PORT)
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
    try:
        import getpass
        banner_user = getpass.getuser()
    except Exception:
        banner_user = ""
    sys.stderr.write("[RB-banner] pid=%d bind=%s:%d host=%s ip=%s user=%s\n" % (os.getpid(), HOST, PORT, hn, ip or "unknown", banner_user))
    sys.stderr.flush()
    while True:
        conn, _addr = s.accept()
        try:
            handle_connection(conn)
        except Exception:
            traceback.print_exc()
            _safe_close(conn)


if __name__ == "__main__":
    start_server()
