"""spec §6.5：`user update` 改变 role 的连接身份/凭据组时必须先探测 host-key。

合并后的条目（endpoint + 解析后凭据）一旦与注册表里的旧组不同，就视为新
endpoint：host-key 基准按首信任重建（从 known_hosts 重新读取），并与新配置
一起原子落盘；探测失败 → 整个 update 拒绝，原条目一个字节都不变。
"""

from __future__ import annotations

import hashlib
import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import register.server as register_server
from register.server import RegistrationServer
from common.registry import UserEntry, load_registry
from common.paths import registry_path, override_work_dir_for_tests
from _ssh_cred import make_credential

_ADMIN_TOKEN = "test-admin-token"


def _admin_auth() -> dict:
    return {"Authorization": "Bearer " + _ADMIN_TOKEN}


class TestUpdateHostKeyProbe(unittest.TestCase):
    def setUp(self):
        self._saved_hash = register_server._ADMIN_TOKEN_HASH
        register_server._ADMIN_TOKEN_HASH = hashlib.sha256(
            _ADMIN_TOKEN.encode("utf-8")
        ).hexdigest()
        self.wd = override_work_dir_for_tests(
            Path(tempfile.mkdtemp(prefix="vb-"))
        )
        self.registry = load_registry(registry_path())
        key = make_credential()
        entry = UserEntry(token="tok-upd-probe", mode="remote")
        entry.ssh.default.host = "server-a"
        entry.ssh.default.user = "alice"
        entry.ssh.default.key_dir, entry.ssh.default.key = key
        for name in ("gui", "daemon", "command", "file", "spectre"):
            role = getattr(entry.roles, name)
            role.root = f"/home/alice/.vb/{name}"
            role.expected_fingerprint = "SHA256:old"
        entry.roles.daemon.daemon_port = 65081
        entry.roles.daemon.local_port = 65082
        entry.roles.daemon.python = "/usr/bin/python3"
        self.registry.register("alice", entry)
        self.server = RegistrationServer(("127.0.0.1", 0), self.registry)
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        register_server._ADMIN_TOKEN_HASH = self._saved_hash

    def _update(self, body: dict) -> tuple[int, str]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request(
            "POST", "/api/user/alice/update", json.dumps(body),
            {"Content-Type": "application/json", **_admin_auth()},
        )
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8")
        conn.close()
        return resp.status, raw

    def test_key_change_reprobes_and_persists_new_fingerprint(self):
        new_key = make_credential("id_new")
        with mock.patch(
            "register.probe.host_key_fingerprint", return_value="SHA256:fresh"
        ) as probe:
            status, raw = self._update({
                "roles": {"command": {
                    "key_dir": new_key[0], "key": new_key[1],
                }},
            })
        self.assertEqual(status, 200, raw)
        self.assertEqual(probe.call_count, 1, "role 组变化必须探测一次")
        entry = self.registry.get("alice")
        self.assertEqual(entry.roles.command.expected_fingerprint, "SHA256:fresh")
        # 其它 role 的组没变 → 旧基准保持
        self.assertEqual(entry.roles.file.expected_fingerprint, "SHA256:old")

    def test_endpoint_change_rebuilds_the_whole_group(self):
        with mock.patch(
            "register.probe.host_key_fingerprint", return_value="SHA256:fresh"
        ) as probe:
            status, raw = self._update({"ssh": {"default": {"host": "server-b"}}})
        self.assertEqual(status, 200, raw)
        self.assertEqual(probe.call_count, 1, "同一新组只探一次")
        entry = self.registry.get("alice")
        for name in ("gui", "daemon", "command", "file", "spectre"):
            self.assertEqual(
                getattr(entry.roles, name).expected_fingerprint, "SHA256:fresh",
                name,
            )

    def test_probe_failure_rejects_update_and_keeps_entry(self):
        before = self.registry.get("alice").model_dump()
        new_key = make_credential("id_new")
        with mock.patch(
            "register.probe.host_key_fingerprint", return_value=None
        ):
            status, raw = self._update({
                "roles": {"command": {
                    "key_dir": new_key[0], "key": new_key[1],
                }},
            })
        self.assertEqual(status, 400, raw)
        self.assertIn("host key fingerprint", raw)
        self.assertEqual(self.registry.get("alice").model_dump(), before)

    def test_explicit_fingerprint_wins_without_probe(self):
        new_key = make_credential("id_new")
        with mock.patch("register.probe.host_key_fingerprint") as probe:
            status, raw = self._update({
                "roles": {"command": {
                    "key_dir": new_key[0], "key": new_key[1],
                    "expected_fingerprint": "SHA256:explicit",
                }},
            })
        self.assertEqual(status, 200, raw)
        probe.assert_not_called()
        self.assertEqual(
            self.registry.get("alice").roles.command.expected_fingerprint,
            "SHA256:explicit",
        )

    def test_spectre_fingerprint_failure_is_non_blocking(self):
        new_key = make_credential("id_new")
        with mock.patch(
            "register.probe.host_key_fingerprint", return_value=None
        ):
            status, raw = self._update({
                "roles": {"spectre": {
                    "key_dir": new_key[0], "key": new_key[1],
                }},
            })
        self.assertEqual(status, 200, raw)
        # 组已变化就是新 endpoint；spectre 例外只放宽阻断，旧基准不能残留
        self.assertIsNone(
            self.registry.get("alice").roles.spectre.expected_fingerprint,
        )


if __name__ == "__main__":
    unittest.main()
