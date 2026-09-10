"""Paramiko backend unit tests: config parsing and pure helpers (no network)."""

import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from transport import paramiko_backend as pb
from transport.paramiko_backend import (
    ParamikoSessionBackend,
    _Deadline,
    _Socks5Proxy,
    _default_known_hosts_files,
    _expand_ssh_path,
)


class TestDeadline(unittest.TestCase):
    def test_remaining(self):
        d = _Deadline.start(5)
        self.assertGreater(d.remaining("cmd"), 0)
        d = _Deadline.start(0)
        import subprocess
        with self.assertRaises(subprocess.TimeoutExpired):
            d.remaining("cmd")


class TestKnownHostsFiles(unittest.TestCase):
    def test_posix_defaults(self):
        paths = _default_known_hosts_files(home=Path("/home/alice"), platform_name="posix")
        self.assertIn(Path("/home/alice/.ssh/known_hosts"), paths)
        self.assertIn(Path("/etc/ssh/ssh_known_hosts"), paths)

    def test_windows_defaults(self):
        paths = _default_known_hosts_files(
            home=Path("C:/Users/alice"), platform_name="nt", program_data="C:/ProgramData"
        )
        self.assertIn(Path("C:/ProgramData/ssh/ssh_known_hosts"), paths)


class TestExpandSshPath(unittest.TestCase):
    def test_common_tokens(self):
        value = "%d/.ssh/%h/%r_%p_%u"
        result = _expand_ssh_path(
            value,
            host_alias="alias",
            hostname="real.example.com",
            host_key_alias="real.example.com",
            port=2222,
            remote_user="bob",
            proxy_jump="",
        )
        self.assertIn("real.example.com", str(result))
        self.assertIn("2222", str(result))

    def test_percent_escape_and_unknown_token(self):
        kw = dict(remote_user="u", proxy_jump="")
        self.assertEqual(str(_expand_ssh_path("%%", host_alias="a", hostname="a", host_key_alias="a", port=22, **kw)), "%")
        # unknown tokens are left untouched (only the known set is substituted)
        self.assertEqual(str(_expand_ssh_path("%Z", host_alias="a", hostname="a", host_key_alias="a", port=22, **kw)), "%Z")


class TestSocks5ProxyParsing(unittest.TestCase):
    def test_valid(self):
        proxy = ParamikoSessionBackend._parse_socks5_proxy("socks5://127.0.0.1:1080")
        self.assertEqual(proxy, _Socks5Proxy(host="127.0.0.1", port=1080))

    def test_none_and_blank(self):
        self.assertIsNone(ParamikoSessionBackend._parse_socks5_proxy(None))
        self.assertIsNone(ParamikoSessionBackend._parse_socks5_proxy("  "))

    def test_invalid_scheme(self):
        with self.assertRaises(ValueError):
            ParamikoSessionBackend._parse_socks5_proxy("http://127.0.0.1:1080")

    def test_missing_port(self):
        with self.assertRaises(ValueError):
            ParamikoSessionBackend._parse_socks5_proxy("socks5://127.0.0.1")

    def test_bad_url(self):
        with self.assertRaises(ValueError):
            ParamikoSessionBackend._parse_socks5_proxy(":::bad")


