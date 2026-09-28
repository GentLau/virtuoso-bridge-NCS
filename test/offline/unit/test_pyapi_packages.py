"""Contracts for the remaining production ``basic`` passthrough package."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pyapi.models import CommandResult, ExecutionStatus, VirtuosoResult
from pyapi.packages.basic import (
    CommandRequest,
    DownloadRequest,
    Package as BasicPackage,
    SkillRequest,
    UploadRequest,
)


class FakeMiddle:
    def __init__(self):
        self.calls = []
        self.upload_result = CommandResult(0, "up", "")
        self.skill_result = VirtuosoResult(
            status=ExecutionStatus.SUCCESS, output="2"
        )
        self.command_result = CommandResult(0, "cmd", "")
        self.download_result = CommandResult(0, "down", "")

    def upload_file(
        self, local_path, remote_path, timeout=None, *, token, recursive=False
    ):
        self.calls.append(
            ("upload", str(local_path), remote_path, token, recursive)
        )
        return self.upload_result

    def execute_skill(self, skill_code, timeout=None, *, token):
        self.calls.append(("skill", skill_code, token))
        return self.skill_result

    def run_command(self, cmd, timeout=None, *, token, parallel=False):
        self.calls.append(("command", cmd, token, parallel))
        return self.command_result

    def download_file(
        self, remote_path, local_path, timeout=None, *, token, recursive=False
    ):
        self.calls.append(
            ("download", remote_path, str(local_path), token, recursive)
        )
        return self.download_result


class TestBasicPackageContracts(unittest.TestCase):
    def test_command_failure_has_error_fallback(self):
        middle = FakeMiddle()
        middle.command_result = CommandResult(7, "", "")
        result = BasicPackage(middle).run_command(
            CommandRequest(token="tok", cmd="exit 7")
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "command failed with rc=7")

    def test_parallel_rejects_string(self):
        with self.assertRaises(ValueError):
            CommandRequest(token="tok", cmd="x", parallel="no")

    def test_recursive_rejects_string(self):
        with self.assertRaises(ValueError):
            UploadRequest(
                token="tok", local_path="a", remote_path="b", recursive="no"
            )
        with self.assertRaises(ValueError):
            DownloadRequest(
                token="tok", remote_path="a", local_path="b", recursive="no"
            )

    def test_timeout_rejects_bool(self):
        with self.assertRaises(ValueError):
            BasicPackage(FakeMiddle()).execute_skill(
                SkillRequest(token="tok", skill_code="1", timeout=True)
            )

    def test_skill_success_passthrough(self):
        middle = FakeMiddle()
        result = BasicPackage(middle).execute_skill(
            SkillRequest(token="tok", skill_code="1+1")
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.result.output, "2")


if __name__ == "__main__":
    unittest.main()
