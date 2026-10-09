# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-10-09 18:35
# 依赖: 无
# =======================================================================
"""P-138 回归（离线）：`gui.auto_dismiss` 必须能识别 ADE Message 系列模态。

背景（2026-10-09 两轮实测）：`list_windows` 曾把 `ADE Assembler Message 3016/2406`
分类为 `kind=window`（`_DIALOG_WORDS` 不含 `Message`），而 `auto_dismiss` 只挑
`kind=="dialog"` → 对这类真实模态永远 `dismissed=[]`，只能依赖 `send_key` 白名单。

判据（修复无关）：ADE Message 系列标题必须分类为 `kind == "dialog"`；
普通窗口仍为 `window`；既有 dialog 关键词不受影响。
2026-10-09 已修：`_DIALOG_WORDS` 收窄增补 `ade assembler message \\d+`。
"""
from __future__ import annotations

import sys
import unittest

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from pyapi.packages.gui import parse_xwininfo_tree


def _line(window_id: str, title: str) -> str:
    return (f'     0x{window_id} "{title}": ("virtuoso" "virtuoso")  '
            "696x82+1+38  +324+316")


class TestAutoDismissSeesAdeMessageDialogs(unittest.TestCase):
    def test_ade_message_titles_classified_as_dialog(self):
        for title in ("ADE Assembler Message 3016", "ADE Assembler Message 2406",
                      "ADE Assembler Message 1610"):
            windows = parse_xwininfo_tree(_line("1234", title))
            self.assertEqual(len(windows), 1, windows)
            self.assertEqual(
                windows[0]["kind"],
                "dialog",
                f"{title!r} 应分类为 dialog（当前 {windows[0]['kind']!r}），"
                "否则 gui.auto_dismiss 永远看不见它",
            )

    def test_control_plain_window_stays_window(self):
        windows = parse_xwininfo_tree(_line("2222", "Library Manager"))
        self.assertEqual(windows[0]["kind"], "window")

    def test_control_existing_error_title_still_dialog(self):
        windows = parse_xwininfo_tree(_line("3333", "Some Error Report"))
        self.assertEqual(windows[0]["kind"], "dialog")