class TestSshConfigLookup(unittest.TestCase):
    def setUp(self):
        self.cfg = Path(tempfile.mkdtemp()) / "config"
        self.cfg.write_text(
            "Host myserver\n"
            "  HostName real.example.com\n"
            "  User bob\n"
            "  Port 2222\n"
            "  IdentityFile ~/.ssh/id_ed25519\n"
            "  ProxyJump jumphost\n",
            encoding="utf-8",
        )
        self.backend = ParamikoSessionBackend(
            host="myserver",
            user=None,
            jump_host=None,
            jump_user=None,
            ssh_key_path=None,
            ssh_config_path=self.cfg,
            ssh_cmd="ssh",
            connect_timeout=5,
            max_sessions=3,
        )

    def tearDown(self):
        self.backend.close()

    def test_lookup_hostname_user_port(self):
        lookup = self.backend._lookup("myserver", None, None)
        self.assertEqual(lookup.get("hostname"), "real.example.com")
        self.assertEqual(lookup.get("user"), "bob")
        self.assertIn(lookup.get("port"), (2222, "2222"))
        self.assertEqual(tuple(lookup.get("identityfile")), ("~/.ssh/id_ed25519",))

    def test_endpoint_uses_config(self):
        endpoint = self.backend._endpoint("myserver", None)
        self.assertEqual(endpoint.hostname, "real.example.com")
        self.assertEqual(endpoint.username, "bob")
        self.assertEqual(endpoint.port, 2222)

    def test_parse_proxy_jump(self):
        pj = self.backend._parse_proxy_jump("alice@jump.example.com:2200", "myserver")
        self.assertEqual(pj.host, "jump.example.com")
        self.assertEqual(pj.username, "alice")
        self.assertEqual(pj.port, 2200)

    def test_expand_connection_tokens(self):
        endpoint = self.backend._endpoint("myserver", None)
        out = self.backend._expand_connection_tokens("ssh -W %h:%p %r", endpoint=endpoint)
        self.assertIn("real.example.com:2222", out)


class TestConstructionValidation(unittest.TestCase):
    def test_missing_config_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            ParamikoSessionBackend(
                host="h", user="u", jump_host=None, jump_user=None,
                ssh_key_path=None, ssh_config_path=Path(tempfile.mkdtemp()) / "nope",
                ssh_cmd="ssh", connect_timeout=5, max_sessions=3,
            )

    def test_zero_max_sessions_raises(self):
        with self.assertRaises(ValueError):
            ParamikoSessionBackend(
                host="h", user=None, jump_host=None, jump_user=None,
                ssh_key_path=None, ssh_config_path=None,
                ssh_cmd="ssh", connect_timeout=5, max_sessions=0,
            )


class TestPureClassHelpers(unittest.TestCase):
    def test_transport_is_ready(self):
        self.assertFalse(pb.ParamikoSessionBackend._transport_is_ready(None))
        transport = type("T", (), {})()
        transport.is_active = lambda: True
        transport.is_authenticated = lambda: True
        client = type("C", (), {})()
        client.get_transport = lambda: transport
        self.assertTrue(pb.ParamikoSessionBackend._transport_is_ready(client))
        transport.is_active = lambda: False
        self.assertFalse(pb.ParamikoSessionBackend._transport_is_ready(client))
        client2 = type("C2", (), {})()
        client2.get_transport = lambda: None
        self.assertFalse(pb.ParamikoSessionBackend._transport_is_ready(client2))

    def test_decode(self):
        self.assertEqual(pb.ParamikoSessionBackend._decode([b"a", b"b"]), "ab")

    def test_error_result(self):
        rc, out, err = pb.ParamikoSessionBackend._error_result(RuntimeError("boom"))
        self.assertEqual(rc, 255)
        self.assertIn("boom", err)
        import errno
        rc2, _, _ = pb.ParamikoSessionBackend._error_result(OSError(errno.ENOENT, "missing"))
        self.assertEqual(rc2, 1)


