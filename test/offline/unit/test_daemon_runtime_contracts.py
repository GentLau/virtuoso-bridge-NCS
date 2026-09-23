"""L0 runtime/protocol contracts for the two bottom daemons.

`test_daemon_parity.py` / `test_daemon_log_contract.py` already pin the pure
helpers (``classify_level`` / ``filter_delta`` / ``_parse_meta`` / ``_temp_dir``
/ ``_read_range``).  This file covers what was still dark:

* ``_is_virtuoso_process`` (the /proc probe that gates SIGINT),
* the watchdog timer and its interaction with ``_timeout_flag``,
* ``_read_frame`` / ``_read_byte`` (including the EAGAIN and EOF paths),
* ``handle_connection`` end to end: silent drops, NAK guards, the inline and
  temp-file wrappers, log frames, the internal-error path and cleanup,
* ``start_server`` (argv, EADDRINUSE, banner, accept loop),
* the ``__main__`` guard,
* the small stream helpers (``_safe_sendall`` / ``_safe_close`` / ``_emit_stat``
  / ``_send_error``) under a failing peer.

Everything runs in-process against the fake-CIW harness; no Virtuoso, no fixed
port, no repository writes.
"""

from __future__ import annotations

import errno
import io
import json
import os
import runpy
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

UNIT_DIR = Path(__file__).resolve().parent
if str(UNIT_DIR) not in sys.path:
    sys.path.insert(0, str(UNIT_DIR))

from _daemon_harness import (  # noqa: E402
    DAEMON_FILES,
    NAK,
    RS,
    STX,
    US,
    FakeConn,
    FakeStream,
    error_frame,
    load_daemon,
    meta_frame,
    request,
    run_request,
    value_frame,
)

VARIANTS = ("py3", "py27")
MODULES = {name: load_daemon(f"daemon_runtime_{name}", "tok", DAEMON_FILES[name])
           for name in VARIANTS}


def _as_stream(name: str, data: bytes):
    """py3 daemon reads bytes; py27 daemon reads text (its stdout stays binary)."""
    return data.decode("utf-8") if name == "py27" else data


class ScriptedStdin:
    """Feeds scripted reads to whichever stream shape the variant uses.

    ``read`` must honour ``size``: the daemon reads the frame **one byte at a
    time** (``sys.stdin.buffer.read(1)``), so a fake that hands back a whole
    scripted chunk per call makes the reader consume the RS terminator as part
    of the body and then loop for ever on the exhausted script.  Chunks are
    therefore sliced, and a chunk that is fully consumed moves on.
    """

    def __init__(self, script) -> None:
        self.script = list(script)
        self.buffer = self

    def read(self, size: int = -1):
        while self.script:
            item = self.script[0]
            if isinstance(item, BaseException):
                self.script.pop(0)
                raise item
            if size is None or size < 0:
                self.script.pop(0)
                return item
            if not item:
                self.script.pop(0)
                continue
            chunk, rest = item[:size], item[size:]
            if rest:
                self.script[0] = rest
            else:
                self.script.pop(0)
            return chunk
        return b""

    def fileno(self) -> int:
        return 0


class RecordingStderr:
    def __init__(self) -> None:
        self.text = ""

    def write(self, data) -> None:
        self.text += data

    def flush(self) -> None:
        return None


class BrokenStderr:
    def write(self, data) -> None:
        raise OSError("stderr is gone")

    def flush(self) -> None:
        raise OSError("stderr is gone")


class FailingSendConn(FakeConn):
    def sendall(self, data) -> None:
        raise OSError("peer went away")


class FakeProcOpen:
    """Stand-in for ``open`` used by the /proc probes."""

    def __init__(self, files, fail_binary=False, fail_text=False) -> None:
        self.files = files
        self.fail_binary = fail_binary
        self.fail_text = fail_text
        self.calls = []

    def __call__(self, path, mode="r", **kwargs):
        binary = "b" in mode
        self.calls.append((path, mode))
        if binary and self.fail_binary:
            raise OSError(errno.ENOENT, "no such file")
        if not binary and self.fail_text:
            raise OSError(errno.ENOENT, "no such file")
        try:
            payload = self.files[path]
        except KeyError:
            raise OSError(errno.ENOENT, "no such file") from None
        text, raw = payload if isinstance(payload, tuple) else (payload, payload)
        return _FakeFileHandle(raw if binary else text)


class _FakeFileHandle:
    def __init__(self, data) -> None:
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._data


