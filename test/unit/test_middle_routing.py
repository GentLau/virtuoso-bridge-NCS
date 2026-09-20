"""BusinessServer routing tests with RemoteClient/SkillClient mocked."""

import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pyapi.models import CommandResult, ExecutionStatus, VirtuosoResult
from transport.middle import BusinessServer
from common.registry import UserEntry, load_registry
from common.paths import registry_path, override_work_dir_for_tests
from transport import middle as middle_mod


def make_remote_entry(token="tok-1"):
    entry = UserEntry(token=token, mode="remote")
    entry.ssh.default.host = "daemon-a"
    entry.ssh.default.user = "alice"
    entry.roles.daemon.host = "daemon-a"
    entry.roles.daemon.daemon_port = 65081
    entry.roles.daemon.local_port = 65082
    entry.roles.command.host = "daemon-a"
    entry.roles.command.user = "alice"
    entry.roles.daemon.expected_user = "alice"
    entry.roles.daemon.root = "/home/alice/.virtuoso-bridge"
    return entry


class FakeRemoteClient:
    instances = {}

    def __init__(self, entry, targets, user="alice"):
        self.entry = entry
        self.targets = targets
        self.user = user
        self.closed = False
        FakeRemoteClient.instances[entry.token] = self

    def close(self):
        self.closed = True

    def ensure_tunnel(self, deadline=None):
        self.ensure_tunnel_called = True
        self.ensure_tunnel_deadline = deadline

    def run_command(self, cmd, timeout=None, parallel=False):
        return CommandResult(0, f"remote:{cmd}:{parallel}", "")

    def upload_file(self, local_path, remote_path, timeout=None, recursive=False):
        return CommandResult(0, str(local_path), "")

    def download_file(self, remote_path, local_path, timeout=None, recursive=False):
        return CommandResult(0, str(local_path), "")


class FakeSkillClient:
    instances = {}

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        FakeSkillClient.instances[kwargs["token"]] = self

    def execute_skill(
        self,
        skill_code,
        timeout=None,
        *,
        log_level=None,
        log_max_bytes=None,
    ):
        self.last_call = {
            "log_level": log_level,
            "log_max_bytes": log_max_bytes,
        }
        return VirtuosoResult(status=ExecutionStatus.SUCCESS, output="2")


