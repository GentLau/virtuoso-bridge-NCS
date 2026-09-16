"""Upper-layer business package tests (no transport/SSH dependencies)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pyapi.models import CommandResult, ExecutionStatus, VirtuosoResult
from pyapi.packages.file_skill_command_file import FileSkillCommandFilePackage
from pyapi.packages.parallel_probe import ParallelProbePackage


class FakeMiddle:
    def __init__(self):
        self.calls = []
        self.upload_result = CommandResult(0, "up", "")
        self.skill_result = VirtuosoResult(status=ExecutionStatus.SUCCESS, output="2")
        self.command_result = CommandResult(0, "cmd", "")
        self.download_result = CommandResult(0, "down", "")
        self.raise_on = set()

    def _maybe(self, name):
        if name in self.raise_on:
            raise RuntimeError(f"{name} boom")

    def upload_file(self, local_path, remote_path, timeout=None, *, token, recursive=False):
        self._maybe("upload")
        self.calls.append(("upload", str(local_path), remote_path, token, recursive))
        return self.upload_result

    def execute_skill(self, skill_code, timeout=None, *, token):
        self._maybe("skill")
        self.calls.append(("skill", skill_code, token))
        return self.skill_result

    def run_command(self, cmd, timeout=None, *, token, parallel=False):
        self._maybe("command")
        self.calls.append(("command", cmd, token, parallel))
        return self.command_result

    def download_file(self, remote_path, local_path, timeout=None, *, token, recursive=False):
        self._maybe("download")
        self.calls.append(("download", remote_path, str(local_path), token, recursive))
        return self.download_result


class TestFileSkillCommandFilePackage(unittest.TestCase):
    def test_success_order(self):
        middle = FakeMiddle()
        pkg = FileSkillCommandFilePackage(middle)
        result = pkg.run(
            token="tok", local_input="a.in", remote_input="r/a.in",
            skill_code="1+1", command="run", remote_output="r/out", local_output="out",
        )
        self.assertTrue(result.ok)
        self.assertEqual([s.name for s in result.steps], ["upload", "skill", "command", "download"])
        self.assertEqual([c[0] for c in middle.calls], ["upload", "skill", "command", "download"])

    def test_stops_on_each_failure(self):
        for name, attr in (
            ("upload", "upload_result"),
            ("command", "command_result"),
            ("download", "download_result"),
        ):
            middle = FakeMiddle()
            setattr(middle, attr, CommandResult(1, "", f"{name} boom"))
            result = FileSkillCommandFilePackage(middle).run(
                token="tok", local_input="a", remote_input="b", skill_code="1",
                command="c", remote_output="d", local_output="e",
            )
            self.assertFalse(result.ok)
            self.assertIn(name, result.error)
        middle = FakeMiddle()
        middle.skill_result = VirtuosoResult(status=ExecutionStatus.ERROR, errors=["skill boom"])
        result = FileSkillCommandFilePackage(middle).run(
            token="tok", local_input="a", remote_input="b", skill_code="1",
            command="c", remote_output="d", local_output="e",
        )
        self.assertFalse(result.ok)
        self.assertIn("skill boom", result.error)


class TestParallelProbePackage(unittest.TestCase):
    def test_mixed_success(self):
        middle = FakeMiddle()
        pkg = ParallelProbePackage(middle)
        result = pkg.run(token="tok", commands=["a", "b"], uploads=[("local", "remote")], max_workers=2)
        self.assertTrue(result.ok)
        self.assertEqual(len(result.results), 3)
        self.assertEqual({c[0] for c in middle.calls}, {"command", "upload"})

    def test_failure_reported(self):
        middle = FakeMiddle()
        middle.command_result = CommandResult(1, "", "bad")
        result = ParallelProbePackage(middle).run(token="tok", commands=["a"], max_workers=1)
        self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main()