class TestIsVirtuosoProcess(unittest.TestCase):
    """The SIGINT target must be validated before ``os.kill``."""

    def test_rejects_non_pid_values(self):
        for name in VARIANTS:
            mod = MODULES[name]
            for pid in ("4321", 0, 1, -3, None):
                with self.subTest(variant=name, pid=pid):
                    self.assertFalse(mod._is_virtuoso_process(pid))

    def test_comm_name_match(self):
        for name in VARIANTS:
            mod = MODULES[name]
            opener = FakeProcOpen({"/proc/4321/comm": ("  Virtuoso\n", b"  Virtuoso\n")})
            with mock.patch.object(mod, "open", opener, create=True):
                self.assertTrue(mod._is_virtuoso_process(4321))
            self.assertEqual(opener.calls, [("/proc/4321/comm", "r" if name == "py3" else "rb")])

    def test_falls_back_to_cmdline(self):
        for name in VARIANTS:
            mod = MODULES[name]
            opener = FakeProcOpen(
                {
                    "/proc/4321/comm": ("bash\n", b"bash\n"),
                    "/proc/4321/cmdline": (None, b"/tools/virtuoso/bin/dfII\0-sv\0"),
                }
            )
            with mock.patch.object(mod, "open", opener, create=True):
                self.assertTrue(mod._is_virtuoso_process(4321))
            self.assertEqual([c[0] for c in opener.calls],
                             ["/proc/4321/comm", "/proc/4321/cmdline"])

    def test_unrelated_process_is_rejected(self):
        for name in VARIANTS:
            mod = MODULES[name]
            opener = FakeProcOpen(
                {
                    "/proc/4321/comm": ("bash\n", b"bash\n"),
                    "/proc/4321/cmdline": (None, b"/bin/bash\0-i\0"),
                }
            )
            with mock.patch.object(mod, "open", opener, create=True):
                self.assertFalse(mod._is_virtuoso_process(4321))

    def test_unreadable_proc_entries_are_false(self):
        for name in VARIANTS:
            mod = MODULES[name]
            with mock.patch.object(mod, "open", FakeProcOpen({}), create=True):
                self.assertFalse(mod._is_virtuoso_process(4321))
            opener = FakeProcOpen(
                {"/proc/4321/comm": ("bash\n", b"bash\n")},
                fail_binary=True,
            )
            with mock.patch.object(mod, "open", opener, create=True):
                self.assertFalse(mod._is_virtuoso_process(4321))


class TestFcntlNonBlockingSetup(unittest.TestCase):
    """On hosts with fcntl the daemon flips its stdin to non-blocking."""

    def test_nonblocking_applied_when_fcntl_available(self):
        for name in VARIANTS:
            fake_fcntl = types.ModuleType("fcntl")
            calls = []
            fake_fcntl.F_GETFL = 3
            fake_fcntl.F_SETFL = 4
            fake_fcntl.fcntl = lambda fd, *args: calls.append((fd, *args)) or 0x41
            fake_stdin = ScriptedStdin([])
            # Windows has no os.O_NONBLOCK; the real host that runs this branch
            # (Linux) always does, so supply it for the import.
            with mock.patch.dict(sys.modules, {"fcntl": fake_fcntl}), \
                    mock.patch.object(sys, "stdin", fake_stdin), \
                    mock.patch.object(os, "O_NONBLOCK", 0o4000, create=True):
                mod = load_daemon(f"daemon_fcntl_{name}", "tok", DAEMON_FILES[name])
            self.assertIs(mod._fcntl, fake_fcntl)
            self.assertEqual(calls, [(0, 3), (0, 4, 0x41 | 0o4000)])


class TestWatchdog(unittest.TestCase):
    def test_stale_generation_does_not_interrupt(self):
        for name in VARIANTS:
            mod = MODULES[name]
            mod._timeout_flag = False
            mod._watchdog_gen = 9
            with mock.patch.object(mod.os, "kill") as kill:
                mod._watchdog_cb(3)
            kill.assert_not_called()
            self.assertFalse(mod._timeout_flag)

    def test_second_fire_is_idempotent(self):
        for name in VARIANTS:
            mod = MODULES[name]
            mod._timeout_flag = True
            mod._watchdog_gen = 9
            with mock.patch.object(mod.os, "kill") as kill:
                mod._watchdog_cb(9)
            kill.assert_not_called()

    def test_matching_generation_interrupts_virtuoso(self):
        for name in VARIANTS:
            mod = MODULES[name]
            mod._timeout_flag = False
            mod._watchdog_gen = 11
            # ``new=<lambda>`` yields the lambda from the context manager, so
            # ``is_virt.assert_called_once_with`` raised AttributeError; a Mock
            # both records the call and keeps the same behaviour.
            is_virt = mock.Mock(return_value=True)
            with mock.patch.object(mod, "virtuoso_pid", 4321), \
                    mock.patch.object(mod, "_is_virtuoso_process", is_virt), \
                    mock.patch.object(mod.os, "kill") as kill:
                mod._watchdog_cb(11)
            self.assertTrue(mod._timeout_flag)
            is_virt.assert_called_once_with(4321)
            kill.assert_called_once_with(4321, mod.signal.SIGINT)

    def test_unknown_or_foreign_target_skips_kill(self):
        for name in VARIANTS:
            mod = MODULES[name]
            mod._timeout_flag = False
            mod._watchdog_gen = 12
            with mock.patch.object(mod, "virtuoso_pid", None), \
                    mock.patch.object(mod.os, "kill") as kill:
                mod._watchdog_cb(12)
            kill.assert_not_called()
            mod._timeout_flag = False
            mod._watchdog_gen = 13
            with mock.patch.object(mod, "virtuoso_pid", 4321), \
                    mock.patch.object(mod, "_is_virtuoso_process", lambda pid: False), \
                    mock.patch.object(mod.os, "kill") as kill:
                mod._watchdog_cb(13)
            kill.assert_not_called()

    def test_kill_failure_is_swallowed(self):
        for name in VARIANTS:
            mod = MODULES[name]
            mod._timeout_flag = False
            mod._watchdog_gen = 14
            with mock.patch.object(mod, "virtuoso_pid", 4321), \
                    mock.patch.object(mod, "_is_virtuoso_process", lambda pid: True), \
                    mock.patch.object(mod.os, "kill", side_effect=ProcessLookupError):
                mod._watchdog_cb(14)
            self.assertTrue(mod._timeout_flag)


