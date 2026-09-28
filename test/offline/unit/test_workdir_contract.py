"""`common.paths` one-work-root-per-process contract.

Path-sensitive cases run in fresh subprocesses; a pytest process is not
allowed to switch the process-wide root in place.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = str(ROOT / "src")


def _run(code: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-c", code], env=env, text=True, capture_output=True
    )


class TestWorkRootContract(unittest.TestCase):
    def test_same_path_twice_is_idempotent(self):
        code = """
from common.paths import init_work_dir, work_root
import tempfile
p = tempfile.mkdtemp(prefix="vb-wd-")
assert init_work_dir(p) == init_work_dir(p)
assert work_root() == init_work_dir(p)
"""
        result = _run(code)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_different_path_raises_without_rebinding(self):
        code = """
from common.paths import init_work_dir, work_root
import tempfile
p = tempfile.mkdtemp(prefix="vb-wd-")
q = tempfile.mkdtemp(prefix="vb-wd-")
init_work_dir(p)
try:
    init_work_dir(q)
except RuntimeError as exc:
    assert "already initialized" in str(exc)
else:
    raise AssertionError("different work root must fail")
assert work_root() == __import__("pathlib").Path(p).resolve()
"""
        result = _run(code)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_uninitialized_derivations_raise(self):
        code = """
from common import paths
for probe in (paths.work_root, paths.temp_dir, paths.log_dir,
              paths.artifact_dir, paths.registry_path, paths.config_path):
    try:
        probe()
    except RuntimeError as exc:
        assert "work dir not initialized" in str(exc)
    else:
        raise AssertionError("uninitialized path access must fail")
"""
        result = _run(code)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_derived_paths_live_under_root_and_are_created(self):
        code = """
from common import paths
from pathlib import Path
import tempfile
root = Path(tempfile.mkdtemp(prefix="vb-wd-"))
paths.init_work_dir(root)
assert paths.registry_path() == root / "registry.json"
assert paths.config_path() == root / "config.json"
for name, fn in (("temp", paths.temp_dir), ("log", paths.log_dir),
                 ("artifact", paths.artifact_dir)):
    created = fn()
    assert created == root / name
    assert created.is_dir()
assert paths.command_log_file() == root / "log" / "commands.log"
"""
        result = _run(code)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(os.name == "nt", "Windows default root uses APPDATA")
    def test_default_work_dir_uses_appdata_on_windows(self):
        from common import paths
        from unittest import mock

        with tempfile.TemporaryDirectory(prefix="vb-appdata-") as td, \
                mock.patch.dict(os.environ, {"APPDATA": td}):
            self.assertEqual(paths.default_work_dir(), Path(td) / "virtuoso_bridge")

    @unittest.skipUnless(os.name != "nt", "POSIX default root uses XDG_CONFIG_HOME")
    def test_default_work_dir_honours_xdg_on_posix(self):
        from common import paths
        from unittest import mock

        with tempfile.TemporaryDirectory(prefix="vb-xdg-") as td, \
                mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": td}):
            self.assertEqual(paths.default_work_dir(), Path(td) / "virtuoso_bridge")


if __name__ == "__main__":
    unittest.main()
