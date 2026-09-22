"""上层业务包读 common 基座拿本机路径的契约测试。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from common.paths import init_work_dir, override_work_dir_for_tests
from pyapi.models import ExecutionStatus, QueryResult
from pyapi.packages.demo import OPERATIONS, Package, PathsFactsRequest


class FakeQueryMiddle:
    def __init__(self, ok: bool) -> None:
        self.ok = ok

    def query(self, *, token: str) -> QueryResult:
        if self.ok:
            return QueryResult(status=ExecutionStatus.SUCCESS)
        return QueryResult(
            status=ExecutionStatus.ERROR, errors=["invalid token"],
        )


class TestUpperLayerPaths(unittest.TestCase):
    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp(prefix="vb-upper-")))

    def test_operation_is_registered(self):
        self.assertIn("demo.paths.facts", {op[0] for op in OPERATIONS})

    def test_paths_facts_reads_common_base(self):
        package = Package(middle=None)          # 本操作不调用中层
        result = package.paths_facts(PathsFactsRequest(token="tok"))
        self.assertTrue(result.ok)
        self.assertEqual(result.work_root, str(self.wd))
        for value in (result.temp_dir, result.log_dir, result.artifact_dir):
            self.assertTrue(Path(value).is_dir(), value)
        self.assertEqual(result.steps[0]["detail"]["work_root"], str(self.wd))

    def test_missing_token_is_structural_error(self):
        package = Package(middle=None)
        with self.assertRaises(ValueError):
            package.paths_facts(PathsFactsRequest(token=""))

    def test_invalid_token_is_business_failure(self):
        package = Package(middle=FakeQueryMiddle(ok=False))
        result = package.paths_facts(PathsFactsRequest(token="bad"))
        self.assertFalse(result.ok)
        self.assertIn("invalid token", result.error or "")

    def test_valid_token_passes_with_middle(self):
        package = Package(middle=FakeQueryMiddle(ok=True))
        result = package.paths_facts(PathsFactsRequest(token="good"))
        self.assertTrue(result.ok)

    def test_entry_init_is_idempotent_for_same_path(self):
        self.assertEqual(init_work_dir(self.wd), self.wd)
        with self.assertRaises(RuntimeError):
            init_work_dir(Path(tempfile.mkdtemp(prefix="vb-other-")))


if __name__ == "__main__":
    unittest.main()
