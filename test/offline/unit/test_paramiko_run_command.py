"""Paramiko run_command / close / ensure_connected 分支。"""

import contextlib
import socket
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import paramiko  # noqa: E402 - backend runtime dependency

from common import paramiko_backend as pb


def backend(**kw):
    params = dict(
        host="server-a", user="alice", jump_host=None, jump_user=None,
        ssh_key_path=None, ssh_config_path=None, connect_timeout=5, max_sessions=4,
    )
    params.update(kw)
    return pb.ParamikoSessionBackend(**params)


class FakeChannel:
    def __init__(self, out=b"hello ", err=b"warn", rc=3, exit_hold=False):
        self._out = [out] if out else []
        self._err = [err] if err else []
        self._rc = rc
        self.sent = b""
        self.exec_called = None
        self.shutdown_called = False
        self.closed = False
        self._exit_hold = exit_hold

    # exec side
    def settimeout(self, value):
        self.timeout = value

    def exec_command(self, cmd):
        self.exec_called = cmd

    def sendall(self, data):
        self.sent += data

    def shutdown_write(self):
        self.shutdown_called = True

    def close(self):
        self.closed = True

    # collect side
    def recv_ready(self):
        return bool(self._out)

    def recv(self, n):
        return self._out.pop(0)

    def recv_stderr_ready(self):
        return bool(self._err)

    def recv_stderr(self, n):
        return self._err.pop(0)

    def exit_status_ready(self):
        return True

    @property
    def eof_received(self):
        return True

    @property
    def closed_state(self):
        return True

    def recv_exit_status(self):
        return self._rc


class FakeTransport:
    def __init__(self, channel):
        self._channel = channel
        self.opened = 0

    def open_session(self, timeout=None):
        self.opened += 1
        if isinstance(self._channel, Exception):
            raise self._channel
        return self._channel


def lease(transport):
    """把 ``_session_lease`` 换成产出指定 transport 的上下文管理器（方法签名）。"""

    @contextlib.contextmanager
    def _lease(self, deadline, command):
        yield transport

    return _lease


class TestRunCommand(unittest.TestCase):
    def test_success(self):
        b = backend()
        channel = FakeChannel()
        transport = FakeTransport(channel)
        with mock.patch.object(pb.ParamikoSessionBackend, "_session_lease", lease(transport)):
            rc, out, err = b.run_command("echo hi", timeout=5)
        self.assertEqual((rc, out, err), (3, "hello ", "warn"))
        self.assertEqual(channel.exec_called, "sh -l")
        self.assertEqual(channel.sent, b"echo hi")
        self.assertTrue(channel.closed)

    def test_socket_timeout_maps_to_timeout_expired(self):
        b = backend()
        transport = FakeTransport(socket.timeout("slow"))
        with mock.patch.object(pb.ParamikoSessionBackend, "_session_lease", lease(transport)):
            with self.assertRaises(subprocess.TimeoutExpired):
                b.run_command("sleep 99", timeout=5)

    def test_generic_failure_is_transport_kind(self):
        b = backend()
        transport = FakeTransport(paramiko.SSHException("channel broke"))
        with mock.patch.object(pb.ParamikoSessionBackend, "_session_lease", lease(transport)), \
             mock.patch.object(pb.ParamikoSessionBackend, "_invalidate_if_transport_failed") as invalidate:
            rc, out, err = b.run_command("echo hi", timeout=5)
        self.assertEqual(rc, 255)
        self.assertTrue(err.startswith("VB-TRANSPORT: "), err)
        invalidate.assert_called_once()


class TestClose(unittest.TestCase):
    def test_close_releases_clients_and_jump_channel(self):
        b = backend(jump_host="bastion")
        b._target_client = mock.Mock()
        b._jump_channel = mock.Mock()
        b._jump_client = mock.Mock()
        target, jump_channel, jump_client = b._target_client, b._jump_channel, b._jump_client
        b.close()
        target.close.assert_called_once()
        jump_channel.close.assert_called_once()
        jump_client.close.assert_called_once()
        self.assertIsNone(b._target_client)
        self.assertIsNone(b._jump_channel)
        self.assertIsNone(b._jump_client)


class TestEnsureConnected(unittest.TestCase):
    def test_ready_transport_returns_immediately(self):
        b = backend()
        with mock.patch.object(pb.ParamikoSessionBackend, "_transport_is_ready", return_value=True), \
             mock.patch.object(pb.ParamikoSessionBackend, "_close_locked") as close_locked:
            b.ensure_connected(2)
        close_locked.assert_not_called()

    def test_lock_timeout_raises_timeout_expired(self):
        b = backend()
        fake_lock = mock.Mock()
        fake_lock.acquire.return_value = False
        b._connect_lock = fake_lock
        with self.assertRaises(subprocess.TimeoutExpired):
            b.ensure_connected(1)
        fake_lock.acquire.assert_called_once()


if __name__ == "__main__":
    unittest.main()
