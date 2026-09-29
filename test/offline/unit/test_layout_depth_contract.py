"""P-082：`layout.read(depth>0)` 必然失败 —— region 格式在内部自相矛盾。

`read()` 校验时要求 `object_filter.*.region` 是**扁平** `[x0,y0,x1,y1]`
（`_filter_region`），但 depth>0 分支又把它交给 `_bbox()`，后者要求**嵌套**
`[[x,y],[x,y]]` —— 任何输入都无法同时满足，`depth>0` 请求在构造 SKILL 文本时
必然 `ValueError: bbox must be [ [x, y], [x, y] ]`，`_q()` 根本不会被调用。

本文件用 stub middle（一旦被触达就抛哨兵）区分「死在参数格式」与「正常走到
传输层」：
* depth=1 + layers + region：**不得**出现 bbox 格式错误（P-082 修复后转绿）；
* depth=0 同一 filter：正常走到传输层（对照，证明 stub 姿势成立）；
* depth=1 无 filter：必须参数错误（现行为，保持）。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from pyapi.packages import layout as L  # noqa: E402

FILTER = {"shape": {"layers": [["y0", "drawing"]],
                    "region": [[0.0, 0.0], [10.0, 10.0]]},
          "instance": "none", "via": "none"}


class _Stub:
    def execute_skill(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("__transport_reached__")

    def run_command(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("__transport_reached__")

    def query(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("__transport_reached__")

    def download_file(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("__transport_reached__")


class TestLayoutDepth(unittest.TestCase):
    def setUp(self) -> None:
        self.pkg = L.Package(_Stub())

    def _read(self, **extra):
        return self.pkg.read(L.ReadRequest(
            token="t", library="L", cell="C", view="layout", focus=["shapes"],
            detail="index", **extra))

    def test_depth_positive_must_not_die_on_bbox_format(self):
        result = self._read(depth=1, object_filter=FILTER)
        self.assertNotIn("bbox must be", result.error or "")

    def test_depth_zero_reaches_transport(self):
        result = self._read(depth=0, object_filter=FILTER)
        self.assertIn("__transport_reached__", result.error or "")

    def test_depth_positive_without_filter_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            self._read(depth=1, object_filter=None)
        self.assertIn("depth > 0", str(ctx.exception))

    def test_negative_depth_is_rejected(self):
        with self.assertRaises(ValueError):
            self._read(depth=-1, object_filter=FILTER)

    def test_bad_region_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            self._read(depth=0, object_filter=FILTER, region_mode="bogus")


if __name__ == "__main__":
    unittest.main()
