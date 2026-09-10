"""Bottom-daemon wire tests.

Handler-level tests feed a fake Virtuoso pipe (works on Windows); subprocess
tests exercise real startup / invalid-token paths without a Virtuoso pipe.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from bridge.resources import ramic_bridge_daemon_3 as daemon

STX = b"\x02"
NAK = b"\x15"
RS = b"\x1e"
US = b"\x1f"


class FakePipeBuffer:
    """Non-blocking-ish byte pipe controllable from the test."""

    def __init__(self):
        self.pending = bytearray()
        self.lock = threading.Lock()
        self.written = bytearray()

    def read(self, n=1):
        with self.lock:
            if not self.pending:
                return b""
            out = bytes(self.pending[:n])
            del self.pending[:n]
            return out

    def feed(self, data: bytes):
        with self.lock:
            self.pending.extend(data)

    def write(self, data: bytes):
        with self.lock:
            self.written.extend(data)

    def flush(self):
        pass


class FakeStdin:
    def __init__(self, buffer):
        self.buffer = buffer


class FakeStdout:
    def __init__(self, buffer):
        self.buffer = buffer

    def flush(self):
        pass


class DaemonHandlerTestBase(unittest.TestCase):
    def _run_handler(self, request: dict, token="tok-1"):
        stdin_buf = FakePipeBuffer()
        stdout_buf = FakePipeBuffer()
        stdin = FakeStdin(stdin_buf)
        stdout = FakeStdout(stdout_buf)

        a, b = socket.socketpair()
        thread = threading.Thread(target=daemon.handle_connection, args=(a,))
        with mock.patch.object(daemon, "DAEMON_TOKEN", token), \
             mock.patch("sys.stdin", stdin), \
             mock.patch("sys.stdout", stdout), \
             mock.patch("sys.stderr", FakeStdout(FakePipeBuffer())):
            thread.start()
            b.sendall(json.dumps(request).encode("utf-8"))
            b.shutdown(socket.SHUT_WR)
            # once the skill has been written to the fake Virtuoso pipe,
            # answer with the two frames the il would produce
            for _ in range(100):
                if stdout_buf.written:
                    break
                time.sleep(0.01)
            if request.get("token") == token and "skill" in request:
                stdin_buf.feed(STX + b"2" + RS)
                stdin_buf.feed(US + b"/nonexistent/CDS.log" + US + b"0" + RS)
            chunks = []
            while True:
                chunk = b.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
            b.close()
            thread.join(timeout=5)
        a.close()
        return b"".join(chunks), bytes(stdout_buf.written)


class TestDaemonHandler(DaemonHandlerTestBase):
    def test_invalid_token_is_nak_without_touching_pipe(self):
        raw, sent = self._run_handler({"skill": "1+1", "timeout": 5, "token": "wrong"})
        self.assertTrue(raw.startswith(NAK), raw)
        self.assertIn("invalid token", raw.decode())
        self.assertEqual(sent, b"")

    def test_valid_single_line_skill_roundtrip(self):
        raw, sent = self._run_handler({"skill": "1+1", "timeout": 5, "token": "tok-1"})
        self.assertTrue(raw.startswith(STX), raw)
        body = json.loads(raw[1:].rstrip(RS).decode("utf-8"))
        self.assertEqual(body["value"], "2")
        self.assertEqual(body["log"], "")
        self.assertIn(b"let((", sent)

    def test_multiline_skill_is_packaged_into_il_file(self):
        raw, sent = self._run_handler({"skill": "a = 1\nb = 2", "timeout": 5, "token": "tok-1"})
        self.assertTrue(raw.startswith(STX), raw)
        self.assertIn(b'load("', sent)
        self.assertIn(b".il", sent)

    def test_timeout_without_virtuoso_reply(self):
        # do not feed frames; the watchdog should produce a TimeoutError
        a, b = socket.socketpair()
        thread = threading.Thread(target=daemon.handle_connection, args=(a,))
        with mock.patch.object(daemon, "DAEMON_TOKEN", "tok-1"), \
             mock.patch("sys.stdin", FakeStdin(FakePipeBuffer())), \
             mock.patch("sys.stdout", FakeStdout(FakePipeBuffer())), \
             mock.patch("sys.stderr", FakeStdout(FakePipeBuffer())):
            thread.start()
            b.sendall(json.dumps({"skill": "1+1", "timeout": 0.3, "token": "tok-1"}).encode())
            b.shutdown(socket.SHUT_WR)
            chunks = []
            while True:
                chunk = b.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
            b.close()
            thread.join(timeout=5)
        a.close()
        raw = b"".join(chunks)
        self.assertTrue(raw.startswith(NAK), raw)
        self.assertIn("TimeoutError", raw.decode())

    def test_json_decode_error(self):
        a, b = socket.socketpair()
        thread = threading.Thread(target=daemon.handle_connection, args=(a,))
        with mock.patch.object(daemon, "DAEMON_TOKEN", "tok-1"), \
             mock.patch("sys.stdin", FakeStdin(FakePipeBuffer())), \
             mock.patch("sys.stdout", FakeStdout(FakePipeBuffer())), \
             mock.patch("sys.stderr", FakeStdout(FakePipeBuffer())):
            thread.start()
            b.sendall(b"{not json")
            b.shutdown(socket.SHUT_WR)
            chunks = []
            while True:
                chunk = b.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
            b.close()
            thread.join(timeout=5)
        a.close()
        raw = b"".join(chunks)
        self.assertTrue(raw.startswith(NAK), raw)
        self.assertIn("JSONDecodeError", raw.decode())


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Py2Pipe:
    """Text-mode fake pipe used by the Python 2.7 daemon variant."""

    def __init__(self):
        self.pending = ""
        self.written = b""
        self.lock = threading.Lock()

    def read(self, n=1):
        with self.lock:
            if not self.pending:
                return ""
            out, self.pending = self.pending[:n], self.pending[n:]
            return out

    def feed(self, data: bytes):
        with self.lock:
            self.pending += data.decode("latin-1")

    def write(self, data):
        with self.lock:
            self.written += data

    def flush(self):
        pass


class TestDaemon27Handler(unittest.TestCase):
    """Same wire scenarios against the Python 2.7-compatible daemon."""

    def _run(self, request, token="tok-1"):
        from bridge.resources import ramic_bridge_daemon_27 as d27
        stdin_pipe = Py2Pipe()
        stdout_pipe = Py2Pipe()
        a, b = socket.socketpair()
        thread = threading.Thread(target=d27.handle_connection, args=(a,))
        with mock.patch.object(d27, "DAEMON_TOKEN", token), \
             mock.patch("sys.stdin", type("S", (), {"read": stdin_pipe.read})()), \
             mock.patch("sys.stdout", type("S", (), {"write": stdout_pipe.write, "flush": lambda s: None})()), \
             mock.patch("sys.stderr", type("S", (), {"write": lambda s, d: None, "flush": lambda s: None})()):
            thread.start()
            b.sendall(json.dumps(request).encode("utf-8"))
            b.shutdown(socket.SHUT_WR)
            for _ in range(100):
                if stdout_pipe.written:
                    break
                time.sleep(0.01)
            if request.get("token") == token:
                stdin_pipe.feed(STX + b"2" + RS)
                stdin_pipe.feed(US + b"/nonexistent/CDS.log" + US + b"0" + RS)
            chunks = []
            while True:
                chunk = b.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
            b.close()
            thread.join(timeout=5)
        a.close()
        return b"".join(chunks), stdout_pipe.written

    def test_invalid_token_nak(self):
        raw, _ = self._run({"skill": "1+1", "token": "wrong"})
        self.assertTrue(raw.startswith(NAK), raw)
        self.assertIn(b"invalid token", raw)

    def test_valid_single_line(self):
        raw, sent = self._run({"skill": "1+1", "timeout": 5, "token": "tok-1"})
        self.assertTrue(raw.startswith(STX), raw)
        body = json.loads(raw[1:].rstrip(RS).decode("utf-8"))
        self.assertEqual(body["value"], "2")
        self.assertIn(b"let((", sent)

    def test_multiline_packaged(self):
        raw, sent = self._run({"skill": "a = 1\nb = 2", "timeout": 5, "token": "tok-1"})
        self.assertTrue(raw.startswith(STX), raw)
        self.assertIn(b'load("', sent)


class TestDaemonSubprocess(unittest.TestCase):
    DAEMON = Path(__file__).resolve().parents[2] / "src" / "bridge" / "resources" / "ramic_bridge_daemon_3.py"

    def _start(self, *args):
        proc = subprocess.Popen(
            [sys.executable, "-u", str(self.DAEMON), *args],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        return proc

    def _wait_port(self, port, timeout=5.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                s = socket.create_connection(("127.0.0.1", port), timeout=0.3)
                s.close()
                return True
            except OSError:
                time.sleep(0.05)
        return False

    def test_missing_token_exits_nonzero(self):
        proc = self._start("127.0.0.1", str(_free_port()))
        rc = proc.wait(timeout=10)
        err = proc.stderr.read()
        proc.stdout.close()
        proc.stderr.close()
        self.assertNotEqual(rc, 0)
        self.assertIn(b"token", err.lower())

    def test_port_in_use_exits_nonzero(self):
        blocker = socket.socket()
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        port = blocker.getsockname()[1]
        proc = self._start("127.0.0.1", str(port), "tok-1")
        try:
            rc = proc.wait(timeout=10)
            err = proc.stderr.read()
            proc.stdout.close()
            proc.stderr.close()
            self.assertNotEqual(rc, 0)
            self.assertIn(b"error", err.lower())
        finally:
            blocker.close()

    def test_invalid_token_over_tcp(self):
        port = _free_port()
        proc = self._start("127.0.0.1", str(port), "tok-1")
        try:
            self.assertTrue(self._wait_port(port), "daemon did not bind")
            s = socket.create_connection(("127.0.0.1", port), timeout=5)
            s.sendall(json.dumps({"skill": "1+1", "token": "wrong"}).encode())
            s.shutdown(socket.SHUT_WR)
            raw = b""
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                raw += chunk
            s.close()
            self.assertTrue(raw.startswith(NAK), raw)
            self.assertIn(b"invalid token", raw)
        finally:
            proc.terminate()
            proc.wait(timeout=5)
            proc.stdout.close()
            proc.stderr.close()


if __name__ == "__main__":
    unittest.main()