class TestReadFrame(unittest.TestCase):
    """Frame reader: normal frames, EOF, EAGAIN and the timeout frame."""

    def _read(self, name, script):
        mod = MODULES[name]
        stdin = ScriptedStdin([_as_stream(name, item) if isinstance(item, bytes) else item
                               for item in script])
        with mock.patch.object(mod.sys, "stdin", stdin):
            return mod._read_frame()

    def test_reads_value_and_error_frames(self):
        for name in VARIANTS:
            with self.subTest(variant=name):
                self.assertEqual(self._read(name, [b"\x02pay", b"load\x1e"]), b"\x02payload")
                self.assertEqual(self._read(name, [b"\x15boom\x1e"]), b"\x15boom")

    def test_returns_timeout_frame_on_eof(self):
        for name in VARIANTS:
            mod = MODULES[name]
            mod._timeout_flag = True
            with self.subTest(variant=name):
                self.assertEqual(self._read(name, []), b"\x15SKILL execution timed out\x1e")

    def test_returns_timeout_frame_on_slow_consumer(self):
        for name in VARIANTS:
            with self.subTest(variant=name):
                # one stray byte, then the watchdog fires before STX arrives
                mod = MODULES[name]
                mod._timeout_flag = False
                stdin = ScriptedStdin([_as_stream(name, b"x")])
                with mock.patch.object(mod.sys, "stdin", stdin):
                    mod._timeout_flag = True
                    got = mod._read_frame()
                self.assertEqual(got, b"\x15SKILL execution timed out\x1e")
                # STX received, then timeout while still inside the body
                mod._timeout_flag = False
                stdin = ScriptedStdin([_as_stream(name, b"\x02"), _as_stream(name, b"A")])
                with mock.patch.object(mod.sys, "stdin", stdin):
                    mod._timeout_flag = True
                    got = mod._read_frame()
                self.assertEqual(got, b"\x15SKILL execution timed out\x1e")

    def test_returns_timeout_frame_on_eagain(self):
        for name in VARIANTS:
            mod = MODULES[name]
            for script in ([IOError(errno.EAGAIN, "again")],
                           [_as_stream(name, b"\x02"), IOError(errno.EWOULDBLOCK, "again")]):
                with self.subTest(variant=name, script=script):
                    mod._timeout_flag = True
                    self.assertEqual(self._read(name, script),
                                     b"\x15SKILL execution timed out\x1e")

    def test_non_eagain_ioerror_propagates(self):
        for name in VARIANTS:
            mod = MODULES[name]
            mod._timeout_flag = False
            with self.subTest(variant=name):
                with self.assertRaises(IOError):
                    self._read(name, [IOError(errno.EIO, "disk gone")])


