"""`view_type` 参数合同（P-080）：read 路径也必须校验非空字符串。

背景：`verilog.py` / `veriloga.py` 的 `read()` 只校验 token/目标/focus，
**从不碰 `view_type`** —— 传 `""` 或 `123` 也会被静默接受，然后在传输层
按硬编码主文件名（`verilog.v` / `veriloga.va`）继续跑；而 `write()` /
`check_and_save()` 走 `_require_text(view_type)` 会拒绝。两条路径口径不一致。

本文件用"stub middle 是否被触达"区分两种结果：
* 非法 view_type 必须在触达传输层**之前**抛 ValueError；
* 合法 view_type 必须放行到传输层（stub 抛 `_ReachedTransport` 作为哨兵）。

`read` 的非法值两条用 strict xfail 钉住缺陷（P-080）；修复后 XPASS 会转红，
提醒把 xfail 删掉。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from pyapi.packages import verilog as VLOG  # noqa: E402
from pyapi.packages import veriloga as VLOGA  # noqa: E402


class _ReachedTransport(AssertionError):
    """哨兵：校验已放行、代码触达了传输层。"""


class _StubMiddle:
    def __init__(self) -> None:
        self.called = False

    def execute_skill(self, *args, **kwargs):  # noqa: ANN002, ANN003
        self.called = True
        raise _ReachedTransport("transport reached")

    def query(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise _ReachedTransport("transport reached")

    def download_file(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise _ReachedTransport("transport reached")

    def run_command(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise _ReachedTransport("transport reached")


class TestVerilogViewType(unittest.TestCase):
    def setUp(self) -> None:
        self.middle = _StubMiddle()
        self.pkg = VLOG.Package(self.middle)

    @pytest.mark.xfail(strict=True, reason="P-080: verilog.read 不校验 view_type")
    def test_read_rejects_blank_view_type(self):
        with self.assertRaises(ValueError):
            self.pkg.read(VLOG.ReadRequest(
                token="t", library="L", cell="C", view_type=""))

    @pytest.mark.xfail(strict=True, reason="P-080: verilog.read 不校验 view_type")
    def test_read_rejects_non_string_view_type(self):
        with self.assertRaises(ValueError):
            self.pkg.read(VLOG.ReadRequest(
                token="t", library="L", cell="C", view_type=123))

    def test_read_accepts_valid_view_type(self):
        """合法值必须放行到传输层（哨兵证明没有误杀）。read 会把传输异常
        包成 Result.error，所以断言"触达过 stub + 错误文本含哨兵"。"""
        result = self.pkg.read(VLOG.ReadRequest(
            token="t", library="L", cell="C", view_type="text.v"))
        self.assertTrue(self.middle.called, "valid view_type must reach transport")
        self.assertIn("_ReachedTransport", result.error or "")

    def test_write_rejects_blank_view_type(self):
        with self.assertRaises(ValueError):
            self.pkg.write(VLOG.WriteRequest(
                token="t", library="L", cell="C", view_type="", commands=[]))


class TestVerilogAViewType(unittest.TestCase):
    def setUp(self) -> None:
        self.middle = _StubMiddle()
        self.pkg = VLOGA.Package(self.middle)

    @pytest.mark.xfail(strict=True, reason="P-080: veriloga.read 不校验 view_type")
    def test_read_rejects_blank_view_type(self):
        with self.assertRaises(ValueError):
            self.pkg.read(VLOGA.ReadRequest(
                token="t", library="L", cell="C", view_type=""))

    @pytest.mark.xfail(strict=True, reason="P-080: veriloga.read 不校验 view_type")
    def test_read_rejects_non_string_view_type(self):
        with self.assertRaises(ValueError):
            self.pkg.read(VLOGA.ReadRequest(
                token="t", library="L", cell="C", view_type=123))

    def test_read_accepts_valid_view_type(self):
        result = self.pkg.read(VLOGA.ReadRequest(
            token="t", library="L", cell="C", view_type="text.veriloga"))
        self.assertTrue(self.middle.called, "valid view_type must reach transport")
        self.assertIn("_ReachedTransport", result.error or "")

    def test_write_rejects_blank_view_type(self):
        with self.assertRaises(ValueError):
            self.pkg.write(VLOGA.WriteRequest(
                token="t", library="L", cell="C", view_type="", commands=[]))

    def test_check_and_save_rejects_blank_view_type(self):
        with self.assertRaises(ValueError):
            self.pkg.check_and_save(VLOGA.CheckSaveRequest(
                token="t", library="L", cell="C", view_type=""))


if __name__ == "__main__":
    unittest.main()
