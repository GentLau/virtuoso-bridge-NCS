"""Paramiko shell/tunnel wrappers and stream helpers (fake sessions, no SSH).

``ParamikoShellProcess`` and ``ParamikoTunnel`` are the pieces that make the
Paramiko backend behave like the OpenSSH subprocess backend: exit polling,
daemonized local forwarding, and bounded stream pumping.  They are pure
process-local logic, so everything here runs offline; the wire-level
equivalents live in ``test/semi/transport``.
"""

from __future__ import annotations

import queue
import socket
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from common import paramiko_backend as pb


class _FakeChannel:
    """Channel double with an optional scripted receive buffer."""

    def __init__(self, *, exit_status=0, exit_ready=True, chunks=()):
        self._exit_status = exit_status
        self._exit_ready = exit_ready
        self._recv_queue: queue.Queue = queue.Queue()
        for chunk in chunks:
            self._recv_queue.put(chunk)
        self.sent: list[bytes] = []
        self.closed = False
        self.shutdown_writes = 0

    # -- exit status -------------------------------------------------------
    def exit_status_ready(self):
        return self._exit_ready

    def recv_exit_status(self):
        return self._exit_status

    # -- io ----------------------------------------------------------------
    def recv(self, _n):
        try:
            return self._recv_queue.get(timeout=0.05)
        except queue.Empty:
            return b""

    def sendall(self, data):
        self.sent.append(data)

    def shutdown_write(self):
        self.shutdown_writes += 1

    def close(self):
        self.closed = True
        self._exit_ready = True


class _FakeStream:
    def __init__(self, *, fail_close=False):
        self.closed = False
        self._fail_close = fail_close

    def close(self):
        if self._fail_close:
            raise OSError("already closed")
        self.closed = True


class _FakeBackend:
    def __init__(self):
        self.released = 0

    def _release_shell_gate(self):
        self.released += 1


class TestParamikoShellProcess(unittest.TestCase):
    def _process(self, channel=None, **kwargs):
        self.backend = _FakeBackend()
        self.channel = channel or _FakeChannel()
        self.stdin = _FakeStream(**kwargs)
        self.stdout = _FakeStream(**kwargs)
        return pb.ParamikoShellProcess(
            self.channel, self.stdin, self.stdout, self.backend  # type: ignore[arg-type]
        )

    def test_poll_returns_none_while_running_and_status_after_exit(self):
        channel = _FakeChannel(exit_status=7, exit_ready=False)
        proc = self._process(channel)
        self.assertIsNone(proc.poll())
        channel._exit_ready = True
        self.assertEqual(proc.poll(), 7)

    def test_poll_maps_closed_channel_to_255(self):
        channel = _FakeChannel()
        channel.recv_exit_status = mock.Mock(side_effect=RuntimeError("closed"))
        proc = self._process(channel)
        self.assertEqual(proc.poll(), 255)

    def test_wait_without_timeout_reads_exit_status(self):
        proc = self._process(_FakeChannel(exit_status=3))
        self.assertEqual(proc.wait(), 3)

    def test_wait_returns_as_soon_as_status_is_ready(self):
        channel = _FakeChannel(exit_status=4, exit_ready=False)
        proc = self._process(channel)
        threading.Timer(0.05, lambda: setattr(channel, "_exit_ready", True)).start()
        self.assertEqual(proc.wait(timeout=2), 4)

    def test_wait_times_out_when_status_never_arrives(self):
        proc = self._process(_FakeChannel(exit_ready=False))
        with self.assertRaises(subprocess.TimeoutExpired):
            proc.wait(timeout=0.05)

    def test_kill_and_terminate_both_close_and_release_the_gate(self):
        proc = self._process()
        proc.terminate()
        self.assertTrue(self.channel.closed)
        self.assertEqual(self.backend.released, 1)

        # second close is a no-op: the gate must not be released twice
        proc.close()
        self.assertEqual(self.backend.released, 1)

        other = self._process()
        other.kill()
        self.assertTrue(self.channel.closed)
        self.assertEqual(self.backend.released, 1)

    def test_close_swallows_stream_and_channel_errors(self):
        channel = _FakeChannel()
        channel.close = mock.Mock(side_effect=RuntimeError("gone"))
        proc = self._process(channel, fail_close=True)
        proc.close()  # must not raise
        self.assertEqual(self.backend.released, 1)