class TestHandleConnectionGuards(unittest.TestCase):
    """Every malformed foreign packet must be dropped without a response."""

    def test_empty_and_foreign_payloads_are_dropped_silently(self):
        for name in VARIANTS:
            mod = MODULES[name]
            for payload in (b"", b"{not json", b"\xff\xfe", b"[1,2]", b'"str"',
                            b'{"skill": "1+1"}', b'{"skill": 1, "token": "tok"}'):
                with self.subTest(variant=name, payload=payload):
                    conn = FakeConn(payload)
                    _out, sent, _unread, parsed = run_request(mod, request(), conn=conn)
                    self.assertEqual(sent, b"")
                    self.assertIsNone(parsed)
                    self.assertEqual(conn.shutdown_calls, 1)  # finally -> _safe_close

    def test_oversized_packet_is_dropped(self):
        for name in VARIANTS:
            mod = MODULES[name]
            payload = json.dumps(request(skill="x" * 64)).encode()
            conn = FakeConn(payload, chunk_size=8)
            with self.subTest(variant=name), \
                    mock.patch.object(mod, "_MAX_REQUEST_BYTES", 16):
                _out, sent, _unread, parsed = run_request(mod, request(), conn=conn)
            self.assertEqual(sent, b"")
            self.assertIsNone(parsed)

    def test_receive_timeout_is_dropped(self):
        for name in VARIANTS:
            mod = MODULES[name]
            conn = FakeConn(b"", recv_error=mod.socket.timeout("slow"))
            with self.subTest(variant=name):
                _out, sent, _unread, _parsed = run_request(mod, request(), conn=conn)
            self.assertEqual(sent, b"")
            self.assertEqual(conn.timeout, mod._REQUEST_READ_TIMEOUT)

    def test_invalid_timeout_values_are_dropped(self):
        for name in VARIANTS:
            mod = MODULES[name]
            for bad in (True, "abc", 0, -1, float("inf"), float("nan"), None):
                with self.subTest(variant=name, timeout=bad):
                    _out, sent, _unread, _parsed = run_request(mod, request(timeout=bad))
                    self.assertEqual(sent, b"")

    def test_bad_token_is_naked(self):
        for name in VARIANTS:
            mod = MODULES[name]
            _out, sent, _unread, parsed = run_request(mod, request(token="nope"))
            with self.subTest(variant=name):
                self.assertTrue(sent.startswith(NAK))
                self.assertEqual(parsed, {"error": "invalid token", "log": ""})

    def test_empty_daemon_token_rejects_every_request(self):
        for name in VARIANTS:
            mod = load_daemon(f"daemon_notoken_{name}", "", DAEMON_FILES[name])
            _out, sent, _unread, parsed = run_request(mod, request(token=""))
            with self.subTest(variant=name):
                self.assertTrue(sent.startswith(NAK))
                self.assertEqual(parsed["error"], "invalid token")

    def test_bad_log_level_and_budget_are_naked(self):
        for name in VARIANTS:
            mod = MODULES[name]
            cases = (
                {"log_level": "loud"},
                {"log_max_bytes": "many"},
                {"log_max_bytes": None},
                {"log_max_bytes": 0},
                {"log_max_bytes": -5},
            )
            for overrides in cases:
                with self.subTest(variant=name, overrides=overrides):
                    _out, sent, _unread, parsed = run_request(mod, request(**overrides))
                    self.assertTrue(sent.startswith(NAK))
                    self.assertTrue(parsed["error"].startswith("invalid "))


