"""Paramiko 后端纯助手与配置解析错误分支。"""

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from common import paramiko_backend as pb


class TestSocks5Parsing(unittest.TestCase):
    def test_empty_is_none(self):
        self.assertIsNone(pb.ParamikoSessionBackend._parse_socks5_proxy(None))
        self.assertIsNone(pb.ParamikoSessionBackend._parse_socks5_proxy("   "))

    def test_valid(self):
        parsed = pb.ParamikoSessionBackend._parse_socks5_proxy("socks5://127.0.0.1:1080")
        self.assertEqual((parsed.host, parsed.port), ("127.0.0.1", 1080))

    def test_invalid_forms(self):
        for value in ("http://127.0.0.1:1080", "socks5://u:p@h:1080",
                      "socks5://h", "socks5://h:0", "socks5://h:70000",
                      "socks5://h:1080/path"):
            with self.assertRaises(ValueError, msg=value):
                pb.ParamikoSessionBackend._parse_socks5_proxy(value)


class TestProxyJumpParsing(unittest.TestCase):
    def test_empty_and_none(self):
        self.assertIsNone(pb.ParamikoSessionBackend._parse_proxy_jump("", "server-a"))
        self.assertIsNone(pb.ParamikoSessionBackend._parse_proxy_jump("none", "server-a"))
        self.assertIsNone(pb.ParamikoSessionBackend._parse_proxy_jump("None", "server-a"))

    def test_user_host_port_form(self):
        hop = pb.ParamikoSessionBackend._parse_proxy_jump("alice@bastion:2222", "server-a")
        self.assertEqual((hop.host, hop.username, hop.port), ("bastion", "alice", 2222))

    def test_ssh_url_form(self):
        hop = pb.ParamikoSessionBackend._parse_proxy_jump("ssh://bob@bastion:2200", "server-a")
        self.assertEqual((hop.host, hop.username, hop.port), ("bastion", "bob", 2200))

    def test_multi_hop_rejected(self):
        with self.assertRaises(ValueError):
            pb.ParamikoSessionBackend._parse_proxy_jump("a@h1,h2", "server-a")

    def test_invalid_forms(self):
        for value in ("@bastion", "ssh://bastion/path", "ssh://:22"):
            with self.assertRaises(ValueError, msg=value):
                pb.ParamikoSessionBackend._parse_proxy_jump(value, "server-a")


class TestLookupSshG(unittest.TestCase):
    def _backend(self):
        return pb.ParamikoSessionBackend(
            host="server-a", user="alice", jump_host=None, jump_user=None,
            ssh_key_path=None, ssh_config_path=None,
            connect_timeout=5, max_sessions=4,
        )

    def test_lookup_parses_and_caches(self):
        backend = self._backend()
        raw = b"hostname real-a\nuser alice\nport 22\nproxyjump none\nidentityfile ~/.ssh/id_ed25519\n"
        with mock.patch.object(pb.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0, stdout=raw, stderr=b"")
            first = backend._lookup("server-a", "alice", 22)
            second = backend._lookup("server-a", "alice", 22)
        self.assertEqual(run.call_count, 1, "ssh -G 结果必须缓存（每 endpoint 一次）")
        self.assertEqual(first, second)
        self.assertEqual(first.get("hostname"), "real-a")

    def test_lookup_failure_raises_with_detail(self):
        backend = self._backend()
        with mock.patch.object(pb.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=255, stdout=b"", stderr=b"bad config")
            with self.assertRaises(ValueError) as ctx:
                backend._lookup("server-a", "alice", 22)
        self.assertIn("bad config", str(ctx.exception))

    def test_endpoint_accepts_true_strict_host_key_checking(self):
        backend = self._backend()
        lookup = {
            "hostname": "real-a",
            "user": "alice",
            "port": 22,
            "stricthostkeychecking": "true",
            "identityfile": (),
            "proxyjump": "",
        }
        with mock.patch.object(backend, "_lookup", return_value=lookup):
            endpoint = backend._endpoint("server-a", "alice")
        self.assertEqual(endpoint.hostname, "real-a")


if __name__ == "__main__":
    unittest.main()
