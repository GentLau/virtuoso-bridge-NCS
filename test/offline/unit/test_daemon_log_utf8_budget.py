"""spec：日志限长的字节截断不得产出半个 UTF-8 字符（§5 与 §8-7）。

锚点：``src/bridge/resources/ramic_bridge_daemon_{3,27}.py`` 的 ``filter_delta()``。

为什么单列一个文件：既有离线用例（``test_new_core`` / ``test_daemon_parity`` /
``test_offline/core/daemon_log_protocol_tb.py``）只覆盖 **ASCII** 截断，
spec 明文要求的那一条——"字节截断允许落在多字节字符中间，此时丢弃该半个字符，
最终内容始终是合法 UTF-8"——此前**没有任何断言**（第五轮矩阵里是缺口项）。

断言口径（不放宽）：
1. 返回的 body 必须是该 error 增量的**字节前缀**；
2. 截断点必须落在字符边界上（下一个字节不是 UTF-8 续接字节 0b10xxxxxx）；
3. 不得出现替换字符 U+FFFD；
4. body 自身字节数 ≤ ``log_max_bytes``（说明行不计入，按 spec §5）；
5. py3 / py27 两份实现逐点 parity。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from bridge.resources import ramic_bridge_daemon_3 as d3
from bridge.resources import ramic_bridge_daemon_27 as d27

MODULES = [("daemon_3", d3), ("daemon_27", d27)]

DEGRADE_NOTE = "[log auto-degraded: error-only due to log_max_bytes]"
TRUNCATE_NOTE = "[log truncated: increment not fully returned due to log_max_bytes]"

#: 含 3 字节（中文）与 4 字节（emoji）字符的 error 增量
ERR_TEXT = "\\e 中文字符测试\u4e2d\U0001f9ea\u4e2d"


def _body(text):
    """剥掉两句说明（说明行以换行开头，属格式而非正文），拿到受预算约束的正文。"""
    return text.split(DEGRADE_NOTE)[0].split(TRUNCATE_NOTE)[0].rstrip("\n")


def _assert_clean_cut(case, body, err_text):
    err_bytes = err_text.encode("utf-8")
    body_bytes = body.encode("utf-8")
    case.assertTrue(
        err_bytes.startswith(body_bytes),
        f"body 不是 error 增量的字节前缀: {body_bytes!r} 不是 {err_bytes!r} 的前缀",
    )
    cut = len(body_bytes)
    if cut < len(err_bytes):
        nxt = err_bytes[cut]
        case.assertNotEqual(
            nxt & 0xC0,
            0x80,
            f"截断点落在多字节字符中间（下一字节 0x{nxt:02x} 是续接字节）",
        )
    case.assertNotIn("\ufffd", body, "不得用替换字符兜底")
    body.encode("utf-8")  # 合法 UTF-8：不能抛


class TestUtf8ByteBudget(unittest.TestCase):
    def test_cut_mid_character_drops_the_half_character(self):
        """截断点刻意落在 3 字节字符中间：只丢弃半个字符，不产出半个、不补 U+FFFD。"""
        raw = ERR_TEXT + "\n"
        # "\e " 占 3 字节，再切 1 字节 → 正好落进第一个汉字（3 字节）内部
        max_bytes = 4
        for name, mod in MODULES:
            with self.subTest(daemon=name):
                text, truncated = mod.filter_delta(raw, "all", max_bytes)
                self.assertTrue(truncated, name)
                body = _body(text)
                _assert_clean_cut(self, body, ERR_TEXT)
                self.assertEqual(body, "\\e ", f"{name}: 半个汉字必须被丢弃")
                self.assertLessEqual(len(body.encode("utf-8")), max_bytes, name)
                self.assertIn(DEGRADE_NOTE, text, name)
                self.assertIn(TRUNCATE_NOTE, text, name)

    def test_byte_budget_sweep_never_emits_half_character(self):
        """对 0..len 的每个预算逐点扫：截断点必须在字符边界上。"""
        raw = ERR_TEXT + "\n"
        total = len(ERR_TEXT.encode("utf-8"))
        for name, mod in MODULES:
            for max_bytes in range(0, total + 4):
                with self.subTest(daemon=name, max_bytes=max_bytes):
                    text, truncated = mod.filter_delta(raw, "all", max_bytes)
                    body = _body(text)
                    _assert_clean_cut(self, body, ERR_TEXT)
                    self.assertLessEqual(
                        len(body.encode("utf-8")), max_bytes, f"{name}@{max_bytes}"
                    )
                    self.assertEqual(
                        truncated,
                        (DEGRADE_NOTE in text) or (TRUNCATE_NOTE in text),
                        f"{name}@{max_bytes}: truncated 标志与说明行必须一致",
                    )

    def test_four_byte_character_boundary(self):
        """4 字节字符（emoji）同样不能切一半。"""
        raw = "\\e \U0001f9ea\U0001f9ea\U0001f9ea\n"
        for name, mod in MODULES:
            for max_bytes in range(3, 3 + 4 * 3):
                with self.subTest(daemon=name, max_bytes=max_bytes):
                    text, _ = mod.filter_delta(raw, "all", max_bytes)
                    _assert_clean_cut(self, _body(text), "\\e \U0001f9ea\U0001f9ea\U0001f9ea")

    def test_exact_boundary_keeps_the_whole_character(self):
        """恰好切在字符边界上时，整字符必须保留（不是"多丢一个"）。"""
        raw = ERR_TEXT + "\n"
        boundary = len("\\e 中文".encode("utf-8"))
        for name, mod in MODULES:
            with self.subTest(daemon=name):
                text, _ = mod.filter_delta(raw, "all", boundary)
                self.assertEqual(_body(text), "\\e 中文", name)

    def test_py3_and_py27_are_byte_identical(self):
        """两份 daemon 实现逐点 parity（含截断点落在多字节字符内部的情形）。"""
        raw = ERR_TEXT + "\n\\o info line\n" + ("\\e " + "\u4e2d" * 30 + "\n")
        for max_bytes in range(0, 120):
            with self.subTest(max_bytes=max_bytes):
                self.assertEqual(
                    d3.filter_delta(raw, "all", max_bytes),
                    d27.filter_delta(raw, "all", max_bytes),
                )
                self.assertEqual(
                    d3.filter_delta(raw, "error", max_bytes),
                    d27.filter_delta(raw, "error", max_bytes),
                )


if __name__ == "__main__":
    unittest.main()