class TestHandleConnectionProtocol(unittest.TestCase):
    """Happy paths: the wrapper sent to the CIW, the response, counters."""

    def test_single_line_skill_uses_inline_wrapper(self):
        for name in VARIANTS:
            mod = MODULES[name]
            before = mod._RB_CALLS
            ciw, sent, _unread, parsed = run_request(
                mod, request(skill="1+1", log_level="off"), value_frame("2"))
            with self.subTest(variant=name):
                self.assertTrue(sent.startswith(STX))
                self.assertEqual(parsed, {"value": "2", "log": ""})
                self.assertIn(b"RBDLogOn=nil", ciw)
                self.assertIn(b"let(((__vb_r progn(1+1\n))) hiFlush() __vb_r)", ciw)
                self.assertEqual(mod._RB_CALLS, before + 1)

    def test_multi_line_skill_goes_through_a_temp_file_and_is_cleaned(self):
        for name in VARIANTS:
            mod = MODULES[name]
            with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
                with mock.patch.object(mod, "TEMP_DIR", tmp):
                    ciw, sent, _unread, parsed = run_request(
                        mod, request(skill="a = 1\nb = 2", log_level="off"),
                        value_frame("ok"))
                    leftovers = list(Path(tmp).glob("vb_eval_*.il"))
            with self.subTest(variant=name):
                self.assertIn(b'load("', ciw)
                self.assertEqual(leftovers, [])
                self.assertEqual(parsed["value"], "ok")

    def test_multi_line_skill_survives_unlink_failure(self):
        for name in VARIANTS:
            mod = MODULES[name]
            with tempfile.TemporaryDirectory(prefix="vb-") as tmp, \
                    mock.patch.object(mod, "TEMP_DIR", tmp), \
                    mock.patch.object(mod.os, "unlink", side_effect=OSError(errno.EACCES, "busy")):
                _ciw, sent, _unread, parsed = run_request(
                    mod, request(skill="a\nb", log_level="off"), value_frame("ok"))
            with self.subTest(variant=name):
                self.assertTrue(sent.startswith(STX))
                self.assertEqual(parsed["value"], "ok")

    def test_error_frame_propagates_and_counts(self):
        for name in VARIANTS:
            mod = MODULES[name]
            before = mod._RB_ERRORS
            _ciw, sent, _unread, parsed = run_request(
                mod, request(log_level="off"), error_frame("boom"))
            with self.subTest(variant=name):
                self.assertTrue(sent.startswith(NAK))
                self.assertEqual(parsed, {"error": "boom", "log": ""})
                self.assertEqual(mod._RB_ERRORS, before + 1)

    def test_log_off_never_reads_the_second_frame(self):
        for name in VARIANTS:
            mod = MODULES[name]
            trailing = meta_frame("/tmp/never-read.log", 0, 5)
            _ciw, sent, unread, parsed = run_request(
                mod, request(log_level="off"), value_frame("2") + trailing)
            with self.subTest(variant=name):
                self.assertTrue(sent.startswith(STX))
                self.assertEqual(parsed["log"], "")
                self.assertEqual(unread, trailing)

    def test_log_all_returns_the_requested_interval(self):
        for name in VARIANTS:
            mod = MODULES[name]
            with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
                log = Path(tmp) / "CDS.log"
                log.write_bytes(b"\\o first\n\\e second\n")
                ciw = value_frame("2") + meta_frame(str(log), 0, log.stat().st_size)
                _ciw, sent, _unread, parsed = run_request(
                    mod, request(log_level="all"), ciw)
            with self.subTest(variant=name):
                self.assertTrue(sent.startswith(STX))
                self.assertEqual(parsed["log"], "\\o first\n\\e second\n")

    def test_log_all_with_unreadable_file_reports_fixed_warning(self):
        for name in VARIANTS:
            mod = MODULES[name]
            missing = Path(tempfile.gettempdir()) / "vb-absent-runtime-CDS.log"
            if missing.exists():  # pragma: no cover - defensive
                missing.unlink()
            ciw = value_frame("2") + meta_frame(str(missing), 0, 10)
            _ciw, sent, _unread, parsed = run_request(mod, request(log_level="all"), ciw)
            with self.subTest(variant=name):
                self.assertTrue(sent.startswith(STX))
                self.assertEqual(parsed["value"], "2")
                self.assertTrue(parsed["warnings"][0].startswith("CDS.log unavailable: "))
                self.assertEqual(parsed["log"], "")

    def test_log_all_without_second_frame_times_out_but_keeps_the_value(self):
        for name in VARIANTS:
            mod = MODULES[name]
            _ciw, sent, _unread, parsed = run_request(
                mod, request(timeout=0.05, log_level="all"), value_frame("2"))
            with self.subTest(variant=name):
                self.assertTrue(sent.startswith(STX))
                self.assertEqual(parsed["value"], "2")
                self.assertTrue(parsed["warnings"][0].startswith("CDS.log unavailable: "))

    def test_temp_dir_is_created_for_multi_line_requests(self):
        for name in VARIANTS:
            mod = MODULES[name]
            with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
                target = Path(tmp) / "nested" / "deeper"
                with mock.patch.object(mod, "TEMP_DIR", str(target)):
                    _ciw, _sent, _unread, parsed = run_request(
                        mod, request(skill="a\nb", log_level="off"), value_frame("ok"))
                self.assertTrue(target.is_dir())
            with self.subTest(variant=name):
                self.assertEqual(parsed["value"], "ok")

    def test_makedirs_failure_does_not_break_the_request(self):
        """A non-creatable temp dir surfaces as the daemon's internal error.

        Documented behaviour: multi-line SKILL needs a temp file, so the whole
        request fails with ``internal daemon error`` instead of silently
        evaluating a different (inline) form.
        """
        for name in VARIANTS:
            mod = MODULES[name]
            with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
                missing = str(Path(tmp) / "gone")
                with mock.patch.object(mod, "TEMP_DIR", missing), \
                        mock.patch.object(mod.os, "makedirs", side_effect=OSError(errno.EACCES, "no")):
                    _ciw, sent, _unread, parsed = run_request(
                        mod, request(skill="a\nb", log_level="off"), value_frame("ok"))
            with self.subTest(variant=name):
                self.assertTrue(sent.startswith(NAK))
                self.assertEqual(parsed["error"], "internal daemon error")

    def test_stdin_read_error_ends_the_drain_loop(self):
        for name in VARIANTS:
            mod = MODULES[name]
            script = [IOError(errno.EIO, "stdin gone"), _as_stream(name, b"\x021\x1e")]
            conn = FakeConn(json.dumps(request(log_level="off")).encode())
            stdout = FakeStream()
            stdin = ScriptedStdin(script)
            with self.subTest(variant=name), \
                    mock.patch.object(mod.sys, "stdin", stdin), \
                    mock.patch.object(mod.sys, "stdout", stdout):
                mod.handle_connection(conn)
                mod._timeout_flag = True
            self.assertEqual(json.loads(bytes(conn.sent)[1:-1].decode())["value"], "1")

    def test_peer_failures_during_send_and_close_are_swallowed(self):
        for name in VARIANTS:
            mod = MODULES[name]
            conn = FailingSendConn(json.dumps(request(token="bad")).encode(),
                                   shutdown_error=OSError("already closed"))
            with self.subTest(variant=name):
                mod.handle_connection(conn)  # must not raise
            self.assertEqual(conn.shutdown_calls, 1)

    def test_internal_value_error_is_reported_to_the_traceback_only(self):
        """A reader ``ValueError`` is malformed input: log it, send nothing.

        Only the py3 daemon honours this today; see the characterisation test
        below for the py2.7 variant (P-029).
        """
        mod = MODULES["py3"]
        conn = FakeConn(json.dumps(request(log_level="off")).encode())
        stderr = RecordingStderr()
        with mock.patch.object(mod, "_read_frame", side_effect=ValueError("bad frame")), \
                mock.patch.object(mod.sys, "stderr", stderr), \
                mock.patch.object(mod.traceback, "print_exc") as print_exc:
            mod.handle_connection(conn)
        print_exc.assert_called_once()
        self.assertEqual(bytes(conn.sent), b"")

    def test_py27_reader_value_error_is_answered_with_nack(self):
        """P-029 characterisation: the py2.7 daemon answers the same ValueError
        with a NACK frame (``internal daemon error``) instead of staying silent.

        The two daemon variants must not diverge on the malformed-input
        contract.  This test pins *today's* behaviour so the gap is visible in
        the suite as well as in the bug tracker: when P-029 is fixed it MUST go
        red, and it should then be rewritten to the py3 expectation above.
        """
        mod = MODULES["py27"]
        conn = FakeConn(json.dumps(request(log_level="off")).encode())
        with mock.patch.object(mod, "_read_frame", side_effect=ValueError("bad frame")), \
                mock.patch.object(mod.sys, "stderr", RecordingStderr()), \
                mock.patch.object(mod.traceback, "print_exc") as print_exc:
            mod.handle_connection(conn)
        print_exc.assert_called_once()
        self.assertIn(b"internal daemon error", bytes(conn.sent))

    def test_internal_error_sends_nack_and_counts(self):
        for name in VARIANTS:
            mod = MODULES[name]
            before = mod._RB_ERRORS
            conn = FakeConn(json.dumps(request(log_level="off")).encode())
            with self.subTest(variant=name), \
                    mock.patch.object(mod, "_read_frame", side_effect=RuntimeError("kaboom")), \
                    mock.patch.object(mod.traceback, "print_exc"):
                mod.handle_connection(conn)
            sent = bytes(conn.sent)
            self.assertTrue(sent.startswith(NAK))
            self.assertEqual(json.loads(sent[1:-1].decode())["error"], "internal daemon error")
            self.assertEqual(mod._RB_ERRORS, before + 1)


