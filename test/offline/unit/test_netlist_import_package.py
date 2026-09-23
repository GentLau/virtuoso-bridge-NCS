"""典型业务包（netlist_import）的契约测试：只依赖 fake middle，无 SSH/Virtuoso。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pyapi.models import CommandResult, ExecutionStatus, VirtuosoResult
from pyapi.packages.netlist_import import OPERATION_NAME, Package, Request, Result


class FakeMiddle:
    """记录调用并返回可配置结果；接口签名与 pyapi.models.Middle 一致。"""

    def __init__(self):
        self.calls: list[tuple] = []
        self.upload_result = CommandResult(0, "up", "")
        self.skill_results: dict[str, VirtuosoResult] = {}

    def upload_file(self, local_path, remote_path, timeout=None, *, token, recursive=False):
        self.calls.append(("upload", str(local_path), remote_path, token))
        return self.upload_result

    def execute_skill(self, skill_code, timeout=None, *, token):
        self.calls.append(("skill", skill_code, token))
        for marker, result in self.skill_results.items():
            if marker in skill_code:
                return result
        return VirtuosoResult(status=ExecutionStatus.SUCCESS, output="ok")

    def run_command(self, cmd, timeout=None, *, token, parallel=False):
        return CommandResult(0, "", "")

    def download_file(self, remote_path, local_path, timeout=None, *, token, recursive=False):
        return CommandResult(0, "", "")

    def run_gui_command(self, cmd, timeout=None, *, token):
        return CommandResult(0, "", "")

    def run_spectre_command(self, cmd, timeout=None, *, token):
        return CommandResult(0, "", "")


def make_request(**overrides) -> Request:
    values = dict(
        token="tok-1", local_netlist="local/netlist.scs",
        library="mylib", cell="mycell", job="job-1",
    )
    values.update(overrides)
    return Request(**values)


class TestNetlistImport(unittest.TestCase):
    def test_reference_stub_fails_explicitly_without_side_effects(self):
        middle = FakeMiddle()
        result = Package(middle).run(make_request())
        self.assertFalse(result.ok)
        self.assertIn("reference stub", result.error)
        self.assertEqual(result.steps, [])
        self.assertEqual(middle.calls, [])

    def test_validation_failures(self):
        middle = FakeMiddle()
        for kwargs, message in (
            ({"token": ""}, "token"),
            ({"library": ""}, "library"),
            ({"cell": None}, "cell"),
            ({"job": ""}, "job"),
            ({"timeout": -1}, "timeout"),
        ):
            with self.assertRaises(ValueError, msg=message) as ctx:
                Package(middle).run(make_request(**kwargs))
            self.assertIn(message, str(ctx.exception))

    def test_self_description_exports(self):
        self.assertEqual(OPERATION_NAME, "virtuoso.netlist.import")
        for name in ("Request", "Result", "Package"):
            self.assertTrue(hasattr(__import__("pyapi.packages.netlist_import", fromlist=[name]), name))


if __name__ == "__main__":
    unittest.main()