class TestBusinessServerRouting(unittest.TestCase):
    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))
        self.reg = load_registry(registry_path())
        FakeRemoteClient.instances.clear()
        FakeSkillClient.instances.clear()

    def _server(self):
        return BusinessServer(self.wd)

    def test_execute_skill_remote_routes_and_tunnels(self):
        entry = make_remote_entry()
        self.reg.register("alice", entry)
        server = self._server()
        with mock.patch("transport.middle.RemoteClient", FakeRemoteClient), \
             mock.patch("transport.middle.SkillClient", FakeSkillClient):
            r = server.execute_skill("1+1", token="tok-1")
        self.assertTrue(r.ok)
        self.assertEqual(r.output, "2")
        self.assertTrue(FakeRemoteClient.instances["tok-1"].ensure_tunnel_called)
        self.assertEqual(FakeSkillClient.instances["tok-1"].kwargs["log_level"], "all")

    def test_execute_skill_log_params_override_registry(self):
        entry = make_remote_entry()
        entry.cdslog.log_level = "error"
        entry.cdslog.log_max_bytes = 1024
        self.reg.register("alice", entry)
        server = self._server()
        with mock.patch("transport.middle.RemoteClient", FakeRemoteClient), \
             mock.patch("transport.middle.SkillClient", FakeSkillClient):
            result = server.execute_skill(
                "1+1",
                token="tok-1",
                log_level="warn",
            )
        self.assertTrue(result.ok)
        client = FakeSkillClient.instances["tok-1"]
        self.assertEqual(
            client.last_call,
            {"log_level": "warn", "log_max_bytes": None},
        )
        self.assertEqual(client.kwargs["log_max_bytes"], 1024)

    def test_execute_skill_log_max_bytes_override(self):
        entry = make_remote_entry()
        self.reg.register("alice", entry)
        server = self._server()
        with mock.patch("transport.middle.RemoteClient", FakeRemoteClient), \
             mock.patch("transport.middle.SkillClient", FakeSkillClient):
            result = server.execute_skill(
                "1+1",
                token="tok-1",
                log_max_bytes=2048,
            )
        self.assertTrue(result.ok)
        client = FakeSkillClient.instances["tok-1"]
        self.assertEqual(
            client.last_call,
            {"log_level": None, "log_max_bytes": 2048},
        )

    def test_execute_skill_unknown_token(self):
        server = self._server()
        r = server.execute_skill("1+1", token="nope")
        self.assertEqual(r.status, ExecutionStatus.ERROR)
        self.assertIn("invalid token", r.errors[0])

    def test_run_command_remote_passes_parallel(self):
        entry = make_remote_entry()
        self.reg.register("alice", entry)
        server = self._server()
        with mock.patch("transport.middle.RemoteClient", FakeRemoteClient):
            serial = server.run_command("echo a", token="tok-1")
            parallel = server.run_command("echo b", token="tok-1", parallel=True)
        self.assertEqual(serial.stdout, "remote:echo a:False")
        self.assertEqual(parallel.stdout, "remote:echo b:True")

    def test_upload_download_remote(self):
        entry = make_remote_entry()
        self.reg.register("alice", entry)
        server = self._server()
        with mock.patch("transport.middle.RemoteClient", FakeRemoteClient):
            up = server.upload_file(Path("a.txt"), "/remote/a.txt", token="tok-1")
            down = server.download_file("/remote/a.txt", Path("b.txt"), token="tok-1")
        self.assertEqual(up.returncode, 0)
        self.assertEqual(down.returncode, 0)

    def test_remote_clients_cached_per_token(self):
        entry = make_remote_entry()
        self.reg.register("alice", entry)
        server = self._server()
        with mock.patch("transport.middle.RemoteClient", FakeRemoteClient):
            server.run_command("echo a", token="tok-1")
            server.run_command("echo b", token="tok-1")
        self.assertEqual(len(FakeRemoteClient.instances), 1)

    def test_thread_pool_exceeded_for_remote(self):
        entry = make_remote_entry()
        entry.runtime.thread_pool_size = 1
        self.reg.register("alice", entry)
        server = self._server()
        server._capacity["tok-1"] = mock.Mock()
        server._capacity["tok-1"].acquire.return_value = False
        with mock.patch("transport.middle.RemoteClient", FakeRemoteClient):
            r = server.run_command("echo x", token="tok-1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("thread pool exceeded", r.stderr)


class TestMiddleErrorAndLocalPaths(unittest.TestCase):
    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))
        self.server = BusinessServer(self.wd)

    def test_run_command_unknown_token(self):
        r = self.server.run_command("echo x", token="ghost")
        self.assertEqual(r.returncode, 1)
        self.assertIn("invalid token", r.stderr)

    def test_upload_unknown_token(self):
        r = self.server.upload_file(Path("a.txt"), "/x/a.txt", token="ghost")
        self.assertEqual(r.returncode, 1)
        self.assertIn("invalid token", r.stderr)

    def test_download_unknown_token(self):
        r = self.server.download_file("/x/a.txt", Path("b.txt"), token="ghost")
        self.assertEqual(r.returncode, 1)
        self.assertIn("invalid token", r.stderr)

    def test_local_command_timeout(self):
        r = self.server._local_command('"{}" -c "import time; time.sleep(5)"'.format(sys.executable), 0.1)
        self.assertEqual(r.returncode, 124)
        self.assertIn("timed out", r.stderr)

    def test_local_upload_missing_source(self):
        r = self.server._local_upload(Path("missing.txt"), str(Path(self.wd) / "dst.txt"), recursive=False)
        self.assertEqual(r.returncode, 1)

    def test_local_download_missing_source(self):
        r = self.server._local_download(str(Path(self.wd) / "missing"), Path(self.wd) / "out.txt", recursive=False)
        self.assertEqual(r.returncode, 1)

    def test_local_upload_directory_requires_recursive(self):
        src = Path(self.wd) / "tree"
        src.mkdir()
        r = self.server._local_upload(src, str(Path(self.wd) / "dst"), recursive=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("recursive=True", r.stderr)

    def test_local_upload_recursive(self):
        src = Path(self.wd) / "tree"
        (src / "sub").mkdir(parents=True)
        (src / "sub" / "f.txt").write_text("x", encoding="utf-8")
        dst = Path(self.wd) / "copy"
        r = self.server._local_upload(src, str(dst), recursive=True)
        self.assertEqual(r.returncode, 0)
        self.assertEqual((dst / "sub" / "f.txt").read_text(encoding="utf-8"), "x")

    def test_local_download_recursive(self):
        src = Path(self.wd) / "tree"
        (src / "sub").mkdir(parents=True)
        (src / "sub" / "f.txt").write_text("x", encoding="utf-8")
        dst = Path(self.wd) / "copy"
        r = self.server._local_download(str(src), dst, recursive=True)
        self.assertEqual(r.returncode, 0)
        self.assertEqual((dst / "sub" / "f.txt").read_text(encoding="utf-8"), "x")

    def test_local_recursive_mismatches_are_path_kind(self):
        """§4.6: 对象类型与 recursive 不符 → kind=path（本地模式同样适用）。"""
        src_file = Path(self.wd) / "f.txt"
        src_file.write_text("x", encoding="utf-8")
        up = self.server._local_upload(
            src_file, str(Path(self.wd) / "up-out"), recursive=True
        )
        self.assertEqual(up.kind, "path")
        down = self.server._local_download(
            str(src_file), Path(self.wd) / "down-out", recursive=True
        )
        self.assertEqual(down.kind, "path")

    def test_local_upload_of_special_file_is_path_kind(self):
        """非普通文件（这里用目录以外的最小可构造物）不得进入传输。"""
        directory = Path(self.wd) / "a-directory"
        directory.mkdir()
        result = self.server._local_upload(
            directory, str(Path(self.wd) / "out"), recursive=False
        )
        self.assertEqual(result.kind, "path")


class TestReloadDefersInFlightClose(unittest.TestCase):
    """v27: /api/process/reload 不打断在途请求。"""

    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))
        self.reg = load_registry(registry_path())

    def test_reload_defers_cache_close_for_in_flight_token(self):
        """v27: reload 不打断在途请求 —— 缓存等 in-flight 归零再关。"""
        self.reg.register("alice", make_remote_entry("tok-reload"))
        with mock.patch.object(middle_mod, "RemoteClient", FakeRemoteClient):
            server = BusinessServer()
            entry = server.registry.by_token("tok-reload")
            sem = server._acquire("tok-reload", entry)
            self.assertIsNotNone(sem)
            client = server._remote("tok-reload")
            self.assertIs(server._clients["tok-reload"], client)

            server.reload_registry()
            self.assertIn("tok-reload", server._clients, "must not interrupt in-flight")
            self.assertFalse(client.closed)

            server._release(sem, "tok-reload")
            self.assertNotIn("tok-reload", server._clients)
            self.assertTrue(client.closed)
            server.close()

    def test_reload_closes_idle_token_cache_immediately(self):
        self.reg.register("alice", make_remote_entry("tok-idle"))
        with mock.patch.object(middle_mod, "RemoteClient", FakeRemoteClient):
            server = BusinessServer()
            client = server._remote("tok-idle")
            server.reload_registry()
            self.assertNotIn("tok-idle", server._clients)
            self.assertTrue(client.closed)
            server.close()