class TestStreamHelpers(unittest.TestCase):
    def test_send_error_writes_a_nak_frame(self):
        for name in VARIANTS:
            mod = MODULES[name]
            conn = FakeConn()
            mod._send_error(conn, "boom")
            sent = bytes(conn.sent)
            with self.subTest(variant=name):
                self.assertTrue(sent.startswith(NAK))
                self.assertTrue(sent.endswith(RS))
                self.assertEqual(json.loads(sent[1:-1].decode())["error"], "boom")

    def test_safe_sendall_and_close_swallow_oserrors(self):
        for name in VARIANTS:
            mod = MODULES[name]
            with self.subTest(variant=name):
                mod._safe_sendall(FailingSendConn(), b"x")
                mod._safe_close(FailingSendConn())
                mod._safe_close(FakeConn(shutdown_error=OSError("nope")))

    def test_emit_stat_forced_and_throttled(self):
        for name in VARIANTS:
            mod = MODULES[name]
            stderr = RecordingStderr()
            with self.subTest(variant=name), mock.patch.object(mod.sys, "stderr", stderr):
                mod._RB_LAST_STAT_T = 0.0
                mod._emit_stat(force=True)
                first = stderr.text
                mod._emit_stat()  # inside the 1s window -> throttled away
            self.assertIn("[RB-stat] count=", first)
            self.assertEqual(stderr.text, first)

    def test_emit_stat_handles_a_broken_stderr(self):
        for name in VARIANTS:
            mod = MODULES[name]
            with self.subTest(variant=name), \
                    mock.patch.object(mod.sys, "stderr", BrokenStderr()):
                mod._emit_stat(force=True)

    def test_temp_dir_creation_failure_is_swallowed(self):
        for name in VARIANTS:
            mod = MODULES[name]
            with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
                missing = str(Path(tmp) / "not-there")
                with self.subTest(variant=name), \
                        mock.patch.object(mod, "TEMP_DIR", missing), \
                        mock.patch.object(mod.os, "makedirs", side_effect=OSError(errno.EACCES, "no")):
                    self.assertEqual(mod._temp_dir(), missing)


