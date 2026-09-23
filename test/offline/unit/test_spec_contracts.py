"""Unit contracts for the frozen spec additions (file-root, connect budget)."""

import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from common.registry import UserEntry, canonical_host, endpoint_key
from transport.remote_roles import resolve


class TestFileRootFallback(unittest.TestCase):
    def test_file_root_is_the_single_bridge_workdir(self):
        entry = UserEntry(token="tok-123", mode="remote")
        entry.ssh.default.host = "server"
        entry.ssh.default.user = "alice"
        entry.roles.daemon.root = "~/.virtuoso-bridge/alice"
        entry.roles.daemon.host = "server"
        entry.roles.daemon.daemon_port = 65081
        targets = resolve(entry, user="alice")
        self.assertEqual(targets.daemon.root, "~/.virtuoso-bridge/alice")


class TestEndpointKeyVectors(unittest.TestCase):
    """配置一览 §6.5 测试向量：规范化的 key 必须逐条复现。"""

    def test_vectors_from_spec(self):
        vectors = [
            # (host, user, jump_host, jump_user, proxy, expected_key)
            ("server-a", "ssh-user", None, None, None,
             "v1:8c6325e8a41f89a4c29d81eb66db201c4414d33f87702607d23d43a1baf94b0b"),
            (" Server-A. ", "ssh-user", None, None, None,
             "v1:8c6325e8a41f89a4c29d81eb66db201c4414d33f87702607d23d43a1baf94b0b"),
            ("server-a", "SSH-User", None, None, None,
             "v1:40701d25d46c873daea45c841226ee0d6d6939209630d5f57459e55c98c2733b"),
            ("[::1]", "u", None, None, None,
             "v1:0bd185aaa4fa1ce6bd5cbeea0a86f061567a632f3ad6bf6f5a8f36b79556526b"),
            ("server-a", "u", "bastion", "jump-user", None,
             "v1:178df3e331df40f8d01408ff226fd22e6be04d8033db187f06bc64a5c3512391"),
            ("server-a", "u", None, None, "socks5://Proxy:1080",
             "v1:f410f0afc8f618e5230416eb191fa6fcdd5c8313828c2e4c4348eed8cfb33630"),
        ]
        for host, user, jump_host, jump_user, proxy, expected in vectors:
            with self.subTest(host=host, user=user):
                self.assertEqual(
                    endpoint_key(host, user, jump_host, jump_user, proxy), expected
                )

    def test_canonical_host_rules(self):
        self.assertEqual(canonical_host(" Server-A. "), "server-a")
        self.assertEqual(canonical_host("[::1]"), "::1")
        self.assertEqual(canonical_host("::1"), "::1")
        self.assertEqual(canonical_host(None), "")

    def test_alias_is_not_resolved(self):
        """不做名称解析：不同字符串 = 不同 endpoint，bridge 不查 DNS。"""
        self.assertNotEqual(
            endpoint_key("prod-alias", "u"), endpoint_key("prod.example.com", "u")
        )


if __name__ == "__main__":
    unittest.main()
