"""Runner creation must be single-flight per endpoint / role.

Regression for the process storm seen in the 2026-09-15 live runs: the first
burst of concurrent calls on one token created one SSHRunner (=> one transport,
one persistent shell, one ``ssh -N -L``) *per thread* because ``_runner()`` used
an unsynchronised check-then-act.
"""

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from common.registry import UserEntry
from transport.remote_roles import resolve
from common.paths import override_work_dir_for_tests
from transport.tunnel import RemoteClient

THREADS = 16


class CountingRunner:
    instances = 0
    lock = threading.Lock()

    def __init__(self, **kwargs):
        with CountingRunner.lock:
            CountingRunner.instances += 1
        self.kwargs = kwargs
        time.sleep(0.05)  # widen the check-then-act window

    @property
    def is_tunnel_alive(self) -> bool:
        return False

    def start_port_forward(self, *a, **k):
        return None

    def stop_port_forward(self):
        return None

    def close(self):
        return None

    def run_command(self, cmd, timeout=None):
        from pyapi.models import CommandResult
        return CommandResult(0, "", "")


def make_entry(backend="paramiko"):
    entry = UserEntry(token="tok-race", mode="remote")
    entry.ssh.backend = backend
    for role in ("daemon", "command", "file"):
        getattr(entry.roles, role).host = "server-a"
        getattr(entry.roles, role).user = "alice"
    entry.roles.daemon.daemon_port = 65081
    entry.roles.daemon.local_port = 65082
    entry.roles.gui.host = "server-a"
    entry.roles.gui.user = "alice"
    entry.roles.spectre.host = "server-a"
    entry.roles.spectre.user = "alice"
    return entry


class TestRunnerSingleFlight(unittest.TestCase):
    def setUp(self):
        override_work_dir_for_tests(Path(tempfile.mkdtemp()))
        CountingRunner.instances = 0

    def _hammer(self, fn):
        errors = []

        def worker():
            try:
                fn()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        self.assertEqual(errors, [])

    def test_endpoint_runner_is_created_once(self):
        entry = make_entry()
        with mock.patch("transport.tunnel.SSHRunner", CountingRunner):
            client = RemoteClient(entry, resolve(entry, "alice"), "alice")
            role = client.targets.command
            self._hammer(lambda: client._runner(role))
        self.assertEqual(CountingRunner.instances, 1, "runner created per thread")

    def test_one_shot_runner_is_created_once(self):
        entry = make_entry(backend="openssh")
        with mock.patch("transport.tunnel.SSHRunner", CountingRunner):
            client = RemoteClient(entry, resolve(entry, "alice"), "alice")
            role = client.targets.gui
            self._hammer(lambda: client._one_shot_runner(role))
        self.assertEqual(CountingRunner.instances, 1, "one-shot runner created per thread")


if __name__ == "__main__":
    unittest.main()
