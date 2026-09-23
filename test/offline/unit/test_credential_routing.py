"""按 role 分离凭据的运行期连接复用（spec 路由设计 §4）。

同一 endpoint + **解析后凭据一致** → 复用一条连接；凭据不同 → 各自独立建连，
且每条连接使用该 role 自己的私钥路径。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from common.registry import UserEntry
from transport.remote_roles import resolve
from transport.tunnel import RemoteClient
from _ssh_cred import make_credential


class _RecordingRunner:
    created: list["_RecordingRunner"] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.closed = False
        _RecordingRunner.created.append(self)

    def close(self):
        self.closed = True

    def stop_port_forward(self):
        return None


def _entry() -> UserEntry:
    entry = UserEntry(token="tok-cred", mode="remote")
    entry.ssh.default.host = "server-a"
    entry.ssh.default.user = "alice"
    entry.ssh.default.key_dir = _KEY_A[0]
    entry.ssh.default.key = _KEY_A[1]
    entry.roles.command.host = "server-a"
    entry.roles.command.user = "alice"
    entry.roles.file.host = "server-a"
    entry.roles.file.user = "alice"
    entry.roles.daemon.host = "server-a"
    entry.roles.daemon.user = "alice"
    entry.roles.daemon.daemon_port = 65081
    entry.roles.daemon.local_port = 65082
    return entry


_KEY_A = make_credential("id_ed25519")
_KEY_B = make_credential("id_rsa")


class TestPerRoleCredentialReuse(unittest.TestCase):
    def setUp(self):
        _RecordingRunner.created = []

    def _client(self, entry: UserEntry) -> RemoteClient:
        return RemoteClient(entry, resolve(entry, "alice"), "alice")

    def test_same_endpoint_same_credentials_share_one_runner(self):
        entry = _entry()
        with mock.patch("transport.tunnel.SSHRunner", _RecordingRunner):
            client = self._client(entry)
            command = client.command_runner
            file_runner = client.file_runner
            client.close()
        self.assertIs(command, file_runner)
        self.assertEqual(len(_RecordingRunner.created), 1)
        self.assertEqual(
            _RecordingRunner.created[0].kwargs["ssh_key_path"],
            Path(_KEY_A[0]) / _KEY_A[1],
        )

    def test_same_endpoint_different_credentials_get_distinct_runners(self):
        entry = _entry()
        entry.roles.file.key_dir = _KEY_B[0]
        entry.roles.file.key = _KEY_B[1]
        with mock.patch("transport.tunnel.SSHRunner", _RecordingRunner):
            client = self._client(entry)
            command = client.command_runner
            file_runner = client.file_runner
            client.close()
        self.assertIsNot(command, file_runner)
        self.assertEqual(len(_RecordingRunner.created), 2)
        key_paths = {
            runner.kwargs["ssh_key_path"] for runner in _RecordingRunner.created
        }
        self.assertEqual(
            key_paths,
            {
                Path(_KEY_A[0]) / _KEY_A[1],
                Path(_KEY_B[0]) / _KEY_B[1],
            },
        )

    def test_role_level_credential_overrides_global(self):
        entry = _entry()
        entry.roles.command.key_dir = _KEY_B[0]
        entry.roles.command.key = _KEY_B[1]
        with mock.patch("transport.tunnel.SSHRunner", _RecordingRunner):
            client = self._client(entry)
            client.command_runner
            client.close()
        self.assertEqual(
            _RecordingRunner.created[0].kwargs["ssh_key_path"],
            Path(_KEY_B[0]) / _KEY_B[1],
        )

    def test_one_shot_runner_uses_role_credential(self):
        """openssh 后端的一次性通道（gui/spectre/parallel）也带 role 自己的 key。"""
        entry = _entry()
        entry.ssh.backend = "openssh"
        with mock.patch("transport.tunnel.SSHRunner", _RecordingRunner):
            client = self._client(entry)
            one_shot = client._one_shot_runner(client.targets.command)
            client.close()
        self.assertEqual(
            one_shot.kwargs["ssh_key_path"], Path(_KEY_A[0]) / _KEY_A[1]
        )
        self.assertFalse(one_shot.kwargs["persistent_shell"])


if __name__ == "__main__":
    unittest.main()