class TestLocalShellStartupBound(unittest.TestCase):
    """端到端 deadline：本地常驻 shell 起不来时必须报错，不能永久挂起。"""

    def test_local_shell_startup_is_bounded(self):
        read_fd, write_fd = os.pipe()
        read_end = os.fdopen(read_fd, "rb")
        write_end = os.fdopen(write_fd, "wb")

        class _NullStdin:
            def write(self, data):
                return len(data)

            def flush(self):
                return None

            def close(self):
                return None

        class _SilentProc:
            """启动后既无输出也无 EOF 的 shell（模拟卡死的本地 shell）。"""

            def __init__(self, *args, **kwargs):
                self.stdin = _NullStdin()
                self.stdout = read_end
                self.returncode = None

            def poll(self):
                return None

            def terminate(self):
                return None

            def kill(self):
                return None

            def wait(self, timeout=None):
                return 0

        outcome: dict = {}

        def run():
            try:
                with mock.patch.object(
                    middle_mod.subprocess, "Popen", side_effect=_SilentProc
                ), mock.patch.object(
                    middle_mod._LocalCommandSession,
                    "_BANNER_TIMEOUT",
                    0.2,
                    create=True,
                ):
                    try:
                        middle_mod._LocalCommandSession()
                    except RuntimeError:
                        outcome["raised"] = True
                    else:
                        outcome["returned"] = True
            except BaseException as exc:  # noqa: BLE001
                outcome["exc"] = exc

        worker = threading.Thread(target=run, daemon=True)
        started = time.monotonic()
        worker.start()
        worker.join(timeout=3.0)
        bounded = not worker.is_alive()
        elapsed = time.monotonic() - started
        write_end.close()
        read_end.close()
        worker.join(timeout=2.0)

        self.assertTrue(
            bounded,
            "local command shell startup is unbounded (call hangs forever)",
        )
        self.assertLess(elapsed, 3.0)
        self.assertTrue(outcome.get("raised"), outcome)

    def test_local_session_removes_temp_dir_on_close(self):
        """本地会话关闭后不得在工作目录留下 temp/local_err_* 目录。"""
        err_dir = Path(tempfile.mkdtemp())
        session = middle_mod._LocalCommandSession(err_dir=err_dir)
        session_dir = session._err_dir
        self.assertTrue(session_dir.exists())
        session.close()
        self.assertFalse(
            session_dir.exists(), f"leftover local session dir: {session_dir}"
        )


if __name__ == "__main__":
    unittest.main()
