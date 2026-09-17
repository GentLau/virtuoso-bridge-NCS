"""Resource release contracts (spec: 每轮资源盘点零残留)."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from transport.middle import BusinessServer
from common.registry import UserEntry, load_registry
from common.paths import registry_path, override_work_dir_for_tests
from transport.tunnel import RemoteClient
from transport.remote_roles import resolve


class FakeRunner:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.stopped_forward = False
        self.closed = False
        FakeRunner.instances.append(self)

    @property
    def is_tunnel_alive(self):
        return False

    def start_port_forward(self, *a, **k):
        return None

    def stop_port_forward(self):
        self.stopped_forward = True

    def close(self):
        self.closed = True

    def run_command(self, cmd, timeout=None):
        from pyapi.models import CommandResult
        return CommandResult(0, "", "")


class TestRunnerCloseStopsTunnel(unittest.TestCase):
    def setUp(self):
        FakeRunner.instances = []

    def test_close_stops_port_forward(self):
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            entry = UserEntry(token="tok-x", mode="remote")
            entry.ssh.default.host = "server-a"
            entry.ssh.default.user = "u"
            entry.roles.command.host = "server-a"
            entry.roles.command.user = "u"
            entry.roles.daemon.host = "server-a"
            entry.roles.daemon.user = "u"
            entry.roles.daemon.daemon_port = 65081
            entry.roles.daemon.local_port = 65082
            client = RemoteClient(entry, resolve(entry, "alice"), "alice")
            runner = client.command_runner
            client.close()
        self.assertTrue(runner.stopped_forward, "client.close() must stop the tunnel")
        self.assertTrue(runner.closed)


class TestBusinessServerClose(unittest.TestCase):
    def test_close_releases_clients_once(self):
        wd = Path(tempfile.mkdtemp())
        override_work_dir_for_tests(wd)
        registry = load_registry(registry_path())
        entry = UserEntry(token="tok-c", mode="remote")
        entry.ssh.default.host = "server-a"
        entry.ssh.default.user = "u"
        entry.roles.command.host = "server-a"
        entry.roles.command.user = "u"
        entry.roles.daemon.host = "server-a"
        entry.roles.daemon.user = "u"
        registry.register("alice", entry)
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            server = BusinessServer(wd)          # loads the registry written above
            client = server._remote("tok-c")
            runner = client.command_runner
            server.close()
            self.assertEqual(server._clients, {})
            server.close()                        # idempotent
            self.assertTrue(runner.stopped_forward)
            self.assertTrue(runner.closed)


if __name__ == "__main__":
    unittest.main()
