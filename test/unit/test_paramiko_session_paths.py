"""Paramiko 会话层：传输就绪判定、连接探测、known_hosts 解析、通道聚合。"""

import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import paramiko  # noqa: E402 - backend runtime dependency
from common import paramiko_backend as pb


def backend(**kw):
    params = dict(
        host="server-a", user="alice", jump_host=None, jump_user=None,
        ssh_key_path=None, ssh_config_path=None, connect_timeout=5, max_sessions=4,
    )
    params.update(kw)
    return pb.ParamikoSessionBackend(**params)


class FakeTransport:
    def __init__(self, active=True, authenticated=True):
        self._active = active
        self._auth = authenticated

    def is_active(self):
        return self._active

    def is_authenticated(self):
        return self._auth


class FakeClient:
    def __init__(self, transport=None):
        self._transport = transport

    def get_transport(self):
        return self._transport


class TestTransportReady(unittest.TestCase):
    def test_branches(self):
        ready = pb.ParamikoSessionBackend._transport_is_ready
        self.assertFalse(ready(None))
        self.assertFalse(ready(FakeClient(None)))
        self.assertFalse(ready(FakeClient(FakeTransport(active=False))))
        self.assertFalse(ready(FakeClient(FakeTransport(authenticated=False))))
        self.assertTrue(ready(FakeClient(FakeTransport())))


class TestTestConnection(unittest.TestCase):
    def test_success(self):
        b = backend()
        with mock.patch.object(pb.ParamikoSessionBackend, "ensure_connected") as ensure:
            self.assertTrue(b.test_connection(3))
        ensure.assert_called_once_with(3)

    def test_failures_are_false(self):
        b = backend()
        for exc in (OSError("boom"), socket.error("net"), subprocess.TimeoutExpired("ssh", 3),
                    paramiko.SSHException("ssh error")):
            with self.subTest(exc=type(exc).__name__):
                with mock.patch.object(pb.ParamikoSessionBackend, "ensure_connected", side_effect=exc):
                    self.assertFalse(b.test_connection(3))


class TestKnownHostsFiles(unittest.TestCase):
    def test_defaults_when_unset(self):
        files = pb.ParamikoSessionBackend._known_hosts_files(
            {}, host_alias="server-a", hostname="server-a", host_key_alias="server-a",
            port=22, username="alice",
        )
        self.assertTrue(all(isinstance(f, Path) for f in files))

    def test_none_disables(self):
        files = pb.ParamikoSessionBackend._known_hosts_files(
            {"userknownhostsfile": "none", "globalknownhostsfile": "none"},
            host_alias="server-a", hostname="server-a", host_key_alias="server-a",
            port=22, username="alice",
        )
        self.assertEqual(files, ())

    def test_mixed_none_is_invalid(self):
        with self.assertRaises(ValueError):
            pb.ParamikoSessionBackend._known_hosts_files(
                {"userknownhostsfile": "/tmp/kh none"},
                host_alias="server-a", hostname="server-a", host_key_alias="server-a",
                port=22, username="alice",
            )

    def test_custom_paths_are_expanded_and_ordered(self):
        tmp = Path(tempfile.mkdtemp())
        files = pb.ParamikoSessionBackend._known_hosts_files(
            {"userknownhostsfile": str(tmp / "u_kh"), "globalknownhostsfile": str(tmp / "g_kh")},
            host_alias="server-a", hostname="server-a", host_key_alias="server-a",
            port=22, username="alice",
        )
        self.assertEqual(files[0], tmp / "u_kh")
        self.assertEqual(files[1], tmp / "g_kh")


class TestChannelAggregation(unittest.TestCase):
    class FakeChannel:
        def __init__(self):
            self._out = [b"hello "]
            self._err = [b"warn"]

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
        def closed(self):
            return True

        def recv_exit_status(self):
            return 3

    def test_collect_channel_reads_both_streams(self):
        b = backend()
        deadline = pb._Deadline.start(5)
        rc, out, err = b._collect_channel(self.FakeChannel(), deadline, "cmd")
        self.assertEqual((rc, out, err), (3, "hello ", "warn"))

    def test_decode_tolerates_invalid_utf8(self):
        self.assertEqual(pb.ParamikoSessionBackend._decode([b"\xff\xfe"]), "\ufffd\ufffd")


if __name__ == "__main__":
    unittest.main()