class TestStreamHelpers(unittest.TestCase):
    def test_read_stream_collects_until_eof(self):
        class _Stream:
            def __init__(self):
                self._chunks = [b"a", b"b", b""]

            def read(self, _n):
                return self._chunks.pop(0)

        chunks: list[bytes] = []
        failures: queue.Queue = queue.Queue()
        pb._read_stream(_Stream(), chunks, failures)
        self.assertEqual(chunks, [b"a", b"b"])
        self.assertTrue(failures.empty())

    def test_read_stream_reports_failure(self):
        class _Stream:
            def read(self, _n):
                raise OSError("broken")

        chunks: list[bytes] = []
        failures: queue.Queue = queue.Queue()
        pb._read_stream(_Stream(), chunks, failures)
        self.assertIsInstance(failures.get_nowait(), OSError)

    def test_send_stream_to_channel_forwards_and_shuts_down(self):
        class _Stream:
            def __init__(self):
                self._chunks = [b"x", b"y", b""]

            def read(self, _n):
                return self._chunks.pop(0)

        channel = _FakeChannel()
        failures: queue.Queue = queue.Queue()
        pb._send_stream_to_channel(_Stream(), channel, failures)
        self.assertEqual(channel.sent, [b"x", b"y"])
        self.assertEqual(channel.shutdown_writes, 1)
        self.assertTrue(failures.empty())

    def test_send_stream_reports_channel_failure(self):
        class _Stream:
            def read(self, _n):
                return b"payload"

        channel = _FakeChannel()
        channel.sendall = mock.Mock(side_effect=OSError("closed"))
        failures: queue.Queue = queue.Queue()
        pb._send_stream_to_channel(_Stream(), channel, failures)
        self.assertIsInstance(failures.get_nowait(), OSError)

    def test_copy_stream_writes_and_closes_destination(self):
        class _Stream:
            def __init__(self):
                self._chunks = [b"1", b"2", b""]

            def read(self, _n):
                return self._chunks.pop(0)

        class _Sink:
            def __init__(self):
                self.data = b""
                self.closed = False

            def write(self, chunk):
                self.data += chunk

            def close(self):
                self.closed = True

        sink = _Sink()
        failures: queue.Queue = queue.Queue()
        pb._copy_stream(_Stream(), sink, failures)
        self.assertEqual(sink.data, b"12")
        self.assertTrue(sink.closed)
        self.assertTrue(failures.empty())

    def test_copy_stream_swallows_close_error_and_reports_read_error(self):
        class _Stream:
            def read(self, _n):
                raise OSError("read failed")

        class _Sink:
            def write(self, _chunk):
                return None

            def close(self):
                raise OSError("close failed")

        failures: queue.Queue = queue.Queue()
        pb._copy_stream(_Stream(), _Sink(), failures)
        self.assertIsInstance(failures.get_nowait(), OSError)

    def test_channel_open_failure_detection(self):
        class ChannelException(Exception):
            def __init__(self, code):
                super().__init__("boom")
                self.code = code

        self.assertTrue(pb._is_channel_open_failure(Exception("Connect failed")))
        self.assertTrue(
            pb._is_channel_open_failure(Exception("Unable to open channel."))
        )
        self.assertTrue(pb._is_channel_open_failure(ChannelException(2)))
        self.assertFalse(pb._is_channel_open_failure(ChannelException(1)))
        self.assertFalse(pb._is_channel_open_failure(Exception("Timeout opening channel.")))
        self.assertFalse(pb._is_channel_open_failure(Exception("nope")))


class _FakeTransport:
    def __init__(self, *, active=True, authenticated=True, channel_factory=None):
        self._active = active
        self._authenticated = authenticated
        self.channel_factory = channel_factory or (lambda: _FakeChannel())
        self.opened: list[tuple] = []

    def is_active(self):
        return self._active

    def is_authenticated(self):
        return self._authenticated

    def open_channel(self, kind, dest, src, timeout=None):
        self.opened.append((kind, dest, src, timeout))
        return self.channel_factory()