class TestLocalFileRangeReader(unittest.TestCase):
    def test_path_and_offset_edges(self):
        for name in VARIANTS:
            mod = MODULES[name]
            reader = mod.LocalFileRangeReader()
            with self.subTest(variant=name):
                self.assertEqual(reader.read("", 0, 10), ("", "CDS.log path unavailable"))
                self.assertEqual(
                    reader.read(str(Path(tempfile.gettempdir()) / "vb-absent-CDS.log"), 0, 10),
                    ("", "CDS.log unreadable"))
            with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
                log = Path(tmp) / "CDS.log"
                log.write_bytes(b"abcdef")
                with self.subTest(variant=name, case="clamped"):
                    self.assertEqual(reader.read(str(log), -5, 3), ("abc", None))
                    self.assertEqual(reader.read(str(log), 4, 999), ("ef", None))
                    self.assertEqual(reader.read(str(log), 5, 2), ("", None))
                    self.assertEqual(reader.read(str(log), 99, 120), (b"abcdef".decode(), None))
                with self.subTest(variant=name, case="directory"):
                    self.assertEqual(reader.read(tmp, 0, 4), ("", "CDS.log unreadable"))

    def test_read_range_delegates_to_the_active_reader(self):
        for name in VARIANTS:
            mod = MODULES[name]
            recorder = mock.Mock()
            recorder.read.return_value = ("delta", None)
            with self.subTest(variant=name), mock.patch.object(mod, "_READER", recorder):
                self.assertEqual(mod._read_range("/tmp/CDS.log", 1, 2), ("delta", None))
            recorder.read.assert_called_once_with("/tmp/CDS.log", 1, 2)

    def test_parse_meta_rejects_unparsable_offsets(self):
        for name in VARIANTS:
            mod = MODULES[name]
            payload = b"/tmp/CDS.log" + US + b"abc" + US + b"xyz"
            with self.subTest(variant=name):
                self.assertEqual(mod._parse_meta(payload), ("/tmp/CDS.log", 0, 0))
                self.assertEqual(mod._parse_meta(b"/tmp/CDS.log" + US + b"1"), (None, 0, 0))
                self.assertEqual(mod._parse_meta(b"\x1f\x1f"), (None, 0, 0))
                self.assertEqual(
                    mod._parse_meta(b'"CDS.log"' + US + b" 2 " + US + b"8"),
                    ("CDS.log", 2, 8))

    def test_keep_defaults_to_keeping_unknown_levels(self):
        for name in VARIANTS:
            mod = MODULES[name]
            with self.subTest(variant=name):
                self.assertTrue(mod._keep("future-level", "\\o info"))


class FakeSock:
    """Socket double for ``start_server`` (supports both daemon shapes)."""

    def __init__(self, module) -> None:
        self.module = module
        self.bound = []
        self.listen_calls = []
        self.closed = 0
        self.connected = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def setsockopt(self, *args):
        self.sockopts = args

    def bind(self, address):
        error = self.module.bind_error
        if error is not None:
            raise error
        self.bound.append(address)

    def listen(self, backlog):
        self.listen_calls.append(backlog)

    def accept(self):
        if self.module.accept_queue:
            return self.module.accept_queue.pop(0)
        raise self.module.stop_error("accept loop exited")

    def connect(self, address):
        self.connected.append(address)
        if self.module.probe_error is not None:
            raise self.module.probe_error

    def getsockname(self):
        return self.module.probe_address

    def close(self):
        self.closed += 1


class FakeSocketModule:
    AF_INET = 2
    SOCK_STREAM = 1
    SOCK_DGRAM = 2
    SOL_SOCKET = 0xFFFF
    SO_REUSEADDR = 4
    SHUT_RDWR = 2
    timeout = TimeoutError

    class _StopServer(Exception):
        pass

    def __init__(self, *, ip="10.1.2.3", accept_queue=(), bind_error=None,
                 probe_error=None, hostname="host-a", gethostbyname="10.9.9.9",
                 hostname_error=None) -> None:
        self.sockets = []
        self.probe_address = (ip, 80)
        self.accept_queue = list(accept_queue)
        self.bind_error = bind_error
        self.probe_error = probe_error
        self.hostname = hostname
        self.gethostbyname_value = gethostbyname
        self.hostname_error = hostname_error
        self.stop_error = FakeSocketModule._StopServer

    def socket(self, family, kind):
        sock = FakeSock(self)
        self.sockets.append((family, kind, sock))
        return sock

    def gethostname(self):
        if self.hostname_error is not None:
            raise self.hostname_error
        return self.hostname

    def gethostbyname(self, name):
        if self.hostname_error is not None:
            raise self.hostname_error
        return self.gethostbyname_value