class TestBackendExecutionPaths(unittest.TestCase):
    def setUp(self):
        self.cfg = Path(tempfile.mkdtemp()) / "config"
        self.cfg.write_text("Host server\n  HostName real.example.com\n", encoding="utf-8")
        self.backend = ParamikoSessionBackend(
            host="server", user="u", jump_host=None, jump_user=None,
            ssh_key_path=None, ssh_config_path=self.cfg, ssh_cmd="ssh",
            connect_timeout=5, max_sessions=3,
        )

    def tearDown(self):
        self.backend.close()

    def test_collect_channel(self):
        channel = type("C", (), {})()
        chunks = [b"hello ", b"world"]
        channel.recv_ready = lambda: bool(chunks)
        channel.recv = lambda n: chunks.pop(0) if chunks else b""
        channel.recv_stderr_ready = lambda: False
        channel.recv_stderr = lambda n: b""
        channel.exit_status_ready = lambda: not chunks
        channel.eof_received = True
        channel.closed = True
        channel.recv_exit_status = lambda: 0
        rc, out, err = self.backend._collect_channel(channel, pb._Deadline.start(5), "cmd")
        self.assertEqual((rc, out, err), (0, "hello world", ""))

    def test_run_command_error_returns_255(self):
        import contextlib
        @contextlib.contextmanager
        def broken(*a, **k):
            raise RuntimeError("boom")
            yield
        with __import__("unittest").mock.patch.object(self.backend, "_session_lease", broken):
            rc, out, err = self.backend.run_command("echo hi", timeout=5)
        self.assertEqual(rc, 255)
        self.assertIn("boom", err)

    def test_upload_text_error_returns_255(self):
        import contextlib
        @contextlib.contextmanager
        def broken(*a, **k):
            raise RuntimeError("upload boom")
            yield
        with __import__("unittest").mock.patch.object(self.backend, "_session_lease", broken):
            from transport.transfer import build_text_upload_plan
            plan = build_text_upload_plan("/tmp/x.txt", b"abc")
            rc, out, err = self.backend.upload_text(plan, b"abc", timeout=5)
        self.assertEqual(rc, 255)
        self.assertIn("upload boom", err)

    def test_download_file_success(self):
        from unittest import mock
        from transport.transfer import build_file_download_plan
        target = Path(tempfile.mkdtemp()) / "out.bin"
        plan = build_file_download_plan("/remote/out.bin", target)

        @contextmanager
        def fake_sftp(*a, **k):
            class Sftp:
                def get(self, remote, local, callback=None):
                    Path(local).write_bytes(b"downloaded")
                def close(self):
                    pass
            yield Sftp()

        with mock.patch.object(self.backend, "_sftp", fake_sftp):
            rc, out, err = self.backend.download_file(plan, timeout=5)
        self.assertEqual(rc, 0)
        self.assertEqual(target.read_bytes(), b"downloaded")

    def test_download_file_error_discards_stage(self):
        from unittest import mock
        from transport.transfer import build_file_download_plan
        target = Path(tempfile.mkdtemp()) / "out.bin"
        plan = build_file_download_plan("/remote/out.bin", target)

        @contextmanager
        def broken(*a, **k):
            raise RuntimeError("download boom")
            yield

        with mock.patch.object(self.backend, "_sftp", broken):
            rc, out, err = self.backend.download_file(plan, timeout=5)
        self.assertEqual(rc, 255)
        self.assertIn("download boom", err)
        self.assertFalse(plan.stage_path.exists())

    def test_test_connection(self):
        with __import__("unittest").mock.patch.object(self.backend, "ensure_connected", return_value=None):
            self.assertTrue(self.backend.test_connection(timeout=2))
        with __import__("unittest").mock.patch.object(self.backend, "ensure_connected", side_effect=OSError("no")):
            self.assertFalse(self.backend.test_connection(timeout=2))

    def test_tar_result_combines_errors(self):
        rc, out, err = pb.ParamikoSessionBackend._tar_result(
            0, 0, [b"ok"], [b"remote err"], [b"local err"]
        )
        self.assertEqual((rc, out), (0, "ok"))
        self.assertIn("Remote tar error: remote err", err)
        self.assertIn("Local tar error: local err", err)

    def test_stop_tar_transfer(self):
        channel = type("C", (), {"close": lambda s: None})()
        proc = type("P", (), {})()
        proc.poll = lambda: None
        proc.kill = lambda: None
        proc.wait = lambda timeout=None: None
        stream = type("S", (), {"close": lambda s: None})()
        worker = type("W", (), {})()
        worker.is_alive = lambda: False
        worker.join = lambda timeout=None: None
        pb.ParamikoSessionBackend._stop_tar_transfer(channel, proc, [stream], [worker])

    def test_wait_tar_transfer_success(self):
        import queue as q
        channel = type("C", (), {})()
        channel.exit_status_ready = lambda: True
        channel.recv_exit_status = lambda: 0
        proc = type("P", (), {})()
        proc.poll = lambda: 0
        proc.wait = lambda timeout=None: 0
        worker = type("W", (), {})()
        worker.is_alive = lambda: False
        failures = q.Queue()
        rc_r, rc_l = pb.ParamikoSessionBackend._wait_tar_transfer(
            channel, proc, [worker], failures, pb._Deadline.start(5), "cmd"
        )
        self.assertEqual((rc_r, rc_l), (0, 0))


if __name__ == "__main__":
    unittest.main()
