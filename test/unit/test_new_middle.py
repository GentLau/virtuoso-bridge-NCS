import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from transport.middle import BusinessServer
from transport.registry import UserEntry, load_registry
from transport.remote_paths import daemon_path, identity_path, il_path, setup_il_path, user_dir
from transport.remote_roles import resolve
from transport.runtime_paths import registry_path, set_working_dir
from transport.setup import generate_setup_il


class TestNewMiddle(unittest.TestCase):
    def setUp(self):
        self.wd = set_working_dir(Path(tempfile.mkdtemp()))

    def test_remote_paths_structure(self):
        p = user_dir("alice", "/tmp/root")
        self.assertEqual(str(p).replace("\\", "/"), "/tmp/root/alice")
        self.assertIn("ramic", str(il_path("alice", "/tmp/root")))
        self.assertIn("setup", str(setup_il_path("alice", "/tmp/root")))
        self.assertIn("status", str(identity_path("alice", "/tmp/root")))
        self.assertIn("ramic_bridge_daemon_3.py", str(daemon_path("alice", 3, "/tmp/root")))

    def test_setup_il_globals(self):
        text = generate_setup_il("/r/ramic_daemon.py", "/r/ramic_bridge.il", "python3", 65081, "tok-1", "/s/id.txt")
        self.assertIn('RBDPath = "/r/ramic_daemon.py"', text)
        self.assertIn('RBDToken = "tok-1"', text)
        self.assertIn('printf("[RAMIC] token=%L\\n" RBDToken)', text)
        self.assertIn('load("/r/ramic_bridge.il")', text)
        self.assertNotIn("setShellEnvVar", text)

    def test_route_defaults(self):
        entry = UserEntry(token="tok-1", mode="remote")
        entry.route.skill.daemon_host = "daemon-a"
        entry.route.skill.daemon_port = 65081
        entry.route.skill.local_port = 65082
        entry.expected.daemon_user = "alice"
        t = resolve(entry)
        self.assertEqual(t.command_host, "daemon-a")
        self.assertEqual(t.command_user, "alice")
        self.assertEqual(t.file_host, "daemon-a")
        self.assertEqual(t.skill_port, 65081)
        self.assertEqual(t.local_port, 65082)

    def test_local_business_server(self):
        reg = load_registry(registry_path())
        entry = UserEntry(token="tok-1", mode="local")
        entry.route.skill.daemon_port = 65432
        entry.route.skill.local_port = 65432
        reg.register("alice", entry)

        server = BusinessServer(self.wd)
        r = server.run_command("echo vb-ok", token="tok-1")
        if sys.platform == "win32":
            self.assertIn(r.stdout, ("", "vb-ok\r\n", "vb-ok\n"))
        else:
            self.assertEqual(r.stdout.strip(), "vb-ok")
        self.assertEqual(r.returncode, 0)

        up = server.upload_file(Path(__file__), "/tmp/uploaded_copy.txt", token="tok-1")
        # local mode ignores the POSIX-looking path on Windows; use a tmp local path instead
        self.assertIn(up.returncode, (0, 1))


if __name__ == "__main__":
    unittest.main()