class TestParamikoTunnel(unittest.TestCase):
    def _tunnel(self, transport=None, getter=None):
        transport = transport if transport is not None else _FakeTransport()
        getter = getter or (lambda: transport)
        tunnel = pb.ParamikoTunnel(getter, "127.0.0.1", 0, "remote.local", 1234)
        self.addCleanup(tunnel.terminate)
        return tunnel, transport

    def test_round_trip_forwards_bytes_through_the_channel(self):
        channel = _FakeChannel(chunks=[b"pong", b""])

        def echo(data):
            channel._recv_queue.put(b"pong")
            return None

        channel.sendall = echo  # type: ignore[assignment]
        transport = _FakeTransport(channel_factory=lambda: channel)
        tunnel, _transport = self._tunnel(transport)
        port = tunnel._listener.getsockname()[1]

        with socket.create_connection(("127.0.0.1", port), timeout=5) as client:
            client.sendall(b"ping")
            client.settimeout(5)
            self.assertEqual(client.recv(64), b"pong")

        self.assertEqual(transport.opened[0][0], "direct-tcpip")
        self.assertEqual(transport.opened[0][1], ("remote.local", 1234))

    def test_inactive_transport_refuses_without_crashing(self):
        transport = _FakeTransport(active=False)
        tunnel, _transport = self._tunnel(transport)
        port = tunnel._listener.getsockname()[1]
        with socket.create_connection(("127.0.0.1", port), timeout=5) as client:
            client.settimeout(5)
            self.assertEqual(client.recv(64), b"")
        self.assertEqual(transport.opened, [])

    def test_refused_channel_is_dropped(self):
        transport = _FakeTransport(channel_factory=lambda: None)
        tunnel, _transport = self._tunnel(transport)
        port = tunnel._listener.getsockname()[1]
        with socket.create_connection(("127.0.0.1", port), timeout=5) as client:
            client.settimeout(5)
            self.assertEqual(client.recv(64), b"")

    def test_poll_terminates_when_transport_disappears(self):
        transport = _FakeTransport()
        tunnel, _transport = self._tunnel(transport)
        self.assertIsNone(tunnel.poll())
        transport._active = False
        self.assertEqual(tunnel.poll(), 0)
        self.assertEqual(tunnel.poll(), 0)  # idempotent

    def test_poll_terminates_on_transport_error(self):
        def getter():
            raise RuntimeError("transport gone")

        tunnel, _transport = self._tunnel(getter=getter)
        self.assertEqual(tunnel.poll(), 0)

    def test_terminate_closes_listener_channels_and_clients(self):
        channel = _FakeChannel()
        transport = _FakeTransport(channel_factory=lambda: channel)
        tunnel, _transport = self._tunnel(transport)
        client = _FakeStream()
        with tunnel._lock:
            tunnel._channels.add(channel)
            tunnel._clients.add(client)
        tunnel.terminate()
        tunnel.terminate()  # second call returns early
        self.assertTrue(channel.closed)
        self.assertTrue(client.closed)
        with self.assertRaises(OSError):
            tunnel._listener.getsockname()

    def test_wait_joins_pump_threads_and_returns_zero(self):
        tunnel, _transport = self._tunnel()
        self.assertEqual(tunnel.wait(timeout=1.0), 0)
        tunnel.terminate()
        self.assertEqual(tunnel.wait(timeout=1.0), 0)

    def test_pumps_swallow_peer_errors(self):
        tunnel, _transport = self._tunnel()

        class _BadClient:
            def recv(self, _n):
                raise OSError("peer died")

        class _BadChannel:
            def recv(self, _n):
                raise OSError("peer died")

            def shutdown_write(self):
                raise OSError("closed")

            def sendall(self, _data):
                raise OSError("closed")

        class _BadSock:
            def shutdown(self, _how):
                raise OSError("closed")

            def sendall(self, _data):
                raise OSError("closed")

        tunnel._pump_local_to_channel(_BadClient(), _BadChannel())
        tunnel._pump_channel_to_local(_BadChannel(), _BadSock())

    def test_accept_loop_exits_on_listener_error(self):
        tunnel, _transport = self._tunnel()
        tunnel._listener.close()
        tunnel._stop.set()
        tunnel._accept_loop()  # no exception even after the listener is gone


if __name__ == "__main__":
    unittest.main()
