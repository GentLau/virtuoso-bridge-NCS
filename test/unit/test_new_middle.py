import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from transport.middle import BusinessServer
from common.registry import UserEntry, load_registry
from common.remote_paths import daemon_path, identity_path, il_path, setup_il_path, user_dir
from transport.remote_roles import resolve
from common.paths import registry_path, override_work_dir_for_tests
from common.setup import generate_setup_il


class TestNewMiddle(unittest.TestCase):
    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))

    def test_remote_paths_structure(self):
        root = "/tmp/root/alice"
        p = user_dir("alice", root)
        self.assertEqual(str(p).replace("\\", "/"), root)
        self.assertIn("ramic", str(il_path("alice", root)))
        self.assertIn("setup", str(setup_il_path("alice", root)))
        self.assertIn("status", str(identity_path("alice", root)))
        self.assertIn("ramic_bridge_daemon_3.py", str(daemon_path("alice", 3, root)))

    def test_setup_il_globals(self):
        text = generate_setup_il(
            "/r/ramic_daemon.py",
            "/r/ramic_bridge.il",
            "python3",
            65081,
            "tok-1",
            "/s/id.txt",
            temp_dir="/r/root",
            log_path="/r/root/status/daemon.log",
        )
        self.assertIn('RBDPath = "/r/ramic_daemon.py"', text)
        self.assertIn('RBDToken = "tok-1"', text)
        self.assertIn('RBTempDir = "/r/root"', text)
        self.assertIn('RBDLogPath = "/r/root/status/daemon.log"', text)
        self.assertIn('printf("[RAMIC] token=%L\\n" RBDToken)', text)
        self.assertIn('load("/r/ramic_bridge.il")', text)
        self.assertNotIn("setShellEnvVar", text)

    def test_bridge_il_uses_configured_runtime_paths(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "bridge"
            / "resources"
            / "ramic_bridge.il"
        ).read_text(encoding="utf-8")
        self.assertNotIn("/tmp/RB.log", source)
        self.assertIn("RBTempDir", source)
        self.assertIn("RBDLogPath", source)

    def test_route_defaults(self):
        from common.registry import SshDefaults
        entry = UserEntry(token="tok-1", mode="remote")
        entry.ssh.default = SshDefaults(host="daemon-a", user="alice")
        entry.roles.daemon.daemon_port = 65081
        entry.roles.daemon.local_port = 65082
        t = resolve(entry)
        self.assertEqual(t.command.host, "daemon-a")
        self.assertEqual(t.command.user, "alice")
        self.assertEqual(t.file.host, "daemon-a")
        self.assertEqual(t.daemon_port, 65081)
        self.assertEqual(t.local_port, 65082)

    def test_local_business_server(self):
        reg = load_registry(registry_path())
        entry = UserEntry(token="tok-1", mode="local")
        entry.roles.daemon.daemon_port = 65432
        entry.roles.daemon.local_port = 65432
        reg.register("alice", entry)

        server = BusinessServer(self.wd)
        r = server.run_command("echo vb-ok", token="tok-1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("vb-ok", r.stdout)

        # the previous assertion accepted "0 or 1" (i.e. also plain failure);
        # upload a real temp file to a path under the work dir instead
        src = Path(self.wd) / "upload_src.txt"
        src.write_text("payload", encoding="utf-8")
        dst = Path(self.wd) / "upload_dst.txt"
        up = server.upload_file(src, str(dst), token="tok-1")
        self.assertEqual(up.returncode, 0, up.stderr)
        self.assertEqual(dst.read_text(encoding="utf-8"), "payload")


if __name__ == "__main__":
    unittest.main()
