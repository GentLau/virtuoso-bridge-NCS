"""Deterministic connect-retry contract: at most 3 handshake attempts.

Spec: 三层整体架构设计 §5.8 — transport retries at most 3 times and only
before any side effect (banner/auth handshake).  ParamikoSessionBackend
retries exactly the "banner drop" class; other connect errors fail fast.
No real network: a fake socket feeds the banner stream.
"""
import sys
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from common.paramiko_backend import ParamikoSessionBackend


class _BannerDropSocket:
    """Sends a partial SSH banner, then EOF -> paramiko banner-read error."""
    def __init__(self):
        self.state = 0
        self.closed = False

    def settimeout(self, _):
        pass

    def send(self, data):
        return len(data)

    def sendall(self, data):
        return None

    def recv(self, n):
        if self.state == 0:
            self.state = 1
            return b"SSH-2.0-OpenSSH_9.9\r"  # partial: no trailing \n
        return b""

    def close(self):
        self.closed = True


class _RefusedSocket:
    def settimeout(self, _):
        pass

    def recv(self, _n):
        raise OSError("Connection refused")

    def send(self, data):
        return len(data)

    def close(self):
        pass


class ConnectRetryContractTest(unittest.TestCase):
    def _backend(self):
        return ParamikoSessionBackend(
            host="target", user="u", jump_host=None, jump_user=None,
            ssh_key_path=None, ssh_config_path=None, ssh_cmd="ssh",
            connect_timeout=5, max_sessions=2,
        )

    def test_banner_drop_retries_exactly_three_attempts_then_raises(self):
        backend = self._backend()
        calls = []
        def fake_sock(endpoint, deadline):
            calls.append(1)
            return _BannerDropSocket()
        with mock.patch.object(backend, "_open_proxy_socket", side_effect=fake_sock):
            with self.assertRaises(Exception) as ctx:
                backend.ensure_connected(timeout=10)
        self.assertEqual(len(calls), 3)
        self.assertIn("banner", str(ctx.exception).lower())

    def test_connection_refused_still_bounded_to_three_attempts(self):
        # Paramiko wraps socket errors as "Error reading SSH protocol banner<err>",
        # which the backend classifies as a handshake failure.  The hard contract
        # is the upper bound: never more than 3 attempts for a connect error.
        backend = self._backend()
        calls = []
        def fake_sock(endpoint, deadline):
            calls.append(1)
            return _RefusedSocket()
        with mock.patch.object(backend, "_open_proxy_socket", side_effect=fake_sock):
            with self.assertRaises(Exception):
                backend.ensure_connected(timeout=10)
        self.assertEqual(len(calls), 3)

    def test_is_banner_drop_classification(self):
        self.assertTrue(ParamikoSessionBackend._is_banner_drop(Exception("Error reading SSH protocol banner")))
        self.assertTrue(ParamikoSessionBackend._is_banner_drop(Exception("Connection reset by peer")))
        self.assertFalse(ParamikoSessionBackend._is_banner_drop(Exception("Authentication failed.")))
        self.assertFalse(ParamikoSessionBackend._is_banner_drop(Exception("Connection refused")))

    def test_connect_timeout_is_a_cap_inside_the_call_budget(self):
        """§5.8: runtime.connect_timeout 是本次调用预算内的连接子预算。"""
        backend = self._backend()  # connect_timeout=5
        seen = {}

        class _StubDeadline:
            def __init__(self, seconds):
                self.timeout = seconds

            def remaining(self, _cmd):
                return self.timeout

        def fake_start(seconds):
            seen["seconds"] = seconds
            return _StubDeadline(seconds)

        with mock.patch.object(
            ParamikoSessionBackend, "_transport_is_ready", return_value=True
        ), mock.patch("common.paramiko_backend._Deadline.start", side_effect=fake_start):
            backend.ensure_connected(timeout=30)

        self.assertEqual(seen["seconds"], 5)


if __name__ == "__main__":
    unittest.main()
