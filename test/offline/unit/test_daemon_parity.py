"""Parity tests: the Python 3 and Python 2.7 daemons share one fixture set."""

import os
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from bridge.resources import ramic_bridge_daemon_3 as d3
from bridge.resources import ramic_bridge_daemon_27 as d27

MODULES = [("daemon_3", d3), ("daemon_27", d27)]


class TestDaemonParity(unittest.TestCase):
    def _classify(self, mod, line):
        return mod.classify_level(line)

    def test_safe_close_shuts_down_and_closes(self):
        """C1: 连接收尾必须 close()，不能只 shutdown()（fd 不能等 GC）。"""
        for name, mod in MODULES:
            with self.subTest(daemon=name):
                conn = mock.Mock()
                mod._safe_close(conn)
                conn.shutdown.assert_called_once_with(socket.SHUT_RDWR)
                conn.close.assert_called_once()

    def test_classify_parity(self):
        for name, mod in MODULES:
            self.assertEqual(mod.classify_level("\\e x"), "error", name)
            self.assertEqual(mod.classify_level("\\w x"), "warning", name)
            self.assertEqual(mod.classify_level("\\o x"), "info", name)
            self.assertEqual(mod.classify_level("plain"), "info", name)

    def test_filter_levels_parity(self):
        raw = "\\o out\n\\w warn\n\\e error\nVB-BEGIN\nVB-END\nplain\n"
        for name, mod in MODULES:
            text, _ = mod.filter_delta(raw, "off", 1000)
            self.assertEqual(text, "", name)
            text, _ = mod.filter_delta(raw, "warn", 1000)
            self.assertIn("warn", text, name)
            self.assertIn("error", text, name)
            self.assertNotIn("out", text, name)
            self.assertNotIn("plain", text, name)  # unclassified = info, dropped by warn
            text, _ = mod.filter_delta(raw, "error", 1000)
            self.assertIn("error", text, name)
            self.assertNotIn("warn", text, name)

    def test_truncation_degrade_parity(self):
        raw = "\\e " + ("x" * 200) + "\n" + ("\\o y\n" * 100)
        for name, mod in MODULES:
            text, truncated = mod.filter_delta(raw, "all", 50)
            self.assertTrue(truncated, name)
            self.assertIn("error-only", text, name)
            self.assertNotIn("\\o y", text, name)

    def test_parse_meta_parity(self):
        for name, mod in MODULES:
            self.assertEqual(mod._parse_meta(b"/tmp/CDS.log\x1f10\x1f42"), ("/tmp/CDS.log", 10, 42))
            self.assertEqual(mod._parse_meta(b"no-separator"), (None, 0, 0))
            self.assertEqual(mod._parse_meta(b"/p\x1fabc"), (None, 0, 0))

    def test_temp_dir_uses_configured_working_dir(self):
        for name, mod in MODULES:
            configured = Path(tempfile.mkdtemp(prefix="vb-"))
            previous = mod.TEMP_DIR
            try:
                mod.TEMP_DIR = str(configured)
                self.assertEqual(Path(mod._temp_dir()), configured, name)
            finally:
                mod.TEMP_DIR = previous

    def test_temp_dir_fallback_is_not_system_tmp(self):
        for name, mod in MODULES:
            previous = mod.TEMP_DIR
            try:
                mod.TEMP_DIR = ""
                fallback = Path(mod._temp_dir()).resolve()
                self.assertNotEqual(
                    fallback,
                    Path(tempfile.gettempdir()).resolve(),
                    name,
                )
                self.assertTrue(fallback.is_dir(), name)
            finally:
                mod.TEMP_DIR = previous

    def test_read_range_offset_delta(self):
        for name, mod in MODULES:
            f = Path(tempfile.mkdtemp(prefix="vb-")) / "CDS.log"
            f.write_bytes(b"abc")
            self.assertEqual(mod._read_range(str(f), 0, 2), ("ab", None), name)
            self.assertEqual(mod._read_range(str(f), 2, 3), ("c", None), name)
            # rotated/truncated file: start > size -> read current file from 0
            self.assertEqual(mod._read_range(str(f), 100, 50), ("abc", None), name)
            self.assertEqual(mod._read_range(str(f), -1, 99), ("abc", None), name)
            self.assertEqual(mod._read_range("", 0, 10), ("", "CDS.log path unavailable"), name)


class TestDaemonSocketHardening(unittest.TestCase):
    """Direct-port hardening: bounded reads; foreign packets are dropped."""

    def _exchange(self, mod, payload, *, hold_open=False):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        address = listener.getsockname()
        errors = []

        def serve():
            try:
                conn, _ = listener.accept()
                try:
                    mod.handle_connection(conn)
                finally:
                    conn.close()
            except Exception as exc:  # noqa: BLE001 - diagnostic
                errors.append(exc)
            finally:
                listener.close()

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        client = socket.create_connection(address, timeout=3)
        client.sendall(payload)
        if not hold_open:
            client.shutdown(socket.SHUT_WR)
        data = b""
        try:
            while b"\x1e" not in data:
                chunk = client.recv(65536)
                if not chunk:
                    break
                data += chunk
        finally:
            client.close()
            thread.join(timeout=3)
        self.assertFalse(thread.is_alive(), "daemon handler did not terminate")
        self.assertEqual(errors, [])
        return data

    def test_foreign_payload_is_dropped_silently(self):
        for name, mod in MODULES:
            old_timeout = mod._REQUEST_READ_TIMEOUT
            try:
                mod._REQUEST_READ_TIMEOUT = 0.3
                data = self._exchange(
                    mod, b'{"skill": 5, "token": "x"}'
                )
            finally:
                mod._REQUEST_READ_TIMEOUT = old_timeout
            self.assertEqual(data, b"", name)
            self.assertNotIn(b"Traceback", data, name)
            self.assertNotIn(b"object has no attribute", data, name)

    def test_half_open_request_is_dropped_silently(self):
        for name, mod in MODULES:
            old_timeout = mod._REQUEST_READ_TIMEOUT
            try:
                mod._REQUEST_READ_TIMEOUT = 0.2
                data = self._exchange(
                    mod, b'{"skill": "1+1"', hold_open=True
                )
            finally:
                mod._REQUEST_READ_TIMEOUT = old_timeout
            self.assertEqual(data, b"", name)

    def test_watchdog_rejects_pid_one_and_stale_generation(self):
        for name, mod in MODULES:
            self.assertFalse(mod._is_virtuoso_process(1), name)
            old_pid = mod.virtuoso_pid
            old_gen = mod._watchdog_gen
            old_flag = mod._timeout_flag
            calls = []
            try:
                mod.virtuoso_pid = os.getpid()
                mod._watchdog_gen = 2
                mod._timeout_flag = False
                with mock.patch.object(
                    mod, "_is_virtuoso_process", return_value=True
                ), mock.patch.object(
                    mod.os, "kill", side_effect=lambda *a: calls.append(a)
                ):
                    mod._watchdog_cb(1)
            finally:
                mod.virtuoso_pid = old_pid
                mod._watchdog_gen = old_gen
                mod._timeout_flag = old_flag
            self.assertEqual(calls, [], name)


if __name__ == "__main__":
    unittest.main()