class TestStartServer(unittest.TestCase):
    def test_missing_token_exits_with_error(self):
        for name in VARIANTS:
            mod = MODULES[name]
            stderr = RecordingStderr()
            with self.subTest(variant=name), \
                    mock.patch.object(mod.sys, "argv", ["daemon", "127.0.0.1", "65432"]), \
                    mock.patch.object(mod.sys, "stderr", stderr):
                with self.assertRaises(SystemExit) as caught:
                    mod.start_server()
            self.assertEqual(caught.exception.code, 1)
            self.assertIn("non-empty token", stderr.text)

    def test_main_guard_routes_into_start_server(self):
        for name in VARIANTS:
            stderr = io.StringIO()
            with self.subTest(variant=name), \
                    mock.patch.object(sys, "argv", ["daemon"]), \
                    redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as caught:
                    runpy.run_path(str(DAEMON_FILES[name]), run_name="__main__")
            self.assertEqual(caught.exception.code, 1)
            self.assertIn("non-empty token", stderr.getvalue())

    def test_bind_conflict_exits_with_the_documented_message(self):
        for name in VARIANTS:
            mod = MODULES[name]
            fake = FakeSocketModule(bind_error=OSError(errno.EADDRINUSE, "in use"))
            stderr = RecordingStderr()
            with self.subTest(variant=name), \
                    mock.patch.object(mod, "socket", fake), \
                    mock.patch.object(mod.sys, "argv",
                                      ["daemon", "127.0.0.1", "65081", "tok", "/tmp/work"]), \
                    mock.patch.object(mod.sys, "stderr", stderr):
                with self.assertRaises(SystemExit) as caught:
                    mod.start_server()
            self.assertEqual(caught.exception.code, 1)
            self.assertIn("already in use", stderr.text)

    def test_other_bind_errors_propagate(self):
        for name in VARIANTS:
            mod = MODULES[name]
            fake = FakeSocketModule(bind_error=OSError(errno.EACCES, "denied"))
            with self.subTest(variant=name), \
                    mock.patch.object(mod, "socket", fake), \
                    mock.patch.object(mod.sys, "argv",
                                      ["daemon", "127.0.0.1", "65081", "tok"]):
                with self.assertRaises(OSError):
                    mod.start_server()

    def _run_server(self, name, fake, argv):
        mod = MODULES[name]
        stderr = RecordingStderr()
        handled = []

        def handler(conn):
            handled.append(conn)
            raise RuntimeError("client handler blew up")

        with mock.patch.object(mod, "socket", fake), \
                mock.patch.object(mod.sys, "argv", argv), \
                mock.patch.object(mod.sys, "stderr", stderr), \
                mock.patch.object(mod, "handle_connection", handler), \
                mock.patch.object(mod.traceback, "print_exc") as print_exc:
            with self.assertRaises(FakeSocketModule._StopServer):
                mod.start_server()
        return stderr.text, handled, print_exc

    def test_accept_loop_uses_the_banner_and_survives_a_bad_client(self):
        for name in VARIANTS:
            fake = FakeSocketModule()
            conn = FakeConn()
            fake.accept_queue.append((conn, ("127.0.0.1", 40000)))
            with self.subTest(variant=name):
                text, handled, print_exc = self._run_server(
                    name, fake, ["daemon", "127.0.0.1", "65082", "tok", "/tmp/work"])
                self.assertEqual(handled, [conn])
                print_exc.assert_called_once()
                self.assertEqual(conn.shutdown_calls, 1)
                self.assertIn("[RB-banner] pid=", text)
                self.assertIn("bind=127.0.0.1:65082", text)
                self.assertIn("host=host-a", text)
                self.assertIn("ip=10.1.2.3", text)
                self.assertIn("user=", text)

    def test_banner_falls_back_when_the_ip_probe_fails(self):
        for name in VARIANTS:
            fake = FakeSocketModule(probe_error=OSError("no route"), gethostbyname="10.5.5.5")
            with self.subTest(variant=name):
                text, _handled, _print_exc = self._run_server(
                    name, fake, ["daemon", "127.0.0.1", "65082", "tok"])
                self.assertIn("ip=10.5.5.5", text)

    def test_banner_degrades_gracefully_when_identity_lookup_fails(self):
        for name in VARIANTS:
            fake = FakeSocketModule(probe_error=OSError("no route"),
                                    hostname_error=OSError("no dns"))
            with self.subTest(variant=name), \
                    mock.patch.dict(sys.modules, {"getpass": None}):
                text, _handled, _print_exc = self._run_server(
                    name, fake, ["daemon", "127.0.0.1", "65082", "tok"])
                self.assertIn("host=unknown", text)
                self.assertIn("ip=unknown", text)
                self.assertIn("user=", text)


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
